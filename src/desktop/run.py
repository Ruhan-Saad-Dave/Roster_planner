"""Desktop runner launching FastAPI daemon and opening application window."""
import sys
import os
os.environ["DISABLE_SQLALCHEMY_CEXT"] = "1"
import time
import threading
import webbrowser
import uvicorn

# Ensure repository root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

def start_server(port=8000):
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=port, log_level="warning")

def main():
    port = 8000
    print(f"[*] Starting LocalRoster v2 backend server on http://127.0.0.1:{port}...")

    # Start FastAPI server in a background thread
    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()

    time.sleep(1.2)  # Allow server to bind

    url = f"http://127.0.0.1:{port}"
    print(f"[✓] LocalRoster v2 is running at: {url}")

    # Attempt to use pywebview if installed, otherwise launch system browser
    try:
        import webview
        print("[*] Launching standalone desktop window via pywebview...")
        webview.create_window("LocalRoster v2 - Offline Workforce Planner", url, width=1280, height=840)
        webview.start()
    except ImportError:
        print(f"[*] Opening browser to {url}...")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Shutting down LocalRoster v2.")

if __name__ == "__main__":
    main()
