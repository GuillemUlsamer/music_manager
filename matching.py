import os
import re
from collections import Counter

import log
from slskd_client import user_score_adjust

MIN_BITRATE = 256
LOW_BITRATE = 192
LAST_RESORT_BITRATE = 128
AUDIO_EXTS = ('.mp3', '.flac')
GENERIC_WORDS = {'mix', 'remix', 'edit', 'version', 'original', 'radio', 'extended',
                 'feat', 'ft', 'vs', 'the', 'a', 'and', '&'}

def loose_title(title):
    t = re.sub(r'[\(\[].*?[\)\]]', ' ', title)
    t = re.sub(r"[`'’]", '', t)   # They're -> Theyre, no They re
    t = re.sub(r'[^\w\s]', ' ', t)
    words = [w for w in t.split() if w.lower() not in GENERIC_WORDS]
    return ' '.join(words) if words else t.strip()

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
    req_w = get_words(request_title)
    res_w = get_words(result_title)
    core = (req_w - GENERIC_WORDS) or req_w

    common = core.intersection(res_w)
    return (len(common) / len(core)) >= 0.6

def normalize_for_match(s):
    s = re.sub(r"[`'’]", '', s).lower()
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

REMIX_KEYWORDS = ['remix', 'bootleg', 'edit', 'mix', 'refix', 'rmx']

def result_display_name(filename):
    parts = filename.replace('\\', '/').split('/')
    base = os.path.splitext(parts[-1])[0]
    base = re.sub(r'^\s*\d{1,3}\s*[-._)]\s*', '', base)
    parent = parts[-2] if len(parts) > 1 else ''
    return f"{parent} {base}".strip(), base

def core_phrase(s):
    return ' '.join(w for w in normalize_for_match(s).split() if w not in GENERIC_WORDS)

def context_terms(search_artist, album_hint=None):
    terms = [normalize_for_match(p) for p in re.split(r'\s*(?:&|/|,|\bvs\.?|\bfeat\.?|\bft\.?)\s*', search_artist, flags=re.IGNORECASE)]
    if album_hint:
        terms.append(normalize_for_match(album_hint))
        terms.append(normalize_for_match(re.sub(r'\d+', '', album_hint)))
    return [t for t in terms if len(t) >= 3]

