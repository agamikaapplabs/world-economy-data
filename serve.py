from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os, sys
ROOT=Path(__file__).resolve().parent
os.chdir(ROOT)
PORT=8765
class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control","no-store, no-cache, must-revalidate")
        super().end_headers()
try:
    print(f"Serving {ROOT} at http://127.0.0.1:{PORT}/")
    ThreadingHTTPServer(("127.0.0.1",PORT),Handler).serve_forever()
except OSError as e:
    print(f"Server could not start on port {PORT}: {e}")
    print("If another V4 server is already running, it may already be serving these files.")
