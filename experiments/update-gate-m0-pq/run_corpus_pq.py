"""pq-gate M0 runner: for each jump, start OLD and NEW image in throwaway
containers with the app's native TLS enabled, probe with the PINNED static
Go client (tlsprobe), double-probe for stability, diff.

Mechanics mirror experiments/update-gate-m0/run_corpus.py:
- fresh throwaway container per probe run (label probe-proxy=pqgate)
- double probe per image: values kept only if identical across both runs
- fail-closed: any probe error or not-ready => recorded, jump counts as
  ERROR (would be HOLD in gate semantics), never as no-diff
- after each app's last image use, docker rmi (host disk is 98% full)
- results accumulate to results_pq.json (resume-safe, keyed app|old|new)
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import corpus_pq as corpus  # noqa: E402

HERE = Path(__file__).parent
RESULTS = HERE / "results_pq.json"
TLSPROBE = HERE / "tlsprobe"
CONT_PREFIX = "pqgate"
LABEL = {"probe-proxy": "pqgate"}

# cert fingerprint fields are OUR fixed cert, constant by construction —
# but kept in the fingerprint to prove the probe really saw our cert (a
# mismatch would mean we probed something else).
CERT_KEYS = {"cert_cn", "cert_issuer_cn", "cert_key_bits", "cert_key_type",
             "cert_sig_alg"}


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_tls_ready(port: int, grace: int) -> bool:
    """Fail-closed readiness: the pinned probe itself must complete once."""
    deadline = time.time() + grace
    while time.time() < deadline:
        r = subprocess.run([str(TLSPROBE), f"127.0.0.1:{port}", "probe.test"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            return True
        time.sleep(4)
    return False


def probe_image(dc, app: str, tag: str, run_id: int) -> list[dict]:
    """Start throwaway container of app:tag with native TLS, probe twice."""
    spec = corpus.APPS[app]
    image = f"{spec['repo']}:{tag}"
    port = free_port()
    cname = f"{CONT_PREFIX}-{app}-{run_id}"
    mounts = {}
    for src, dst, mode in spec["mounts"]:
        mounts[f"{HERE / src}"] = {"bind": dst, "mode": mode}
    cont = dc.containers.run(
        image, name=cname, detach=True, remove=True,
        environment=spec["env"], ports={f"{spec['port']}/tcp": port},
        labels=LABEL,
        entrypoint=spec["entrypoint"],
        command=spec["cmd"] or None,
        volumes=mounts)
    try:
        ok = wait_tls_ready(port, spec["grace"])
        fps = []
        for _ in range(2):  # double probe
            r = subprocess.run(
                [str(TLSPROBE), f"127.0.0.1:{port}", "probe.test"],
                capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                raise RuntimeError(f"tlsprobe failed (fail-closed): "
                                    f"{r.stdout.strip()[:200]}")
            fps.append(json.loads(r.stdout))
        fps[0]["_tls_ready"] = ok
        return fps
    finally:
        try:
            cont.stop(timeout=10)
        except Exception:
            pass
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                dc.containers.get(cname)
                time.sleep(1)
            except Exception:
                break


def stable_fp(runs: list[dict]) -> tuple[dict, dict]:
    stable, flaky = {}, {}
    keys = set()
    for r in runs:
        keys |= set(r.keys())
    for k in keys:
        vals = [r.get(k) for r in runs]
        if all(v == vals[0] for v in vals):
            stable[k] = vals[0]
        else:
            flaky[k] = vals
    return stable, flaky


def diff_fps(old: dict, new: dict) -> dict:
    changed = {}
    for k in sorted(set(old) | set(new)):
        if k == "_tls_ready":
            continue
        if old.get(k) != new.get(k):
            changed[k] = {"old": old.get(k), "new": new.get(k)}
    return changed


def classify(changed: dict) -> str:
    """Gate semantics (critic condition c): a crypto-visible diff that a
    PQ migration / HNDL decision would consume -> crypto-visible; only
    non-crypto leaves -> minor; nothing -> no-diff."""
    if not changed:
        return "no-diff"
    crypto_keys = {"tls_versions", "tls_version", "groups_accepted",
                   "cipher_suite", "cert_key_type", "cert_key_bits",
                   "cert_sig_alg"}
    if any(k in crypto_keys for k in changed):
        return "crypto-visible"
    return "minor"


def rmi(image: str):
    try:
        subprocess.run(["docker", "rmi", image], capture_output=True,
                       timeout=180)
    except Exception:
        pass


def load_results() -> dict:
    if RESULTS.exists():
        try:
            return json.loads(RESULTS.read_text())
        except Exception:
            pass
    return {}


def main(only_apps: list[str]):
    import docker
    dc = docker.from_env()
    res = load_results()
    jumps = [j for j in corpus.JUMPS
             if not only_apps or j["app"] in only_apps]
    jumps = [j for j in jumps
             if f"{j['app']}|{j['old']}|{j['new']}" not in res]

    needed, last_use = {}, {}
    for i, j in enumerate(jumps):
        needed.setdefault(j["app"], set()).update([j["old"], j["new"]])
        last_use.setdefault(j["app"], {})
        for tag in (j["old"], j["new"]):
            last_use[j["app"]][tag] = max(last_use[j["app"]].get(tag, -1), i)

    fp_cache = {}

    def get_fp(app, tag, idx):
        key = (app, tag)
        if key not in fp_cache:
            image = f"{corpus.APPS[app]['repo']}:{tag}"
            print(f"    pulling {image} ...", flush=True)
            dc.images.pull(image)
            runs = probe_image(dc, app, tag, idx)
            stable, flaky = stable_fp(runs)
            fp_cache[key] = (stable, flaky)
        return fp_cache[key]

    for i, j in enumerate(jumps):
        rkey = f"{j['app']}|{j['old']}|{j['new']}"
        print(f"[{i+1}/{len(jumps)}] {j['app']} {j['old']} -> {j['new']} "
              f"({j['note']})", flush=True)
        try:
            old_s, old_f = get_fp(j["app"], j["old"], i * 2)
            new_s, new_f = get_fp(j["app"], j["new"], i * 2 + 1)
            changed = diff_fps(old_s, new_s)
            res[rkey] = {
                "app": j["app"], "old": j["old"], "new": j["new"],
                "cls": j["cls"], "strict": j["strict"], "note": j["note"],
                "diff": bool(changed), "n_changed": len(changed),
                "diff_class": classify(changed),
                "changed_fields": changed,
                "old_fp": old_s, "new_fp": new_s,
                "flaky_old": {k: len(v) for k, v in old_f.items()},
                "flaky_new": {k: len(v) for k, v in new_f.items()},
            }
        except Exception as e:
            res[rkey] = {
                "app": j["app"], "old": j["old"], "new": j["new"],
                "cls": j["cls"], "note": j["note"],
                "error": f"FAIL-CLOSED: {str(e)[:300]}",
                "diff": True, "diff_class": "crypto-visible",
            }
        RESULTS.write_text(json.dumps(res, indent=2))
        r = res[rkey]
        print(f"    diff={r['diff']} class={r['diff_class']} "
              f"n={r.get('n_changed')}", flush=True)
        for tag in (j["old"], j["new"]):
            if last_use[j["app"]].get(tag) == i:
                image = f"{corpus.APPS[j['app']]['repo']}:{tag}"
                rmi(image)
                fp_cache.pop((j["app"], tag), None)
                print(f"    rmi {image}", flush=True)
    print("DONE —", RESULTS)


if __name__ == "__main__":
    main(sys.argv[1:])
