#!/bin/sh
# homeassistant TLS wrapper (pq-gate M0 probe corpus): enable the native
# aiohttp TLS server via configuration.yaml (http: ssl_certificate /
# ssl_key) using our fixed probe cert, then exec the stock entrypoint.
set -e
mkdir -p /config
cat > /config/configuration.yaml <<EOF
http:
  ssl_certificate: /certs/cert.pem
  ssl_key: /certs/key.pem
default_config:
EOF
exec /init
