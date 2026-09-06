# DOGFOOD.md — Milestone 3: real-machine dogfood (the ship-gate experiment)

**Date**: 2026-09-06. Read-only dogfood on the operator's actual host:
no live service was modified, restarted, or re-routed; replay ran on
throwaway networks/containers; generated blocks went to a scratch dir.

## The host's real setup (finding a)

The machine runs a 4-container compose stack `doclamp-genadmin`
(custom PHP/JWT admin app on Apache, MySQL, Redis, phpMyAdmin).
**No local reverse proxy is running** — no caddy/nginx/traefik process,
dev override strips the labels and publishes ports directly
(:8081 web, :8082 phpMyAdmin). BUT the production compose carries
real Traefik labels: `Host(doclampgenadmin.local)` and
`Host(genadminphpmyadmin.local)` on the TLS `websecure` entrypoint.
So: **2 real proxy-fronted services (by config), 0 locally live** —
the dogfood ran against the real containers locally.

## What ran

1. `probe-proxy doclampgenadmin-web` — end-to-end (probe → synthesize →
   replay-verify) against the operator's own custom PHP app.
2. `probe-proxy doclampgenadmin-admin` — same, against real phpMyAdmin.
3. `probe-proxy verify` on both generated blocks (drift + broken probes).
4. Traefik-equivalent simulation: throwaway Caddy replicating the
   production edge's upstream behavior (X-Forwarded-Proto: https +
   X-Forwarded-For), full probe suite replayed and diffed vs direct.

## Results

| run | result |
|---|---|
| web (custom PHP app) | **zero-diff, iteration 1**; pass-through block, usable as-is |
| admin (phpMyAdmin) | 1 persistent diff ×3 iters: `cookie_secure_flag` direct=true via=false; loop honestly reported "no known fixer" rather than guessing |
| verify (both blocks) | 0 drift; web 0 broken probes; admin 1 broken probe (the same cookie flag) |
| Traefik-equivalent sim (both apps) | **0 diffs — the operator's production TLS-edge config is behavior-preserving** |

## Findings

- **(b) Usable blocks: 2/2.** The operator would accept both blocks
  (pass-through + warnings); the web app's block was verified zero-diff
  in one iteration.
- **(c) A real invisible-killer class quirk, but NOT an operator error.**
  phpMyAdmin only sets the `Secure` cookie flag when it sees
  X-Forwarded-Proto: https. Plain-:80 Caddy (and the probe's plain
  config) rewrites XFP to http → **Secure flag silently dropped**.
  The replay loop caught it 3/3 and refused to paper over it. Under the
  operator's ACTUAL production config (TLS edge → XFP: https) the flag
  is preserved — sim showed 0 diffs. The killer insight: the "correct"
  config is proto-relative; any plain-HTTP front silently degrades
  cookie security, and replay-verify is what makes that visible.
- **(d) Quirk class the suite mis-scores: proto-relative behavior.**
  The suite treats "direct vs via" differences as config bugs, but here
  the difference is the app correctly reacting to a header the proxy
  legitimately changes. The right fix (future work): replay should
  simulate the edge's XFP/XFF when the operator's front is TLS — i.e.
  verify against the *intended* edge semantics, not a plain :80.
  Also: the 15-probe suite did NOT miss any behavior class on these two
  real apps beyond that.
- **Side observations**: (1) my first sim script leaked two docker
  networks (caddy container still attached when `net.remove()` ran) —
  probe-proxy's own e2e cleans up correctly, but sim/one-off scripts
  should reuse its disconnect-then-remove order. (2) `uv tool install`
  from checkout worked first try after adding `paths.py` (installed
  tools must not write to site-packages — original code would have).

## Verdict for the ship gate

The narrow story survives contact with a real machine: pass-through
synthesis + replay-verify produced an accepted, provably-correct block
for the operator's custom app in one iteration, and surfaced one real
proto-relative cookie-security behavior on phpMyAdmin that no catalog
documents. Whether that is enough value for v1 is the director's call.