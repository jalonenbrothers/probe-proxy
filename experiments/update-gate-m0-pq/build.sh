#!/bin/sh
# Build tlsprobe pinned (critic binding condition b):
#   - static binary, CGO_ENABLED=0, built inside golang:1.24-alpine
#   - NEVER touches host OpenSSL 3.0 (classical-only, would under-report PQ)
#   - version-pinned toolchain container; reproducible via git
set -e
cd "$(dirname "$0")"
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine \
  env CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /src/tlsprobe ./tlsprobe.go
echo "built: $PWD/tlsprobe"
