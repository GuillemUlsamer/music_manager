import os
import re
import sys
import warnings
import glob
import time
import shutil
import json
import subprocess
import threading
import hashlib
from concurrent.futures import ThreadPoolExecutor
import gspread
from google.oauth2.service_account import Credentials
import argparse
import requests
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, ID3NoHeaderError
from mutagen.mp3 import MP3
from urllib.parse import quote
from pathlib import Path

# Suppress Google Auth EOL warnings
warnings.filterwarnings('ignore', message='.*Python version.*past its end of life.*')

# --- CONFIGURATION ---
import bootstrap

SCRIPT_DIR = bootstrap.SCRIPT_DIR
CREDENTIALS_FILE = bootstrap.CREDENTIALS_FILE

_CONFIG = None

def cfg():
    global _CONFIG
    if _CONFIG is None:
        if not bootstrap.is_configured():
            raise SystemExit("Music Manager is not set up yet: open gui.py and complete the first-run setup.")
        _CONFIG = bootstrap.load_config()
    return _CONFIG

def slskd_url():
    return cfg()['url']

def slskd_headers():
    return {"X-API-Key": cfg()['api_key']}

def slskd_inbox():
    return cfg()['inbox']

MIN_BITRATE = 256
AUDIO_EXTS = ('.mp3', '.flac')
STOP_EVENT = threading.Event()

def check_stop():
    if STOP_EVENT.is_set():
        raise SystemExit("Stopped by user.")
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

# Columns (0-indexed)
COL_ARTIST = 1
COL_TITLE = 2
COL_DURATION = 3
COL_CHECKBOX = 5  # Column F
COL_STATUS = 6    # Column G
COL_NOTES = 7     # Column H

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def setup_gspread():
    if not CREDENTIALS_FILE.exists():
        print(f"Error: {CREDENTIALS_FILE} not found.")
        return None
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

IMAGE_URL_RE = re.compile(r'=IMAGE\(\s*"([^"]+)"', re.IGNORECASE)
COVER_CACHE_DIR = bootstrap.CACHE_DIR / 'covers'

def _read_cover_url(client, spreadsheet_id):
    params = {'valueRenderOption': 'FORMULA'}
    try:
        data = client.http_client.values_get(spreadsheet_id, 'C2', params=params) # donde está la portada
    except AttributeError:   # gspread < 6
        data = client.open_by_key(spreadsheet_id).values_get('C2', params=params)
    values = data.get('values') or [['']]
    match = IMAGE_URL_RE.search(values[0][0] or '')
    return match.group(1) if match else None

def fetch_image(url, timeout=10):
    COVER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = COVER_CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + '.img')
    if cached.exists():
        return cached.read_bytes()
    r = requests.get(url, headers={'User-Agent': 'music-manager/2.0'}, timeout=timeout)
    r.raise_for_status()
    cached.write_bytes(r.content)
    return r.content

def list_playlists(with_images=True, workers=8):
    client = setup_gspread()
    if not client:
        return []
    files = sorted(client.list_spreadsheet_files(), key=lambda f: f['name'].lower())
    playlists = [{'title': f['name'], 'id': f['id'], 'image_url': None, 'image': None} for f in files]

    def fill(p):
        try:
            p['image_url'] = _read_cover_url(client, p['id'])
            if with_images and p['image_url']:
                p['image'] = fetch_image(p['image_url'])
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fill, playlists))
    return playlists

def sanitize_filename(name):
    # Retrieve quotes before stripping
    name = name.replace('"', "'")
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

GENERIC_WORDS = {'mix', 'remix', 'edit', 'version', 'original', 'radio', 'extended',
                 'feat', 'ft', 'vs', 'the', 'a', 'and', '&'}

def loose_title(title):
    t = re.sub(r'[\(\[].*?[\)\]]', ' ', title)
    t = re.sub(r'[^\w\s]', ' ', t)
    words = [w for w in t.split() if w.lower() not in GENERIC_WORDS]
    return ' '.join(words) if words else t.strip()

def strip_discogs_suffix(name):
    return re.sub(r'\s*\(\d+\)\s*$', '', name or '').strip()

SHORT_UPPER = {'dj', 'mc', 'vs', 'ft', 'ep', 'lp', 'uk', 'usa', 'nl'}

# por si viene en mayusculas todo
def smart_title(text):
    if text != text.upper() or not any(c.isalpha() for c in text):
        return text
    words = []
    for w in text.split(' '):
        words.append(w.upper() if w.lower() in SHORT_UPPER else w.capitalize())
    return ' '.join(words)

def clean_artist(name):
    name = strip_discogs_suffix(name)
    name = re.sub(r'^\s*DJ\s+', '', name, flags=re.IGNORECASE)
    return smart_title(re.sub(r'\s+', ' ', name).strip())

