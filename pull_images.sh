#!/bin/bash
# Pre-pull all M0 images (parallel) so matrix run doesn't serialise pulls.
cd "$(dirname "$0")"
imgs=(
  ghcr.io/immich-app/immich-server:release
  jellyfin/jellyfin:latest
  nextcloud:latest
  ghcr.io/home-assistant/home-assistant:stable
  pihole/pihole:latest
  gitea/gitea:latest
  grafana/grafana:latest
  louislam/uptime-kuma:1
  docker.n8n.io/n8nio/n8n:latest
  vaultwarden/server:latest
)
for i in "${imgs[@]}"; do
  sg docker -c "docker pull -q '$i' >/dev/null 2>&1" &
done
wait
sg docker -c "docker images --format '{{.Repository}}:{{.Tag}}' | grep -E 'immich|jellyfin|nextcloud|home-assistant|pihole|gitea|grafana|uptime-kuma|n8n|vaultwarden' | sort"
echo "PULL DONE"
