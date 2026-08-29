#!/bin/bash
# Re-run only the apps that failed to stand up in the first matrix pass.
cd "$(dirname "$0")"
exec sg docker -c ".venv/bin/python -m probe_proxy matrix_retry immich vaultwarden"
