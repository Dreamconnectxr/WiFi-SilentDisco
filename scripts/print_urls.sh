#!/usr/bin/env bash
set -euo pipefail

get_lan_ip() {
  local ip
  if command -v ip >/dev/null 2>&1; then
    ip=$(ip -4 addr show scope global | awk '/inet / {print $2}' | cut -d/ -f1 | head -n1)
    if [[ -n "${ip}" ]]; then
      echo "${ip}"
      return
    fi
  fi
  if command -v hostname >/dev/null 2>&1; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [[ -n "${ip}" ]]; then
      echo "${ip}"
      return
    fi
  fi
  ip=$(getent hosts $(hostname) 2>/dev/null | awk '{print $1}' | head -n1)
  if [[ -n "${ip}" ]]; then
    echo "${ip}"
    return
  fi
  echo "127.0.0.1"
}

HOST_IP=$(get_lan_ip)

cat <<MSG
Detected LAN IP: ${HOST_IP}

OBS RTMP Server: rtmp://${HOST_IP}:1935/app
OBS Stream Key: stream
VLC (LL-HLS):   http://${HOST_IP}:3333/app/stream/llhls.m3u8
VLC (HLS-TS):   http://${HOST_IP}:3333/app/stream/master.m3u8?format=ts

docker compose up -d
docker compose logs -f ovenmediaengine
MSG
