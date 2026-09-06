"""Milestone 1 — replay-verify loop.

For each catalog app: launch the app container (as in M0), launch Caddy
with the synthesized config on a docker network, replay the FULL probe
suite through the proxy, and diff against a direct probe run. Iterate
up to 3 times (fixers may adjust the config) until zero diffs.

Kill condition: <5 of 10 apps zero-diff after 3 iterations.
"""
from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import docker
import httpx

from . import probes
from .apps import APPS
from . import synthesize
from .paths import data_dir

OUT_DIR = data_dir() / "replay"
MAX_ITER = 3
NETWORK = "probe-proxy-m1"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_ready(port: int, path: str, grace: int) -> bool:
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + grace
    while time.time() < deadline:
        try:
            r = httpx.get(base + path, timeout=3, follow_redirects=True)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def diff_fingerprints(direct: dict, via: dict) -> list:
    """List of {probe, key, direct, via} for every mismatch."""
    out = []
    for probe, _fn in probes.PROBES:
        d, v = direct.get(probe, {}), via.get(probe, {})
        keys = set(d) | set(v)
        for k in sorted(keys):
            if k in synthesize.VOLATILE_KEYS:
                continue
            if d.get(k) != v.get(k):
                out.append({"probe": probe, "key": k,
                            "direct": d.get(k), "via": v.get(k)})
    return out


def confirm_diffs(direct_base: str, via_base: str, diffs: list,
                  samples: int = 3) -> list:
    """Re-run probes that show diffs and keep only diffs that persist
    in a majority of samples. Guards against flaky timing-sensitive
    probes (e.g. sse chunk counts varying with TCP coalescing)."""
    if not diffs:
        return []
    by_probe: dict[str, list] = {}
    for d in diffs:
        by_probe.setdefault(d["probe"], []).append(d)
    keys = {p: {d["key"] for d in ds} for p, ds in by_probe.items()}
    votes: dict[str, int] = {}
    with httpx.Client(timeout=probes.TIMEOUT) as dc, \
            httpx.Client(timeout=probes.TIMEOUT) as vc:
        fns = dict(probes.PROBES)
        for _ in range(samples):
            for p in by_probe:
                fn = fns[p]
                try:
                    d_kv = fn(direct_base, dc)
                except Exception as e:
                    d_kv = {"error": type(e).__name__}
                try:
                    v_kv = fn(via_base, vc)
                except Exception as e:
                    v_kv = {"error": type(e).__name__}
                for k in keys[p]:
                    if d_kv.get(k) != v_kv.get(k):
                        votes[f"{p}.{k}"] = votes.get(f"{p}.{k}", 0) + 1
    majority = samples // 2 + 1
    return [d for d in diffs if votes.get(f"{d['probe']}.{d['key']}", 0)
            >= majority]



def start_caddy(dc, net: str, caddyfile: str, name: str = "probe-proxy-m1-caddy"):
    """Run caddy:2 with the given Caddyfile; return (container, host_port)."""
    import tempfile
    import uuid
    port = free_port()
    f = tempfile.NamedTemporaryFile("w", suffix=".Caddyfile", delete=False)
    f.write(caddyfile)
    f.close()
    cont = dc.containers.run(
        "caddy:2", name=f"{name}-{uuid.uuid4().hex[:6]}", detach=True,
        remove=True, network=net, ports={"80/tcp": port},
        volumes={f.name: {"bind": "/etc/caddy/Caddyfile", "mode": "ro"}})
    return cont, port


def wait_caddy(port: int, timeout: int = 30) -> bool:
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(base + "/", timeout=2, follow_redirects=False)
            return True  # any response (even 502) = caddy listening
        except Exception:
            pass
        time.sleep(1)
    return False


