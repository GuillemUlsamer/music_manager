import json
import queue
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, Response

import bootstrap
import log
import manager
import sheets

app = FastAPI(title="Mulsa")
_covers = {}  # diccionario de portadas de playlists, para que no se pidan cada vez

# ---------- eventos (SSE) ----------
# Cada navegador conectado a /events tiene su propia cola. El handler de log.py mete
# cada evento en todas las colas; el endpoint /events saca de la suya y lo escribe.
# Es lo que en gui.py hacia LogView.handle con after(0, ...).
_clients = []
_clients_lock = threading.Lock()

def _log_handler(kind, song_id, text, tag):
    event = {"kind": kind, "song_id": song_id, "text": text, "tag": tag}
    with _clients_lock:
        for q in _clients:
            q.put(event)

log.set_handler(_log_handler)
log.open_file(bootstrap.APP_DIR / 'mulsa.log')

@app.get("/events")
def events():
    q = queue.Queue()
    with _clients_lock:
        _clients.append(q)

    # Un generador: cada "yield" es un trozo de la respuesta. La peticion no termina
    # hasta que el cliente cierra; mientras, bloquea en q.get() esperando eventos.
    def stream():
        try:
            while True:
                event = q.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            with _clients_lock:
                _clients.remove(q)

    return StreamingResponse(stream(), media_type="text/event-stream")

# ---------- playlists ----------
# Ejemplo completo: de aqui copias el patron para el resto.
# with_images=False porque la imagen va por su propio endpoint (abajo); asi la lista
# responde rapido y Angular pide cada portada por separado con <img src=...>.
@app.get("/playlists")
def playlists():
    result = sheets.list_playlists(with_images=False)
    _covers.update({p["title"]: p["image_url"] for p in result})
    return [{"name": p["title"], "cover_url": p["image_url"]} for p in result]

# busca la playlist por su nombre y devuelve la portada
@app.get("/playlists/{name}/cover")
def playlist_cover(name: str):
    url = _covers.get(name)
    if not url:
        raise HTTPException(404, "playlist has no cover")
    return Response(content=sheets.fetch_image(url), media_type="image/jpeg")

# ---------- ejecucion ----------
_run_thread = None

@app.post("/run/{name}")
def run(name: str):
    global _run_thread
    if _run_thread and _run_thread.is_alive():
        raise HTTPException(409, "already running")
    _run_thread = threading.Thread(target=manager.run_manager, args=(name,), daemon=True)
    _run_thread.start()
    return {"status": "started"}

@app.post("/stop")
def stop():
    manager.stop_manager()
    return {"status": "stopping"}

@app.get("/status")
def status():
    return {"running": bool(_run_thread and _run_thread.is_alive())}

@app.get("/log")
def full_log():
    detailed = (bootstrap.APP_DIR / 'mulsa.log').read_text(encoding='utf-8')
    return Response(content=log.summary_text() + "\n\n----- detailed -----\n" + detailed, media_type="text/plain")

# ---------- settings ----------
# get de los settings
@app.get("/settings")
def get_settings():
    configured = bootstrap.is_configured()
    if bootstrap.CONFIG_FILE.exists():
        config = bootstrap.load_config() 
    else:
        config = {}
        
    soulseek_username = config.get("soulseek_username", "")
    music_dir = config.get("music_dir", str(bootstrap.DEFAULT_MUSIC_DIR))
    share_dir = config.get("share_dir", "")
    listen_port = config.get("listen_port", bootstrap.LISTEN_PORT)
    credentials_file = str(bootstrap.CREDENTIALS_FILE)
    return {
        "configured": configured,
        "soulseek_username": soulseek_username,
        "music_dir": music_dir,
        "share_dir": share_dir,
        "listen_port": listen_port,
        "credentials_file": credentials_file
    }

# post de los settings
@app.post("/settings")
def save_settings(body: dict):
    # saco los datos del body
    user = body.get("soulseek_username", "").strip()
    pwd = body.get("soulseek_password", "")
    music = body.get("music_dir", "").strip()
    share = body.get("share_dir", "").strip() or None
    port = str(body.get("listen_port", bootstrap.LISTEN_PORT)).strip()
    creds = body.get("credentials_file", str(bootstrap.CREDENTIALS_FILE)).strip()

    # valido los datos
    if not user or not pwd:
        raise HTTPException(400, "Soulseek username and password are required.")
    if not music:
        raise HTTPException(400, "Choose a music folder.")
    try:
        port_num = int(port)
        if not port.isdigit() or port_num < 1 or port_num > 65535:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, "The listen port must be a number between 1 and 65535")
    if not creds:
        raise HTTPException(400, "Select your Google credentials.json file.")

    def work():
        try: 
            bootstrap.run_setup(
                username=user,
                password=pwd,
                music_dir=music,
                share_dir=share,
                credentials_src=creds,
                progress=log.line,
                listen_port=port_num,
            )
        except Exception as e:
            log.line(f"Error during setup: {e}", "error")

    threading.Thread(target=work, daemon=True).start()
    return {"status": "started"}