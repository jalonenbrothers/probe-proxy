#!/bin/sh
# pihole v6 native TLS wrapper (pq-gate M0 probe corpus).
# FTL reads a COMBINED cert+key PEM from /etc/pihole/tls.pem
# (webserver.tls.cert default; FTLCONF_webserver_tls_key is NOT a valid
# env knob — FTL rejects it). Copy our fixed probe cert into place, then
# exec the stock entrypoint /usr/bin/start.sh.
set -e
mkdir -p /etc/pihole
cp /certs/combined.pem /etc/pihole/tls.pem
chmod 644 /etc/pihole/tls.pem
exec /usr/bin/start.sh "$@"
