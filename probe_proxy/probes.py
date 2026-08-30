"""probe-proxy — Milestone 0 probe suite.

Probes a live HTTP endpoint and returns a behavioral fingerprint dict.
Each probe is a function taking (base_url) -> dict of fingerprint values.
No synthesis, no config generation — observation only.
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx

TIMEOUT = 15.0


# ---------------------------------------------------------------- probes

def probe_root(base: str, c: httpx.Client) -> dict:
    r = c.get(base + "/", follow_redirects=False)
    return {
        "root_status": r.status_code,
        "root_location": (r.headers.get("location") or "")[:80],
        "root_server": r.headers.get("server", ""),
        "root_powered_by": r.headers.get("x-powered-by", ""),
    }


def probe_redirect_chain(base: str, c: httpx.Client) -> dict:
    """GET / following redirects manually; record chain of status[:location]."""
    chain, url, hops = [], base + "/", 0
    while hops < 6:
        r = c.get(url, follow_redirects=False)
        loc = r.headers.get("location")
        chain.append(f"{r.status_code}")
        if r.status_code in (301, 302, 303, 307, 308) and loc:
            url = str(httpx.URL(url).join(loc))
            hops += 1
        else:
            break
    return {"redirect_chain": ">".join(chain) if len(chain) > 1 else "none",
            "redirect_hops": hops}


def probe_tls_redirect(base: str, c: httpx.Client) -> dict:
    """Does /redirect-to?url=https://... bounce http->https or honor client?"""
    try:
        r = c.get(base + "/redirect-to?url=https://example.com&status_code=302",
                  follow_redirects=False)
        return {"tls_redirect_status": r.status_code,
                "tls_redirect_honors_param": bool(r.headers.get("location"))}
    except Exception as e:
        return {"tls_redirect_status": -1,
                "tls_redirect_honors_param": False}


def probe_http_to_https_upgrade(base: str, c: httpx.Client) -> dict:
    """Probe X-Forwarded-Proto: https on / — does the app upgrade links or redirect?"""
    try:
        r = c.get(base + "/", headers={"X-Forwarded-Proto": "https"},
                  follow_redirects=False)
        return {"xfp_status": r.status_code,
                "xfp_location": (r.headers.get("location") or "")[:60]}
    except Exception as e:
        return {"xfp_status": -1, "xfp_location": f"err:{type(e).__name__}"}


def probe_header_reflect(base: str, c: httpx.Client) -> dict:
    """Send X-Forwarded-For/Proto/Host and see whether any response header,
    body echo, or Set-Cookie domain acknowledges them (apps that build
    absolute URLs react to X-Forwarded-Host)."""
    sent = {"X-Forwarded-For": "198.51.100.7",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "probe.example.test"}
    try:
        r = c.get(base + "/", headers=sent, follow_redirects=False)
        blob = json.dumps(dict(r.headers)) + (r.text or "")[:2000]
        return {
            "xfh_acknowledged": "probe.example.test" in blob,
            "xff_acknowledged": "198.51.100.7" in blob,
            "set_cookie": bool(r.headers.get("set-cookie")),
            "cookie_secure_flag": "secure" in (r.headers.get("set-cookie") or "").lower(),
        }
    except Exception as e:
        return {"xfh_acknowledged": False, "xff_acknowledged": False,
                "set_cookie": False, "cookie_secure_flag": False,
                "err": type(e).__name__}


def probe_websocket(base: str, c: httpx.Client) -> dict:
    """Try WS handshake on / and a few common WS paths."""
    import websockets
    results = {}
    for path in ("/", "/ws", "/socket.io/?EIO=4&transport=websocket",
                 "/api/socket", "/websockets", "/events"):
        url = base.replace("http://", "ws://") + path
        try:
            async def _t():
                async with websockets.connect(url, open_timeout=5,
                                              close_timeout=2) as ws:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=3)
                        return f"open+data:{str(msg)[:24]}"
                    except asyncio.TimeoutError:
                        return "open"
            results[path] = asyncio.get_event_loop().run_until_complete(_t())
        except Exception as e:
            results[path] = f"fail:{type(e).__name__}"
    open_paths = [p for p, v in results.items() if v.startswith("open")]
    return {"ws_open_paths": open_paths if open_paths else "none",
            "ws_any_data": any(":data:" in v for v in results.values())}


GAP_MS = 50  # inter-chunk gap threshold: survives TCP coalescing noise


def sse_metrics(t_starts: list[float]) -> dict:
    """Turn per-chunk arrival timestamps into coalescing-stable metrics.

    Raw chunk COUNTS are TCP-coalescing noise (M1: gitea 5 chunks direct
    vs 1 via an identical config). What actually matters — and survives
    coalescing — is the *timing structure*: how many gaps between chunk
    arrivals are >= GAP_MS (i.e. distinct events arriving over time vs one
    buffered burst). M2 change.
    """
    gaps = [b - a for a, b in zip(t_starts, t_starts[1:])]
    return {
        "sse_chunks_observed": len(t_starts),
        "sse_gaps_ge_50ms": sum(1 for g in gaps if g * 1000 >= GAP_MS),
        "sse_max_gap_ms": round(max(gaps) * 1000) if gaps else 0,
    }


