#!/bin/bash
cd "$(dirname "$0")"
sg docker -c 'docker rm -f $(docker ps -aq --filter label=probe-proxy=m0) 2>/dev/null' || true
sg docker -c 'docker pull -q ghcr.io/immich-app/postgres:17-vectorchord1.1.1' >/dev/null 2>&1
exec sg docker -c ".venv/bin/python -m probe_proxy matrix_retry immich"
