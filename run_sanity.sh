#!/bin/bash
cd "$(dirname "$0")"
exec sg docker -c ".venv/bin/python test_sanity.py"
