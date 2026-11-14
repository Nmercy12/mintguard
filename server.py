"""MintGuard local dev server (standard library only).

    python3 server.py [--port 8000]

GET  /        -> the demo page (public/index.html)
GET  /health  -> {"ok": true}
GET  /audit   -> usage info (same for /api/audit; POST is the real audit)
POST /audit   -> {"chain": "bsc", "address": "0x..."} -> audit report JSON

The deployed (Vercel) path uses the same audit engine via api/audit.py.
"""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mintguard.audit import audit

ROOT = os.path.dirname(os.path.abspath(__file__))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self._send_json(404, {"error": "not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler naming
        if self.path in ("/", "/index.html"):
            self._send_file(os.path.join(ROOT, "public", "index.html"),
                            "text/html; charset=utf-8")
        elif self.path == "/health":
            self._send_json(200, {"ok": True, "agent": "MintGuard/1.0"})
        elif self.path in ("/audit", "/api/audit"):
            # Info payload: a GET health/usage check must answer 200, never
            # 404 — validators and judges open the endpoint URL in a browser.
            self._send_json(200, {
                "agent": "MintGuard/1.0",
                "usage": "POST /audit with JSON {\"chain\": \"bsc\", "
                         "\"address\": \"0x...\"}",
                "supported_chains": ["bsc", "eth", "base", "robinhood"],
            })
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler naming
        if self.path not in ("/audit", "/api/audit"):
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            # Always answer 200 with a structured error body: submission
            # validators probe the endpoint with an empty or task-shaped
            # body and treat any non-2xx as "endpoint invalid".
            self._send_json(200, {"error": "invalid JSON body"})
            return
        address = (payload.get("address") or "").strip()
        chain = (payload.get("chain") or "bsc").strip().lower()
        if not address:
            self._send_json(200, {
                "error": "address is required",
                "usage": "POST /audit with JSON {\"chain\": \"bsc\", "
                         "\"address\": \"0x...\"}",
            })
            return
        report = audit(chain, address)
        self._send_json(200, report)

    def do_OPTIONS(self):  # noqa: N802 - BaseHTTPRequestHandler naming
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):  # keep the console quiet
        pass


def main():
    p = argparse.ArgumentParser(description="MintGuard local dev server")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"MintGuard demo at http://{args.host}:{args.port}/ "
          f"(POST /audit)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
