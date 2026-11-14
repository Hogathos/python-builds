# Iris code review — basic web / networking fundamentals, 2026-11-13

Reviewed: proxy.py (575 lines), api.py (478 lines), db.py (192 lines), from GitHub main, Hogathos/python-builds, agent-observability-proxy/. Tests: 11 files, suite 60/60.

## Verdict

Mostly solid for a local M1-M4 proxy. Allowlist, rate limit, hop-by-hop stripping, trace ID, fail-closed kill-switch, metadata-only logging are all present and correct.

Missing basic fundamentals, in order of importance:

## Basic — missing, fix before calling it solid

1. **Streaming / no buffering.** _handle reads the whole upstream response into memory with resp.read(), then sends it. That breaks SSE / WebSocket streaming, breaks large downloads, adds latency, and uses memory per response. A proxy should stream chunks through, not buffer the whole body. Same for request bodies: reads whole Content-Length body into memory, no size limit.
   - Fix: stream response in chunks, forward headers first, body in chunks. Add a max body size, or stream request body too.

2. **Chunked transfer encoding, request side.** Response side is handled by http.client resp.read() de-chunking, then re-sent with Content-Length. Request side is not: _handle only reads Content-Length. A chunked POST (Transfer-Encoding: chunked, no Content-Length) will be read as 0 bytes, or misread. Many clients / agents send chunked.
   - Fix: support chunked request bodies, or reject them with 501 / 400 in plain words, never silently drop the body.

3. **Keep-alive / connection reuse, upstream.** Every plain HTTP request opens a new HTTPConnection, no pooling, no keep-alive to upstream. Works, slow, and breaks clients that expect keep-alive. Downstream: protocol_version HTTP/1.1, Content-Length set, so keep-alive to the client mostly works, but CONNECT sets close_connection True.
   - Fix: reuse upstream connections per host, or document one-shot as a limit.

4. **Allowlist bypass by IP form.** is_allowed matches host strings, not resolved IPs. 0x7f.0.0.1, 2130706433, 0177.0.0.1, ::ffff:127.0.0.1, 127.1, trailing dot, case / encoding variants can slip past or be blocked inconsistently. DNS rebinding: an allowed hostname can resolve to a private IP after the check.
   - Fix: normalize IP forms, resolve and check the resolved IP, or block non-canonical forms. At minimum, test the IP-form cases.

5. **HTTP methods not implemented.** do_GET / POST / PUT / PATCH / DELETE / HEAD / OPTIONS only. TRACE, etc. return 501 from BaseHTTPRequestHandler. That is correct-ish, but log it as a row, not a silent 501 with no trace.
   - Fix: log unimplemented methods, or add them to _handle.

6. **WebSocket / Upgrade.** Hop-by-hop strips Upgrade, so plain HTTP WebSocket upgrade will break. CONNECT tunnel preserves it, plain HTTP does not. Name it, or support Upgrade properly.
   - Fix: either support Upgrade passthrough, or return a plain-words 501 saying WebSocket needs CONNECT.

7. **Request smuggling / header hygiene.** No check for duplicate Content-Length, or Content-Length + Transfer-Encoding together. http.server / http.client may parse inconsistently. No max header size, no max request line.
   - Fix: reject CL+TE together, reject duplicate CL, cap header size.

8. **IPv6 / Host parsing edge cases.** _target splits Host on ":" with rsplit, which breaks unbracketed IPv6, and _target returns None / 501 for https absolute-form (correct) but also for malformed ports without a clear row in all paths.
   - Fix: parse Host with proper IPv6 bracket handling, test IPv6 cases.

## Basic — present, correct, keep

- Hop-by-hop headers stripped both ways: Connection, Keep-Alive, Proxy-Connection, Proxy-Authorization, TE, Trailer, Transfer-Encoding, Upgrade.
- Host header rewritten to dest_label, X-Trace-Id forwarded / generated, X-Task-Number / X-Strategy stripped, never forwarded.
- Allowlist: host or host:port, IPv6 bracket form, 403 blocked, never opens tunnel.
- Rate limit: sliding window per destination, 429, recovery after window.
- CONNECT: 200 then raw relay, never decrypted, bytes counted only, 502 on upstream failure, 403 / 429 before tunnel opens.
- Relay: select loop, idle timeout 30s, partial bytes on timeout, close both sides on EOF.
- Fail-closed: proxy down = agent stops, zero new rows, proven.
- Metadata only: no Authorization / API-key headers logged, no bodies logged, tokens only if upstream JSON reports usage, cost never invented.
- API: GET only, read-only SQLite mode=ro, no-store, limit 1..100, 404 on unknown trace.
- DB: one row per attempt, threaded lock, migration race handled for outcome / reason, T9 still gated / specced, not done.

## Not basic — known limits, do not call them bugs

- HTTP/2, QUIC / UDP, direct DNS: proxy is HTTP/1.1 only. Alok point, already filed.
- B→C downstream hops: invisible by design, needs gateway / SDK.
- OS-level egress: env-var proxy only catches well-behaved clients.
- TLS: no termination by design, no cert validation to do on the proxy side.
- No auth on the API: loopback only, by design. If ever exposed beyond 127.0.0.1, that is a separate decision.

## Order to fix

1. Streaming + chunked request bodies — biggest functional gap, affects real agent sessions.
2. Allowlist IP-form normalization + CL+TE rejection — security hygiene.
3. Keep-alive upstream + WebSocket / method logging — correctness, smaller.
4. Then the Alok trace fields prompt (already cooked, iris-trace-fields-spark-prompt.md) — bytes_tx/rx, close_reason, connect_ms/duration_ms, honest CONNECT rows, allowlist UX.

None of these need a control endpoint, MITM, or Steer build. All are proxy.py / api.py / db.py work, tests each.
