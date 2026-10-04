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
import gspread
from google.oauth2.service_account import Credentials
import argparse
import requests
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from urllib.parse import quote
from pathlib import Path

# Suppress Google Auth EOL warnings
warnings.filterwarnings('ignore', message='.*Python version.*past its end of life.*')

# --- CONFIGURATION ---
# Rutas ancladas a la carpeta del script, no al directorio desde el que se ejecuta.
SCRIPT_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = SCRIPT_DIR / 'credentials.json'
SLSKD_CONFIG_FILE = SCRIPT_DIR / 'slskd_config.json'

def load_slskd_config():
    if not SLSKD_CONFIG_FILE.exists():
        raise SystemExit(f"Falta {SLSKD_CONFIG_FILE}")
    with open(SLSKD_CONFIG_FILE, encoding='utf-8') as f:
        return json.load(f)

# cosas del slskd
SLSKD = load_slskd_config()
SLSKD_URL = SLSKD["url"]
SLSKD_INBOX = SLSKD["inbox"]
SLSKD_HEADERS = {"X-API-Key": SLSKD["api_key"]}

MIN_BITRATE = 256
AUDIO_EXTS = ('.mp3', '.flac')
STOP_EVENT = threading.Event()

def check_stop():
    if STOP_EVENT.is_set():
        raise SystemExit("Detenido por el usuario.")
SEARCH_WAIT_SEC = 5
DOWNLOAD_WAIT_SEC = 240

# api del slskd
def slskd_get(path, **params):
    r = requests.get(f"{SLSKD_URL}{path}", headers=SLSKD_HEADERS, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def slskd_post(path, payload):
    r = requests.post(f"{SLSKD_URL}{path}", headers=SLSKD_HEADERS, json=payload, timeout=10)
    r.raise_for_status()
    return r.json() if r.content else None

# para comprobar que esté arrancado el slskd
def slskd_logged_in():
    app = slskd_get("/application")
    return 'LoggedIn' in str(app.get('server', {}).get('state', ''))

def ensure_slskd():
    """Devuelve el proceso si lo arrancamos nosotros, None si ya corria."""
    proc = None
    try:
        if slskd_logged_in():
            return None
        print("slskd arrancado pero sin conectar a Soulseek, esperando...")
    except requests.exceptions.ConnectionError:
        exe = SLSKD.get("exe")
        if not exe or not os.path.exists(exe):
            raise SystemExit("slskd no responde y no encuentro el exe (campo 'exe' en slskd_config.json).")
        print("Arrancando slskd...")
        proc = subprocess.Popen([exe], creationflags=subprocess.CREATE_NO_WINDOW)

    for _ in range(60):
        time.sleep(1)
        try:
            if slskd_logged_in():
                print("slskd conectado a Soulseek.")
                return proc
        except requests.exceptions.ConnectionError:
            continue
    if proc:
        proc.terminate()
    raise SystemExit("slskd no ha conectado con Soulseek en 60 segundos.")

# para pararlo
def stop_slskd(proc):
    if proc is None:
        return
    print("Cerrando slskd...")
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

def list_spreadsheets():
    client = setup_gspread()
    if not client:
        return []
    return sorted(sh.title for sh in client.openall())

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
    inbox = os.path.abspath(SLSKD_INBOX)
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
    base = f"{SLSKD_URL}/transfers/downloads/{quote(username, safe='')}/{transfer_id}"
    requests.delete(base, headers=SLSKD_HEADERS, timeout=10)                       # cancela
    requests.delete(base, headers=SLSKD_HEADERS, params={'remove': 'true'}, timeout=10)  # borra

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
        requests.put(f"{SLSKD_URL}/searches/{search_id}", headers=SLSKD_HEADERS, timeout=10)
        for _ in range(10):
            time.sleep(0.5)
            state = slskd_get(f"/searches/{search_id}")
            if state["state"].startswith("Completed"):
                break

    responses = slskd_get(f"/searches/{search_id}/responses")
    requests.delete(f"{SLSKD_URL}/searches/{search_id}", headers=SLSKD_HEADERS, timeout=10)
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
        print("   > slskd no registra la transferencia")
        return None

    if 'Succeeded' not in transfer['state']:
        print(f"   > Transfer ended: {transfer['state']}")
        slskd_remove_transfer(username, transfer['id'])
        return None

    matches = glob.glob(os.path.join(SLSKD_INBOX, '**', glob.escape(remote_name)), recursive=True)
    if not matches:
        print(f"   > Descargado pero no lo encuentro en {SLSKD_INBOX}")
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

def convert_to_mp3(src, dst):
    print("   > Convirtiendo FLAC a MP3 320...")
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', src,
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

            # --- duracion (misma logica que v1, mas el caso "desconocida") ---
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

            # --- remix (igual que v1) ---
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

            # --- nuevo: calidad y disponibilidad ---
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

def tag_file(filepath, artist, title, album):
    try:
        audio = MP3(filepath, ID3=EasyID3)
        try:
            audio.add_tags()
        except Exception:
            pass
        audio['artist'] = artist
        audio['title'] = title
        audio['album'] = album
        audio.save()
        # print(f"Tagged: {filepath}")
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
            
            artist = row[COL_ARTIST]
            title = row[COL_TITLE]
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
                    tag_file(final_path, artist, title, worksheet.title)
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
    download_dir = str(SCRIPT_DIR.parent / (spreadsheet_name.upper() + " PLAYLIST"))

    print("\n\nEjecutando El creador de playlists")
    print(f"Spreadsheet: {spreadsheet_name}")
    print(f"Guardando en: {download_dir}")

    STOP_EVENT.clear()
    slskd_proc = None
    try:
        slskd_proc = ensure_slskd()
        client = setup_gspread()
        if not client:
            return
        print("\nMirando a ver que quieres...")
        process_sheet(client, spreadsheet_name, download_dir)
        print("\nFinished :)")
    except SystemExit as e:
        print(f"\n{e}")
    except Exception as e:
        print(f"Global Error: {e}")
    finally:
        stop_slskd(slskd_proc)

def stop_manager():
    print("Deteniendo...")
    STOP_EVENT.set()
    

def main():
    parser = argparse.ArgumentParser(description="Music Manager v2")
    parser.add_argument("name", help="Name of the spreadsheet (and output folder)")
    args = parser.parse_args()
    run_manager(args.name)

if __name__ == "__main__":
    main()