def clean_title(name):
    name = name.replace('`', "'").replace('’', "'")
    return smart_title(re.sub(r'\s+', ' ', name).strip())

# para limpiar el formato de duración, que tenga sentido
def parse_duration(duration_val):
    if not duration_val: return 0
    try:
        parts = list(map(int, str(duration_val).strip().split(':')))
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2: return parts[0] * 60 + parts[1]
    except ValueError: pass
    return 0

# Esto es para comparar el titulo de la canción que quiero con lo que he encontrado
def check_title_similarity(request_title, result_title):
    def normalize(s):
        s = s.replace('`', "'").replace('’', "'")
        return re.sub(r'[\s\W_]+', '', s.lower())
    
    req_s = normalize(request_title)
    res_s = normalize(result_title)
    
    if req_s and (req_s in res_s or res_s in req_s):
        return True
        
    def get_words(s):
        s = s.replace('`', "'").replace('’', "'")
        return set(re.findall(r'\w+', s.lower()))
    
    req_w = get_words(request_title)
    res_w = get_words(result_title)
    
    if not req_w: return True 
    common = req_w.intersection(res_w)
    # si al menos la mitad de las palabras coinciden, lo consideramos suficientemente similar
    return (len(common) / len(req_w)) >= 0.6

def cleanup_empty_dirs(path):
    inbox = os.path.abspath(slskd_inbox())
    path = os.path.abspath(path)
    while path.startswith(inbox) and path != inbox:
        try:
            os.rmdir(path)          # solo borra si esta vacia; si no, lanza OSError
        except OSError:
            break
        path = os.path.dirname(path)

def normalize_for_match(s):
    s = s.replace('`', "'").replace('’', "'").lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()

def is_strong_track_match(request_artist, request_title, result_title):
    req_title_norm = normalize_for_match(request_title)
    req_full_norm = normalize_for_match(f"{request_artist} {request_title}")
    result_norm = normalize_for_match(result_title)

    if not req_title_norm or not result_norm:
        return False

    title_in_result = req_title_norm in result_norm
    full_in_result = req_full_norm in result_norm if req_full_norm else False

    req_words = set(req_title_norm.split())
    res_words = set(result_norm.split())
    overlap_ratio = (len(req_words.intersection(res_words)) / len(req_words)) if req_words else 0

    return full_in_result or (title_in_result and overlap_ratio >= 0.85)

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


REMIX_KEYWORDS = ['remix', 'bootleg', 'edit', 'mix', 'refix', 'rmx']

def result_display_name(filename):
    parts = filename.replace('\\', '/').split('/')
    base = os.path.splitext(parts[-1])[0]
    base = re.sub(r'^\s*\d{1,3}\s*[-._)]\s*', '', base)
    parent = parts[-2] if len(parts) > 1 else ''
    return f"{parent} {base}".strip(), base

