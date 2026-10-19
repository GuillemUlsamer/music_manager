import threading

"""
Sustituye a print(), la info detallada se queda en un log.
  song(id, text)      crea la linea de una cancion y la deja como "actual" en este hilo
  status(text, tag)   sobreescribe el estado de la cancion actual
  detail(text)        solo al fichero de log (busquedas, rechazos, errores...)
  line(text, tag)     linea suelta (arranque, fin)
"""

_handler = None                 # lo pone el GUI
_current = threading.local()    # cancion actual, distinta en cada hilo
_file = None

def set_handler(handler):
    global _handler
    _handler = handler

def open_file(path):
    global _file
    _file = open(path, 'w', encoding='utf-8')   # se vacia en cada arranque de la app

def _emit(kind, text, tag=None):
    song_id = getattr(_current, 'song', None)
    if _file:
        _file.write(f"{song_id or '-'} | {text}\n")
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
