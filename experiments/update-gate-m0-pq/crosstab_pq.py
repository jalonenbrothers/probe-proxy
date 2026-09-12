"""pq-gate M0 cross-tab: live-negotiation-diff vs static-CBOM-diff over the
SAME 20 jumps. This is the concept's genuine delta — data nobody has.

Cells:
  live\static   diff        no-diff
  diff          both-see    live-only   (live sees what static misses)
  no-diff       static-only static-blind (CBOM noise without live change)

Kill bar (critic): <10% of jumps crypto-visible live AND none of the
diffs decision-relevant -> concept collapses to update-gate2 + testssl.sh.
Decision-relevance: a diff that would change an HNDL/compat decision =
kex group set changed (esp. PQ hybrid added/removed), TLS version set
changed, cipher set changed, cert key type/sig changed.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent

CRYPTO_KEYS = {"tls_versions", "tls_version", "groups_accepted",
              "cipher_suite", "cert_key_type", "cert_key_bits",
              "cert_sig_alg"}
PQ_GROUPS = {"X25519MLKEM768", "X25519Kyber768Draft00"}


def load(p, default):
    f = HERE / p
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return default


def main():
    live = load("results_pq.json", {})
    stat = load("results_acdi.json", {})

    keys = sorted(set(live) & set(stat))
    rows = []
    for k in keys:
        L, S = live[k], stat[k]
        live_diff = L.get("diff") and L.get("diff_class") == "crypto-visible"
        static_diff = bool(S.get("static_diff"))
        # decision-relevance of live diff
        dec = []
        cf = L.get("changed_fields", {})
        for field, change in cf.items():
            if field in ("groups_accepted", "groups_added", "groups_removed"):
                old_s, new_s = set(change.get("old", [])), set(change.get("new", []))
                pqs_add = PQ_GROUPS & (new_s - old_s)
                pqs_rem = PQ_GROUPS & (old_s - new_s)
                if pqs_add:
                    dec.append(f"PQ kex ADDED {sorted(pqs_add)}")
                if pqs_rem:
                    dec.append(f"PQ kex REMOVED {sorted(pqs_rem)}")
            elif field == "tls_versions":
                dec.append(f"TLS version set {change['old']} -> {change['new']}")
            elif field == "cipher_suite":
                dec.append(f"cipher {change['old']} -> {change['new']}")
            elif field in ("cert_key_type", "cert_key_bits", "cert_sig_alg"):
                dec.append(f"cert {field} {change['old']} -> {change['new']}")
        rows.append({
            "jump": k, "app": L.get("app"),
            "live_diff": live_diff, "static_diff": static_diff,
            "cell": ("both" if live_diff and static_diff else
                     "live-only" if live_diff else
                     "static-only" if static_diff else "neither"),
            "decision_relevant": dec,
        })

    n = len(rows)
    both = sum(1 for r in rows if r["cell"] == "both")
    lo = sum(1 for r in rows if r["cell"] == "live-only")
    so = sum(1 for r in rows if r["cell"] == "static-only")
    neither = sum(1 for r in rows if r["cell"] == "neither")
    live_pct = 100 * (both + lo) / n if n else 0
    dec_any = [r for r in rows if r["decision_relevant"]]

    print(f"cross-tab over {n} jumps (live x static)")
    print(f"  both-see      : {both}")
    print(f"  live-only     : {lo}  <- concept's delta")
    print(f"  static-only   : {so}  <- acdi sees, live missed")
    print(f"  neither       : {neither}")
    print(f"  live crypto-visible rate: {both+lo}/{n} = {live_pct:.0f}%")
    print(f"  decision-relevant live diffs: {len(dec_any)}")
    for r in dec_any:
        print(f"    {r['jump']}: {'; '.join(r['decision_relevant'])}")
    out = {"n": n, "both": both, "live_only": lo, "static_only": so,
           "neither": neither, "live_rate_pct": round(live_pct, 1),
           "decision_relevant": dec_any, "rows": rows}
    (HERE / "crosstab_pq.json").write_text(json.dumps(out, indent=2))
    print("written crosstab_pq.json")
    # kill-bar verdict
    if live_pct < 10 and not dec_any:
        print("VERDICT: KILL — kill bar met (concept collapses to "
              "update-gate2 + testssl.sh)")
    else:
        print("VERDICT: SURVIVES this corpus — kill bar not met")


if __name__ == "__main__":
    main()
