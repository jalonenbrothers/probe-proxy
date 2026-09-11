"""update-gate² — M1: the pre-pull gate (IDEA-10).

`probe-proxy baseline <container>`: double-probe the CURRENTLY RUNNING
service, store its stable fingerprint + image tag/digest in SQLite
(baselines table).

`probe-proxy gate <image:tag>`: pull the NEW image (or reuse a local
one), double-probe it in a THROWAWAY container (never touching the
operator's running service), diff its stable fingerprint against the
stored baseline, and print a verdict:

    ALLOW        (exit 0)  no stable behavioral diff
    HOLD known   (exit 2)  diff, but entirely of classes probe-proxy
                           knows how to synthesize around (header/SSE/
                           compression/redirect/...) — re-run synthesis
                           before upgrading
    HOLD unknown (exit 3)  any stable diff outside the known classes
    error        (exit 1)  anything else (pull failure, no baseline, ...)

Mechanics carried over from the M0 corpus (lessons there are load-bearing):
- double-probe + stability filter (values kept only if identical across
  two runs) is REQUIRED for deterministic verdicts — applied at the
  SECTION level (probe section present & stable in both runs)
- diff keys are `section.leaf` prefixed; timing leaves
  (sse_first_chunk_ms, sse_chunks_observed) are stripped as noise
- the classifier matches KNOWN_LEAVES against the LEAF of the prefixed
  key (M0 bug: bare-name matching misclassified every diff as "unknown")
"""
from __future__ import annotations

import json
import socket
import sys
import time

import docker

from . import probes
from .paths import repo_file

DB = repo_file("probe_results.db")

CONT_PREFIX = "gate"
GATE_LABEL = {"probe-proxy": "gate"}  # marks OUR throwaway containers

# ------------------------------------------------------------- exit codes
EXIT_ALLOW = 0
EXIT_ERROR = 1
EXIT_HOLD_KNOWN = 2
EXIT_HOLD_UNKNOWN = 3

# timing/measurement-noise leaves — never part of a verdict (M0 lesson)
TIMING_LEAVES = {"sse_first_chunk_ms", "sse_chunks_observed"}

# proxy-relevant classes the shipped engine knows how to synthesize
# around — parity with M0 reclassify.py KNOWN_LEAVES (do not diverge;
# the smoke corpus verdicts depend on exact parity)
KNOWN_LEAVES = (
    "root_", "xfp_", "xfh_", "cookie_", "set_cookie",
    "sse_content_type", "sse_streamed", "sse_gaps_ge_50ms",
    "sse_max_gap_ms",  # SSE streaming behavior = proxy-relevant
    "compression",
    "options_allow", "path_statuses", "well_known",
    "redirect_", "tls_redirect", "post10mb", "post10mb_len_header",
    "post10mb_status", "propfind_status", "websocket", "root_status",
)

# known-class groups for HOLD-known reporting (leaf -> class name)
LEAF_CLASSES = (
    ("root_", "header"), ("root_status", "status"),
    ("xfp_", "header"), ("xfh_", "header"), ("cookie_", "cookie"),
    ("set_cookie", "cookie"), ("cookie_secure_flag", "cookie"),
    ("sse_", "sse"), ("compression", "compression"),
    ("vary", "compression"),
    ("options_allow", "method"), ("propfind_status", "method"),
    ("path_statuses", "paths"), ("well_known", "paths"),
    ("redirect_", "redirect"), ("tls_redirect", "redirect"),
    ("post10mb", "large-body"), ("post10mb_len_header", "large-body"),
    ("post10mb_status", "large-body"), ("websocket", "websocket"),
)


# ------------------------------------------------------------- store

