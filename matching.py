import os
import re

MIN_BITRATE = 256

AUDIO_EXTS = ('.mp3', '.flac')

GENERIC_WORDS = {'mix', 'remix', 'edit', 'version', 'original', 'radio', 'extended',
                 'feat', 'ft', 'vs', 'the', 'a', 'and', '&'}

def loose_title(title):
    t = re.sub(r'[\(\[].*?[\)\]]', ' ', title)
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

