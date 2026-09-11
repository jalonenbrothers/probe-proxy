"""probe-proxy CLI — Milestone 2 + update-gate² (M1).

Usage:
  probe-proxy <container-name> [--json]     # end-to-end: probe -> synthesize
                                            # -> replay-verify (<=3 iters)
                                            # -> print Caddy block + report
  probe-proxy <http://host:port> [--json]   # same, against a running URL
  probe-proxy verify <config-file> [--json] # re-run replay against a user's
                                            # EXISTING Caddyfile; report drift
                                            # from generated block + broken
                                            # probes (hand-edit counter)
  probe-proxy matrix                        # run full M0 matrix over catalog
  probe-proxy run <name-or-url>             # probe suite only
  probe-proxy baseline <container> [--json] # update-gate²: record the running
                                            # service's stable fingerprint
  probe-proxy gate <image:tag> [--service NAME] [--port N]
                       [--env K=V ...] [--cap-add CAP] [--json]
                                            # update-gate²: pull new image,
                                            # double-probe in a throwaway
                                            # container, diff vs baseline.
                                            # exit 0 ALLOW / 2 HOLD known /
                                            # 3 HOLD unknown / 1 error
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

from . import probes
from . import synthesize
from .paths import repo_file

DB = repo_file("probe_results.db")


def store_open():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS probe_results (
        app TEXT, probe TEXT, key TEXT, value TEXT, ts REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS hand_edits (
        config_path TEXT, edit_count INTEGER, ts REAL)""")
    return con


def store_fingerprint(con, app: str, fp: dict):
    ts = time.time()
    for probe, kv in fp.items():
        if probe == "_meta":
            continue
        if not isinstance(kv, dict):
            kv = {"value": kv}
        for k, v in kv.items():
            con.execute("INSERT INTO probe_results VALUES (?,?,?,?,?)",
                        (app, probe, k, json.dumps(v, default=str), ts))
    con.commit()


def count_hand_edit(config_path: str, edits: int):
    """M0 scaffold, now real (M2): `verify` writes a row per drift run."""
    con = store_open()
    con.execute("INSERT INTO hand_edits VALUES (?,?,?)",
                (config_path, edits, time.time()))
    con.commit()
    con.close()


def run_against_url(base: str, label: str) -> dict:
    fp = probes.run_all(base.rstrip("/"))
    con = store_open()
    store_fingerprint(con, label, fp)
    con.close()
    return fp


def cmd_matrix():
    from . import matrix
    matrix.run()


def cmd_run(target: str):
    if target.startswith("http://") or target.startswith("https://"):
        fp = run_against_url(target, "adhoc")
    else:
        from . import matrix
        fp = matrix.run_single(target)
    print(json.dumps(fp, indent=2, default=str))


# ---------------------------------------------------------------- M2: e2e

def _target_parts(target: str):
    """Resolve a target into (upstream, host_port, app_or_None, clean)."""
    import docker
    from docker.errors import NotFound, APIError
    if target.startswith(("http://", "https://")):
        return target, None, None, target
    dc = docker.from_env()
    try:
        cont = dc.containers.get(target)
    except NotFound:
        # maybe a compose service: match by label
        for c in dc.containers.list():
            labels = (c.labels or {})
            svc = labels.get("com.docker.compose.service")
            proj = labels.get("com.docker.compose.project", "")
            if svc == target or f"{proj}-{svc}" == target:
                cont = c
                break
        else:
            raise SystemExit(
                f"error: container or compose service '{target}' not found "
                f"or not running.\nStart it first, or target a URL: "
                f"probe-proxy http://host:port")
    host_port = None
    app_port = None
    for p, binds in (cont.attrs["NetworkSettings"]["Ports"] or {}).items():
        if binds and binds[0].get("HostPort") and p.endswith("/tcp"):
            app_port = int(p.split("/")[0])
            host_port = int(binds[0]["HostPort"])
            break
    if app_port is None:
        # no published port: we can still synthesize from container ports
        # metadata, but probing direct needs a published port — error later.
        app_port = 80
    upstream = f"{cont.name}:{app_port}"
    return (upstream, host_port, cont, target)


