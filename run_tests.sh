#!/bin/bash
set -e
cd "$(dirname "$0")"
.venv/bin/python -m pytest test_synthesize.py test_analyze.py test_m2.py test_gate.py -q
