import requests

from tagging import strip_discogs_suffix
from matching import loose_title, score_candidates
from slskd_client import slskd_search, slskd_download

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
