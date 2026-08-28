"""No-dependency local launcher for the educational demo.

It serves the frontend and the access/session endpoints when FastAPI is not
available. Screenshot analysis remains available through the full FastAPI
server described in README.md.
"""

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from key_store import (
    KeyStoreError,
    activate_access_key,
    activate_admin_session,
    is_admin_access_key,
    initialize_database,
    load_local_env,
    validate_session,
)


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "outputs" / "aviator-signal-demo.html"


class Handler(BaseHTTPRequestHandler):
    server_version = "RoyalBetKingDemo/1.0"

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        if not path.is_file() or ROOT not in path.resolve().parents:
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Device-ID")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json(200, {"status": "ok", "mode": "standalone-demo"})
            return
        if parsed.path == "/api/auth/session":
            token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            device_id = parse_qs(parsed.query).get("device_id", [""])[0]
            self.send_json(200, {"valid": validate_session(token, device_id)})
            return
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_file(FRONTEND)
            return
        relative = parsed.path.lstrip("/").replace("/", "\\")
        self.send_file(ROOT / relative)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/analyze-history":
            self.send_json(503, {"detail": "Screenshot analysis needs the full FastAPI server and Gemini configuration."})
            return
        if parsed.path != "/api/auth/activate":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            access_key = str(payload.get("access_key", "")).replace(" ", "")
            device_id = str(payload.get("device_id", ""))
            subject = self.client_address[0] + ":standalone"
            if is_admin_access_key(access_key):
                result = activate_admin_session(access_key, device_id, subject)
            else:
                result = activate_access_key(access_key, device_id, subject)
            self.send_json(200, result)
        except KeyStoreError as error:
            self.send_json(error.status_code, {"detail": error.message})
        except (ValueError, json.JSONDecodeError):
            self.send_json(400, {"detail": "Invalid activation request."})
        except Exception as error:
            self.send_json(500, {"detail": "Local server error: " + str(error)})

    def log_message(self, format_string, *args):
        sys.stdout.write("[Royal BetKing] " + (format_string % args) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    load_local_env()
    initialize_database()
    port = int(os.getenv("RBK_PORT", "8080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Royal BetKing demo running at http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()
