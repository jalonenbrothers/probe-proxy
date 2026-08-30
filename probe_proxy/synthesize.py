"""Milestone 1 — fingerprint-driven Caddy config synthesis.

synthesize(fp) maps a behavioral fingerprint (from probe_proxy.probes)
to Caddy reverse_proxy directives. Policy: pass-through by default;
only observed *behavioral* quirks add directives. Ambiguous or
policy-not-behavior fingerprint values degrade to sane defaults WITH
warnings — never a confidently-wrong config.
"""
from __future__ import annotations

# keys whose values are timing/volatile — never drive synthesis.
# sse_chunks_observed: TCP-coalescing noise (M1); the gap-based keys are
# the coalescing-stable replacement (M2).
VOLATILE_KEYS = {"sse_first_chunk_ms", "sse_chunks_observed"}


def _clean(fp: dict, probe: str) -> dict:
    kv = fp.get(probe)
    if not isinstance(kv, dict):
        return {}
    return {k: v for k, v in kv.items() if k not in VOLATILE_KEYS}


def synthesize(fp: dict, upstream: str, listen: str = ":80") -> dict:
    """Return {caddyfile, params, warnings} built from fingerprint fp."""
    params: list[str] = []
    warnings: list[str] = []

    root = _clean(fp, "root")
    sse = _clean(fp, "sse")
    ws = _clean(fp, "websocket")
    comp = _clean(fp, "compression")
    reflect = _clean(fp, "header_reflect")
    post = _clean(fp, "large_post")
    wellknown = _clean(fp, "well_known")

    # --- streaming responses: flush immediately, no buffering
    if sse.get("sse_streamed"):
        params.append("flush_interval -1")

    # --- error'd probes: policy-not-behavior -> pass-through + warning
    for probe in ("root", "sse", "websocket", "compression",
                  "header_reflect", "large_post"):
        if "error" in (fp.get(probe) or {}):
            warnings.append(f"probe '{probe}' errored during fingerprinting; "
                            f"using pass-through default")

    # --- websocket: Caddy reverse_proxy upgrades WS transparently.
    # Only a warning path: if WS paths were open but streaming params
    # conflict, nothing to do — note it.
    if ws.get("ws_open_paths") not in (None, "none"):
        warnings.append(f"websocket paths {ws['ws_open_paths']} open; "
                        f"Caddy upgrades transparently, no directive needed")

    # --- compression: NEVER enable Caddy encode — it would CHANGE
    # observed behavior vs direct (apps that already compress would
    # double-encode; apps that don't would gain encoding).
    if comp.get("compression") and comp["compression"] != "none":
        warnings.append(f"app already emits {comp['compression']}; Caddy "
                        f"encode left off to preserve identity")

    # --- header reflection: Caddy sets/augments X-Forwarded-* by
    # default; only if the app IGNORES them do we keep strict
    # pass-through (default) — no directive either way. Recorded as
    # observation for the report, not config.
    if reflect.get("xfh_acknowledged"):
        warnings.append("app acknowledges X-Forwarded-Host; default "
                        "Caddy header pass-through preserves this")

    # --- large POST: no body limit directive by default. If the
    # fingerprint shows the app resetting on 10MB, keep Caddy out of
    # the way (no request_body max_size).
    if post.get("post10mb_status") == "conn-reset":
        warnings.append("app resets connections on large bodies; no Caddy "
                        "body limit set (pass-through)")

    # --- well-known redirects: 301s on caldav/carddav are app policy,
    # passed through untouched.
    if wellknown.get("well_known") and "301" in (wellknown["well_known"] or ""):
        warnings.append("well-known 301 redirects are app policy; "
                        "passed through unchanged")

    return {"caddyfile": render(upstream, params),
            "params": params, "warnings": warnings}


# ---------------------------------------------------------------- fixers
# iteration deltas applied when a replay diff names a probe. Each fixer
# receives (params, warnings, diffs) and mutates params/warnings.

def _fix_streaming(params, warnings, diffs):
    if "flush_interval -1" not in params:
        params.append("flush_interval -1")
        warnings.append("iter: added flush_interval -1 for streaming "
                        "diff (sse broken by buffering)")
        return True
    return False


def _fix_location_rewrite(params, warnings, diffs):
    for d in diffs:
        if "location" in d.get("key", "") or d["probe"] in ("redirect_chain",):
            if not any("header_down Location" in p for p in params):
                params.append(
                    'header_down Location "^https?://[^/]+(.*)$" "$1"')
                warnings.append("iter: rewriting absolute Location headers "
                                "(upstream leaked its internal host)")
                return True
    return False


def _fix_xff_reject(params, warnings, diffs):
    """App answers 4xx to X-Forwarded-For (e.g. Home Assistant rejects
    untrusted-proxy headers): stop sending XFF."""
    for d in diffs:
        if (d["probe"] in ("root", "common_paths", "well_known",
                           "method_allow", "redirect_chain",
                           "tls_redirect", "xfp_upgrade", "sse",
                           "large_post", "compression")
                and isinstance(d.get("via"), int) and 400 <= d["via"] < 500
                and isinstance(d.get("direct"), int) and d["direct"] < 400):
            if not any("header_up -X-Forwarded-For" in p for p in params):
                params.append("header_up -X-Forwarded-For")
                warnings.append("iter: app rejects X-Forwarded-For "
                                "(4xx on previously-2xx/3xx paths); "
                                "dropping XFF header")
                return True
    return False


FIXERS = [
    (("sse",), _fix_streaming),
    (("root", "redirect_chain", "xfp_upgrade", "tls_redirect"),
     _fix_location_rewrite),
    (("root", "common_paths", "well_known", "method_allow",
      "redirect_chain", "tls_redirect", "xfp_upgrade", "sse",
      "large_post", "compression"), _fix_xff_reject),
]


def iterate(params: list, warnings: list, diffs: list) -> bool:
    """Apply one fixer pass for the observed diffs. True if changed."""
    changed = False
    for probes, fixer in FIXERS:
        if any(d["probe"] in probes for d in diffs):
            if fixer(params, warnings, diffs):
                changed = True
    if not changed:
        warnings.append("iter: no known fixer applies to diffs: "
                        + ", ".join(f"{d['probe']}.{d['key']}" for d in diffs))
    return changed


def block_body(upstream: str, params: list, listen: str = ":80") -> str:
    """The Caddyfile text WITHOUT probe-proxy marker comments."""
    lines = ["{", "  admin off", "  auto_https off", "}",
             f"{listen} {{", f"  reverse_proxy {upstream} {{"]
    for p in params:
        lines.append(f"    {p}")
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n"


def marker_for(body: str) -> str:
    """Managed-by marker line: comment carrying a sha256 of the block body.

    Machine-checkable: `probe-proxy verify` strips marker lines, hashes the
    remaining block, and compares against the marker to measure hand-edit
    drift. Content-hash of the exact body (excluding the marker itself).
    """
    import hashlib
    h = hashlib.sha256(body.strip().encode()).hexdigest()[:16]
    return f"# managed-by probe-proxy v0.2 sha256:{h}"


def render(upstream: str, params: list, listen: str = ":80") -> str:
    """Caddyfile with managed-by marker (hand-edit counter, M2)."""
    body = block_body(upstream, params, listen)
    return marker_for(body) + "\n" + body
