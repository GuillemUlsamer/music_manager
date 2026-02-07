import os
import re
import warnings

# Suppress Google Auth EOL warnings
warnings.filterwarnings('ignore', message='.*Python version.*past its end of life.*')

import gspread
from google.oauth2.service_account import Credentials
import sys
import argparse
import yt_dlp
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

# --- CONFIGURATION ---
CREDENTIALS_FILE = 'credentials.json'
# SPREADSHEET_NAME & BASE_DOWNLOAD_DIR are now handled via arguments

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

class MyLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        if "HTTP Error 403" in msg or "Deprecated Feature" in msg:
            return 
        print(f"   > Error: {msg}")

def setup_gspread():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"Error: {CREDENTIALS_FILE} not found.")
        return None
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def sanitize_filename(name):
    # Retrieve quotes before stripping
    name = name.replace('"', "'")
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def parse_duration(duration_val):
    if not duration_val: return 0
    try:
        parts = list(map(int, str(duration_val).strip().split(':')))
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2: return parts[0] * 60 + parts[1]
    except ValueError: pass
    return 0

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
    return (len(common) / len(req_w)) >= 0.5

def download_track(artist, title, output_path, expected_duration_sec=0, tolerance=60):
    # Definition of search attempts
    # We use multiple YouTube search variations as the primary strategy.
    # The 'Deep' search pulls 50 results to find obscure/unblocked uploads.
    attempts = [
        {'source': 'YouTube (Exact)', 'prefix': 'ytsearch25:', 'query': f"\"{artist} - {title}\""},
        {'source': 'YouTube (Loose)', 'prefix': 'ytsearch25:', 'query': f"{artist} {title}"}, 
        {'source': 'YouTube (Deep)',  'prefix': 'ytsearch50:', 'query': f"{artist} {title} audio"}, 
    ]
    
    # Ensure int for formatting
    exp_sec_int = int(expected_duration_sec)
    duration_fmt = f"{exp_sec_int//60}:{exp_sec_int%60:02d}"
    
    # 1. Identify Specific Remix Request
    # Look for terms in brackets like (Stunned Guys Remix)
    specific_remix = None
    remix_match = re.search(r'\(([^)]*(?:Remix|Mix|Edit|Bootleg)[^)]*)\)', title, re.IGNORECASE)
    if remix_match:
        # Normalize: replace backticks and smart quotes
        specific_remix = remix_match.group(1).lower().replace('`', "'").replace('’', "'")

    # Generic remix keywords for fallback detection
    remix_keywords = ['remix', 'bootleg', 'edit', 'mix', 'refix', 'rmx']
    is_generic_remix_req = any(x in title.lower() for x in remix_keywords)

    # This was previously adding to a 'failed_urls' blacklist.
    failed_urls = set()

    for attempt in attempts:
        print(f"\n   > Search [{attempt['source']}]: {attempt['query']} (Target: {duration_fmt} ±{tolerance}s)")

        search_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'noplaylist': True,
            'default_search': attempt['prefix'],
            'extract_flat': 'in_playlist',
            'ignoreerrors': True, 
            'logger': MyLogger(),
            'cookiesfrombrowser': ('firefox',),
            'extractor_args': {'youtube': {'player_client': ['web']}},
        }

        try:
            with yt_dlp.YoutubeDL(search_opts) as ydl:
                info = ydl.extract_info(attempt['query'], download=False)
                
                raw_entries = []
                if 'entries' in info: raw_entries = info['entries']
                elif 'url' in info: raw_entries = [info]
                
                viable_candidates = []

                for entry in raw_entries:
                    if not entry: continue
                    val_dur = entry.get('duration', 0)
                    if not val_dur: continue
                    
                    val_title = entry.get('title', 'Unknown')
                    diff = abs(val_dur - expected_duration_sec)
                    
                    val_title_lower = val_title.lower().replace('`', "'").replace('’', "'")
                    
                    # Improve matching logic to avoid false positives on 'Full Album' mixes if searching for single tracks
                    if diff > 600 and expected_duration_sec > 0: # If result is >10m off (e.g. 1hr mix)
                         continue 

                    penalty = 0
                    current_tolerance = tolerance
                    
                    if specific_remix:
                        if specific_remix in val_title_lower:
                            current_tolerance = 240 
                            penalty = -50 
                        else:
                            penalty = 200 
                    elif is_generic_remix_req:
                        if not any(kw in val_title_lower for kw in remix_keywords):
                            if diff > 5: penalty = 100
                    else:
                        if any(kw in val_title_lower for kw in remix_keywords):
                             if diff > 5: penalty = 100

                    final_diff = diff + penalty
                    if final_diff <= current_tolerance:
                        if check_title_similarity(title, val_title):
                            viable_candidates.append({
                                'score': final_diff,
                                'entry': entry,
                                'title': val_title,
                                'duration': val_dur
                            })

                viable_candidates.sort(key=lambda x: x['score'])

                for candidate in viable_candidates:
                    dl_url = candidate['entry']['url']
                    if dl_url in failed_urls: continue

                    print(f"   > Match: '{candidate['title']}' ({int(candidate['duration'])//60}:{int(candidate['duration'])%60:02d})")

                    dl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': output_path + '.%(ext)s',
                        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '320'}],
                        'quiet': True,
                        'noplaylist': True,
                        'logger': MyLogger(),
                        'cookiesfrombrowser': ('firefox',),
                        'extractor_args': {'youtube': {'player_client': ['android', 'ios']}},
                        'cachedir': False, 
                    }
                    
                    try:
                        with yt_dlp.YoutubeDL(dl_opts) as ydl:
                            ydl.download([dl_url])
                        
                        final_file = output_path + ".mp3"
                        if os.path.exists(final_file): return final_file
                    except Exception as e:
                        print(f"   > Download Error: {e}")
                        failed_urls.add(dl_url)
                        continue 

        except Exception:
            # print(f"   > Source Error ({src_name}): {e}")
            continue

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
    try:
        sheet = client.open(spreadsheet_name)
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Spreadsheet '{spreadsheet_name}' not found.")
        return

    if not os.path.exists(base_download_dir):
        os.makedirs(base_download_dir)

    for worksheet in sheet.worksheets():
        rows = worksheet.get_all_values()
        if len(rows) < 2: continue
        
        for i in range(1, len(rows)):
            row = rows[i]
            row_num = i + 1
            
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

            if is_checked and "Downloaded" not in status:
                print(f"[{worksheet.title}] Downloading: {filename}")
                worksheet.update_cell(row_num, COL_STATUS + 1, "Downloading...")
                
                exp_seconds = parse_duration(duration_str)
                final_path = download_track(artist, title, file_path, expected_duration_sec=exp_seconds, tolerance=60)
                
                if final_path:
                    tag_file(final_path, artist, title, worksheet.title)
                    worksheet.update_cell(row_num, COL_STATUS + 1, "Downloaded")
                    print("   > Done.")
                else:
                    worksheet.update_cell(row_num, COL_STATUS + 1, "Failed, Do it manually") 
                    print("   > Failed.")

            elif not is_checked and "Downloaded" in status and "Deleting" not in status:
                print(f"[{worksheet.title}] Deleting: {filename}")
                if os.path.exists(mp3_path):
                    try:
                        os.remove(mp3_path)
                        print("   > Deleted.")
                    except Exception as e:
                        print(f"   > Del Error: {e}")
                
                worksheet.update_cell(row_num, COL_STATUS + 1, "")

def main():
    parser = argparse.ArgumentParser(description="Music Manager")
    parser.add_argument("name", help="Name of the spreadsheet (and output folder)")
    args = parser.parse_args()

    # Determine paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_music_dir = os.path.dirname(script_dir)
    download_dir = os.path.join(base_music_dir, str.upper(args.name) + " PLAYLIST")

    print("\n\nEjecutando El creador de playlists")
    print(f"Spreadsheet: {args.name}")
    print(f"Guardando en: {download_dir}")

    client = setup_gspread()
    if not client:
        return

    try:
        print("\nMirando a ver que quieres...")
        process_sheet(client, args.name, download_dir)
    except Exception as e:
        print(f"Global Error: {e}")
        
    print("Finished :)")

if __name__ == "__main__":
    main()
