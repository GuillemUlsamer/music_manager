import os
import re
import hashlib
import warnings
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore', message='.*Python version.*past its end of life.*')

import gspread
from google.oauth2.service_account import Credentials
import requests

import bootstrap
from stop import check_stop
from tagging import sanitize_filename, clean_artist, clean_title, tag_file
from downloader import download_track

CREDENTIALS_FILE = bootstrap.CREDENTIALS_FILE

# Columns (0-indexed)
COL_ARTIST = 1
COL_TITLE = 2
COL_DURATION = 3
COL_CHECKBOX = 5  # Column F
COL_STATUS = 6    # Column G
COL_NOTES = 7     # Column H
COL_YEAR = 9      # Column J
COL_COVER = 10    # Column K

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

# para limpiar el formato de duración, que tenga sentido
def parse_duration(duration_val):
    if not duration_val: return 0
    try:
        parts = list(map(int, str(duration_val).strip().split(':')))
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2: return parts[0] * 60 + parts[1]
    except ValueError: pass
    return 0

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
        album_year = header[COL_YEAR] if len(header) > 9 else ''      # J1
        cover_url = header[COL_COVER] if len(header) > 10 else ''     # K1
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

