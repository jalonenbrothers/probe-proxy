"""Milestone 2 — honest baseline: synthesized vs EMPTY config, per app.

For each catalog app, in ONE container session (same direct fingerprint):
  (a) synthesize + replay-verify loop (<=3 iters, fixers allowed)
  (b) replay with an EMPTY/default reverse_proxy block (1 iter, no fixers)
Delta table: where does replay-verified synthesis earn its keep vs
just writing `reverse_proxy app:80` with no parameters?

Kill/retreat condition (from card): if synthesized beats empty on <=2/10
apps, the honest value story narrows to 'catches invisible killers only'.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import docker
import httpx

from . import probes, synthesize
from .apps import APPS
from .replay import (confirm_diffs, diff_fingerprints, free_port,
                     replay_against, start_caddy, wait_caddy, wait_ready)

from .paths import data_dir

OUT_DIR = data_dir() / "replay"


def run_baseline_single(name: str, dc=None) -> dict:
    dc = dc or docker.from_env()
    app = next(a for a in APPS if a["name"] == name)
    app_port = free_port()
    net = dc.networks.create(f"probe-proxy-m2b-{name}", driver="bridge")
    dep_conts, caddy = [], None
    try:
        cont = dc.containers.run(
            app["image"], name=f"probe-proxy-m2b-{name}",
            detach=True, remove=True, network=net.name,
            environment=app["env"],
            ports={f"{app['port']}/tcp": app_port},
            labels={"probe-proxy": "m2"})
        for i, dep in enumerate(app.get("deps", [])):
            dep_conts.append(dc.containers.run(
                dep["image"], name=f"probe-proxy-m2b-{name}-dep{i}",
                detach=True, remove=True, network_mode=f"container:{cont.id}",
                environment=dep["env"], labels={"probe-proxy": "m2"}))

        ok = wait_ready(app_port, app["ready_path"], app["grace"])
        if not ok:
            print(f"[{name}] NOT READY — probing anyway")
        direct_base = f"http://127.0.0.1:{app_port}"
        direct = probes.run_all(direct_base)
        upstream = f"probe-proxy-m2b-{name}:{app['port']}"

        # (a) synthesized, full loop
        synth = synthesize.synthesize(direct, upstream)
        params, warnings = synth["params"], list(synth["warnings"])
        syn_res = replay_against(dc, net.name, direct_base, direct, upstream,
                                 params, warnings, f"{name}-synth")
        (OUT_DIR / f"Caddyfile.{name}").write_text(syn_res["caddyfile"])

        # (b) EMPTY config, single pass, no fixers — the naive baseline
        empty_params = []
        empty_warn = []
        empty_res = replay_against(dc, net.name, direct_base, direct,
                                   upstream, empty_params, empty_warn,
                                   f"{name}-empty", max_iter=1)
        (OUT_DIR / f"Caddyfile.{name}.empty").write_text(
            empty_res["caddyfile"])

        return {
            "app": name, "ready": ok,
            "synth": {"zero_diff": syn_res["zero_diff"],
                      "diffs": syn_res["diffs"],
                      "iters": len(syn_res["history"]),
                      "params": params},
            "empty": {"zero_diff": empty_res["zero_diff"],
                      "diffs": empty_res["diffs"]},
            "warnings": warnings,
        }
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
            dc.containers.get(f"probe-proxy-m2b-{name}").stop(timeout=10)
        except Exception:
            pass
        try:
            net.remove()
        except Exception:
            pass


def run(only=None):
    OUT_DIR.mkdir(exist_ok=True)
    results = {}
    for app in APPS:
        if app["name"] == "httpbin":
            continue
        if only and app["name"] not in only:
            continue
        print(f"=== {app['name']} ({app['image']})")
        try:
            results[app["name"]] = run_baseline_single(app["name"])
        except Exception as e:
            print(f"  FAILED: {e}")
            results[app["name"]] = {"app": app["name"], "error": str(e)}
    if only and (OUT_DIR / "baseline.json").exists():
        old = json.loads((OUT_DIR / "baseline.json").read_text())
        old.update(results)
        results = old
    (OUT_DIR / "baseline.json").write_text(
        json.dumps(results, indent=2, default=str))

    # delta table
    lines = ["| app | empty: diffs | synth: diffs | synth wins |",
             "|---|---|---|---|"]
    wins = 0
    for a, r in results.items():
        if "error" in r:
            lines.append(f"| {a} | ERROR | ERROR | ? |")
            continue
        ne, ns = len(r["empty"]["diffs"]), len(r["synth"]["diffs"])
        win = "YES" if ns < ne else ("tie" if ns == ne else "NO")
        if ns < ne:
            wins += 1
        lines.append(f"| {a} | {ne} | {ns} | {win} |")
    table = "\n".join(lines)
    (OUT_DIR / "baseline_table.md").write_text(table + "\n")
    print(f"\nsynthesized beats empty on {wins}/{len(results)} apps")
    print(f"results -> {OUT_DIR / 'baseline.json'}")
    return results
