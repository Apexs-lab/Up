#!/usr/bin/env python3
"""
Up Dashboard — local server + API proxy
---------------------------------------
The Up Banking API (https://api.up.com.au) doesn't allow direct browser
requests (no CORS), so this tiny server does two things:

  1. Serves the dashboard (index.html) at http://localhost:8765
  2. Proxies anything under /up/* to https://api.up.com.au/api/v1/*
     attaching your personal access token as the Authorization header.

Your token never leaves your machine — it's sent from the page to this
local server, then straight to Up over HTTPS.

Run:
    python3 server.py
    # then open http://localhost:8765

Optionally set the token as an environment variable so you don't have to
paste it into the page each time:
    UP_API_TOKEN="up:yeah:xxxxxxxx" python3 server.py

Stdlib only — no pip installs needed.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = int(os.environ.get("PORT", "8765"))
HOST = os.environ.get("HOST", "127.0.0.1")
UP_BASE = "https://api.up.com.au/api/v1"
ENV_TOKEN = os.environ.get("UP_API_TOKEN", "").strip()


class Handler(SimpleHTTPRequestHandler):
    # Serve files from the directory this script lives in
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def end_headers(self):
        # Prevent caching so account/token-related data is not persisted by intermediaries.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        if self.path == "/token-status":
            self._send_json(200, {"hasEnvToken": bool(ENV_TOKEN)})
            return
        if self.path.startswith("/up/"):
            self._proxy()
            return
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def _proxy(self):
        token = self.headers.get("X-Up-Token", "").strip() or ENV_TOKEN
        if not token:
            self._send_json(401, {"errors": [{"title": "No token provided",
                                              "detail": "Enter your Up personal access token in the dashboard, "
                                                        "or start the server with UP_API_TOKEN set."}]})
            return

        upstream = UP_BASE + self.path[len("/up"):]
        sys.stderr.write("→ proxying to %s\n" % upstream)
        req = urllib.request.Request(upstream, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "up-local-dashboard/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._send_json(502, {"errors": [{"title": "Proxy error", "detail": str(e)}]})

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    shown_host = "localhost" if HOST in ("127.0.0.1", "0.0.0.0") else HOST
    print(f"\n  Up Dashboard running → http://{shown_host}:{PORT}\n")
    if ENV_TOKEN:
        print("  Using token from UP_API_TOKEN environment variable.\n")
    else:
        print("  No UP_API_TOKEN set — you'll be asked for your token in the browser.\n")
    try:
        HTTPServer((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