def score_candidates(responses, search_artist, title, expected_duration_sec=0, tolerance=60, strict=False, album_hint=None, skip_remix_check=False):
    specific_remix = None
    remix_match = re.search(r'\(([^)]*(?:Remix|Mix|Edit|Bootleg)[^)]*)\)', title, re.IGNORECASE)
    if remix_match:
        specific_remix = core_phrase(remix_match.group(1)).split()   # palabras que identifican el remix, sin 'remix'/'mix'/'edit'
    is_generic_remix_req = any(x in title.lower() for x in REMIX_KEYWORDS)

    rejected = Counter()
    terms = context_terms(search_artist, album_hint)
    viable = []
    fallback = []
    last_resort = []
    for resp in responses:
        for f in resp.get('files', []):
            if f.get('isLocked'):
                rejected['locked'] += 1
                continue
            ext = os.path.splitext(f['filename'])[1].lower()
            if ext not in AUDIO_EXTS:
                rejected[f'format {ext}'] += 1
                continue

            match_text, base = result_display_name(f['filename'])
            if strict:
                if core_phrase(loose_title(title)).replace(' ', '') not in core_phrase(base).replace(' ', ''):
                    rejected['title'] += 1
                    continue
                path_norm = normalize_for_match(f['filename'])
                if terms and not any(t in path_norm for t in terms):
                    rejected['no artist/album in path'] += 1
                    continue
            title_words = core_phrase(loose_title(title)).split()
            if not strict and len(title_words) <= 1:
                path_norm = normalize_for_match(f['filename'])
                if terms and not any(t in path_norm for t in terms):
                    rejected['short title, no artist in path'] += 1
                    continue
            if len(title_words) == 1:
                # cuando el titulo es solo una palabra, ser mas estrictos con que la palabra aparezca
                file_title = re.split(r'[\s_]-[\s_]', base)[-1]
                artist_words = set(' '.join(terms).split())
                extra = [w for w in core_phrase(file_title).split() if w != title_words[0] and w not in artist_words]
                if title_words[0] not in core_phrase(file_title).split() or len(extra) > 1:
                    rejected['short title, file title differs'] += 1
                    continue
            if not (check_title_similarity(title, base) or check_title_similarity(loose_title(title), base)):
                rejected['title'] += 1
                continue
            strong_match = is_strong_track_match(search_artist, title, match_text)

            # le damos puntuacion segun lo que dura
            val_dur = f.get('length') or 0
            if strict and not val_dur:
                rejected['no duration'] += 1
                continue
            penalty = 0
            odd_duration = False
            if val_dur and expected_duration_sec > 0:
                duration_delta = val_dur - expected_duration_sec
                diff = abs(duration_delta)
                if val_dur < expected_duration_sec * 0.5:
                    rejected['too short'] += 1
                    continue
                if not strong_match:
                    if diff > 600 or duration_delta < -tolerance or duration_delta > max(tolerance * 2, 90):
                        rejected['duration'] += 1
                        continue
                odd_duration = val_dur < expected_duration_sec * 0.75
                duration_weight = 1.20 if duration_delta < 0 else 0.45
                duration_score = int(diff * duration_weight)
                if strong_match:
                    duration_score = min(duration_score, 40)
            else:
                diff = 0
                duration_score = 0
                if expected_duration_sec > 0:
                    penalty += 30      # no podemos verificar: peor que uno verificado

            # por si es un remix
            base_lower = base.lower().replace('`', "'").replace('’', "'")
            current_tolerance = tolerance
            if skip_remix_check:   # dentro de la carpeta del album solo esta esa version
                pass
            elif specific_remix:
                if ''.join(specific_remix) in normalize_for_match(base).replace(' ', ''):
                    current_tolerance = 240
                    penalty -= 50
                else:
                    rejected['other remix'] += 1
                    continue
            elif is_generic_remix_req:
                if not any(kw in base_lower for kw in REMIX_KEYWORDS) or ('original' in base_lower and 'original' not in title.lower()):
                    rejected['not a remix'] += 1
                    continue
            else:
                if any(kw in base_lower for kw in REMIX_KEYWORDS) and diff > 5:
                    penalty += 100

            if strong_match:
                penalty -= 20

            # mirar la calidad del archivo 
            bitrate = f.get('bitRate') or 0
            low_quality = False
            desperate = False
            if ext == '.flac':
                penalty += 5
            else:
                is_vbr = f.get('isVariableBitRate', False)
                if bitrate and bitrate < MIN_BITRATE and not (is_vbr and bitrate >= 220):
                    if bitrate < LAST_RESORT_BITRATE:
                        rejected[f'bitrate {bitrate}'] += 1
                        continue
                    if bitrate < LOW_BITRATE:
                        desperate = True
                    else:
                        low_quality = True
                if not bitrate:
                    penalty += 25
                elif bitrate < 320:
                    penalty += 10
            if not resp.get('hasFreeUploadSlot', True):
                penalty += 30
            penalty += min(resp.get('queueLength', 0), 50)
            penalty += user_score_adjust(resp['username'])

            final_score = duration_score + penalty
            score_limit = current_tolerance + (60 if strong_match else 0) + 50
            if final_score > score_limit:
                rejected['score'] += 1
                continue
            candidate = {
                'score': final_score,
                'username': resp['username'],
                'file': f,
                'title': base,
                'duration': val_dur,
                'bitrate': bitrate,
                'ext': ext,
                'upload_speed': resp.get('uploadSpeed', 0),
                'odd_duration': odd_duration,
            }
            (last_resort if desperate else fallback if low_quality else viable).append(candidate)

    def dedupe_sort(items):
        seen = set()
        unique = []
        for c in items:
            key = (c['username'], c['title'].lower())
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)
        unique.sort(key=lambda c: (c['score'], -c['bitrate'], -c['upload_speed']))
        return unique

    viable = dedupe_sort(viable)
    fallback = dedupe_sort(fallback)
    # acepta 128 kps si no hay nada mas, mejor eso que nada
    last_resort = dedupe_sort(last_resort)
    if not viable and not fallback and rejected:
        log.detail("Rejected: " + ", ".join(f"{v} {k}" for k, v in rejected.most_common()))
    if fallback:
        log.detail(f"{len(fallback)} low-bitrate fallback(s)")
    return viable + fallback, last_resort
