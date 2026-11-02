"""Local HTTP test server for M1 — the proxy's upstream destination.

Endpoints:
  /        JSON ok
  /echo    JSON: method, path, received trace_id, body byte count,
           whether an Authorization header arrived (never its value)
  /fail    HTTP 500
  /usage   JSON with a self-reported `usage` object (token logging demo)
  /slow    JSON after ?delay=<seconds>

Run:  python server.py --port 18080
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if parsed.path == "/fail":
            self._json(500, {"error": "planned failure"})
        elif parsed.path == "/slow":
            delay = float(parse_qs(parsed.query).get("delay", ["0"])[0])
            time.sleep(min(delay, 5.0))
            self._json(200, {"ok": True, "delay": delay})
        elif parsed.path == "/usage":
            self._json(200, {"ok": True,
                             "usage": {"input_tokens": 42,
                                       "output_tokens": 7}})
        elif parsed.path == "/echo":
            self._json(200, {
                "ok": True,
                "method": self.command,
                "path": self.path,
                "trace_id": self.headers.get("X-Trace-Id"),
                "has_authorization": self.headers.get("Authorization") is not None,
                "body_bytes": len(body),
            })
        else:
            self._json(200, {"ok": True, "path": self.path})

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle


def main():
    parser = argparse.ArgumentParser(description="Local HTTP test server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"test server listening on {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
