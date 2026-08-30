# RUN.md — probe-proxy

## Milestone 0 — probe-coverage matrix (PASSED)

**What it is**: the probe suite alone (no synthesis, no config
generation) run against the top-10 self-hosted apps in fresh
disposable containers, producing a probe x app fingerprint matrix.

**Hypothesis under test**: "Do ~12 behavioral probes distinguish the
top-10 self-hosted apps' fingerprints at all?" If fewer than 8 of 10
apps had distinct fingerprints, the synthesis layer would have nothing
to synthesize from and the concept would be disproven.

**Result**: 10/10 distinguishable — hypothesis NOT disproven.

Run: `bash run_matrix.sh` then `.venv/bin/python analyze.py`
(~25 min incl. container startup).

## Milestone 1 — Caddy synthesis + replay-verify (PASSED)

**What it is**: from a probe fingerprint, synthesize a Caddy
reverse-proxy block; replay EVERY probe through the generated config
(Caddy in docker, same network as the app) and diff against a direct
probe run; iterate up to 3 times (fixers adjust the config from
observed diffs) until zero diffs.

**Hypothesis under test**: "Can a behavior-fingerprint-driven config
generator, closed-loop verified by probe replay, produce proxy
configs that provably preserve app behavior?" Kill condition:
<5/10 apps zero-diff after 3 iterations.

**Result**: **8/10 zero-diff — PASSED** (bar was >=5/10).
See `REPLAY.md` for the per-app replay table; per-app configs live in
`replay/Caddyfile.<app>`, raw results in `replay/replay.json`.

The two residual diffs are genuine proxy-behavior limits, not
synthesis failures:
- **pihole** (large_post 405->502): app answers 405 without reading
  the 10MB body; Caddy hits a broken pipe relaying and reports 502.
  Protocol-level; no Caddy directive fixes it.
- **gitea** (sse chunks 5->1): gitea writes ~5 tiny writes; Caddy
  legitimately coalesces them into one TCP segment. Data is identical.

### Side observations (the interesting part)

1. **Caddy's default reverse_proxy is near-perfect pass-through**:
  6/10 apps zero-diff on iteration 1 with an EMPTY parameter set.
  The default config problem is much smaller than catalogs imply.
2. **The replay loop earned its keep twice**:
   - Home Assistant 400s every request when behind a proxy that sends
     X-Forwarded-For (rejects untrusted proxy headers). The loop
     detected 17 diffs on iter 1 and fixed them all by dropping XFF.
   - Timing-flaky probes (sse chunk counts) caused false diffs until
     diff confirmation (re-sample 3x, keep majority-persistent diffs)
     was added.
3. **Probe noise is mostly TCP-coalescing noise**: direct "streamed"
  chunk counts are sub-millisecond apart — transport, not app,
  behavior. Future probes should measure inter-chunk gaps, not counts.

## How to run locally

```bash
python3 -m venv .venv
.venv/bin/pip install httpx websockets docker
.venv/bin/python test_synthesize.py   # synthesis/diff unit tests, no docker
bash run_sanity.sh                    # M0: httpbin sanity, 12/12 probes
bash run_matrix.sh                    # M0: full matrix (~25 min)
.venv/bin/python analyze.py           # M0: regenerate MATRIX.md + verdict
bash run_replay.sh replay             # M1: full replay-verify loop (~45 min)
bash run_replay.sh replay_retry <app> # M1: re-run selected app(s) only
.venv/bin/python -m probe_proxy replay_report  # M1: regenerate REPLAY.md
```

Requirements: Docker daemon reachable, user in the `docker` group
(scripts wrap with `sg docker` on this host), caddy:2 image (auto-
pulled on first run otherwise `docker pull caddy:2`), ~16 GB disk.

## What the results mean

- **M1 8/10 zero-diff (observed)**: fingerprint-driven synthesis plus
  replay-verify produces behavior-preserving Caddy configs for the
  top-10 self-hosted apps. The concept survives its core delta test.
- **Had it been <5/10**: kill — configs could not be verified to
  preserve behavior; record under IDEA-1 rejected_assumptions and stop.
