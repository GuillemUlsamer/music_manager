"""
Primer arranque de Music Manager: deja slskd descargado y configurado sin que el
usuario toque YAML, keys ni carpetas. Todo vive dentro de tools/ (ignorado por git).
"""
import io
import json
import re
import secrets
import shutil
import zipfile
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
MUSIC_DIR = SCRIPT_DIR.parent

TOOLS_DIR = SCRIPT_DIR / 'tools'
SLSKD_DIR = TOOLS_DIR / 'slskd'
SLSKD_EXE = SLSKD_DIR / 'slskd.exe'
SLSKD_APP_DIR = TOOLS_DIR / 'slskd_data'
SLSKD_YML = SLSKD_APP_DIR / 'slskd.yml'

CONFIG_FILE = SCRIPT_DIR / 'config.json'
CREDENTIALS_FILE = SCRIPT_DIR / 'credentials.json'
INBOX_DIR = MUSIC_DIR / '_slskd_inbox'
INCOMPLETE_DIR = MUSIC_DIR / '_slskd_incomplete'

WEB_PORT = 5030
LISTEN_PORT = 50300
GITHUB_LATEST = 'https://api.github.com/repos/slskd/slskd/releases/latest'


def is_configured():
    return all(p.exists() for p in (CONFIG_FILE, SLSKD_EXE, SLSKD_YML, CREDENTIALS_FILE))


def load_config():
    with open(CONFIG_FILE, encoding='utf-8') as f:
        return json.load(f)


def download_slskd(progress):
    """Baja la ultima release de slskd para Windows x64 y la descomprime en tools/slskd."""
    if SLSKD_EXE.exists():
        progress("slskd already downloaded.")
        return
    progress("Checking latest slskd version...")
    release = requests.get(GITHUB_LATEST, timeout=30, headers={'Accept': 'application/vnd.github+json'})
    release.raise_for_status()
    assets = release.json().get('assets', [])
    asset = next((a for a in assets if re.search(r'win-x64\.zip$', a['name'])), None)
    if not asset:
        raise RuntimeError("Could not find the Windows zip in the slskd release.")

    progress(f"Downloading {asset['name']} ({asset['size'] // 1_000_000} MB)...")
    buf = io.BytesIO()
    with requests.get(asset['browser_download_url'], stream=True, timeout=60) as r:
        r.raise_for_status()
        total, done = asset['size'], 0
        for chunk in r.iter_content(chunk_size=1 << 20):
            buf.write(chunk)
            done += len(chunk)
            progress(f"Downloading slskd... {done * 100 // total}%")

    progress("Extracting slskd...")
    SLSKD_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(buf) as z:
        z.extractall(SLSKD_DIR)
    if not SLSKD_EXE.exists():
        raise RuntimeError("The zip did not contain slskd.exe where expected.")


def write_slskd_yml(username, password, api_key, share_dir=None):
    shares = f"    - {share_dir}\n" if share_dir else ""
    yml = f"""# Generado por Music Manager. No editar a mano: se regenera desde la app.
soulseek:
  username: {username}
  password: "{password}"
  description: "music_manager"
  listen_port: {LISTEN_PORT}

directories:
  downloads: {INBOX_DIR}
  incomplete: {INCOMPLETE_DIR}

shares:
  directories:
{shares}  filters:
    - \\.ini$
    - Thumbs\\.db$
    - desktop\\.ini$

web:
  port: {WEB_PORT}
  https:
    disabled: true
  authentication:
    disabled: false
    username: admin
    password: "{secrets.token_urlsafe(12)}"
    api_keys:
      music_manager:
        key: {api_key}
        role: readwrite
        cidr: 127.0.0.1/32,::1/128

transfers:
  global:
    download:
      slots: 3
    upload:
      slots: 5
      speed_limit: 2000

searches:
  response_limit: 100
  file_limit: 10000
"""
    SLSKD_APP_DIR.mkdir(parents=True, exist_ok=True)
    SLSKD_YML.write_text(yml, encoding='utf-8')


def run_setup(username, password, share_dir=None, credentials_src=None, progress=print):
    """Ejecuta todos los pasos. `progress` recibe mensajes de estado (str)."""
    if credentials_src and Path(credentials_src) != CREDENTIALS_FILE:
        progress("Copying credentials.json...")
        shutil.copyfile(credentials_src, CREDENTIALS_FILE)
    if not CREDENTIALS_FILE.exists():
        raise RuntimeError("credentials.json is missing (Google service account).")

    progress("Creating folders...")
    for d in (TOOLS_DIR, INBOX_DIR, INCOMPLETE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if share_dir and not Path(share_dir).is_dir():
        raise RuntimeError(f"Shared folder does not exist: {share_dir}")

    download_slskd(progress)

    progress("Writing slskd configuration...")
    api_key = load_config().get('api_key') if CONFIG_FILE.exists() else None
    api_key = api_key or secrets.token_hex(24)
    write_slskd_yml(username, password, api_key, share_dir)

    config = {
        'url': f'http://127.0.0.1:{WEB_PORT}/api/v0',
        'api_key': api_key,
        'inbox': str(INBOX_DIR),
        'exe': str(SLSKD_EXE),
        'app_dir': str(SLSKD_APP_DIR),
        'soulseek_username': username,
        'share_dir': share_dir or '',
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    progress("Setup complete.")
    return config
