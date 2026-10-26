import threading
import webbrowser

import uvicorn

from app import config

if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{config.PORT}")).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=config.PORT)
