#!/bin/bash
# Run the M1 replay-verify loop over the 10 catalog apps.
cd "$(dirname "$0")"
exec sg docker -c ".venv/bin/python -m probe_proxy ${1:-replay} ${*:2}"
