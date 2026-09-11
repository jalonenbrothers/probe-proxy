#!/bin/bash
# Run the M2 honest baseline: 10 apps, synthesized vs EMPTY config.
# Optional args: app names to re-run (merged into baseline.json).
cd "$(dirname "$0")"
exec sg docker -c ".venv/bin/python -m probe_proxy baseline-m2 ${*:2}"
