import re

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
from mutagen.mp3 import MP3

def sanitize_filename(name):
    # Retrieve quotes before stripping
    name = name.replace('"', "'")
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

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

