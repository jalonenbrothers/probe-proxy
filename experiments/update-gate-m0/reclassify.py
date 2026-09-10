"""Corrected diff-class reclassification (run_corpus.py bug: known_prefixes and
TIMING_KEYS were compared against bare leaf names, but flattened fingerprint
keys carry section prefixes like 'sse.sse_content_type' — so every diff was
misclassed 'unknown' and timing-noise fields leaked into changed_fields).

This script recomputes, from the stored changed_fields:
  - n_changed_excl_timing (timing keys properly stripped)
  - diff_class_fixed (header-SSE-class vs unknown, prefix-aware)
and prints the corrected breakdown. Does NOT touch the raw corpus.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
rows = json.loads((HERE / "analysis.json").read_text())

TIMING_LEAVES = {"sse_first_chunk_ms", "sse_chunks_observed"}
KNOWN_LEAVES = (
    "root_", "xfp_", "xfh_", "cookie_", "set_cookie",
    "sse_content_type", "sse_streamed", "sse_gaps_ge_50ms",
    "sse_max_gap_ms",  # SSE streaming behavior = proxy-relevant
    "compression",
    "options_allow", "path_statuses", "well_known",
    "redirect_", "tls_redirect", "post10mb", "post10mb_len_header",
    "post10mb_status", "propfind_status", "websocket", "root_status",
)


def leaf(key: str) -> str:
    return key.rsplit(".", 1)[-1] if "." in key else key


def classify_fixed(changed: dict) -> str:
    real = {k: v for k, v in changed.items()
            if leaf(k) not in TIMING_LEAVES and k != "_container_ready"}
    if not real:
        return "no-diff"
    unknown = [k for k in real
               if not any(leaf(k) == p or leaf(k).startswith(p)
                          for p in KNOWN_LEAVES)]
    return "unknown" if unknown else "header-SSE-class"


print(f"{'app':14s} {'old':>12s} {'new':<12s} {'cls':6s} "
      f"{'n':>3s} {'n*':>3s} {'class_old':16s} class_fixed")
flips = 0
for r in rows:
    changed = r["changed"]
    n_excl = sum(1 for k in changed
                 if leaf(k) not in TIMING_LEAVES and k != "_container_ready")
    cls = classify_fixed(changed)
    # does the diff VERDICT flip when timing keys are stripped?
    flip = (r["probe_diff"] and cls == "no-diff")
    flips += flip
    print(f"{r['app']:14s} {r['old']:>12s} {r['new']:<12s} {r['cls']:6s} "
          f"{r['n_changed']:>3d} {n_excl:>3d} {r['diff_class']:16s} {cls}"
          f"{'  <-- VERDICT FLIP' if flip else ''}")

print(f"\nverdict flips (diff -> no-diff after timing strip): {flips}")
for label, pred in [
    ("no-diff", lambda c: c == "no-diff"),
    ("header-SSE-class (known/proxy-relevant)", lambda c: c == "header-SSE-class"),
    ("unknown", lambda c: c == "unknown"),
]:
    n = sum(1 for r in rows if pred(classify_fixed(r["changed"])))
    print(f"  {label:40s} {n}/{len(rows)}")

# persist corrected fields back into analysis.json
for r in rows:
    r["n_changed_excl_timing"] = sum(
        1 for k in r["changed"]
        if leaf(k) not in TIMING_LEAVES and k != "_container_ready")
    r["diff_class_fixed"] = classify_fixed(r["changed"])
(HERE / "analysis.json").write_text(json.dumps(rows, indent=2))
print("analysis.json updated with *_fixed fields")