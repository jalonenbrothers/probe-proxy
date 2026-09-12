# pq-gate M0 — crypto-negotiation probe + cross-tab disproof corpus (IDEA-11)

Experiment: `experiments/update-gate-m0-pq/` in the probe-proxy repo
(github.com/jalonenbrothers/probe-proxy).

## What it is

The smallest experiment capable of disproving IDEA-11 **pq-gate**: a
pre-promote gate that runs the NEW image of a version jump in a
throwaway container and fingerprints what its TLS stack *actually
negotiates* with a pinned, PQ-hybrid-capable probe client — then asks:
does this ever see crypto changes that (a) happen at all, and (b) that
a static CBOM diff of the same images misses?

## Hypothesis under test (the killer assumption)

> Real-world container version jumps produce crypto-visible TLS
> negotiation changes often enough (≥10% of jumps), and at least some
> are invisible to static CBOM scanning, such that a live-negotiation
> gate adds decision-relevant signal beyond update-gate² + testssl.sh /
> static CBOM tooling.

Kill bar (critic, binding): <10% of jumps produce any crypto-visible
negotiation diff AND none of the diffs would change an HNDL/compat
decision → concept collapses to update-gate² + testssl.sh.

## Mechanism (critic binding conditions, all honored)

- **PRE-PROMOTE** framing: the NEW image runs in a throwaway container
  (`docker run --rm`, label `probe-proxy=pqgate`) and is probed live;
  nothing is pulled into the running stack.
- **PINNED probe client**: `tlsprobe` — a static Go binary
  (CGO_ENABLED=0, built in golang:1.24-alpine, `tlsprobe.go` +
  `build.sh`). Host OpenSSL 3.0 (classical-only) is never used; the
  probe client itself offers X25519MLKEM768 so PQ-hybrid acceptance is
  visible. Fail-closed: probe error → HOLD, never ALLOW.
- **Fingerprint** (per image, double-probed; only values identical
  across both probes count — M0/M1 stability discipline):
  TLS versions accepted, kex groups accepted (enumerated via forced
  single-group handshakes, PQ hybrids included), negotiated cipher
  suite + TLS version, cert key type/bits/sig alg, ALPN, OCSP/SCT.
  Kex preference ORDER is not captured (Go client-side limitation,
  documented honestly).
- **Env parity**: identical fixed probe cert, env vars, and TLS-enable
  scripts for old and new image of every jump.
- **Static leg**: pinned acdi v0.5.2 (static musl binary) scans the
  extracted rootfs of both images (docker create + export; absolute
  symlink members skipped — path aliases, not crypto material), then
  `acdi diff` gives the static CBOM delta for the same jump.

## Corpus

20 real version jumps reused from the shipped update-gate² M0 corpus
(t_cf1c5836), restricted to apps with container-start-configurable
native TLS: vaultwarden (Rocket), gitea (Go net/http), grafana (Go
net/http), nextcloud (Apache/mod_ssl), homeassistant (aiohttp).
Pihole v6 and uptime-kuma excluded (documented in corpus_pq.py).
All 20 jumps are major-class; 10 strict-major.

## How to run

    # live-negotiation leg (needs docker + repo venv for 'docker' py module)
    ../../.venv/bin/python run_corpus_pq.py            # or: <app> for a subset
    # static CBOM leg (same jumps)
    python3 run_acdi.py
    # cross-tab + kill-bar verdict
    python3 crosstab_pq.py

Rebuild the pinned probe client:

    ./build.sh    # static Go build inside golang:1.24-alpine

Artifacts: `results_pq.json` (live), `results_acdi.json` +
`cboms/*.json` (static), `crosstab_pq.json` (cross-tab + verdict).

## What the result means

- If the live crypto-visible rate is <10% with no decision-relevant
  diffs → the concept is DISPROVEN on this corpus: a live-negotiation
  gate adds nothing over update-gate² behavioral gating + testssl.sh.
- The interesting cells are **live-only** (live probe sees a negotiation
  change the static CBOM diff misses — the concept's genuine delta)
  and **static-only** (CBOM noise with no live change — the incumbent's
  false-positive shape).

## Deviations / lessons (honest log)

- HA container spec bug: `cmd="sh /pre-tls.sh"` with `entrypoint="sh"`
  expanded to `sh "sh /pre-tls.sh"` → "can't open 'sh'" → all 4 HA
  jumps initially recorded FAIL-CLOSED. Fixed to `cmd="/pre-tls.sh"`,
  re-run clean. (Fail-closed semantics worked as designed: the bug
  produced HOLDs, not false ALLOWs.)
- Host disk at 98–99% forced last-use `docker rmi` hygiene into the
  static leg (mirrors the live leg).
- acdi rootfs extraction: Python tarfile 'data' filter aborts on
  absolute-symlink members present in docker layers (bin/pidof,
  etc/alternatives/*); those members are skipped (path aliases, not
  crypto material) — a partial-fs caveat on the static leg only.

(Results summary appended after the cross-tab completes.)

## Results (2026-09-12, full 20-jump corpus)

Cross-tab (live negotiation diff × static CBOM diff, same 20 jumps):

    both-see      : 0
    live-only     : 2   <- concept's genuine delta
    static-only   : 4   <- CBOM churn with NO live negotiation change
    neither       : 14
    live crypto-visible rate: 2/20 = 10%
    decision-relevant live diffs: 2
      grafana 9.5.21 -> 10.4.19 : PQ kex ADDED X25519MLKEM768
      nextcloud 25.0.13 -> 26.0.13 : TLS version set 1.3/1.2/1.1/1.0 -> 1.3/1.2

VERDICT: **SURVIVES this corpus — kill bar NOT met.** The bar was
"<10% of jumps crypto-visible AND none decision-relevant"; the corpus
shows exactly 10% crypto-visible and 2 decision-relevant diffs,
including the headline event the concept exists to catch: a real
container version jump (grafana 9→10.4) that silently ADDED PQ-hybrid
key exchange (X25519MLKEM768) to the negotiated surface.

The cross-tab itself is the novel data:

- **both-see = 0**: static CBOM diff and live negotiation diff never
  fire on the same jump. They are orthogonal signals, not substitutes.
- **live-only = 2**: both live diffs were invisible to the acdi static
  diff over the same images (nextcloud's Apache config change drops
  TLS 1.0/1.1 — a config-layer change, not a binary-layer one;
  grafana's PQ kex group flip). A static-only gate would have missed
  both.
- **static-only = 4**: acdi flags crypto-asset churn (ML-DSA/ML-KEM
  binaries appearing, DES/RC4 disappearing) with ZERO change to what
  the server actually negotiates. E.g. gitea 1.22→1.23 statically
  gains ML-KEM-768 in the rootfs, yet its live kex surface is
  unchanged — binary presence ≠ negotiated surface. This is the
  incumbent's false-positive shape, quantified.

Side-observations worth recording:
1. Home Assistant (Python 3.13 aiohttp) accepts X25519MLKEM768 on
   every version in the corpus — the OpenSSL-backed Python stack is
   already PQ-hybrid by default, while Go apps only gained it at
   grafana 10.x. The PQ negotiation rollout is real, current, and
   app-stack-dependent.
2. Fail-closed semantics validated in anger: the HA container-spec
   bug produced 4 HOLDs (never false ALLOWs) before it was found and
   fixed.
3. Kex preference order is not captured (Go client limitation) — a
   server whose PREFERENCE flips (PQ-first vs classical-first) with
   the same accepted set would read as no-diff. Documented gap in the
   probe's discrimination.

