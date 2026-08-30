"""probe-proxy CLI — Milestone 0 skeleton.

Usage:
  probe-proxy matrix                 # run full M0 matrix over catalog apps
  probe-proxy run <name-or-url>      # run probe suite against one app/url
  probe-proxy synthesize <fingerprint>  # stub (later milestone)
  probe-proxy replay <config>        # stub (later milestone)
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

from . import probes
from . import synthesize

DB = Path(__file__).resolve().parent.parent / "probe_results.db"


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
    """M0 scaffold: the real product metric — how many hand-edits a user
    still makes after accepting a generated config. Call this whenever a
    user reports/accepts an edit."""
    con = store_open()
    con.execute("INSERT INTO hand_edits VALUES (?,?,?)",
                (config_path, edits, time.time()))
    con.commit()


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


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    cmd, *args = argv
    if cmd == "matrix" or cmd == "matrix_retry":
        cmd_matrix()
    elif cmd == "run":
        cmd_run(args[0])
    elif cmd == "synthesize":
        fp = json.loads(Path(args[0]).read_text())
        out = synthesize.synthesize(fp, args[1] if len(args) > 1 else "app:80")
        print(out["caddyfile"])
        for w in out["warnings"]:
            print(f"# WARNING: {w}", file=sys.stderr)
    elif cmd == "replay":
        from . import replay
        replay.run()
    elif cmd == "replay_retry":
        from . import replay
        replay.run()
    elif cmd == "replay_report":
        from . import report
        report.main()
    elif cmd == "record-edits":
        count_hand_edit(args[0], int(args[1]))
        print("recorded")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
