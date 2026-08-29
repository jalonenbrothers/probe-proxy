# probe-proxy

Empirical reverse-proxy config synthesis with a verify-by-replay loop.
Every reverse-proxy config generator asks you to pick your app from a
catalog of known quirks — and the catalogs rot. probe-proxy inverts this:
run the container, probe its live behavior, synthesize a Caddy block from
the observed behavior fingerprint, then **replay every probe through the
generated config and diff results**, iterating up to 3 times until the
config provably preserves the app's behavior.

**Milestone 0 status: PASSED — 10/10 apps behaviorally distinguishable.**
The disproof experiment (do probes yield distinguishable fingerprints at
all?) did NOT kill the concept. See `MATRIX.md`.

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

## Replay report format (M1 — defined now, implemented later)

Each replay run will emit a report:

```json
{
  "app": "jellyfin",
  "config": "Caddyfile.jellyfin",
  "iteration": 2,
  "probes_total": 12,
  "probes_matching_direct": 12,
  "probes_matching_replayed": 11,
  "diffs": [
    {"probe": "sse", "key": "sse_chunks_observed",
     "direct": 5, "replayed": 1,
     "fix_hint": "disable response buffering for this upstream"}
  ],
  "hand_edits": 0
}
```

`hand_edits` is the real product metric: how many manual edits the user
still makes after accepting a generated config. The counter is scaffolded
from day one (`probe-proxy record-edits <config> <count>` writes to the
`hand_edits` SQLite table).

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

# stubs (M1)
.venv/bin/python -m probe_proxy synthesize <fingerprint>
.venv/bin/python -m probe_proxy replay <config>
```

## Scope notes (from the critic, enforced)

- Throwaway instances only — never probe a real deployment (probes can
  trip auth lockouts / rate limits). All M0 containers are labeled
  `probe-proxy=m0` and removed after probing.
- Policy-not-behavior quirks (client-IP requirements, CORS, cookie
  domains) are OUT of v1 scope; they will degrade to a conservative
  default block with a printed warning, never a confidently wrong config.
