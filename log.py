# Sustituye a print(), la info detallada se queda en un log.
#   song(id, text)      crea la linea de una cancion y la deja como "actual" en este hilo
#   status(text, tag)   sobreescribe el estado de la cancion actual
#   detail(text)        solo al fichero de log (busquedas, rechazos, errores...)
#   line(text, tag)     linea suelta (arranque, fin)
import threading
from time import time

# _handler lo pone el GUI; _current es la cancion actual, distinta en cada hilo
_handler = None
_current = threading.local()
_file = None
_lock = threading.Lock()

def set_handler(handler):
    global _handler
    _handler = handler

def open_file(path):
    global _file
    # se vacia en cada arranque de la app
    _file = open(path, 'w', encoding='utf-8')

def _emit(kind, text, tag=None):
    song_id = getattr(_current, 'song', None)
    if _file:
        with _lock:
            _file.write(f"{time.strftime('%H:%M:%S')} {song_id or '-'} | {text}\n")
            _file.flush()
    if kind == 'detail':
        return
    if _handler:
        _handler(kind, song_id, text, tag)
    else:
        print(text)

def song(song_id, text):
    _current.song = song_id
    _emit('song', text)

def status(text, tag=None):
    _emit('status', text, tag)

def detail(text):
    _emit('detail', text)

def line(text, tag=None):
    _emit('line', text, tag)

