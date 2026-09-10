"""M0 runner: for each jump, probe old (N-1) and new (N) images twice each
with the SHIPPED probe suite (probe_proxy.probes.run_all), diff stable
fingerprints, classify, and clean up images for disk headroom.

Usage: python3 run_corpus.py [app ...]   (probe only listed apps, e.g. for
resuming after a crash). Results accumulate into results.json.

Mechanics:
- fresh throwaway container per probe run (labels probe-proxy=m0gate)
- double probe per image: fingerprint values kept only if identical
  across both runs (stability filter kills nondeterminism, and run-to-run
  instability per value is recorded as `flaky_fields`)
- diff = stable-value mismatches only; unstable values excluded from the
  verdict but recorded per-jump as nondeterminism evidence
- after each app's last image use, `docker rmi` both images (disk is
  ~4GB free on this host; images up to ~2.3GB each)
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/osteri/.hermes/kanban/boards/innovation-lab/"
                  "workspaces/t_cf1c5836/probe-proxy")
sys.path.insert(0, str(Path(__file__).parent))

import corpus  # noqa: E402

RESULTS = Path(__file__).parent / "results.json"
CONT_PREFIX = "m0gate"
LABEL = {"probe-proxy": "m0gate"}

# fingerprint keys that are timing/measurement noise by design (M1/M2
# lesson: first-chunk latency, raw chunk counts) — excluded from diff
TIMING_KEYS = {"sse_first_chunk_ms", "sse_chunks_observed"}


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_ready(port: int, path: str, grace: int) -> bool:
    import httpx
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


def probe_image(dc, app: str, tag: str, run_id: int) -> dict:
    """Start a throwaway container of app:tag, probe it, tear down."""
    import httpx
    from probe_proxy import probes
    spec = corpus.APPS[app]
    image = f"{spec['repo']}:{tag}"
    port = free_port()
    cname = f"{CONT_PREFIX}-{app}-{run_id}"
    # pihole needs NET_ADMIN for its embedded dnsmasq
    kwargs = {}
    if spec.get("cap_add"):
        kwargs["cap_add"] = spec["cap_add"]
    cont = dc.containers.run(
        image, name=cname, detach=True, remove=True,
        environment=spec["env"],
        ports={f"{spec['port']}/tcp": port},
        labels=LABEL, **kwargs)
    try:
        ok = wait_ready(port, spec["ready"], spec["grace"])
        if not ok:
            print(f"    [{image}] NOT READY after {spec['grace']}s — probing anyway")
        base = f"http://127.0.0.1:{port}"
        fp = probes.run_all(base)
        fp["_container_ready"] = ok
        return fp
    finally:
        try:
            cont.stop(timeout=10)
        except Exception:
            pass
        # remove=True needs the docker daemon to reap; brief settle avoids
        # name collisions on the immediate next run
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                dc.containers.get(cname)
                time.sleep(1)
            except Exception:
                break


def stable_fingerprint(runs: list[dict]) -> tuple[dict, dict]:
    """Merge N probe runs: keep values identical across runs.
    Returns (stable_fp, flaky_fields) where flaky maps key->list of values."""
    stable, flaky = {}, {}
    keys = set()
    for r in runs:
        keys |= set(r.keys())
    for k in keys:
        vals = [r.get(k) for r in runs]
        # _meta holds per-probe wall times — always unstable, never diffed
        if k == "_meta":
            continue
        if all(v == vals[0] for v in vals):
            stable[k] = vals[0]
        else:
            flaky[k] = vals
    return stable, flaky


def normalize(v):
    """Normalize a fingerprint value for diffing (sort lists etc.)."""
    if isinstance(v, dict):
        return {k: normalize(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return sorted(normalize(x) for x in v)
    return v


def flatten(prefix: str, obj, out: dict):
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
    else:
        out[prefix] = obj


def diff_fps(old_fp: dict, new_fp: dict) -> dict:
    """Diff two stable fingerprints -> changed fields with old/new values."""
    o, n = {}, {}
    flatten("", old_fp, o)
    flatten("", new_fp, n)
    changed = {}
    for k in sorted(set(o) | set(n)):
        if k in TIMING_KEYS:
            continue
        if normalize(o.get(k)) != normalize(n.get(k)):
            changed[k] = {"old": o.get(k), "new": n.get(k)}
    return changed


def classify(changed: dict) -> str:
    """Diff class for gate semantics (critic condition c).
    no-diff: nothing stable changed
    header-SSE-class: only header/status/SSE content-type/streamed fields
      changed — the proxy-relevant classes probe-proxy knows how to fix
    unknown: anything else"""
    if not changed:
        return "no-diff"
    known_prefixes = ("root_", "xfp_", "xfh_", "cookie_", "set_cookie",
                      "sse_content_type", "sse_streamed", "compression",
                      "options_allow", "path_statuses", "well_known",
                      "redirect_", "tls_redirect", "post10mb",
                      "propfind_status", "websocket")
    unknown = [k for k in changed
               if not any(k == p or k.startswith(p) for p in known_prefixes)]
    return "unknown" if unknown else "header-SSE-class"


def rmi(image: str):
    try:
        subprocess.run(["docker", "rmi", image], capture_output=True, timeout=120)
    except Exception:
        pass


def load_results() -> dict:
    if RESULTS.exists():
        try:
            return json.loads(RESULTS.read_text())
        except Exception:
            pass  # truncated/empty file from a disk-full crash
    return {}


def main(only_apps: list[str]):
    import docker
    dc = docker.from_env()
    res = load_results()
    jumps = [j for j in corpus.JUMPS
             if not only_apps or j["app"] in only_apps]
    jumps = [j for j in jumps
             if f"{j['app']}|{j['old']}|{j['new']}" not in res]  # resume

    # images needed per app: endpoints of chained jumps
    needed = {}
    for j in jumps:
        needed.setdefault(j["app"], set()).update([j["old"], j["new"]])
    last_use = {}
    for i, j in enumerate(jumps):
        last_use.setdefault(j["app"], {})
        for tag in (j["old"], j["new"]):
            last_use[j["app"]][tag] = max(
                last_use[j["app"]].get(tag, -1), i)

    fp_cache = {}  # (app, tag) -> stable fp + flaky (image probed once, reused across jumps)

    def get_fp(app: str, tag: str, idx: int):
        key = (app, tag)
        if key not in fp_cache:
            image = f"{corpus.APPS[app]['repo']}:{tag}"
            print(f"    pulling {image} ...", flush=True)
            try:
                dc.images.pull(image)
            except Exception as e:
                raise RuntimeError(f"pull failed for {image}: {e}")
            runs = [probe_image(dc, app, tag, idx * 2),
                    probe_image(dc, app, tag, idx * 2 + 1)]
            stable, flaky = stable_fingerprint(runs)
            fp_cache[key] = (stable, flaky)
        return fp_cache[key]

    for i, j in enumerate(jumps):
        rkey = f"{j['app']}|{j['old']}|{j['new']}"
        print(f"[{i+1}/{len(jumps)}] {j['app']} {j['old']} -> {j['new']} "
              f"({j['cls']}{' strict' if j['strict'] else ''})", flush=True)
        # disk guard: need ~1.5x the larger app image free before pulling
        try:
            free_gb = int(subprocess.run(
                ["df", "--output=avail", "/"], capture_output=True, text=True)
                .stdout.split()[-1]) / 1024 / 1024
            if free_gb < 6:
                print(f"    WARNING only {free_gb:.1f}GB free", flush=True)
        except Exception:
            pass
        old_stable, old_flaky = get_fp(j["app"], j["old"], i)
        new_stable, new_flaky = get_fp(j["app"], j["new"], i)
        changed = diff_fps(old_stable, new_stable)
        res[rkey] = {
            "app": j["app"], "old": j["old"], "new": j["new"],
            "cls": j["cls"], "strict": j["strict"], "note": j["note"],
            "old_ready": old_stable.get("_container_ready"),
            "new_ready": new_stable.get("_container_ready"),
            "diff": bool(changed), "n_changed": len(changed),
            "diff_class": classify(changed),
            "changed_fields": changed,
            "flaky_old": {k: len(v) for k, v in old_flaky.items()},
            "flaky_new": {k: len(v) for k, v in new_flaky.items()},
        }
        RESULTS.write_text(json.dumps(res, indent=2))
        print(f"    diff={res[rkey]['diff']} n={res[rkey]['n_changed']} "
              f"class={res[rkey]['diff_class']} "
              f"flaky_old={len(old_flaky)} flaky_new={len(new_flaky)}")
        # disk hygiene: drop images whose last use just passed
        for tag in (j["old"], j["new"]):
            if last_use[j["app"]][tag] == i:
                image = f"{corpus.APPS[j['app']]['repo']}:{tag}"
                rmi(image)
                fp_cache.pop((j["app"], tag), None)
                print(f"    rmi {image}")
    print("DONE — results in", RESULTS)


if __name__ == "__main__":
    main(sys.argv[1:])