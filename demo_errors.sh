#!/bin/bash
cd "$(dirname "$0")"
echo "--- e2e on missing container:"
sg docker -c '.venv/bin/python -m probe_proxy no-such-container'; echo "exit=$?"
echo "--- verify on file without marker:"
sg docker -c '.venv/bin/python -m probe_proxy verify /etc/hostname'; echo "exit=$?"
echo "--- json output smoke:"
sg docker -c 'docker rm -f demo2-gitea >/dev/null 2>&1; docker run -d --name demo2-gitea -p 127.0.0.1:3998:3000 gitea/gitea:latest >/dev/null'
sleep 8
sg docker -c '.venv/bin/python -m probe_proxy demo2-gitea --json' | head -12
sg docker -c 'docker rm -f demo2-gitea >/dev/null'
rm -f demo2-gitea.Caddyfile