def store_open():
    import sqlite3
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS baselines (
        service TEXT, image TEXT, digest TEXT,
        fingerprint_json TEXT, ts REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS probe_results (
        app TEXT, probe TEXT, key TEXT, value TEXT, ts REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS hand_edits (
        config_path TEXT, edit_count INTEGER, ts REAL)""")
    return con


def save_baseline(con, service: str, image: str, digest: str, fp: dict):
    con.execute("DELETE FROM baselines WHERE service = ?", (service,))
    con.execute("INSERT INTO baselines VALUES (?,?,?,?,?)",
                (service, image, digest,
                 json.dumps(fp, default=str), time.time()))
    con.commit()


def load_baseline(con, service: str):
    row = con.execute(
        "SELECT image, digest, fingerprint_json, ts FROM baselines "
        "WHERE service = ? ORDER BY ts DESC LIMIT 1",
        (service,)).fetchone()
    if not row:
        return None
    return {"service": service, "image": row[0], "digest": row[1],
            "fingerprint": json.loads(row[2]), "ts": row[3]}


def all_services(con) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT DISTINCT service FROM baselines").fetchall()]


# ------------------------------------------------------------- probing

def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_ready(base: str, grace: int = 60) -> bool:
    import httpx
    deadline = time.time() + grace
    while time.time() < deadline:
        try:
            r = httpx.get(base + "/", timeout=3, follow_redirects=True)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _resolve_service(target: str, dc):
    """Find a running container by name or compose-service label.
    Returns the docker container object or raises LookupError."""
    from docker.errors import NotFound
    try:
        return dc.containers.get(target)
    except NotFound:
        pass
    for c in dc.containers.list():
        labels = c.labels or {}
        svc = labels.get("com.docker.compose.service")
        proj = labels.get("com.docker.compose.project", "")
        if svc == target or f"{proj}-{svc}" == target:
            return c
    raise LookupError(
        f"no running container or compose service named '{target}'")


def _published_port(cont) -> int | None:
    for p, binds in (cont.attrs["NetworkSettings"]["Ports"] or {}).items():
        if binds and binds[0].get("HostPort") and p.endswith("/tcp"):
            return int(binds[0]["HostPort"])
    return None


def _image_name(cont) -> str:
    tags = cont.image.tags or []
    for t in tags:
        if t and ":" in t:  # prefer a fully-qualified tag
            return t
    return tags[0] if tags else "<unknown>"


def probe_running_service(target: str, dc=None) -> dict:
    """Double-probe the RUNNING service (read-only: never starts, stops
    or restarts anything). Returns {service, base, image, digest, runs}."""
    dc = dc or docker.from_env()
    cont = _resolve_service(target, dc)
    port = _published_port(cont)
    if port is None:
        raise SystemExit(
            f"error: container '{target}' publishes no HTTP host port; "
            f"probe-proxy needs to reach it")
    base = f"http://127.0.0.1:{port}"
    runs = [probes.run_all(base), probes.run_all(base)]
    return {"service": target, "base": base, "image": _image_name(cont),
            "digest": (cont.image.id or "").split(":", 1)[-1][:12],
            "runs": runs}


def probe_new_image(dc, image: str, run_id: int, port: int = 80,
                    env: dict | None = None, cap_add: list | None = None):
    """Pull `image` (or reuse a local copy) and double-probe it in a
    THROWAWAY container publishing container port `port` on a free host
    port. Returns {runs, pulled}. Raises RuntimeError on pull failure.

    SAFETY: fresh generated container name + our label; it can never
    collide with or touch an operator's running service. The throwaway
    is stopped (and auto-removed) in `finally`.
    """
    pulled = False
    try:
        dc.images.get(image)
    except docker.errors.ImageNotFound:
        try:
            dc.images.pull(image)
            pulled = True
        except Exception as e:
            raise RuntimeError(f"pull failed for {image}: {e}") from e
    host_port = free_port()
    cname = f"{CONT_PREFIX}-probe-{run_id}"
    kwargs: dict = {"environment": env or {}}
    if cap_add:
        kwargs["cap_add"] = cap_add
    cont = dc.containers.run(
        image, name=cname, detach=True, remove=True,
        ports={f"{port}/tcp": host_port}, labels=GATE_LABEL, **kwargs)
    base = f"http://127.0.0.1:{host_port}"
    try:
        ok = wait_ready(base, grace=90)
        if not ok:
            print(f"[gate] {image} not ready after 90s — probing anyway",
                  file=sys.stderr)
        runs = [probes.run_all(base), probes.run_all(base)]
        return {"runs": runs, "pulled": pulled}
    finally:
        try:
            cont.stop(timeout=10)
        except Exception:
            pass
        # give the daemon a moment to reap (remove=True) so an immediate
        # re-run doesn't collide on the container name
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                dc.containers.get(cname)
                time.sleep(1)
            except Exception:
                break


# ------------------------------------------------- diff & classification

def _strip_timing(section):
    """Drop timing-noise leaves from a probe section dict (M0 lesson #5:
    sse_first_chunk_ms / sse_chunks_observed are measurement noise; if
    they participate in the stability comparison, a section can flake on
    pure timing luck and get dropped — producing spurious old->null
    diffs that flip verdicts run-to-run). Non-dict sections pass through."""
    if not isinstance(section, dict):
        return section
    return {k: v for k, v in section.items() if k not in TIMING_LEAVES}


def stable_fingerprint(runs: list[dict]) -> tuple[dict, dict]:
    """Merge N probe runs into one fingerprint.

    M0 lessons applied:
    - stability is decided at the SECTION level — a section that is
      unstable (or absent) in either run is excluded entirely from the
      diff (recorded as null in M0 results.json)
    - timing-noise leaves are stripped BEFORE the stability comparison:
      a section must not flake (and flip a verdict) on first-chunk-ms
      rounding luck. This extends M0's reclassify fix (which stripped
      timing leaves from the DIFF) to the stability filter that feeds it.
    - '_meta' is per-probe wall time — always noise, never diffed.

    Returns (stable_fp, flaky_sections) where flaky_sections maps
    section-name -> count of runs it was unstable/absent in.
    """
    stable: dict = {}
    flaky: dict = {}
    sections: set = set()
    for r in runs:
        sections |= set(r.keys())
    for s in sorted(sections):
        if s == "_meta":
            continue
        reps = [_strip_timing(r.get(s)) for r in runs]
        if all(x == reps[0] for x in reps):
            stable[s] = reps[0]
        else:
            flaky[s] = sum(1 for x in reps if x != reps[0])
    return stable, flaky


def normalize(v):
    """Sort lists/dicts so unordered containers compare stably."""
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


def leaf(key: str) -> str:
    return key.rsplit(".", 1)[-1] if "." in key else key


def diff_fps(old_fp: dict, new_fp: dict) -> dict:
    """Diff two stable fingerprints -> {section.leaf: {old, new}}.

    Timing-noise leaves are stripped (never part of the diff)."""
    o, n = {}, {}
    flatten("", old_fp, o)
    flatten("", new_fp, n)
    changed = {}
    for k in sorted(set(o) | set(n)):
        if leaf(k) in TIMING_LEAVES:
            continue
        if normalize(o.get(k)) != normalize(n.get(k)):
            changed[k] = {"old": o.get(k), "new": n.get(k)}
    return changed


def classify(changed: dict) -> str:
    """no-diff | header-SSE-class | unknown — parity with M0 reclassify."""
    if not changed:
        return "no-diff"
    unknown = [k for k in changed
               if not any(leaf(k) == p or leaf(k).startswith(p)
                          for p in KNOWN_LEAVES)]
    return "unknown" if unknown else "header-SSE-class"


def is_known(key: str) -> bool:
    l = leaf(key)
    return any(l == p or l.startswith(p) for p in KNOWN_LEAVES)


def known_classes(changed: dict) -> list[str]:
    """Human-facing class names for the known-class fields in a diff."""
    out = set()
    for k in changed:
        if not is_known(k):
            continue
        l = leaf(k)
        for prefix, cls in LEAF_CLASSES:
            if l == prefix or l.startswith(prefix):
                out.add(cls)
                break
    return sorted(out)


def verdict_from_changed(changed: dict) -> dict:
    """Pure verdict computation from a changed-fields dict — the whole
    gate semantics, unit-testable without docker."""
    cls = classify(changed)
    if cls == "no-diff":
        return {"verdict": "ALLOW", "exit_code": EXIT_ALLOW,
                "class": "no-diff", "known_classes": [],
                "changed_fields": changed, "n_changed": 0}
    if cls == "header-SSE-class":
        return {"verdict": "HOLD", "exit_code": EXIT_HOLD_KNOWN,
                "class": "header-SSE-class",
                "known_classes": known_classes(changed),
                "changed_fields": changed, "n_changed": len(changed)}
    unknown = [k for k in changed if not is_known(k)]
    return {"verdict": "HOLD", "exit_code": EXIT_HOLD_UNKNOWN,
            "class": "unknown", "known_classes": [],
            "unknown_fields": unknown,
            "changed_fields": changed, "n_changed": len(changed)}


# ------------------------------------------------------------- commands

def cmd_baseline(target: str, as_json: bool = False) -> int:
    """`probe-proxy baseline <container>` — record the running service's
    stable fingerprint + image as THE baseline for its name."""
    probe = probe_running_service(target)
    stable, flaky = stable_fingerprint(probe["runs"])
    con = store_open()
    save_baseline(con, probe["service"], probe["image"],
                  probe["digest"], stable)
    con.close()
    out = {"service": probe["service"], "image": probe["image"],
           "digest": probe["digest"], "base": probe["base"],
           "flaky_sections": flaky,
           "note": "double-probe stability filter applied"}
    if as_json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"baseline recorded: {probe['service']}")
        print(f"  image:    {probe['image']} ({probe['digest']})")
        print(f"  sections: {len(stable)} stable"
              + (f", {len(flaky)} unstable (excluded)" if flaky else ""))
    return EXIT_ALLOW


def _pick_service(con, image: str) -> str:
    """If --service not given: the service whose baseline image shares
    the gated image's repository. Errors out when ambiguous."""
    repo = image.rsplit(":", 1)[0]
    cands = []
    for s in all_services(con):
        rec = load_baseline(con, s)
        if rec is not None and rec["image"].rsplit(":", 1)[0] == repo:
            cands.append(s)
    if len(cands) == 1:
        return cands[0]
    if not cands:
        raise SystemExit(
            f"error: no baseline recorded for repository '{repo}'. "
            f"Run: probe-proxy baseline <your-container> first, or "
            f"pass --service explicitly.")
    raise SystemExit(
        f"error: multiple baselines share repository '{repo}' "
        f"({', '.join(cands)}); pass --service to disambiguate.")


def _parse_env(items: list[str]) -> dict:
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"error: --env expects K=V, got '{it}'")
        k, v = it.split("=", 1)
        out[k] = v
    return out


