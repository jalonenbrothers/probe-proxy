"""pq-gate M0 crypto-negotiation corpus (IDEA-11, builder M0).

Same-jump live-negotiation probe as the shipped update-gate² M0 corpus
(experiments/update-gate-m0/corpus.py) but fingerprinting the TLS
NEGOTIATION surface of each app's own TLS stack, not HTTP behavior.

Design (critic binding conditions carried verbatim):
- PRE-PROMOTE framing: the NEW image is run in a throwaway container and
  probed live; that is the promotion candidate, not a registry pull.
- PINNED probe client: static Go binary (tlsprobe, built CGO_ENABLED=0 in
  golang:1.24-alpine). Host OpenSSL 3.0 is never used.
- FAIL-CLOSED: probe error => recorded as error and counts as HOLD, never
  as no-diff.
- DOUBLE-PROBE stability filter, M0/M1 lessons carried forward:
  * timing leaves stripped before comparison (none in TLS fp by design,
    but we keep the discipline)
  * env parity: identical env/certs/scripts for old and new image
- Version jumps reused from the M0 corpus (t_cf1c5836), restricted to the
  apps that expose a native TLS server configurable at container start.

Pihole v6 and uptime-kuma are excluded: pihole v6.4.1 ignores tls.pem
when configured via entrypoint wrapper (documented deviation, same shape
as immich/n8n in M0); uptime-kuma has no env-configurable TLS (setup is
UI-driven).
"""

APPS = {
    "vaultwarden": dict(
        repo="vaultwarden/server", port=80, grace=60,
        env={"I_REALLY_WANT_VOLATILE_STORAGE": "true",
             "ROCKET_TLS": '{certs="/ssl/cert.pem",key="/ssl/key.pem"}'},
        mounts=[("certs", "/ssl", "ro")], entrypoint=None, cmd=None,
        tls_note="Rocket native TLS (Rust)"),
    "gitea": dict(
        repo="gitea/gitea", port=3000, grace=90,
        env={"GITEA__server__PROTOCOL": "https",
             "GITEA__server__CERT_FILE": "/ssl/cert.pem",
             "GITEA__server__KEY_FILE": "/ssl/key.pem",
             "GITEA__server__ROOT_URL": "https://probe.test/",
             "GITEA__server__DISABLE_SSH": "true"},
        mounts=[("certs", "/ssl", "ro")], entrypoint=None, cmd=None,
        tls_note="Go net/http native TLS"),
    "grafana": dict(
        repo="grafana/grafana", port=3000, grace=90,
        env={"GF_SERVER_PROTOCOL": "https",
             "GF_SERVER_CERT_FILE": "/ssl/cert.pem",
             "GF_SERVER_CERT_KEY": "/ssl/key.pem",
             "GF_SECURITY_ADMIN_PASSWORD": "throwaway123"},
        mounts=[("certs", "/ssl", "ro")], entrypoint=None, cmd=None,
        tls_note="Go net/http native TLS"),
    "nextcloud": dict(
        repo="nextcloud", port=443, grace=120,
        env={"I_REALLY_WANT_VOLATILE_STORAGE": "true"},
        mounts=[("certs", "/ssl", "ro"),
                ("nextcloud-tls.sh", "/tls.sh", "ro")],
        entrypoint=None, cmd="sh /tls.sh",
        tls_note="Apache mod_ssl (Debian OpenSSL)"),
    "homeassistant": dict(
        repo="homeassistant/home-assistant", port=8123, grace=120,
        env={},
        mounts=[("certs", "/certs", "ro"),
                ("ha-tls.sh", "/pre-tls.sh", "ro")],
        entrypoint="sh", cmd="/pre-tls.sh",
        tls_note="Python aiohttp native TLS"),
}


def J(app, old, new, cls, strict, note):
    return dict(app=app, old=old, new=new, cls=cls, strict=strict, note=note)


# 20 real version jumps reused from the shipped M0 corpus (t_cf1c5836),
# restricted to TLS-probeable apps. Same jump endpoints where chains
# overlap, so old/new fingerprints are shared across adjacent jumps.
JUMPS = [
    # nextcloud — strict X-line bumps
    J("nextcloud", "25.0.13", "26.0.13", "major", True, "X 25->26"),
    J("nextcloud", "27.1.11", "28.0.14", "major", True, "X 27->28"),
    J("nextcloud", "28.0.14", "29.0.8", "major", True, "X 28->29"),
    # grafana — strict X-line bumps
    J("grafana", "9.5.21", "10.4.19", "major", True, "X 9->10.4"),
    J("grafana", "11.6.16", "12.4.10", "major", True, "X 11->12.4"),
    J("grafana", "12.4.10", "13.2.1", "major", True, "X 12->13.2"),
    # homeassistant — month-bump channel
    J("homeassistant", "2025.12.5", "2026.1.3", "major", True, "month+year"),
    J("homeassistant", "2026.2.3", "2026.3.4", "major", False, "month bump"),
    J("homeassistant", "2026.3.4", "2026.4.4", "major", False, "month bump"),
    # gitea — Y-line bumps
    J("gitea", "1.19.4", "1.20.6", "major", False, "Y 1.19->1.20"),
    J("gitea", "1.21.11", "1.22.6", "major", False, "Y 1.21->1.22"),
    J("gitea", "1.22.6", "1.23.8", "major", False, "Y 1.22->1.23"),
    # vaultwarden — Y bumps + a patch
    J("vaultwarden", "1.32.7", "1.33.2", "major", False, "Y 1.32->1.33"),
    J("vaultwarden", "1.34.3", "1.35.8", "major", False, "Y 1.34->1.35"),
    J("vaultwarden", "1.35.8", "1.37.2", "major", False, "Y 1.35->1.37"),
    # cross-stack jump: same app, rebuilt runtime (the PQC-relevant event)
    J("grafana", "10.4.19", "11.6.16", "major", True, "X 10->11.6"),
    J("nextcloud", "26.0.13", "27.1.11", "major", True, "X 26->27.1"),
    J("gitea", "1.20.6", "1.21.11", "major", False, "Y 1.20->1.21"),
    J("vaultwarden", "1.33.2", "1.34.3", "major", False, "Y 1.33->1.34"),
    J("homeassistant", "2026.1.3", "2026.2.3", "major", False, "month bump"),
]

assert len(JUMPS) == 20
assert all(j["app"] in APPS for j in JUMPS)

if __name__ == "__main__":
    majors = sum(1 for j in JUMPS if j["cls"] == "major")
    print(f"{len(JUMPS)} jumps, {majors} major-class, "
          f"{sum(1 for j in JUMPS if j['strict'])} strict-major")
    for j in JUMPS:
        print(f"  {j['app']:15s} {j['old']:>12s} -> {j['new']:<12s} {j['note']}")