def score_candidates(responses, search_artist, title, expected_duration_sec=0, tolerance=60):
    specific_remix = None
    remix_match = re.search(r'\(([^)]*(?:Remix|Mix|Edit|Bootleg)[^)]*)\)', title, re.IGNORECASE)
    if remix_match:
        specific_remix = remix_match.group(1).lower().replace('`', "'").replace('’', "'")
    is_generic_remix_req = any(x in title.lower() for x in REMIX_KEYWORDS)

    viable = []
    for resp in responses:
        for f in resp.get('files', []):
            if f.get('isLocked'):
                continue
            ext = os.path.splitext(f['filename'])[1].lower()
            if ext not in AUDIO_EXTS:
                continue

            match_text, base = result_display_name(f['filename'])
            if not check_title_similarity(title, base):
                continue
            strong_match = is_strong_track_match(search_artist, title, match_text)

            # le damos puntuacion segun lo que dura
            val_dur = f.get('length') or 0
            penalty = 0
            if val_dur and expected_duration_sec > 0:
                duration_delta = val_dur - expected_duration_sec
                diff = abs(duration_delta)
                if diff > 600 and not strong_match:
                    continue
                under_tol, over_tol = tolerance, tolerance
                if strong_match:
                    under_tol = max(tolerance, 90)
                    over_tol = max(tolerance * 5, 240)
                else:
                    over_tol = max(tolerance * 2, 90)
                if duration_delta < -under_tol or duration_delta > over_tol:
                    continue
                duration_weight = 1.20 if duration_delta < 0 else 0.45
                duration_score = int(diff * duration_weight)
            else:
                diff = 0
                duration_score = 0
                if expected_duration_sec > 0:
                    penalty += 30      # no podemos verificar: peor que uno verificado

            # por si es un remix
            base_lower = base.lower().replace('`', "'").replace('’', "'")
            current_tolerance = tolerance
            if specific_remix:
                if specific_remix in base_lower:
                    current_tolerance = 240
                    penalty -= 50
                else:
                    continue
            elif is_generic_remix_req:
                if not any(kw in base_lower for kw in REMIX_KEYWORDS):
                    continue
            else:
                if any(kw in base_lower for kw in REMIX_KEYWORDS) and diff > 5:
                    penalty += 100

            if strong_match:
                penalty -= 20

            # mirar la calidad del archivo 
            bitrate = f.get('bitRate') or 0
            if ext == '.flac':
                penalty += 5
            else:
                is_vbr = f.get('isVariableBitRate', False)
                if bitrate and bitrate < MIN_BITRATE and not (is_vbr and bitrate >= 220):
                    continue
                if not bitrate:
                    penalty += 25
                elif bitrate < 320:
                    penalty += 10
            if not resp.get('hasFreeUploadSlot', True):
                penalty += 30
            penalty += min(resp.get('queueLength', 0), 50)

            final_score = duration_score + penalty
            score_limit = current_tolerance + (60 if strong_match else 0) + 50
            if final_score <= score_limit:
                viable.append({
                    'score': final_score,
                    'username': resp['username'],
                    'file': f,
                    'title': base,
                    'duration': val_dur,
                    'bitrate': bitrate,
                    'ext': ext,
                    'upload_speed': resp.get('uploadSpeed', 0),
                })

    seen = set()
    unique = []
    for c in viable:
        key = (c['username'], c['title'].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    unique.sort(key=lambda c: (c['score'], -c['bitrate'], -c['upload_speed']))
    return unique

MAX_DOWNLOAD_TRIES = 4  


def download_track(artist, title, output_path, expected_duration_sec=0, tolerance=60, album_hint=None):
    search_artist = strip_discogs_suffix(artist)
    exp_sec_int = int(expected_duration_sec)
    duration_fmt = f"{exp_sec_int//60}:{exp_sec_int%60:02d}"

    attempts = [{'source': 'Soulseek (Exact)', 'query': f"{search_artist} {title}"}]
    if album_hint:
        attempts.append({'source': 'Soulseek (Album)', 'query': album_hint})
    attempts.append({'source': 'Soulseek (Loose)', 'query': f"{search_artist} {loose_title(title)}"})
    if loose_title(title).lower() != title.lower():
        attempts.append({'source': 'Soulseek (Title)', 'query': loose_title(title)})
    attempts.append({'source': 'Soulseek (Artist)', 'query': search_artist})

    tried = set()   # (usuario, fichero) ya intentados, para no repetir entre busquedas

    for attempt in attempts:
        print(f"\n   > Search [{attempt['source']}]: {attempt['query']} (Target: {duration_fmt} ±{tolerance}s)")
        try:
            responses = slskd_search(attempt['query'])
        except requests.RequestException as e:
            print(f"   > Search Error: {e}")
            continue

        candidates = score_candidates(responses, search_artist, title, expected_duration_sec, tolerance)
        print(f"   > {len(responses)} users, {len(candidates)} viable")

        tries = 0
        for c in candidates:
            key = (c['username'], c['file']['filename'])
            if key in tried:
                continue
            tried.add(key)
            tries += 1
            if tries > MAX_DOWNLOAD_TRIES:
                break

            dur = int(c['duration'] or 0)
            print(f"   > Match: '{c['title']}' ({dur//60}:{dur%60:02d}, {c['bitrate'] or '?'}kbps) from {c['username']}")
            try:
                final_file = slskd_download(c, output_path)
            except requests.RequestException as e:
                print(f"   > Download Error: {e}")
                continue
            if final_file:
                return final_file

    print("   > No matching track found in any source.")
    return None

def tag_file(filepath, artist, title, album, year='', track_no='', cover_bytes=None):
    try:
        audio = MP3(filepath, ID3=EasyID3)
        try:
            audio.add_tags()
        except Exception:
            pass
        audio['artist'] = artist
        audio['title'] = title
        audio['album'] = album
        if year:
            audio['date'] = str(year)
        if track_no:
            audio['tracknumber'] = str(track_no)
        audio.save()

        if cover_bytes:
            tags = ID3(filepath)
            tags.delall('APIC')
            mime = 'image/png' if cover_bytes[:4] == b'\x89PNG' else 'image/jpeg'
            tags.add(APIC(encoding=3, mime=mime, type=3, desc='Cover', data=cover_bytes))
            tags.save(v2_version=3)
    except Exception as e:
        print(f"Error tagging {filepath}: {e}")

def process_sheet(client, spreadsheet_name, base_download_dir):
    # 1. Abro el spreadsheet (si existe)
    try:
        sheet = client.open(spreadsheet_name)
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Spreadsheet '{spreadsheet_name}' not found.")
        return

    # 2. Creo la carpeta de descargas si no existe
    if not os.path.exists(base_download_dir):
        os.makedirs(base_download_dir)

    # 3. Por cada pagina que tenga el spreadsheet, miro las filas y veo cuales estan checkeadas para descargar o eliminar
    for worksheet in sheet.worksheets():
        rows = worksheet.get_all_values()
        vol_match = re.search(r'\d+', worksheet.title)
        album_name = f"{spreadsheet_name} {vol_match.group(0)}" if vol_match else spreadsheet_name
        header = rows[0] if rows else []
        album_year = header[9] if len(header) > 9 else ''      # J1
        cover_url = header[10] if len(header) > 10 else ''     # K1
        cover_bytes = None
        if cover_url:
            try:
                cover_bytes = fetch_image(cover_url)
            except Exception as e:
                print(f"   > Cover not available: {e}")
        album_hint = f"{spreadsheet_name} {vol_match.group(0)}" if vol_match else None

        # 3.1 Si no hay filas o solo hay una (header), salto esta hoja
        if len(rows) < 2: continue
        
        # 3.2 Por cada fila (excepto la primera que es el header), miro a ver que hago
        for i in range(1, len(rows)):
            check_stop()
            row = rows[i]
            row_num = i + 1
            
            # Miro si la fila tiene cancion (si no hay checkbox, no hay cancion, asi que la salto)
            if len(row) <= COL_CHECKBOX: continue
            
            artist = clean_artist(row[COL_ARTIST])
            title = clean_title(row[COL_TITLE])
            track_no = row[0].strip()
            duration_str = row[COL_DURATION]
            is_checked = row[COL_CHECKBOX].lower() == 'true'
            status = row[COL_STATUS] if len(row) > COL_STATUS else ""
            
            filename = f"{artist} - {title}"
            safe_filename = sanitize_filename(filename)
            
            file_path = os.path.join(base_download_dir, safe_filename)
            mp3_path = file_path + ".mp3"

            # Si esta checkeada y no esta descargada, la descargo
            if is_checked and "Downloaded" not in status:
                print(f"[{worksheet.title}] Downloading: {filename}")
                worksheet.update_cell(row_num, COL_STATUS + 1, "Downloading...")
                
                exp_seconds = parse_duration(duration_str)
                try:
                    final_path = download_track(artist, title, file_path, expected_duration_sec=exp_seconds, tolerance=60, album_hint=album_hint)
                except SystemExit:
                    worksheet.update_cell(row_num, COL_STATUS + 1, "")
                    raise
                
                # si ha funcionado, pongo los tags
                if final_path:
                    tag_file(final_path, artist, title, album_name, album_year, track_no, cover_bytes)
                    worksheet.update_cell(row_num, COL_STATUS + 1, "Downloaded")
                    print("   > Done.")
                else:
                    worksheet.update_cell(row_num, COL_STATUS + 1, "Failed, Do it manually") 
                    print("   > Failed.")

            # Si no esta checkeada pero esta descargada, la borro
            elif not is_checked and "Downloaded" in status and "Deleting" not in status:
                print(f"[{worksheet.title}] Deleting: {filename}")
                if os.path.exists(mp3_path):
                    try:
                        os.remove(mp3_path)
                        print("   > Deleted.")
                    except Exception as e:
                        print(f"   > Del Error: {e}")
                
                worksheet.update_cell(row_num, COL_STATUS + 1, "")

def run_manager(spreadsheet_name):
    download_dir = str(Path(cfg()['music_dir']) / (spreadsheet_name.upper() + " PLAYLIST"))

    print("\n\nRunning the playlist builder")
    print(f"Spreadsheet: {spreadsheet_name}")
    print(f"Saving to: {download_dir}")

    STOP_EVENT.clear()
    slskd_proc = None
    try:
        slskd_proc = ensure_slskd()
        client = setup_gspread()
        if not client:
            return
        print("\nChecking what you want...")
        process_sheet(client, spreadsheet_name, download_dir)
        print("\nFinished :)")
    except SystemExit as e:
        print(f"\n{e}")
    except Exception as e:
        print(f"Global Error: {e}")
    finally:
        stop_slskd(slskd_proc)

def stop_manager():
    print("Stopping...")
    STOP_EVENT.set()
    

def main():
    parser = argparse.ArgumentParser(description="Music Manager v2")
    parser.add_argument("name", help="Name of the spreadsheet (and output folder)")
    args = parser.parse_args()
    run_manager(args.name)

if __name__ == "__main__":
    main()