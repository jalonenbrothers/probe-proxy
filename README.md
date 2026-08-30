# probe-proxy

Empirical reverse-proxy config synthesis with a verify-by-replay loop.
Every reverse-proxy config generator asks you to pick your app from a
catalog of known quirks — and the catalogs rot. probe-proxy inverts this:
run the container, probe its live behavior, synthesize a Caddy block from
the observed behavior fingerprint, then **replay every probe through the
generated config and diff results**, iterating up to 3 times until the
config provably preserves the app's behavior.

**Milestone 1 status: PASSED — 8/10 apps zero-diff through the
synthesized configs.** The replay-verify loop (the core delta) works:
see `REPLAY.md`.

## Milestone 0 — probe-coverage matrix

Twelve probe classes were run against the top-10 self-hosted apps
(fresh throwaway containers; disposable credentials only), plus httpbin
as a sanity target. Result: **10/10 distinct fingerprints**; the kill
condition (<8/10 distinguishable) did not trigger.

Probe discriminative power (distinct value-classes across the 10 apps):

| probe | classes |
|---|---|
| root | 9 |
| common_paths | 8 |
| large_post | 8 |
| method_allow | 7 |
| well_known | 7 |
| xfp_upgrade | 7 |
| sse | 5 |
| tls_redirect | 5 |
| compression | 4 |
| header_reflect | 3 |
| redirect_chain | 3 |
| websocket | 2 |

Full grid: `MATRIX.md`. Raw fingerprints: `matrix.json`. Per-probe rows
in SQLite: `probe_results.db`.

Side observation: the two probes a proxy config actually *needs* to know
(websocket paths, header reflection) are the *weakest* discriminators —
they distinguish apps, but most apps behave identically on them. The
strong signals (root, path map, method allow) are also the ones that
make synthesis easy. The hard part remains replay-verification, which
is exactly the unclaimed delta.

## Repo layout

```
probe_proxy/
  probes.py     # 12 probe classes -> behavior fingerprint dict
  apps.py       # M0 catalog: image, env, ready check, dep sidecars
  matrix.py    # container lifecycle + matrix runner (docker SDK)
  synthesize.py # M1: fingerprint -> Caddyfile params + fixers
  replay.py     # M1: replay-verify loop (direct vs via-config diff)
  report.py     # M1: replay.json -> REPLAY.md
  cli.py       # CLI entry + SQLite store + hand-edit counter scaffold
analyze.py      # fingerprint vectors -> MATRIX.md + distinguishability verdict
run_matrix.sh   # full M0 matrix run (wraps docker group via sg)
run_sanity.sh   # httpbin sanity test (12/12 probes healthy)
test_sanity.py  # sanity assertions
test_analyze.py # analyzer logic checks
MATRIX.md       # M0 deliverable: probe x app grid + verdict
matrix.json     # raw fingerprints
probe_results.db# SQLite probe-result store (+ hand_edits table)
```

## Milestone 1 — synthesis + replay-verify (PASSED: 8/10 zero-diff)

