"""Cross-tab with CORRECTED probe-diff verdicts (timing noise stripped):
probe-diff = n_changed_excl_timing > 0 (reclassified), vs keyword flags.
Also re-derives conditional precision per keyword channel.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
rows = json.loads((HERE / "analysis.json").read_text())

for r in rows:
    r["probe_diff_fixed"] = r["n_changed_excl_timing"] > 0

n = len(rows)
diffs = [r for r in rows if r["probe_diff_fixed"]]
majors = [r for r in rows if r["cls"] == "major"]
major_diffs = [r for r in diffs if r["cls"] == "major"]

print(f"corrected any-diff rate: {len(diffs)}/{n} = {100*len(diffs)/n:.0f}%")
print(f"major-class: {len(majors)} jumps, {len(major_diffs)} with diff "
      f"({100*len(major_diffs)/len(majors):.0f}%)")
print(f"patch-class: {n-len(majors)} jumps, "
      f"{len(diffs)-len(major_diffs)} with diff")

base = len(diffs) / n
for flag_key, label in [("kw_all", "any keyword"),
                        ("kw_strong", "strong keywords")]:
    flag = [r for r in rows if r[flag_key]]
    noflag = [r for r in rows if not r[flag_key]]
    fd = [r for r in flag if r["probe_diff_fixed"]]
    nd = [r for r in noflag if r["probe_diff_fixed"]]
    p_flag = len(fd) / len(flag) if flag else float("nan")
    p_noflag = len(nd) / len(noflag) if noflag else float("nan")
    print(f"\n[{label}]")
    print(f"  flagged:        {len(fd)}/{len(flag)} diff  P(diff|flag)={p_flag:.2f}")
    print(f"  not flagged:   {len(nd)}/{len(noflag)} diff P(diff|noflag)={p_noflag:.2f}")
    print(f"  baseline P(diff)={base:.2f}  lift={p_flag/base:.2f}x")

# diff-class x keyword: what does a flag predict about the CLASS?
print("\n[diff class | strong flag] on diff jumps")
for cls in ("header-SSE-class", "unknown"):
    flagged = sum(1 for r in diffs if r["diff_class_fixed"] == cls and r["kw_strong"])
    total = sum(1 for r in diffs if r["diff_class_fixed"] == cls)
    print(f"  {cls:18s} {flagged}/{total} flagged strong")