def probe_sse(base: str, c: httpx.Client) -> dict:
    """GET / with Accept: text/event-stream; measure chunk arrival times."""
    try:
        with c.stream("GET", base + "/",
                      headers={"Accept": "text/event-stream"},
                      follow_redirects=True) as r:
            ctype = r.headers.get("content-type", "")
            start = time.time()
            t_starts: list[float] = []
            for _ in r.iter_raw():
                t_starts.append(time.time() - start)
                if len(t_starts) >= 5 or time.time() - start > 6:
                    break
            out = {
                "sse_content_type": ctype.split(";")[0],
                # streamed = real temporal separation between chunks
                # (gap-based, coalescing-stable — M2; chunk-count-derived
                # 'streamed' was TCP-coalescing noise)
                "sse_streamed": None,  # filled below from gaps
                "sse_first_chunk_ms": round((t_starts[0] if t_starts else 99) * 1000),
            }
            if t_starts:
                out.update(sse_metrics(t_starts))
                out["sse_streamed"] = out["sse_gaps_ge_50ms"] >= 1
            else:
                out.update({"sse_chunks_observed": 0,
                            "sse_gaps_ge_50ms": 0, "sse_max_gap_ms": 0})
            return out
    except Exception as e:
        return {"sse_content_type": "", "sse_streamed": False,
                "sse_first_chunk_ms": -1, "sse_chunks_observed": 0,
                "sse_gaps_ge_50ms": 0, "sse_max_gap_ms": 0,
                "err": type(e).__name__}


def probe_large_post(base: str, c: httpx.Client) -> dict:
    """POST 10MB; record status + whether body was rejected early."""
    body = b"x" * (10 * 1024 * 1024)
    try:
        r = c.post(base + "/", content=body,
                   headers={"Content-Type": "application/octet-stream"},
                   follow_redirects=True)
        return {"post10mb_status": r.status_code,
                "post10mb_len_header": r.headers.get("content-length", "")}
    except httpx.RemoteProtocolError:
        return {"post10mb_status": "conn-reset", "post10mb_len_header": ""}
    except Exception as e:
        return {"post10mb_status": f"err:{type(e).__name__}",
                "post10mb_len_header": ""}


def probe_well_known(base: str, c: httpx.Client) -> dict:
    out = {}
    for wk in ("carddav", "caldav", "webfinger", "acme-challenge/test",
               "security.txt", "matrix/server"):
        try:
            r = c.get(base + "/.well-known/" + wk, follow_redirects=False)
            out[wk] = r.status_code
        except Exception:
            out[wk] = -1
    return {"well_known": json.dumps(out, sort_keys=True)}


def probe_method_allow(base: str, c: httpx.Client) -> dict:
    """OPTIONS / and a PROPFIND / (WebDAV apps answer 207)."""
    opts = c.options(base + "/")
    try:
        prop = c.request("PROPFIND", base + "/", content="")
        prop_status = prop.status_code
    except Exception:
        prop_status = -1
    return {"options_allow": (opts.headers.get("allow") or "")[:60],
            "propfind_status": prop_status}


def probe_common_paths(base: str, c: httpx.Client) -> dict:
    """Statuses of canonical paths — the strongest discriminator."""
    paths = ("/api", "/login", "/web/", "/websockets", "/health",
             "/api/health", "/status", "/api/v1", "/admin", "/metrics")
    out = {}
    for p in paths:
        try:
            r = c.get(base + p, follow_redirects=False)
            out[p] = r.status_code
        except Exception:
            out[p] = -1
    return {"path_statuses": json.dumps(out, sort_keys=True)}


def probe_compression(base: str, c: httpx.Client) -> dict:
    r = c.get(base + "/", headers={"Accept-Encoding": "gzip, br, zstd"},
              follow_redirects=True)
    enc = r.headers.get("content-encoding", "none")
    return {"compression": enc, "vary": bool(r.headers.get("vary"))}


PROBES = [
    ("root", probe_root),
    ("redirect_chain", probe_redirect_chain),
    ("tls_redirect", probe_tls_redirect),
    ("xfp_upgrade", probe_http_to_https_upgrade),
    ("header_reflect", probe_header_reflect),
    ("websocket", probe_websocket),
    ("sse", probe_sse),
    ("large_post", probe_large_post),
    ("well_known", probe_well_known),
    ("method_allow", probe_method_allow),
    ("common_paths", probe_common_paths),
    ("compression", probe_compression),
]


def run_all(base: str) -> dict:
    fp = {}
    with httpx.Client(base_url=base, timeout=TIMEOUT) as c:
        for name, fn in PROBES:
            t0 = time.time()
            try:
                fp[name] = fn(base, c)
            except Exception as e:
                fp[name] = {"error": type(e).__name__}
            fp.setdefault("_meta", {})[name] = round(time.time() - t0, 2)
    return fp
