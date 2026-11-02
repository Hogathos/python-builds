"""M3 Agent B: the middle agent in the two-agent demo.

Receives a request (arriving through the proxy from Agent A), reads the
X-Trace-Id the proxy forwarded, then calls the upstream test server
through the proxy again, carrying that same trace ID on the second leg.

Metadata only: this agent never logs headers, keys, or bodies. It reads
its request body only to consume it, and returns a small JSON summary.

Run standalone (proxy + test server already running):
  python agent_b.py --port 18081 --proxy http://127.0.0.1:8888 \
      --upstream http://127.0.0.1:18080
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_handler(proxy_url: str, upstream_base: str):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy_url}))

    class AgentBHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep stdout clean
            pass

        def _json(self, code: int, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if payload.get("trace_id"):
                self.send_header("X-Trace-Id", payload["trace_id"])
            self.end_headers()
            self.wfile.write(body)

        def _handle(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)  # consume only; never logged
            # The proxy forwarded (or generated) this ID on leg 1.
            trace_id = self.headers.get("X-Trace-Id")
            # Leg 2: downstream through the proxy, same trace ID.
            req = urllib.request.Request(f"{upstream_base}/echo", method="GET")
            if trace_id:
                req.add_header("X-Trace-Id", trace_id)
            try:
                with opener.open(req, timeout=10) as resp:
                    resp.read()
                    downstream_status = resp.status
                    carried = resp.headers.get("X-Trace-Id") or trace_id
            except Exception:
                self._json(502, {"agent": "B", "trace_id": trace_id,
                                 "downstream_status": 502})
                return
            self._json(200, {"agent": "B", "trace_id": carried,
                             "downstream_status": downstream_status})

        do_GET = _handle
        do_POST = _handle

    return AgentBHandler


def serve(host: str, port: int, proxy_url: str,
          upstream_base: str) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(
        (host, port), make_handler(proxy_url, upstream_base))


def main():
    parser = argparse.ArgumentParser(description="M3 Agent B (middle agent)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--proxy", default="http://127.0.0.1:8888")
    parser.add_argument("--upstream", default="http://127.0.0.1:18080")
    args = parser.parse_args()
    server = serve(args.host, args.port, args.proxy, args.upstream)
    print(f"agent B listening on {args.host}:{args.port} "
          f"proxy={args.proxy} upstream={args.upstream}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
