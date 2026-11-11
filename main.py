import threading
import uvicorn
import webview

from api import app

def serve():
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")

if __name__ == "__main__":
    threading.Thread(target=serve, daemon=True).start()
    webview.create_window("Mulsa", "http://127.0.0.1:8765", width=1200, height=700, resizable=True)
    webview.start()