def cmd_gate(image: str, service: str | None = None,
             port: int = 80, env: dict | None = None,
             cap_add: list | None = None,
             as_json: bool = False) -> int:
    """`probe-proxy gate <image:tag> [--service NAME] [--port N]
    [--env K=V ...] [--cap-add CAP]` — pull the new image, double-probe
    it in a throwaway container, diff against the stored baseline,
    print verdict. Returns the gate exit code.

    NOTE: for a stateful service, `probe-proxy baseline <container>`
    records the fingerprint of the RUNNING (stateful) instance. Gating
    the same image in a bare throwaway will then HOLD on state/env
    differences, not image differences. For such services, pass the
    same env (--env) the compose file gives the service (and --port if
    it listens elsewhere than 80) so the throwaway matches the
    baseline's environment.
    """
    dc = docker.from_env()
    con = store_open()

    svc = service if service is not None else _pick_service(con, image)
    base_rec = load_baseline(con, svc)
    if base_rec is None:
        con.close()
        raise SystemExit(
            f"error: no baseline recorded for service '{svc}'. "
            f"Run: probe-proxy baseline <container> first.")
    con.close()

    print(f"[gate] baseline: {svc} = {base_rec['image']} "
          f"({base_rec['digest']})", file=sys.stderr)
    print(f"[gate] gating new image: {image}", file=sys.stderr)

    new = probe_new_image(dc, image, run_id=int(time.time()) % 100000,
                          port=port, env=env, cap_add=cap_add)
    new_stable, new_flaky = stable_fingerprint(new["runs"])

    changed = diff_fps(base_rec["fingerprint"], new_stable)
    verdict = verdict_from_changed(changed)
    result = {
        "service": svc,
        "baseline_image": base_rec["image"],
        "baseline_digest": base_rec["digest"],
        "new_image": image,
        "pulled": new["pulled"],
        "probe_port": port,
        "probe_env": sorted((env or {}).keys()),
        "flaky_sections": new_flaky,
        **verdict,
    }
    if as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\nVERDICT: {verdict['verdict']}"
              + (f" — {verdict['class']}" if verdict["class"] != "no-diff"
                 else ""))
        print(f"  service:  {svc}")
        print(f"  baseline: {base_rec['image']}")
        print(f"  new:      {image}")
        if verdict["class"] == "header-SSE-class":
            print(f"  changed fields ({verdict['n_changed']}) in known "
                  f"classes: {', '.join(verdict['known_classes'])}")
            for k, v in changed.items():
                print(f"    {k}: {str(v['old'])[:40]} -> "
                      f"{str(v['new'])[:40]}")
        elif verdict["class"] == "unknown":
            print(f"  UNCLASSIFIED changes: "
                  f"{', '.join(verdict['unknown_fields'])}")
            for k, v in changed.items():
                print(f"    {k}: {str(v['old'])[:40]} -> "
                      f"{str(v['new'])[:40]}")
        else:
            print("  no stable behavioral diff")
    return verdict["exit_code"]
