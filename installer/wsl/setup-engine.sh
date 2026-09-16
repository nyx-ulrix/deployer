#!/usr/bin/env bash
# Prepares the dedicated `deployer` WSL2 distro: systemd + open-source Docker Engine (docker-ce).
# Run as root inside the distro by installer/install.ps1. Safe to run again (idempotent).
set -euo pipefail

log() { printf '[setup-engine] %s\n' "$*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "setup-engine.sh must run as root (wsl -d deployer -u root ...)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(-y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

# --- WSL settings -------------------------------------------------------------------------------
# This distro exists only to run Deployer, so the whole file is managed here.
log "Writing /etc/wsl.conf (systemd on, root default user, no Windows PATH)"
cat > /etc/wsl.conf <<'EOF'
# Managed by Deployer (installer/wsl/setup-engine.sh)
[boot]
systemd=true

[user]
default=root

[interop]
enabled=true
# Keep Windows' docker.exe (e.g. Docker Desktop) out of this distro's PATH.
appendWindowsPath=false

[automount]
enabled=true
EOF

# Ubuntu WSL images may run cloud-init on boot; there is nothing for it to do here.
if [ -d /etc/cloud ]; then
  touch /etc/cloud/cloud-init.disabled
fi

# --- Base packages ------------------------------------------------------------------------------
log "Updating Ubuntu packages (this can take a while on the first run)"
apt-get update -q
apt-get upgrade "${APT_OPTS[@]}"
apt-get install "${APT_OPTS[@]}" ca-certificates curl gnupg

# --- Docker apt repository (https://docs.docker.com/engine/install/ubuntu/) ----------------------
log "Configuring the Docker apt repository"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL --retry 3 https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc.tmp
mv -f /etc/apt/keyrings/docker.asc.tmp /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

# shellcheck disable=SC1091
. /etc/os-release
CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME}}"
ARCH="$(dpkg --print-architecture)"
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -q
log "Installing docker-ce, docker-ce-cli, containerd.io, buildx and compose plugins"
apt-get install "${APT_OPTS[@]}" docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# --- Docker daemon defaults ---------------------------------------------------------------------
mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  log "Writing /etc/docker/daemon.json (log rotation)"
  cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
fi

# --- Enable services ----------------------------------------------------------------------------
# On the first run systemd is not PID 1 yet (wsl.conf is applied after `wsl --terminate`), so
# create the unit symlinks directly if systemctl refuses.
enable_unit() {
  local unit="$1"
  if ! systemctl enable "$unit" >/dev/null 2>&1; then
    mkdir -p /etc/systemd/system/multi-user.target.wants
    ln -sf "/lib/systemd/system/${unit}" "/etc/systemd/system/multi-user.target.wants/${unit}"
  fi
}
enable_unit containerd.service
enable_unit docker.service

if [ -d /run/systemd/system ]; then
  log "systemd is running; starting Docker now"
  systemctl restart containerd.service docker.service
fi

apt-get clean
log "Done. Restart the distro (wsl --terminate deployer) to boot with systemd."