def replay_against(dc, net: str, direct_base: str, direct: dict,
                   upstream: str, params: list, warnings: list,
                   label: str, out_name: str | None = None,
                   max_iter: int = MAX_ITER) -> dict:
    """Run the replay-verify iteration loop against an already-running app.

    Shared core for `replay.run_single` (M1 suite), the M2 e2e CLI and
    the M2 baseline. max_iter=1 disables fixers (pure single-pass replay
    — used for the EMPTY-config baseline arm).
    Returns {history, diffs, zero_diff, caddyfile}.
    """
    from . import synthesize as syn
    history, final_diffs, caddy, caddyfile = [], [], None, ""
    for it in range(1, max_iter + 1):
        caddyfile = syn.render(upstream, params)
        if out_name:
            OUT_DIR.mkdir(exist_ok=True)
            (OUT_DIR / f"Caddyfile.{out_name}").write_text(caddyfile)
        try:
            if caddy:
                caddy.stop(timeout=3)
        except Exception:
            pass
        caddy, cport = start_caddy(dc, net, caddyfile)
        wait_caddy(cport)
        via = probes.run_all(f"http://127.0.0.1:{cport}")
        diffs = diff_fingerprints(direct, via)
        if diffs:
            diffs = confirm_diffs(direct_base,
                                   f"http://127.0.0.1:{cport}", diffs)
        history.append({"iteration": it, "params": list(params),
                        "diffs": diffs})
        final_diffs = diffs
        print(f"[{label}] iter {it}: {len(diffs)} diffs "
              + (f"-> {[(d['probe'], d['key']) for d in diffs]}"
                 if diffs else "-> ZERO-DIFF"))
        if not diffs:
            break
        if it < MAX_ITER:
            syn.iterate(params, warnings, diffs)
    if caddy:
        try:
            caddy.stop(timeout=3)
        except Exception:
            pass
    return {"history": history, "diffs": final_diffs,
            "zero_diff": not final_diffs, "caddyfile": caddyfile}


def run_single(name: str, dc=None) -> dict:
    dc = dc or docker.from_env()
    app = next(a for a in APPS if a["name"] == name)
    app_port = free_port()

    net = dc.networks.create(f"probe-proxy-m1-{name}", driver="bridge")
    dep_conts, caddy = [], None
    try:
        cont = dc.containers.run(
            app["image"], name=f"probe-proxy-m1-{name}",
            detach=True, remove=True, network=net.name,
            environment=app["env"],
            ports={f"{app['port']}/tcp": app_port},
            labels={"probe-proxy": "m1"})

        for i, dep in enumerate(app.get("deps", [])):
            dep_conts.append(dc.containers.run(
                dep["image"], name=f"probe-proxy-m1-{name}-dep{i}",
                detach=True, remove=True, network_mode=f"container:{cont.id}",
                environment=dep["env"], labels={"probe-proxy": "m1"}))

        ok = wait_ready(app_port, app["ready_path"], app["grace"])
        if not ok:
            print(f"[{name}] NOT READY after {app['grace']}s — probing anyway")
        direct_base = f"http://127.0.0.1:{app_port}"
        direct = probes.run_all(direct_base)

        # ---- synthesis + replay iterations
        upstream = f"probe-proxy-m1-{name}:{app['port']}"
        synth = synthesize.synthesize(direct, upstream)
        params, warnings = synth["params"], list(synth["warnings"])
        OUT_DIR.mkdir(exist_ok=True)
        res = replay_against(dc, net.name, direct_base, direct, upstream,
                             params, warnings, name, out_name=name)
        history, final_diffs = res["history"], res["diffs"]

        return {"app": name, "ready": ok, "iterations": history,
                "zero_diff": res["zero_diff"], "diffs": final_diffs,
                "warnings": warnings,
                "params": params,
                "caddyfile": (OUT_DIR / f"Caddyfile.{name}").read_text()}
    finally:
        if caddy:
            try:
                caddy.stop(timeout=3)
            except Exception:
                pass
        for d in dep_conts:
            try:
                d.stop(timeout=5)
            except Exception:
                pass
        try:
            dc.containers.get(f"probe-proxy-m1-{name}").stop(timeout=10)
        except Exception:
            pass
        try:
            net.remove()
        except Exception:
            pass


def run():
    import sys
    only = sys.argv[2:] if len(sys.argv) > 2 and sys.argv[1] == "replay_retry" else None
    OUT_DIR.mkdir(exist_ok=True)
    results = {}
    for app in APPS:
        if app["name"] == "httpbin":
            continue  # sanity target, not part of the 10
        if only and app["name"] not in only:
            continue
        print(f"=== {app['name']} ({app['image']})")
        try:
            results[app["name"]] = run_single(app["name"])
        except Exception as e:
            print(f"  FAILED: {e}")
            results[app["name"]] = {"app": app["name"], "error": str(e)}
    if only and (OUT_DIR / "replay.json").exists():
        old = json.loads((OUT_DIR / "replay.json").read_text())
        old.update(results)
        results = old
    (OUT_DIR / "replay.json").write_text(json.dumps(results, indent=2, default=str))
    zero = sum(1 for r in results.values() if r.get("zero_diff"))
    total = len(results)
    verdict = "PASSED (>=5/10 zero-diff)" if zero >= 5 else "KILL (<5/10)"
    print(f"\n{zero}/{total} zero-diff — {verdict}")
    print(f"results -> {OUT_DIR / 'replay.json'}")
    return results
