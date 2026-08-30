"""Milestone 1 — replay report: per-app replay table -> REPLAY.md."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPLAY_DIR = HERE / "replay"
REPORT = HERE / "REPLAY.md"


def main():
    results = json.loads((REPLAY_DIR / "replay.json").read_text())
    apps = [k for k in results if k != "httpbin"]
    zero = [a for a in apps if results[a].get("zero_diff")]
    n_zero, n = len(zero), len(apps)
    verdict = "PASSED (>=5/10 zero-diff)" if n_zero >= 5 else "KILL (<5/10)"

    lines = ["# probe-proxy Milestone 1 — Replay-Verify Report", "",
             f"Apps replayed: {n}. Result: **{n_zero}/{n} zero-diff — {verdict}**",
             "", "Each app: probes run DIRECT to the container vs THROUGH the "
             "synthesized Caddy config; up to 3 synthesis iterations.", "",
             "| app | ready | iters | final diffs | zero-diff |",
             "|---|---|---|---|---|"]
    for a in apps:
        r = results[a]
        if "error" in r:
            lines.append(f"| {a} | ? | - | ERROR: {r['error'][:60]} | no |")
            continue
        iters = len(r["iterations"])
        nd = len(r["diffs"])
        lines.append(f"| {a} | {'yes' if r['ready'] else 'NO'} | {iters} | "
                     f"{nd} | {'YES' if r['zero_diff'] else 'no'} |")

    lines += ["", "## Residual diffs (apps not zero-diff)", ""]
    for a in apps:
        r = results[a]
        if r.get("zero_diff") or "error" in r:
            continue
        lines.append(f"### {a} — {len(r['diffs'])} diffs after "
                     f"{len(r['iterations'])} iteration(s)")
        lines.append("")
        lines.append("| probe | key | direct | via config |")
        lines.append("|---|---|---|---|")
        for d in r["diffs"]:
            lines.append(f"| {d['probe']} | {d['key']} | "
                         f"{str(d['direct'])[:40]} | {str(d['via'])[:40]} |")
        if r.get("warnings"):
            lines.append("")
            lines.append("Warnings: " + "; ".join(r["warnings"]))
        lines.append("")

    lines += ["## Synthesized configs", "",
              "One Caddyfile per app under `replay/Caddyfile.<app>`; the "
              "exact configs replayed, zero-diff or not.", "",
              "## Warnings emitted by synthesis (policy-not-behavior "
              "degradation)", ""]
    for a in apps:
        for w in results[a].get("warnings", []):
            lines.append(f"- {a}: {w}")

    REPORT.write_text("\n".join(lines) + "\n")
    print(f"{n_zero}/{n} zero-diff — {verdict}")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
