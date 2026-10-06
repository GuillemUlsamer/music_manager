import threading

STOP_EVENT = threading.Event()

def check_stop():
    if STOP_EVENT.is_set():
        raise SystemExit("Stopped by user.")