def cmd_e2e(target: str, as_json: bool = False):
    """Single end-to-end run: probe -> synthesize -> replay-verify."""
    from . import replay as replay_mod
    import docker

    upstream, host_port, cont, label = _target_parts(target)
    dc = docker.from_env()

    if host_port is None or cont is None:
        raise SystemExit(
            f"error: container '{target}' has no published HTTP port; "
            f"probe-proxy needs to reach it (publish a port or target a URL).")

    # caddy must share a user-defined network with the app (container-name
    # DNS does not work on the default bridge)
    import uuid
    net = dc.networks.create(f"probe-proxy-e2e-{uuid.uuid4().hex[:6]}",
                             driver="bridge")
    app_connected = False
    try:
        net.connect(cont.id)
        app_connected = True
    except Exception:
        pass
    if not app_connected:
        try:
            net.remove()
        except Exception:
            pass
        raise SystemExit(
            f"error: could not attach '{target}' to a probe network.")

    direct_base = f"http://127.0.0.1:{host_port}"
    print(f"[*] probing {label} at {direct_base} ...", file=sys.stderr)
    direct = probes.run_all(direct_base)

    synth = synthesize.synthesize(direct, upstream)
    params, warnings = synth["params"], list(synth["warnings"])

    print(f"[*] synthesized config ({len(params)} params); replay-verifying...",
          file=sys.stderr)
    try:
        result = replay_mod.replay_against(dc, net.name, direct_base, direct,
                                           upstream, params, warnings, label)
    finally:
        try:
            net.disconnect(cont.id)
        except Exception:
            pass
        try:
            net.remove()
        except Exception:
            pass

    caddyfile = result["caddyfile"]
    # save the generated block so `verify` can later check drift
    out_file = Path(f"{target.replace('/', '_')}.Caddyfile")
    out_file.write_text(caddyfile)
    if as_json:
        out = {"target": target, "upstream": upstream,
               "params": params, "warnings": warnings,
               "iterations": len(result["history"]),
               "diffs": result["diffs"], "zero_diff": result["zero_diff"],
               "caddyfile": caddyfile, "saved_to": str(out_file)}
        print(json.dumps(out, indent=2, default=str))
        return

    # human report
    print(f"\n=== Caddy block for {target} ===\n")
    print(caddyfile)
    print(f"(saved to {out_file})")
    print("=== verification report ===")
    print(f"probes direct:   {direct_base}")
    print(f"probes via:      synthesized config (Caddy, same network)")
    print(f"iterations:      {len(result['history'])}")
    print(f"final diffs:     {len(result['diffs'])}")
    print(f"zero-diff:       {'YES — config preserves observed behavior' if result['zero_diff'] else 'NO'}")
    if result["diffs"]:
        print("\nresidual diffs:")
        for d in result["diffs"]:
            print(f"  {d['probe']}.{d['key']}: direct={str(d['direct'])[:40]} "
                  f"via={str(d['via'])[:40]}")
    if warnings:
        print("\nwarnings (policy-not-behavior degradation):")
        for w in warnings:
            print(f"  - {w}")
    print("\n# paste the block above into your Caddyfile, then later run:")
    print(f"#   probe-proxy verify <your-Caddyfile>")


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    # option parsing for gate (pull name/value pairs out before dispatch)
    service = None
    port = 80
    env_items: list[str] = []
    cap_add: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--service":
            if i + 1 >= len(argv):
                print("usage: probe-proxy gate <image:tag> --service NAME")
                return 1
            service = argv[i + 1]
            del argv[i:i + 2]
        elif a == "--port":
            if i + 1 >= len(argv):
                print("usage: probe-proxy gate <image:tag> --port N")
                return 1
            port = int(argv[i + 1])
            del argv[i:i + 2]
        elif a == "--env":
            if i + 1 >= len(argv):
                print("usage: probe-proxy gate <image:tag> --env K=V")
                return 1
            env_items.append(argv[i + 1])
            del argv[i:i + 2]
        elif a == "--cap-add":
            if i + 1 >= len(argv):
                print("usage: probe-proxy gate <image:tag> --cap-add CAP")
                return 1
            cap_add.append(argv[i + 1])
            del argv[i:i + 2]
        else:
            i += 1
    cmd, *args = argv
    if cmd == "matrix" or cmd == "matrix_retry":
        cmd_matrix()
    elif cmd == "run":
        cmd_run(args[0])
    elif cmd == "verify":
        if not args:
            print("usage: probe-proxy verify <config-file>")
            return 1
        from . import verify
        return verify.main(args[0], as_json=as_json)
    elif cmd in ("replay", "replay_retry"):
        from . import replay
        replay.run()
    elif cmd == "baseline":
        # update-gate²: record the running service's gate baseline
        if not args:
            print("usage: probe-proxy baseline <container> [--json]")
            return 1
        from . import gate
        return gate.cmd_baseline(args[0], as_json=as_json)
    elif cmd == "baseline-m2":
        # M2 honest-baseline experiment suite (moved here; `baseline`
        # now belongs to the update-gate)  — run_baseline.sh calls this
        from . import baseline
        baseline.run(args or None)
    elif cmd == "gate":
        if not args:
            print("usage: probe-proxy gate <image:tag> [--service NAME] "
                  "[--port N] [--env K=V ...] [--cap-add CAP] [--json]")
            return 1
        from . import gate
        return gate.cmd_gate(args[0], service=service, port=port,
                             env=gate._parse_env(env_items),
                             cap_add=cap_add or None, as_json=as_json)
    elif cmd == "replay_report":
        from . import report
        report.main()
    elif cmd == "record-edits":
        count_hand_edit(args[0], int(args[1]))
        print("recorded")
    elif cmd in ("synthesize",):
        fp = json.loads(Path(args[0]).read_text())
        out = synthesize.synthesize(fp, args[1] if len(args) > 1 else "app:80")
        print(out["caddyfile"])
        for w in out["warnings"]:
            print(f"# WARNING: {w}", file=sys.stderr)
    elif cmd.startswith(("http://", "https://")) or not cmd.startswith("-"):
        # end-to-end default: probe-proxy <container-or-service>
        try:
            cmd_e2e(cmd, as_json=as_json)
        except SystemExit:
            raise
        except Exception as e:
            print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
