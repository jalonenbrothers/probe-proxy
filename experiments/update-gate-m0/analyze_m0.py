"""M0 analysis: per-jump table, kill-bar verdict, diff-class breakdown,
and the probe-diff x keyword-scan conditional-precision cross-tab."""
from __future__ import annotations

import json
from pathlib import Path

import corpus

HERE = Path(__file__).parent
res = json.loads((HERE / "results.json").read_text())
kw = json.loads((HERE / "keyword_results.json").read_text())

rows = []
for j in corpus.JUMPS:
    key = f"{j['app']}|{j['old']}|{j['new']}"
    r = res.get(key)
    if not r:
        continue
    k = kw.get(key, {"flags_all": 0, "flags_strong": 0})
    rows.append(dict(j, probe_diff=r["diff"], n_changed=r["n_changed"],
                     diff_class=r["diff_class"],
                     kw_all=k["flags_all"] > 0,
                     kw_strong=k["flags_strong"] > 0,
                     old_ready=r["old_ready"], new_ready=r["new_ready"],
                     flaky=bool(r["flaky_old"] or r["flaky_new"]),
                     changed=r["changed_fields"]))

n = len(rows)
diffs = [r for r in rows if r["probe_diff"]]
majors = [r for r in rows if r["cls"] == "major"]
major_diffs = [r for r in diffs if r["cls"] == "major"]
strict = [r for r in rows if r["strict"]]
strict_diffs = [r for r in diffs if r["strict"]]
flaky = [r for r in rows if r["flaky"]]
not_ready = [r for r in rows if not (r["old_ready"] and r["new_ready"])]

print(f"=== M0 corpus: {n}/32 jumps probed ===")
print(f"any-diff:                {len(diffs)}/{n} = {100*len(diffs)/n:.0f}%")
print(f"major-class jumps:       {len(majors)}, with diff: {len(major_diffs)} "
      f"({100*len(major_diffs)/max(1,len(majors)):.0f}%)")
print(f"strict-semver-major:     {len(strict)}, with diff: {len(strict_diffs)}")
print(f"flaky-field jumps:      {len(flaky)} (nondeterminism evidence)")
print(f"not-ready images:       {len(not_ready)}")

# kill bar: <20% of jumps produce ANY fingerprint diff -> KILL
rate = len(diffs) / n if n else 0
verdict = "KILL" if rate < 0.20 else "PASS"
print(f"\nKILL BAR: any-diff rate {100*rate:.0f}% (kill if <20%) -> {verdict}")
# nondeterminism: flaky fields exist but are excluded; gate viability needs
# the STABLE diff signal. Report flaky rate as secondary kill evidence.

print("\n=== Per-jump table ===")
print(f"{'app':14s} {'old':>12s} {'new':<12s} {'cls':6s} {'diff':4s} "
      f"{'n':>3s} {'class':16s} {'kwA':4s} {'kwS':4s} flaky")
for r in rows:
    print(f"{r['app']:14s} {r['old']:>12s} {r['new']:<12s} {r['cls']:6s} "
          f"{'YES' if r['probe_diff'] else 'no':4s} {r['n_changed']:>3d} "
          f"{r['diff_class']:16s} {'F' if r['kw_all'] else '.':4s} "
          f"{'F' if r['kw_strong'] else '.':4s} {'*' if r['flaky'] else ''}")

# diff-class breakdown (critic condition c)
print("\n=== Diff-class breakdown ===")
for cls in ("no-diff", "header-SSE-class", "unknown"):
    c = sum(1 for r in rows if r["diff_class"] == cls)
    print(f"  {cls:18s} {c}/{n}")

# ---------------------------------------------------------------- cross-tab
def crosstab(flag_key: str, label: str):
    flag = [r for r in rows if r[flag_key]]
    noflag = [r for r in rows if not r[flag_key]]
    fd = [r for r in flag if r["probe_diff"]]
    nd = [r for r in noflag if r["probe_diff"]]
    print(f"\n=== Cross-tab vs keyword channel: {label} ===")
    print(f"{'':18s} probe-diff   no-diff   | total")
    print(f"{'flagged':18s} {len(fd):>10d} {len(flag)-len(fd):>9d} | {len(flag)}")
    print(f"{'not flagged':18s} {len(nd):>10d} {len(noflag)-len(nd):>9d} | {len(noflag)}")
    p_flag = len(fd) / len(flag) if flag else float("nan")
    p_noflag = len(nd) / len(noflag) if noflag else float("nan")
    base = len(diffs) / n if n else 0
    print(f"P(diff | flag)      = {p_flag:.2f}  ({len(fd)}/{len(flag)})")
    print(f"P(diff | no flag)  = {p_noflag:.2f}  ({len(nd)}/{len(noflag)})")
    print(f"P(diff) baseline   = {base:.2f}")
    print(f"lift = {p_flag/base:.2f}x" if base else "n/a")

crosstab("kw_all", "any keyword (soft or strong)")
crosstab("kw_strong", "strong keywords only (breaking/migration/action-required)")

# changed-field inventory: which probe fields actually move across jumps
print("\n=== Changed-field inventory (all diff jumps) ===")
inv = {}
for r in diffs:
    for k in r["changed"]:
        inv[k] = inv.get(k, 0) + 1
for k, c in sorted(inv.items(), key=lambda x: -x[1]):
    print(f"  {c:>2d}x {k}")

(HERE / "analysis.json").write_text(json.dumps(rows, indent=2))
print("\nrows -> analysis.json")