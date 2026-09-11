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

## Milestone 2 — CLI UX + hand-edit counter + honest baseline (PASSED)

**What it is**: (1) `probe-proxy <container-or-compose-service>` — a
single end-to-end command: probe -> synthesize -> replay-verify (<=3
iters) -> print Caddy block (with `# managed-by probe-proxy ...
sha256:<hash>` marker) + human verification report; `--json` supported;
clean errors when the container isn't running. (2) `probe-proxy verify
<config-file>` — re-runs the replay suite against a user's EXISTING
Caddyfile, reports (a) drift from the generated block via the marker
hash, (b) broken probes. Drift + broken-probe rows land in
`probe_results.db` (hand_edits table) — the "users still hand-edit"
metric is now measurable. (3) SSE probe measures inter-chunk timing gaps
(>=50ms) instead of raw chunk counts.

**Hypotheses under test**:
- "A homelab operator can get a verified config in one command" —
  demonstrated live (`demo_m2.sh`): gitea, 1 iteration, zero-diff, saved
  block; hand-edit detected by `verify` with verdict "edited but still
  behavior-preserving".
- "Synthesized configs beat an EMPTY reverse_proxy block" (honest
  baseline) — 3/10 apps (homeassistant 17->0, gitea 1->0, pihole 2->1);
  6 ties at 0/0; vaultwarden empty-arm 0 was large_post flakiness luck.
  Above the retreat bar (<=2/10) so NO retreat, but the value story is
  honestly narrow: Caddy's default is near-perfect for ~6-7/10 apps;
  synthesis+replay earns its keep on the invisible-killer class (HA's
  XFF rejection would silently 400 every request).

**Result**: PASSED (no retreat). The interesting side-observation is
the baseline itself — see README "Honest baseline".

Run:
```bash
bash run_tests.sh                          # M0-M2 unit tests (21)
bash run_baseline.sh                       # full 10-app honest baseline (~4 min cached)
bash demo_m2.sh                            # live e2e CLI + verify demo (throwaway gitea)
bash demo_errors.sh                        # clean-error paths + --json smoke
sg docker -c ".venv/bin/python -m probe_proxy <container>"   # one command, any container
sg docker -c ".venv/bin/python -m probe_proxy verify <Caddyfile>"
```

## Milestone 3 — real-machine dogfood + hygiene + packaging (the ship gate)

**What it is**: probe-proxy run end-to-end against the operator's REAL
compose stack on the actual host (custom PHP/JWT admin app + phpMyAdmin,
production Traefik-label fronted), read-only: throwaway networks/containers,
generated blocks to a scratch dir; plus `uv tool install` packaging.

**Hypothesis under test**: "The narrow value story (pass-through +
replay-verify for the invisible-killer class) survives contact with a
real operator's real machine." Kill condition: real-app runs produce
unusable blocks or catch nothing the operator's config gets wrong.

**Result**: narrow story SURVIVES — see `DOGFOOD.md` for the full log.
2/2 usable blocks; the operator's custom app verified zero-diff in one
iteration; phpMyAdmin surfaced a real proto-relative quirk (Secure
cookie flag only set when X-Forwarded-Proto: https — silently dropped
behind plain-:80 fronts, caught 3/3 by replay, honestly unfixed);
the operator's actual TLS-edge production config simmed 0 diffs (their
config is correct). Ship-gate decision data for the director:
(a) 2 real proxy-fronted services by config (0 locally live — dev host
runs proxy-less), (b) 2/2 blocks acceptable, (c) real invisible-killer
class caught (cookie Secure flag) but no operator error found — their
TLS-edge config is behavior-preserving, (d) mis-scored quirk class:
proto-relative behavior (app reacts to XFP the proxy legitimately
rewrites) — future: verify should simulate intended edge semantics.

Run:
```bash
# dogfood (read-only against a running container):
uv tool install .
probe-proxy <container>            # end-to-end, writes <name>.Caddyfile
probe-proxy verify <name>.Caddyfile # drift + broken-probe check
# unit tests:
.venv/bin/python -m pytest test_synthesize.py test_analyze.py test_m2.py -q
python -m unittest discover        # clean (0 collected, no import errors)
```

## update-gate² M1 — the gate CLI (IDEA-10)

**What it is**: `probe-proxy baseline <container>` (double-probe the
running service, store stable fingerprint + image tag/digest in the
SQLite `baselines` table) and `probe-proxy gate <image:tag>` (pull the
new image, double-probe it in a THROWAWAY container, diff vs baseline,
print ALLOW / HOLD-known / HOLD-unknown; the verdict IS the exit code:
0 / 2 / 3, 1 = error). Reuses the shipped probe suite and diff
mechanics; no reimplementation.

**Hypothesis under test** (the card's kill condition): the CLI produces
DETERMINISTIC verdicts on a 10-jump smoke subset of the M0 corpus,
matching the M0 reclassify results. Determinism is the product.

**What it means**: ALLOW = pull; HOLD-known = re-run synthesis around
the named classes after upgrading; HOLD-unknown = human looks first.

**A real bug the smoke caught** (the run's discovery): the M0
double-probe stability filter compared SECTIONS including timing-noise
leaves (`sse_first_chunk_ms`), so a section could flake on rounding
luck, get dropped, and emit spurious old->null diffs that flipped ALLOW
into a false HOLD (gitea 1.22->1.23, 2 false HOLDs). Fix: strip timing
leaves BEFORE the stability comparison (M0's reclassify fixed the same
leak in the DIFF; the leak in the FILTER feeding it was latent).
Unit-tested in `test_gate.py::test_stable_fingerprint_ignores_timing_noise`.

**Stateful-app note**: `baseline` records the RUNNING instance. Gating
a bare throwaway of a stateful app (env/DB-dependent) holds on state
differences, not image differences — pass the compose env through
`--env K=V --port N --cap-add CAP` (documented in README).

**Compose integration**: deliberately NOT built (card: skip if heavy).
Wrapper pattern: `probe-proxy gate $(yaml-read image:tag of service)`
before `docker compose pull` — resolving "newer tag" via registry APIs
is a follow-up, not v1.

Run:
```bash
.venv/bin/python -m pytest test_gate.py -q   # 24 verdict-logic tests
.venv/bin/python experiments/update-gate-m1/smoke.py   # 10-jump live
# smoke needs docker + ~8GB disk for image pulls; ~20-30 min cold
```
Smoke results: `experiments/update-gate-m1/smoke_results.json`
(expected: 10/10 verdict parity with M0 reclassify).
