import bootstrap

_CONFIG = None

def cfg():
    global _CONFIG
    if _CONFIG is None:
        if not bootstrap.is_configured():
            raise SystemExit("Music Manager is not set up yet: open gui.py and complete the first-run setup.")
        _CONFIG = bootstrap.load_config()
    return _CONFIG

def slskd_url():
    return cfg()['url']

def slskd_headers():
    return {"X-API-Key": cfg()['api_key']}

def slskd_inbox():
    return cfg()['inbox']

