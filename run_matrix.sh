#!/bin/bash
# Run the M0 matrix. This host needs group 'docker'; wrap with sg.
cd "$(dirname "$0")"
exec sg docker -c ".venv/bin/python -m probe_proxy matrix"
