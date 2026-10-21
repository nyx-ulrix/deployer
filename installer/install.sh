#!/usr/bin/env bash
# Installs Deployer on a Linux server (a headless one is fine). Debian and Ubuntu get Docker Engine from
# download.docker.com when it is missing; other x86_64 distributions need Docker and its compose plugin.
#
#   curl -fsSL https://raw.githubusercontent.com/nyx-ulrix/deployer/main/installer/install.sh | sudo bash
#   curl -fsSL .../install.sh | sudo bash -s -- --port 8090 --ref v0.2.0
#
# Options: --port N  --lan  --no-autostart  --prevent-sleep  --from-source  --yes (no questions)
#          --repo owner/name  --ref tag|branch  --install-dir DIR (default /opt/deployer)
#          --source-dir DIR (a local checkout instead of a download)
# This script only fetches Deployer; `installer/deployer.sh install` does the rest. Running it again
# upgrades an existing install and keeps its .env and data.
set -euo pipefail

# Everything runs from main(), so a download cut short by the network never runs half a script.
main() {
  local repo=nyx-ulrix/deployer ref='' source_dir='' here root tmp tag
  local args=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --repo) repo=${2:?--repo needs owner/name}; shift ;;
      --ref) ref=${2:?--ref needs a tag or branch}; shift ;;
      --source-dir) source_dir=${2:?--source-dir needs a folder}; shift ;;
      *) args+=("$1") ;;
    esac
    shift
  done
  if [ "$(id -u)" -ne 0 ]; then
    echo 'Deployer installs as root. Run: curl -fsSL https://raw.githubusercontent.com/nyx-ulrix/deployer/main/installer/install.sh | sudo bash' >&2
    exit 1
  fi
  if ! command -v curl >/dev/null; then
    command -v apt-get >/dev/null || { echo 'curl is needed: install it, then run this again.' >&2; exit 1; }
    apt-get update -q && apt-get install -y -q curl ca-certificates
  fi

  here=$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd || true)
  if [ -n "$source_dir" ]; then
    root=$(cd "$source_dir" && pwd)
    ref=${ref:-local}
  elif [ -z "$ref" ] && [ -n "$here" ] && [ -f "$here/../deploy/docker-compose.yml" ]; then
    root=$(cd "$here/.." && pwd)
    ref=local
    echo "==> Using the Deployer files at $root"
  else
    if [ -z "$ref" ]; then
      # The latest release, else main (no release published yet).
      tag=$(curl -fsSL --max-time 30 -H 'User-Agent: deployer-installer' "https://api.github.com/repos/$repo/releases/latest" 2>/dev/null |
        sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n 1) || true  # compact or pretty JSON
      ref=${tag:-main}
    fi
    tmp=$(mktemp -d)
    # shellcheck disable=SC2064
    trap "rm -rf '$tmp'" EXIT
    echo "==> Downloading https://github.com/$repo/archive/$ref.tar.gz"
    curl -fsSL --retry 3 --retry-delay 3 --connect-timeout 30 "https://github.com/$repo/archive/$ref.tar.gz" |
      tar -xz -C "$tmp" --no-same-owner
    root=$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -n 1)
  fi
  [ -f "$root/deploy/docker-compose.yml" ] || { echo "$root does not contain deploy/docker-compose.yml." >&2; exit 1; }
  [ -f "$root/installer/deployer.sh" ] || {
    echo "Deployer '$ref' predates Linux support (no installer/deployer.sh). Install a newer --ref, or leave it out for the latest." >&2
    exit 1
  }
  # stdin may be this script itself (curl | bash): questions are asked on the terminal instead.
  bash "$root/installer/deployer.sh" install --source-root "$root" --repo "$repo" --ref "$ref" ${args[@]+"${args[@]}"} </dev/null
}

main "$@"
