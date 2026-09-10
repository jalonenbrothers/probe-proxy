"""M0 update-gate² corpus: 32 real version jumps across the probe-proxy top-10 suite.

Major-jump-weighted per critic condition (a): every jump is labelled with
`cls` (the app's own breaking-release channel: X-bump / month-bump / Y-bump
= "major"; patch = "patch") and `strict` (leftmost semver component changed).

Apps covered (8 of top-10):
  nextcloud, grafana, homeassistant, pihole, gitea, uptimekuma,
  vaultwarden, jellyfin
Deviations (documented in report): immich (ghcr.io auth-gated registry,
not enumerable anonymously) and n8n (docker.n8n.io registry API 404s).
"""

# ---------------------------------------------------------------- app specs
APPS = {
    "nextcloud": dict(
        repo="nextcloud", port=80, ready="/status.php", grace=150, env={},
        gh="nextcloud/server", tagfmt="v{}"),
    "grafana": dict(
        repo="grafana/grafana", port=3000, ready="/api/health", grace=120,
        env={"GF_SECURITY_ADMIN_PASSWORD": "throwaway123"},
        gh="grafana/grafana", tagfmt="v{}"),
    "homeassistant": dict(
        repo="homeassistant/home-assistant", port=8123, ready="/api/", grace=120,
        env={}, gh="home-assistant/core", tagfmt="{}"),
    "pihole": dict(
        repo="pihole/pihole", port=80, ready="/admin/", grace=120,
        env={"FTLCONF_webserver_api_password": "throwaway123",
             "FTLCONF_webserver_port": "80"},
        cap_add=["NET_ADMIN"], gh="pi-hole/pi-hole", tagfmt="v{}"),
    "gitea": dict(
        repo="gitea/gitea", port=3000, ready="/api/healthz", grace=120, env={},
        gh="go-gitea/gitea", tagfmt="v{}"),
    "uptimekuma": dict(
        repo="louislam/uptime-kuma", port=3001, ready="/", grace=120, env={},
        gh="louislam/uptime-kuma", tagfmt="{}"),
    "vaultwarden": dict(
        repo="vaultwarden/server", port=80, ready="/alive", grace=90,
        env={"I_REALLY_WANT_VOLATILE_STORAGE": "true"},
        gh="dani-garcia/vaultwarden", tagfmt="{}"),
    "jellyfin": dict(
        repo="jellyfin/jellyfin", port=8096, ready="/web/", grace=90, env={},
        gh="jellyfin/jellyfin", tagfmt="v{}"),
}


def J(app, old, new, cls, strict, note):
    return dict(app=app, old=old, new=new, cls=cls,
                strict=strict, note=note)


# ------------------------------------------------------------- jump corpus
# 32 jumps: 27 major-class (84%) / 5 patch; 11 strict-semver-major (34%).
JUMPS = [
    # nextcloud — strict X-line bumps (25→26→27→28→29)
    J("nextcloud", "25.0.13", "26.0.13", "major", True, "X 25->26"),
    J("nextcloud", "26.0.13", "27.1.11", "major", True, "X 26->27.1"),
    J("nextcloud", "27.1.11", "28.0.14", "major", True, "X 27->28"),
    J("nextcloud", "28.0.14", "29.0.8", "major", True, "X 28->29"),
    # grafana — strict X-line bumps (9->10->11->12->13)
    J("grafana", "9.5.21", "10.4.19", "major", True, "X 9->10.4"),
    J("grafana", "10.4.19", "11.6.16", "major", True, "X 10->11.6"),
    J("grafana", "11.6.16", "12.4.10", "major", True, "X 11->12.4"),
    J("grafana", "12.4.10", "13.2.1", "major", True, "X 12->13.2"),
    # homeassistant — month-bump = HA's breaking-capable channel
    J("homeassistant", "2025.12.5", "2026.1.3", "major", True, "month+year 2025.12->2026.1"),
    J("homeassistant", "2026.1.3", "2026.2.3", "major", False, "month bump"),
    J("homeassistant", "2026.2.3", "2026.3.4", "major", False, "month bump"),
    J("homeassistant", "2026.3.4", "2026.4.4", "major", False, "month bump"),
    # pihole — v5->v6 (the famous breaking jump) + calver steps
    J("pihole", "v5.8.1", "2025.02.0", "major", True, "v5->v6 (breaking webserver/API rewrite)"),
    J("pihole", "2025.02.7", "2025.03.1", "patch", False, "calver patch"),
    J("pihole", "2025.06.2", "2025.07.1", "patch", False, "calver patch"),
    J("pihole", "2025.11.1", "2026.02.0", "major", True, "year-cross calver"),
    # gitea — minor(Y)-line bumps carry gitea's breaking changes
    J("gitea", "1.19.4", "1.20.6", "major", False, "Y 1.19->1.20"),
    J("gitea", "1.20.6", "1.21.11", "major", False, "Y 1.20->1.21"),
    J("gitea", "1.21.11", "1.22.6", "major", False, "Y 1.21->1.22"),
    J("gitea", "1.22.6", "1.23.8", "major", False, "Y 1.22->1.23"),
    # uptime-kuma — Y bumps + one patch
    J("uptimekuma", "1.20.2", "1.21.3", "major", False, "Y 1.20->1.21"),
    J("uptimekuma", "1.21.3", "1.22.1", "major", False, "Y 1.21->1.22"),
    J("uptimekuma", "1.22.1", "1.23.16", "major", False, "Y 1.22->1.23"),
    J("uptimekuma", "1.23.16", "1.23.17", "patch", False, "patch"),
    # vaultwarden — Y bumps + one
    J("vaultwarden", "1.32.7", "1.33.2", "major", False, "Y 1.32->1.33"),
    J("vaultwarden", "1.33.2", "1.34.3", "major", False, "Y 1.33->1.34"),
    J("vaultwarden", "1.34.3", "1.35.8", "major", False, "Y 1.34->1.35"),
    J("vaultwarden", "1.35.8", "1.37.2", "major", False, "Y 1.35->1.37 (skipped 1.36)"),
    # jellyfin — 2 Y bumps + 2 patches
    J("jellyfin", "10.9.11", "10.10.7", "major", False, "Y 10.9->10.10"),
    J("jellyfin", "10.10.7", "10.11.3", "major", False, "Y 10.10->10.11"),
    J("jellyfin", "10.11.3", "10.11.4", "patch", False, "patch"),
    J("jellyfin", "10.11.4", "10.11.5", "patch", False, "patch"),
]

assert len(JUMPS) == 32
assert sum(1 for j in JUMPS if j["cls"] == "major") >= 16  # >=50% major-weighted
assert all(j["app"] in APPS for j in JUMPS)

if __name__ == "__main__":
    print(f"{len(JUMPS)} jumps, "
          f"{sum(1 for j in JUMPS if j['cls']=='major')} major-class, "
          f"{sum(1 for j in JUMPS if j['strict'])} strict-semver-major, "
          f"{sum(1 for j in JUMPS if j['cls']=='patch')} patch")
    for j in JUMPS:
        print(f"  {j['app']:14s} {j['old']:>12s} -> {j['new']:<12s} {j['cls']}"
              f"{' strict' if j['strict'] else ''}")