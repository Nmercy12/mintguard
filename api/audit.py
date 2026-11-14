"""MintGuard Vercel serverless function.

Vercel maps this file to POST /api/audit (and GET for a small info payload).
``vercel.json`` additionally rewrites POST /audit -> /api/audit so the demo
page can use the short path. Standard library only; no env vars needed.

Deploy: connect this repo in the Vercel dashboard (or `vercel` CLI) and
deploy — no build step, no secrets.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mintguard.audit import audit  # noqa: E402


class handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler naming
        self._send_json(200, {
            "agent": "MintGuard/1.0",
            "usage": "POST /api/audit with JSON {\"chain\": \"bsc\", "
                     "\"address\": \"0x...\"}",
            "supported_chains": ["bsc", "eth", "base", "robinhood"],
        })

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler naming
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send_json(400, {"error": "invalid JSON body"})
            return
        address = (payload.get("address") or "").strip()
        chain = (payload.get("chain") or "bsc").strip().lower()
        if not address:
            self._send_json(400, {"error": "address is required"})
            return
        self._send_json(200, audit(chain, address))

    def log_message(self, fmt, *args):
        pass
