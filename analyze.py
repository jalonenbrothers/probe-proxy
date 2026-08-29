"""Analyze matrix.json: build the probe x app grid and compute the
distinguishability verdict.

An app is *distinguishable* if its fingerprint vector differs from every
other app's on at least one probe value. The M0 kill condition:
<8 of 10 apps distinguishable -> synthesis has nothing to synthesize from.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
MATRIX = HERE / "matrix.json"
REPORT = HERE / "MATRIX.md"


def fingerprint_vector(fp: dict) -> dict:
    """Flatten a fingerprint into probe->value strings (errors collapse)."""
    vec = {}
    for probe, kv in fp.items():
        if probe.startswith("_") or not isinstance(kv, dict):
            continue
        if "error" in kv:
            vec[probe] = "ERROR"
            continue
        vec[probe] = json.dumps(kv, sort_keys=True, default=str)
    return vec


def main():
    fps = json.loads(MATRIX.read_text())
    apps = [a for a in fps if a != "httpbin"]  # httpbin = sanity target
    vecs = {a: fingerprint_vector(fps[a]) for a in apps}
    probes = sorted({p for v in vecs.values() for p in v})

    # distinguishable = unique among all other apps' vectors
    distinct = {}
    for a in apps:
        distinct[a] = all(vecs[a] != vecs[b] for b in apps if b != a)

    # per-probe discriminative power: number of distinct value-classes
    probe_power = {}
    for p in probes:
        vals = [vecs[a].get(p, "MISSING") for a in apps]
        probe_power[p] = len(set(vals))

    n_distinct = sum(distinct.values())
    verdict = "DISTINGUISHABLE (>=8/10)" if n_distinct >= 8 else "KILL (<8/10)"

    # ---- write MATRIX.md
    lines = ["# probe-proxy Milestone 0 — Probe-Coverage Matrix", "",
             f"Apps probed: {len(apps)} (+ httpbin sanity target). "
             f"Result: **{n_distinct}/{len(apps)} distinguishable — {verdict}**", ""]
    lines += ["## Distinguishability verdict", "",
              "| app | distinguishable |", "|---|---|"]
    for a in apps:
        lines.append(f"| {a} | {'YES' if distinct[a] else 'no'} |")
    lines += ["", "## Probe discriminative power (distinct value-classes across apps)",
              "", "| probe | classes |", "|---|---|"]
    for p in sorted(probe_power, key=probe_power.get, reverse=True):
        lines.append(f"| {p} | {probe_power[p]} |")
    lines += ["", "## Fingerprint grid (key value per probe x app)", ""]
    # compact grid: pick the first scalar key of each probe for readability
    hdr = ["probe"] + apps
    lines += ["| " + " | ".join(hdr) + " |",
              "|" + "---|" * len(hdr)]
    for p in probes:
        row = [p]
        for a in apps:
            v = vecs[a].get(p, "MISSING")
            row.append(v.replace("|", "\\|")[:60])
        lines.append("| " + " | ".join(row) + " |")
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"{n_distinct}/{len(apps)} distinguishable — {verdict}")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