From a fingerprint, `probe_proxy/synthesize.py` emits a Caddy
reverse-proxy block (pass-through by default; directives only from
observed behavioral quirks — e.g. `flush_interval -1` for streaming
apps). `probe_proxy/replay.py` then replays every probe THROUGH the
generated config (Caddy in docker on the app's network) and diffs
against direct-to-container, re-sampling flaky probes (3x majority
vote) and iterating up to 3 times with fixers derived from the diffs.

Result: **8/10 apps zero-diff** (kill bar was <5/10). Full table:
`REPLAY.md`; configs: `replay/Caddyfile.<app>`; raw:
`replay/replay.json`.

Notable loop saves: Home Assistant 400s on X-Forwarded-For (17 diffs
on iter 1 -> all fixed by dropping XFF via `header_up
-X-Forwarded-For`). The two residuals are proxy physics, not synthesis
errors: pihole answers 405 without draining the request body (Caddy
sees a broken pipe -> 502), and gitea's 5 sub-ms SSE writes get
legitimately coalesced into one TCP segment.

## Usage

```bash
python3 -m venv .venv
.venv/bin/python -m pip install httpx websockets docker

# sanity check (httpbin): all 12 probe classes healthy
bash run_sanity.sh

# full M0 matrix (needs docker group membership; script uses sg)
bash run_matrix.sh

# re-run a subset and merge into matrix.json
sg docker -c ".venv/bin/python -m probe_proxy matrix_retry immich vaultwarden"

# analyze + regenerate MATRIX.md
.venv/bin/python analyze.py

# probe a running instance or catalog app
sg docker -c ".venv/bin/python -m probe_proxy run jellyfin"
.venv/bin/python -m probe_proxy run http://127.0.0.1:8080

# synthesize a Caddyfile from a fingerprint json + upstream
.venv/bin/python -m probe_proxy synthesize matrix.json 127.0.0.1:8096

# full M1 replay-verify loop over the 10 apps (~45 min)
bash run_replay.sh replay

# re-run selected apps and merge into replay/replay.json
bash run_replay.sh replay_retry jellyfin gitea

# regenerate REPLAY.md from replay/replay.json
.venv/bin/python -m probe_proxy replay_report
```

## Milestone 2 — CLI UX + hand-edit counter + honest baseline (PASSED)

Three things landed:

1. **One-command operator flow**: `probe-proxy <container>` runs
   probe -> synthesize -> replay-verify (<=3 iters) -> prints the Caddy
   block (with a `# managed-by probe-proxy ... sha256:<hash>` marker) +
   a human verification report; `--json` for machine output. Clean
   errors when the container isn't running. `probe-proxy verify
   <config-file>` re-runs the replay suite against your EXISTING
   Caddyfile and reports drift + broken probes — the hand-edit counter
   is now real instrumentation, not a scaffold.
2. **SSE probe fixed**: inter-chunk timing gaps (>=50ms) replace raw
   chunk counts, which were TCP-coalescing noise. gitea now drops out
   of residual diffs (zero-diff on the M2 baseline), and `sse_streamed`
   is gap-derived too.
3. **Honest baseline** (below).

### Honest baseline: synthesized vs EMPTY config (the value story)

Every config generator claims to save you from hand-tuning. We measured
it: each of the 10 apps replayed twice in one session — (a) through the
synthesized, loop-verified config, (b) through an EMPTY
`reverse_proxy app:port` block with zero parameters, single pass, no
fixers.

| app | empty config: diffs | synthesized: diffs | synthesis wins |
|---|---|---|---|
| homeassistant | 17 | 0 | **YES** |
| gitea | 1 | 0 | **YES** |
| pihole | 2 | 1 | **YES** |
| vaultwarden | 0 | 2 | no* |
| nextcloud | 1 | 1 | tie |
| immich / jellyfin / grafana / uptimekuma / n8n | 0 | 0 | tie |

Synthesized beats the empty config on **3 of 10 apps** — above the
retreat bar (<=2/10) but the honest headline is: **Caddy's default
reverse_proxy is near-perfect pass-through for ~6-7 of 10 self-hosted
apps**. What synthesis + replay-verify actually buys you is the
invisible-killer class — Home Assistant's 17-diff XFF rejection is
exactly the config that looks fine and breaks the app silently.

* vaultwarden's empty-arm 0 was run-to-run luck: its `large_post`
405/502 diff is app-level nondeterminism (it appeared on the synth side
in this run, on the empty side in M1); the synthesized config had zero
directives, i.e. identical to the empty block.

Run it yourself: `bash run_baseline.sh` (~4 min with images cached);
raw results in `replay/baseline.json`, table in `replay/baseline_table.md`.

## Usage (M2)

```bash
# one command, end-to-end against a running container or compose service
sg docker -c ".venv/bin/python -m probe_proxy my-gitea"
sg docker -c ".venv/bin/python -m probe_proxy my-gitea --json"

# later: did you hand-edit the generated block? did it break anything?
sg docker -c ".venv/bin/python -m probe_proxy verify my-gitea.Caddyfile"
sg docker -c ".venv/bin/python -m probe_proxy verify my-gitea.Caddyfile --json"
```

## Scope notes (from the critic, enforced)

- Throwaway instances only — never probe a real deployment (probes can
  trip auth lockouts / rate limits). All M0 containers are labeled
  `probe-proxy=m0` and removed after probing.
- Policy-not-behavior quirks (client-IP requirements, CORS, cookie
  domains) are OUT of v1 scope; they will degrade to a conservative
  default block with a printed warning, never a confidently wrong config.
