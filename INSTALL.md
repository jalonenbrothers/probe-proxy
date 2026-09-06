# INSTALL.md — probe-proxy

Local install from a checkout (no PyPI publish yet).

## Quickstart (uv — recommended)

```bash
git clone git@github.com:jalonenbrothers/probe-proxy.git
cd probe-proxy
uv tool install .            # installs `probe-proxy` on PATH
probe-proxy <container>      # e.g. probe-proxy my-app-web
```

Requirements: Python >= 3.11, Docker (your user must reach the daemon —
`docker ps` works; probe-proxy creates throwaway networks/containers
for replay-verify only).

## Dev checkout (venv)

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e .
# or the classic:
uv pip install --python .venv/bin/python httpx websockets docker
.venv/bin/python -m probe_proxy <container>
```

## What lands where

- In a **repo checkout**, artifacts (`probe_results.db`, `replay/`,
  `matrix.json`, `*.Caddyfile`) go to the repo dir — unchanged from M0-2.
- When **installed as a tool**, the package never writes into
  site-packages: artifacts land in your current working directory
  (see `probe_proxy/paths.py`).

## Uninstall

```bash
uv tool uninstall probe-proxy
```