import requests

from tagging import strip_discogs_suffix
from matching import loose_title, score_candidates, GENERIC_WORDS, MIN_BITRATE
from slskd_client import slskd_search, slskd_download

MAX_DOWNLOAD_TRIES = 6  

def download_track(artist, title, output_path, expected_duration_sec=0, tolerance=60, album_hint=None):
    search_artist = strip_discogs_suffix(artist)
    exp_sec_int = int(expected_duration_sec)
    duration_fmt = f"{exp_sec_int//60}:{exp_sec_int%60:02d}"

    attempts = [{'source': 'Soulseek (Exact)', 'query': f"{search_artist} {title}"}]
    if album_hint:
        attempts.append({'source': 'Soulseek (Album)', 'query': album_hint})
    attempts.append({'source': 'Soulseek (Loose)', 'query': f"{search_artist} {loose_title(title)}"})
    core_words = [w for w in loose_title(title).split() if w.lower() not in GENERIC_WORDS]
    if loose_title(title).lower() != title.lower() and len(core_words) >= 2:
        attempts.append({'source': 'Soulseek (Title)', 'query': loose_title(title)})
    if ' ' in search_artist.strip() or len(search_artist.strip()) > 5:   # 'Perry', 'Neo', 'Alien': miles de resultados y nada util
        attempts.append({'source': 'Soulseek (Artist)', 'query': search_artist})

    tried = set()   # (usuario, fichero) ya intentados, para no repetir entre busquedas
    last_resort = []   # ficheros a 128-191 kbps, solo si todo lo demas falla
    attempts.append({'source': 'Last resort', 'query': None})

    for attempt in attempts:
        if attempt['query'] is None:
            if not last_resort:
                break
            print(f"\n   > Nothing better found: trying {len(last_resort)} low-bitrate file(s) as a last resort")
            candidates = last_resort
        else:
            print(f"\n   > Search [{attempt['source']}]: {attempt['query']} (Target: {duration_fmt} ±{tolerance}s)")
            try:
                responses = slskd_search(attempt['query'])
            except requests.ConnectionError:
                raise SystemExit("Lost connection to slskd.")
            except requests.RequestException as e:
                print(f"   > Search Error: {e}")
                continue
            strict = attempt['source'] not in ('Soulseek (Exact)', 'Soulseek (Loose)')
            candidates, desperate = score_candidates(responses, search_artist, title, expected_duration_sec, tolerance,
                                                     strict=strict, album_hint=album_hint,
                                                     skip_remix_check=(attempt['source'] == 'Soulseek (Album)'))
            last_resort += desperate
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
            except requests.ConnectionError:
                raise SystemExit("Lost connection to slskd.")
            except requests.RequestException as e:
                print(f"   > Download Error: {e}")
                continue
            if final_file:
                notes = []
                if attempt['source'] in ('Soulseek (Title)', 'Soulseek (Artist)') or not c['duration']:
                    notes.append('verify')
                if c['ext'] != '.flac' and c['bitrate'] and c['bitrate'] < MIN_BITRATE:
                    notes.append(f"{c['bitrate']} kbps")
                return final_file, ', '.join(notes)

    print("   > No matching track found in any source.")
    return None, ''
