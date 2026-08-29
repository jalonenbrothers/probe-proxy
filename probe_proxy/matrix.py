"""Milestone 0 matrix runner: launch each catalog app in a throwaway
container, wait for readiness, probe, tear down, then build the
probe x app matrix with a distinguishability verdict.

Container lifecycle via docker SDK. NOTE: this host requires group 'docker'
membership; the runner script wraps this in `sg docker` if needed.
"""
from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import httpx

from . import probes
from .apps import APPS
from .cli import store_open, store_fingerprint

OUT = Path(__file__).resolve().parent.parent / "matrix.json"


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


def run_single(name: str, docker_client=None):
    import docker
    dc = docker_client or docker.from_env()
    app = next(a for a in APPS if a["name"] == name)
    port = free_port()

    # optional dependency sidecars sharing the app's network namespace,
    # so "localhost" inside the app reaches them
    dep_conts = []
    for dep in app.get("deps", []):
        dep_conts.append(dc.containers.run(
            dep["image"], name=f"probe-proxy-{name}-dep", detach=True,
            remove=True, network_mode=f"container:probe-proxy-{name}-m0-placeholder",
            environment=dep["env"], labels={"probe-proxy": "m0"}) if False else None)

    cont = dc.containers.run(
        app["image"], name=f"probe-proxy-{name}-m0",
        detach=True, remove=True,
        environment=app["env"],
        ports={f"{app['port']}/tcp": port},
        labels={"probe-proxy": "m0"},
    )

    # start deps in the app's netns (docker run --network container:<app>)
    for i, dep in enumerate(app.get("deps", [])):
        dep_conts.append(dc.containers.run(
            dep["image"], name=f"probe-proxy-{name}-dep{i}", detach=True,
            remove=True, network_mode=f"container:{cont.id}",
            environment=dep["env"], labels={"probe-proxy": "m0"}))
    dep_conts = [d for d in dep_conts if d]

    try:
        ok = wait_ready(port, app["ready_path"], app["grace"])
        if not ok:
            print(f"[{name}] NOT READY after {app['grace']}s — probing anyway")
        base = f"http://127.0.0.1:{port}"
        fp = probes.run_all(base)
        fp["_container_ready"] = ok
        con = store_open()
        store_fingerprint(con, name, fp)
        con.close()
        return fp
    finally:
        for d in dep_conts:
            try:
                d.stop(timeout=5)
            except Exception:
                pass
        try:
            cont.stop(timeout=10)
        except Exception:
            pass


def run():
    import sys
    only = sys.argv[2:] if len(sys.argv) > 2 and sys.argv[1] == "matrix_retry" else None
    fps = {}
    for app in APPS:
        if only and app["name"] not in only:
            continue
        print(f"=== {app['name']} ({app['image']})")
        try:
            fps[app["name"]] = run_single(app["name"])
        except Exception as e:
            print(f"  FAILED: {e}")
            fps[app["name"]] = {"error": str(e)}
    # merge into existing matrix.json if this is a retry
    if only and OUT.exists():
        old = json.loads(OUT.read_text())
        old.update(fps)
        fps = old
    OUT.write_text(json.dumps(fps, indent=2, default=str))
    print(f"\nfingerprints -> {OUT}")
    return fps


if __name__ == "__main__":
    run()
