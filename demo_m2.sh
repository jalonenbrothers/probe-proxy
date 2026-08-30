#!/bin/bash
# Live demo of the M2 CLI: end-to-end against a throwaway gitea container,
# then the verify subcommand (hand-edit counter) on the generated block.
set -e
cd "$(dirname "$0")"
sg docker -c 'docker rm -f demo-gitea 2>/dev/null || true'
sg docker -c 'docker run -d --name demo-gitea -p 127.0.0.1:3999:3000 gitea/gitea:latest'
sleep 8
echo "=== e2e run ==="
sg docker -c '.venv/bin/python -m probe_proxy demo-gitea'
echo "=== verify the generated block (unedited) ==="
sg docker -c '.venv/bin/python -m probe_proxy verify demo-gitea.Caddyfile --json'
echo "=== hand-edit the block, then verify again ==="
printf '    header_up X-Real-IP unknown\n' >> demo-gitea.Caddyfile
sg docker -c '.venv/bin/python -m probe_proxy verify demo-gitea.Caddyfile'
sg docker -c 'docker rm -f demo-gitea'
