import os
import json
import threading
import glob
import time
import shutil
import subprocess

import log
from urllib.parse import quote

import requests

from bootstrap import APP_DIR
from config import cfg, slskd_url, slskd_headers, slskd_inbox
from stop import check_stop

SESSION = requests.Session()
USERS_FILE = APP_DIR / 'users.json'
SEARCH_WAIT_SEC = 5
QUEUE_WAIT_SEC = 45
LONG_QUEUE_WAIT_SEC = 180
DOWNLOAD_WAIT_SEC = 240

# Memoria de usuarios de Soulseek: cuantas veces nos han servido bien (ok) o nos han
# dejado colgados (bad). Se guarda en users.json dentro de APP_DIR y sobrevive entre
# ejecuciones. El scoring la usa para ordenar: antes los que ya han servido.
_users = None
_users_lock = threading.Lock()
BUSY_USERS = set()
_busy_lock = threading.Lock()

def _load_users():
    global _users
    if _users is None:
        try:
            _users = json.loads(USERS_FILE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _users = {}
    return _users

def record_user(username, ok):
    with _users_lock:
        u = _load_users().setdefault(username, {'ok': 0, 'bad': 0})
        u['ok' if ok else 'bad'] += 1
        USERS_FILE.write_text(json.dumps(_users, indent=1), encoding='utf-8')

def user_score_adjust(username):
    # Se suma al score (menor = mejor): +20 por fallo, -15 por exito, tope 3 de cada
    u = _load_users().get(username)
    if not u:
        return 0
    return min(u['bad'], 3) * 20 - min(u['ok'], 3) * 15

# api del slskd
def slskd_get(path, **params):
    r = SESSION.get(f"{slskd_url()}{path}", headers=slskd_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def slskd_post(path, payload):
    r = SESSION.post(f"{slskd_url()}{path}", headers=slskd_headers(), json=payload, timeout=30)
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
        log.line("slskd is running but not connected to Soulseek yet, waiting...")
    except requests.exceptions.ConnectionError:
        exe, app_dir = cfg()['exe'], cfg()['app_dir']
        if not os.path.exists(exe):
            raise SystemExit(f"slskd not found at {exe}. Run the first-run setup again.")
        log.line("Starting slskd...")
        proc = subprocess.Popen([exe, '--app-dir', app_dir], creationflags=subprocess.CREATE_NO_WINDOW)

    for _ in range(60):
        time.sleep(1)
        try:
            if slskd_logged_in():
                log.line("slskd connected to Soulseek.")
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
    log.line("Shutting down slskd...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.line("slskd stopped.")

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
    SESSION.delete(base, headers=slskd_headers(), timeout=10)                       # cancela
    SESSION.delete(base, headers=slskd_headers(), params={'remove': 'true'}, timeout=10)  # borra

def slskd_search(query, wait_sec=SEARCH_WAIT_SEC):
    # slskd limita las busquedas seguidas; con varios hilos devuelve 429 y hay que esperar
    for _ in range(5):
        try:
            search = slskd_post("/searches", {"searchText": query})
            break
        except requests.HTTPError as e:
            if e.response.status_code != 429:
                raise
            log.detail("slskd search limit, waiting 3s")
            time.sleep(3)
    else:
        raise requests.HTTPError("slskd search limit reached")
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
        SESSION.put(f"{slskd_url()}/searches/{search_id}", headers=slskd_headers(), timeout=10)
        for _ in range(10):
            time.sleep(0.5)
            state = slskd_get(f"/searches/{search_id}")
            if state["state"].startswith("Completed"):
                break

    responses = slskd_get(f"/searches/{search_id}/responses")
    SESSION.delete(f"{slskd_url()}/searches/{search_id}", headers=slskd_headers(), timeout=10)
    return responses

def slskd_download(candidate, output_path, wait_sec=DOWNLOAD_WAIT_SEC, queue_wait_sec=QUEUE_WAIT_SEC):
    username = candidate['username']
    with _busy_lock:
        BUSY_USERS.add(username)
    try:
        return _slskd_download(candidate, output_path, wait_sec, queue_wait_sec)
    finally:
        with _busy_lock:
            BUSY_USERS.discard(username)

def _slskd_download(candidate, output_path, wait_sec=DOWNLOAD_WAIT_SEC, queue_wait_sec=QUEUE_WAIT_SEC):
    username = candidate['username']
    file_info = candidate['file']
    remote_name = file_info['filename'].replace('\\', '/').split('/')[-1]

    slskd_post(f"/transfers/downloads/{quote(username, safe='')}", 
               [{"filename": file_info['filename'], "size": file_info['size']}])

    transfer = None
    last_state = None
    queued_since = None
    last_bytes = -1
    last_progress = time.time()
    try:
        while time.time() - last_progress < wait_sec:
            check_stop()
            time.sleep(2)
            transfer = find_transfer(username, file_info['filename'])
            if not transfer:
                continue
            state = transfer['state']
            if state != last_state:
                log.status(f"{state} ({username})", "downloading")
                last_state = state
            if state.startswith("Completed"):
                break
            if 'Queued' in state:
                queued_since = queued_since or time.time()
                if time.time() - queued_since > queue_wait_sec:
                    log.detail(f"Still queued at {username}, trying the next user")
                    slskd_remove_transfer(username, transfer['id'])
                    record_user(username, ok=False)
                    candidate['queued'] = True
                    return None
            else:
                queued_since = None
            done = transfer.get('bytesTransferred', 0)
            if done != last_bytes:
                last_bytes = done
                last_progress = time.time()
                if state == 'InProgress' and file_info['size']:
                    log.status(f"Downloading {done * 100 // file_info['size']}%", "downloading")
    except SystemExit:
        if transfer:
            slskd_remove_transfer(username, transfer['id'])
        raise

    if not transfer:
        log.detail("slskd has no record of the transfer")
        record_user(username, ok=False)
        return None

    if 'Succeeded' not in transfer['state']:
        log.detail(f"Transfer ended: {transfer['state']}")
        slskd_remove_transfer(username, transfer['id'])
        record_user(username, ok=False)
        return None

    for _ in range(10):   # slskd marca Succeeded un instante antes de mover el fichero al inbox
        matches = glob.glob(os.path.join(slskd_inbox(), '**', glob.escape(remote_name)), recursive=True)
        if matches:
            break
        time.sleep(1)
    if not matches:
        log.detail(f"Downloaded but not found in {slskd_inbox()}")
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
    record_user(username, ok=True)
    return final_file

def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return 'ffmpeg'

def convert_to_mp3(src, dst):
    log.status("Converting FLAC to MP3 320...", "downloading")
    cmd = [ffmpeg_exe(), '-y', '-loglevel', 'error', '-i', src,
           '-codec:a', 'libmp3lame', '-b:a', '320k', '-map_metadata', '0', dst]
    try:
        subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.detail(f"FFmpeg Error: {e}")
        return False

