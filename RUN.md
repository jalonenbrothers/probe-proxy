# RUN.md — probe-proxy Milestone 0

## What it is

The probe suite alone (NO synthesis, NO config generation) run against
the top-10 self-hosted apps in fresh disposable containers, producing a
probe x app fingerprint matrix.

## Hypothesis under test

"Do ~12 behavioral probes distinguish the top-10 self-hosted apps'
fingerprints at all?" If fewer than 8 of 10 apps had distinct
fingerprints, the synthesis layer would have nothing to synthesize from
and the concept would be disproven.

## Result

**10/10 distinguishable — hypothesis NOT disproven.** Milestone 0
passes; the follow-on synthesis/replay milestone may proceed.

## How to run locally

```bash
python3 -m venv .venv
.venv/bin/python -m pip install httpx websockets docker
bash run_sanity.sh   # httpbin sanity: expect 12/12 probes healthy, exit 0
bash run_matrix.sh   # full matrix; ~25 min incl. container startup
.venv/bin/python analyze.py   # regenerates MATRIX.md, prints verdict
```

Requirements: Docker daemon reachable, user in the `docker` group (the
run scripts wrap with `sg docker` on this host), ~16 GB free disk for
images, outbound network to pull images.

## What the result means

- **10/10 distinguishable (observed)**: probes capture a unique behavior
  fingerprint per app. See `MATRIX.md` for the grid and per-probe
  discriminative power.
- **If it had been <8/10**: kill — no behavioral signal to synthesize
  from; record under IDEA-1 rejected_assumptions and stop.
- Side observation worth carrying forward: the proxy-critical probes
  (websocket paths, X-Forwarded-* reflection) are the weakest
  discriminators — most apps behave identically there. Distinguishing
  apps is easy; the open question is whether a *replayed* config
  preserves behavior, which is M1's verify-by-replay loop.
