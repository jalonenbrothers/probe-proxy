# probe-proxy Milestone 1 — Replay-Verify Report

Apps replayed: 10. Result: **8/10 zero-diff — PASSED (>=5/10 zero-diff)**

Each app: probes run DIRECT to the container vs THROUGH the synthesized Caddy config; up to 3 synthesis iterations.

| app | ready | iters | final diffs | zero-diff |
|---|---|---|---|---|
| vaultwarden | yes | 3 | 0 | YES |
| gitea | yes | 3 | 1 | no |
| grafana | yes | 3 | 0 | YES |
| uptimekuma | yes | 1 | 0 | YES |
| homeassistant | yes | 2 | 0 | YES |
| jellyfin | yes | 1 | 0 | YES |
| immich | yes | 1 | 0 | YES |
| nextcloud | yes | 1 | 0 | YES |
| pihole | yes | 3 | 2 | no |
| n8n | yes | 1 | 0 | YES |

## Residual diffs (apps not zero-diff)

### gitea — 1 diffs after 3 iteration(s)

| probe | key | direct | via config |
|---|---|---|---|
| sse | sse_chunks_observed | 5 | 1 |

Warnings: iter: no known fixer applies to diffs: sse.sse_chunks_observed; iter: no known fixer applies to diffs: sse.sse_chunks_observed

### pihole — 2 diffs after 3 iteration(s)

| probe | key | direct | via config |
|---|---|---|---|
| large_post | post10mb_len_header |  | 0 |
| large_post | post10mb_status | 405 | 502 |

Warnings: iter: no known fixer applies to diffs: large_post.post10mb_len_header, large_post.post10mb_status; iter: no known fixer applies to diffs: large_post.post10mb_status

## Synthesized configs

One Caddyfile per app under `replay/Caddyfile.<app>`; the exact configs replayed, zero-diff or not.

## Warnings emitted by synthesis (policy-not-behavior degradation)

- vaultwarden: iter: added flush_interval -1 for streaming diff (sse broken by buffering)
- vaultwarden: iter: no known fixer applies to diffs: large_post.post10mb_len_header, large_post.post10mb_status
- gitea: iter: no known fixer applies to diffs: sse.sse_chunks_observed
- gitea: iter: no known fixer applies to diffs: sse.sse_chunks_observed
- grafana: app already emits gzip; Caddy encode left off to preserve identity
- grafana: iter: no known fixer applies to diffs: sse.sse_chunks_observed
- grafana: iter: no known fixer applies to diffs: sse.sse_chunks_observed
- uptimekuma: websocket paths ['/socket.io/?EIO=4&transport=websocket'] open; Caddy upgrades transparently, no directive needed
- homeassistant: app already emits br; Caddy encode left off to preserve identity
- homeassistant: iter: added flush_interval -1 for streaming diff (sse broken by buffering)
- homeassistant: iter: rewriting absolute Location headers (upstream leaked its internal host)
- homeassistant: iter: app rejects X-Forwarded-For (4xx on previously-2xx/3xx paths); dropping XFF header
- jellyfin: app already emits br; Caddy encode left off to preserve identity
- nextcloud: app already emits gzip; Caddy encode left off to preserve identity
- nextcloud: well-known 301 redirects are app policy; passed through unchanged
- pihole: iter: no known fixer applies to diffs: large_post.post10mb_len_header, large_post.post10mb_status
- pihole: iter: no known fixer applies to diffs: large_post.post10mb_status
