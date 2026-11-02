"""Demo client for M1: sends requests through the proxy to the local
test server, the way an agent configured with HTTP_PROXY would.

Run (proxy + server already running):
  python client.py --upstream http://127.0.0.1:18080 --proxy http://127.0.0.1:8888
"""
from __future__ import annotations

import argparse
import urllib.request


def call(opener, url, trace_id=None, data=None):
    req = urllib.request.Request(url, data=data,
                                 method="POST" if data else "GET")
    if trace_id:
        req.add_header("X-Trace-Id", trace_id)
    try:
        with opener.open(req, timeout=10) as resp:
            body = resp.read()
            print(f"{resp.status} {url} trace={resp.headers.get('X-Trace-Id')} "
                  f"bytes={len(body)} body={body.decode(errors='replace')[:80]}")
    except urllib.error.HTTPError as exc:
        print(f"{exc.code} {url} trace={exc.headers.get('X-Trace-Id')}")


def main():
    parser = argparse.ArgumentParser(description="Demo proxied client")
    parser.add_argument("--upstream", default="http://127.0.0.1:18080")
    parser.add_argument("--proxy", default="http://127.0.0.1:8888")
    args = parser.parse_args()

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": args.proxy}))
    call(opener, f"{args.upstream}/echo")                        # proxy generates trace
    call(opener, f"{args.upstream}/echo", trace_id="demo-trace-1")  # kept unchanged
    call(opener, f"{args.upstream}/echo", trace_id="demo-trace-1",
         data=b"hello")                                          # retry of same trace+endpoint
    call(opener, f"{args.upstream}/usage")
    call(opener, f"{args.upstream}/fail")


if __name__ == "__main__":
    main()
