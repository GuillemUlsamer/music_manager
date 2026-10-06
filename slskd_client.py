import os
import glob
import time
import shutil
import subprocess
from urllib.parse import quote

import requests

from config import cfg, slskd_url, slskd_headers, slskd_inbox
from stop import check_stop

SEARCH_WAIT_SEC = 5

DOWNLOAD_WAIT_SEC = 240

# api del slskd
def slskd_get(path, **params):
    r = requests.get(f"{slskd_url()}{path}", headers=slskd_headers(), params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def slskd_post(path, payload):
    r = requests.post(f"{slskd_url()}{path}", headers=slskd_headers(), json=payload, timeout=10)
    r.raise_for_status()
    return r.json() if r.content else None

# para comprobar que esté arrancado el slskd
def slskd_logged_in():
    app = slskd_get("/application")
    return 'LoggedIn' in str(app.get('server', {}).get('state', ''))

def ensure_slskd():
    proc = None
    try:
        if slskd_logged_in():
            return None
        print("slskd is running but not connected to Soulseek yet, waiting...")
    except requests.exceptions.ConnectionError:
        exe, app_dir = cfg()['exe'], cfg()['app_dir']
        if not os.path.exists(exe):
            raise SystemExit(f"slskd not found at {exe}. Run the first-run setup again.")
        print("Starting slskd...")
        proc = subprocess.Popen([exe, '--app-dir', app_dir], creationflags=subprocess.CREATE_NO_WINDOW)

    for _ in range(60):
        time.sleep(1)
        try:
            if slskd_logged_in():
                print("slskd connected to Soulseek.")
                return proc
        except requests.exceptions.ConnectionError:
            continue
    if proc:
        proc.terminate()
    raise SystemExit("slskd did not connect to Soulseek within 60 seconds.")

# para pararlo
def stop_slskd(proc):
    if proc is None:
        return
    print("Shutting down slskd...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

def cleanup_empty_dirs(path):
    inbox = os.path.abspath(slskd_inbox())
    path = os.path.abspath(path)
    while path.startswith(inbox) and path != inbox:
        try:
            os.rmdir(path)          # solo borra si esta vacia; si no, lanza OSError
        except OSError:
            break
        path = os.path.dirname(path)

def find_transfer(username, filename):
    try:
        user = slskd_get(f"/transfers/downloads/{quote(username, safe='')}")
    except requests.exceptions.HTTPError:
        return None
    for d in user.get('directories', []):
        for t in d.get('files', []):
            if t['filename'] == filename:
                return t
    return None

def slskd_remove_transfer(username, transfer_id):
    base = f"{slskd_url()}/transfers/downloads/{quote(username, safe='')}/{transfer_id}"
    requests.delete(base, headers=slskd_headers(), timeout=10)                       # cancela
    requests.delete(base, headers=slskd_headers(), params={'remove': 'true'}, timeout=10)  # borra

def slskd_search(query, wait_sec=SEARCH_WAIT_SEC):
    search = slskd_post("/searches", {"searchText": query})
    search_id = search["id"]

    deadline = time.time() + wait_sec
    state = search
    while time.time() < deadline:
        check_stop()
        time.sleep(1)
        state = slskd_get(f"/searches/{search_id}")
        if state["state"].startswith("Completed"):
            break

    if not state["state"].startswith("Completed"):
        requests.put(f"{slskd_url()}/searches/{search_id}", headers=slskd_headers(), timeout=10)
        for _ in range(10):
            time.sleep(0.5)
            state = slskd_get(f"/searches/{search_id}")
            if state["state"].startswith("Completed"):
                break

    responses = slskd_get(f"/searches/{search_id}/responses")
    requests.delete(f"{slskd_url()}/searches/{search_id}", headers=slskd_headers(), timeout=10)
    return responses

def slskd_download(candidate, output_path, wait_sec=DOWNLOAD_WAIT_SEC):
    username = candidate['username']
    file_info = candidate['file']
    remote_name = file_info['filename'].replace('\\', '/').split('/')[-1]

    slskd_post(f"/transfers/downloads/{quote(username, safe='')}", 
               [{"filename": file_info['filename'], "size": file_info['size']}])

    transfer = None
    deadline = time.time() + wait_sec
    try:
        while time.time() < deadline:
            check_stop()
            time.sleep(2)
            transfer = find_transfer(username, file_info['filename'])
            if transfer and transfer['state'].startswith("Completed"):
                break
    except SystemExit:
        if transfer:
            slskd_remove_transfer(username, transfer['id'])
        raise

    if not transfer:
        print("   > slskd has no record of the transfer")
        return None

    if 'Succeeded' not in transfer['state']:
        print(f"   > Transfer ended: {transfer['state']}")
        slskd_remove_transfer(username, transfer['id'])
        return None

    matches = glob.glob(os.path.join(slskd_inbox(), '**', glob.escape(remote_name)), recursive=True)
    if not matches:
        print(f"   > Downloaded but not found in {slskd_inbox()}")
        slskd_remove_transfer(username, transfer['id'])
        return None

    final_file = output_path + ".mp3"
    os.makedirs(os.path.dirname(final_file), exist_ok=True)
    if candidate['ext'] == '.flac':
        ok = convert_to_mp3(matches[0], final_file)
        os.remove(matches[0])
        if not ok:
            final_file = None
    else:
        shutil.move(matches[0], final_file)
    cleanup_empty_dirs(os.path.dirname(matches[0]))
    slskd_remove_transfer(username, transfer['id'])
    return final_file

def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return 'ffmpeg'

def convert_to_mp3(src, dst):
    print("   > Converting FLAC to MP3 320...")
    cmd = [ffmpeg_exe(), '-y', '-loglevel', 'error', '-i', src,
           '-codec:a', 'libmp3lame', '-b:a', '320k', '-map_metadata', '0', dst]
    try:
        subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"   > FFmpeg Error: {e}")
        return False

