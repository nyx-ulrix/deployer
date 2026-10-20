#!/usr/bin/env bash
# Deployer management CLI for Linux, headless servers included (the Windows twin is deployer.ps1).
#
#   deployer help       every command
#   deployer guide      first steps on a new server
#   deployer actions    what to do next, worked out from this install's state
#
# Installed as /usr/local/bin/deployer -> <install dir>/installer/deployer.sh. Needs root (the Docker
# socket and .env are root-only), so it starts itself again with sudo. `install` is run by
# installer/install.sh, which downloads Deployer first.
set -euo pipefail
umask 022

SELF=$(readlink -f "${BASH_SOURCE[0]}")
DEFAULT_DIR=/opt/deployer
DEFAULT_REPO=nyx-ulrix/deployer
UNIT_PATH=/etc/systemd/system/deployer.service
BIN_LINK=/usr/local/bin/deployer
APP_PORT_FIRST=8100
APP_PORT_LAST=8199
SLEEP_TARGETS=(sleep.target suspend.target hibernate.target hybrid-sleep.target)

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_STEP=$'\033[36m' C_OK=$'\033[32m' C_WARN=$'\033[33m' C_ERR=$'\033[31m' C_OFF=$'\033[0m'
else
  C_STEP='' C_OK='' C_WARN='' C_ERR='' C_OFF=''
fi

# --- Arguments ------------------------------------------------------------------------------------
# Flags work Linux-style (--yes, --follow) and the way the Windows docs spell them (-Yes, -Follow).
CMD=${1:-help}
[ $# -gt 0 ] && shift
ORIG=("$@")
CMD=${CMD,,}
case $CMD in -h|--help) CMD=help ;; esac
POS=() YES=0 FOLLOW=0 TAIL=200 REF='' REPO='' PORT_ARG='' FROM_SOURCE=0 KEEP_DATA=0 FORCE=0 JSON=0
BACKGROUND=0 LAN='' AUTOSTART=1 PREVENT_SLEEP=0 SOURCE_ROOT='' INSTALL_DIR=${DEPLOYER_HOME:-}
NESTED=0 UPDATING=0 LAST_BACKUP='' PREV_REF='' PREV_MONGO8=1
if [ "$CMD" = compose ]; then
  [ "${1:-}" = -- ] && shift
  POS=("$@")
  set --
fi
while [ $# -gt 0 ]; do
  case "$1" in
    --) shift; POS+=("$@"); break ;;
    -?*)
      opt=${1#-}; opt=${opt#-}; opt=${opt,,}; opt=${opt//-/}
      case "$opt" in
        y|yes|noninteractive) YES=1 ;;
        f|follow) FOLLOW=1 ;;
        n|tail) TAIL=${2:?"$1 needs a number"}; shift ;;
        ref) REF=${2:?"$1 needs a tag or branch"}; shift ;;
        repo) REPO=${2:?"$1 needs owner/name"}; shift ;;
        port) PORT_ARG=${2:?"$1 needs a port number"}; shift ;;
        installdir) INSTALL_DIR=${2:?"$1 needs a folder"}; shift ;;
        sourceroot) SOURCE_ROOT=${2:?"$1 needs a folder"}; shift ;;
        fromsource) FROM_SOURCE=1 ;;
        keepdata) KEEP_DATA=1 ;;
        force) FORCE=1 ;;
        json) JSON=1 ;;
        background) BACKGROUND=1 ;;
        lan|enablelan) LAN=1 ;;
        nolan) LAN=0 ;;
        noautostart) AUTOSTART=0 ;;
        preventsleep) PREVENT_SLEEP=1 ;;
        h|help) CMD=help ;;
        *) printf 'Unknown option %s. See: deployer help\n' "$1" >&2; exit 2 ;;
      esac ;;
    *) POS+=("$1") ;;
  esac
  shift
done

if [ "$(id -u)" -ne 0 ] && [ "$CMD" != help ]; then
  command -v sudo >/dev/null || { echo "deployer needs root: run it as root." >&2; exit 1; }
  keep=()
  for v in DEPLOYER_HOME DEPLOYER_NEW_PASSWORD DEPLOYER_OAUTH_CLIENT_ID DEPLOYER_OAUTH_CLIENT_SECRET NO_COLOR; do
    [[ -v $v ]] && keep+=("$v")
  done
  pe=()
  [ ${#keep[@]} -gt 0 ] && pe=("--preserve-env=$(IFS=,; echo "${keep[*]}")")
  exec sudo ${pe[@]+"${pe[@]}"} -- bash "$SELF" "$CMD" ${ORIG[@]+"${ORIG[@]}"}
fi

if [ -z "$INSTALL_DIR" ]; then
  INSTALL_DIR=$DEFAULT_DIR
  [ -f "$(dirname "$(dirname "$SELF")")/docker-compose.yml" ] && INSTALL_DIR=$(dirname "$(dirname "$SELF")")
fi
INSTALL_DIR=${INSTALL_DIR%/}
ENV_FILE=$INSTALL_DIR/.env

# --- Output ---------------------------------------------------------------------------------------

step() { printf '\n%s==> %s%s\n' "$C_STEP" "$*" "$C_OFF"; }
info() { printf '    %s\n' "$*"; }
ok() { printf '    %s[ok]%s %s\n' "$C_OK" "$C_OFF" "$*"; }
warn() { printf '    %s[!]%s %s\n' "$C_WARN" "$C_OFF" "$*"; }
err() { printf '    %s[x]%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; }

# next "command - why" ...: the suggested follow-ups printed after a command (not in the service log).
next() {
  [ "$BACKGROUND" = 1 ] || [ "$NESTED" = 1 ] && return 0
  printf '\n    %sNext:%s\n' "$C_STEP" "$C_OFF"
  local line
  for line in "$@"; do printf '      %s\n' "$line"; done
}

# die "message" ["suggestion" ...]
die() {
  err "$1"
  shift
  [ "$UPDATING" = 1 ] && update_recovery
  [ $# -gt 0 ] && next "$@"
  exit 1
}

# ask "question" y|n -> 0 for yes. --yes, or no terminal, takes the default.
ask() {
  local answer hint='[y/N]'
  [ "$2" = y ] && hint='[Y/n]'
  if [ "$YES" = 1 ] || ! { : </dev/tty; } 2>/dev/null; then [ "$2" = y ]; return; fi
  while :; do
    printf '    %s %s ' "$1" "$hint" >/dev/tty
    IFS= read -r answer </dev/tty || answer=''
    case "${answer,,}" in
      '') [ "$2" = y ]; return ;;
      y|yes) return 0 ;;
      n|no) return 1 ;;
    esac
  done
}

# confirm WORD: the user types WORD (--yes skips it).
confirm() {
  local answer
  [ "$YES" = 1 ] && return 0
  { : </dev/tty; } 2>/dev/null || die "No terminal to confirm in. Add --yes to run this from a script."
  printf '    Type %s to continue: ' "$1" >/dev/tty
  IFS= read -r answer </dev/tty || answer=''
  [ "$answer" = "$1" ] && return 0
  info 'Cancelled.'
  return 1
}

read_secret() {
  { : </dev/tty; } 2>/dev/null || return 1
  printf '    %s: ' "$1" >/dev/tty
  IFS= read -rs REPLY </dev/tty || REPLY=''
  printf '\n' >/dev/tty
}

# --- .env -------------------------------------------------------------------------------------------

env_get() {
  [ -f "$ENV_FILE" ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=\\(.*\\)\$/\\1/p" "$ENV_FILE" | tail -n 1 | sed 's/[[:space:]]*$//'
}

# env_set KEY VALUE [missing]: replace KEY in place or append it; "missing" never changes an existing
# value (secrets: the databases already use them).
env_set() {
  local tmp
  if grep -q "^[[:space:]]*$1[[:space:]]*=" "$ENV_FILE" 2>/dev/null; then
    [ "${3:-}" = missing ] && return 0
    tmp=$(mktemp "$ENV_FILE.XXXXXX")
    K=$1 V=$2 awk '$0 ~ "^[[:space:]]*" ENVIRON["K"] "[[:space:]]*=" { print ENVIRON["K"] "=" ENVIRON["V"]; next } { print }' "$ENV_FILE" >"$tmp"
    mv -f "$tmp" "$ENV_FILE"
  else
    # A hand-edited file may end without a newline; the new key must start its own line.
    [ ! -s "$ENV_FILE" ] || [ -z "$(tail -c 1 "$ENV_FILE")" ] || printf '\n' >>"$ENV_FILE"
    printf '%s=%s\n' "$1" "$2" >>"$ENV_FILE"
  fi
  chmod 600 "$ENV_FILE"
}

# Letters and digits only: safe inside URLs (redis://), shells and connection strings.
secret() {
  local s
  s=$(head -c 2048 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9')
  printf '%s' "${s:0:$1}"
}

json_str() {
  local s=$1
  s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\t'/\\t}; s=${s//$'\r'/\\r}; s=${s//$'\n'/\\n}
  printf '"%s"' "$s"
}

# Reads a value from the API's compact JSON (no jq on most servers).
json_val() { sed -n "s/.*\"$1\":\"\\([^\"]*\\)\".*/\\1/p" <<<"$2" | head -n 1; }
json_true() { grep -q "\"$1\":true" <<<"$2"; }

# --- Context --------------------------------------------------------------------------------------

load_ctx() {
  [ -f "$ENV_FILE" ] && [ -f "$INSTALL_DIR/docker-compose.yml" ] ||
    die "Deployer is not installed in $INSTALL_DIR." \
      "curl -fsSL https://raw.githubusercontent.com/$DEFAULT_REPO/main/installer/install.sh | sudo bash   - install it" \
      "deployer <command> --install-dir <folder>   - an install somewhere else"
  PORT=$(env_get DEPLOYER_HTTP_PORT)
  [[ $PORT =~ ^[0-9]+$ ]] || PORT=8080
  BIND=$(env_get DEPLOYER_BIND)
  BIND=${BIND:-127.0.0.1}
}

dc() { docker compose --project-directory "$INSTALL_DIR" -f "$INSTALL_DIR/docker-compose.yml" "$@"; }

engine_ok() { command -v docker >/dev/null && docker info >/dev/null 2>&1; }

ensure_engine() {
  engine_ok && return 0
  command -v docker >/dev/null || die "Docker is not installed." "Run the installer again: it installs Docker Engine on Debian/Ubuntu"
  [ -d /run/systemd/system ] && systemctl start docker >/dev/null 2>&1 || true
  local i
  for i in $(seq 1 30); do engine_ok && return 0; sleep 2; done
  die "The Docker engine is not running." \
    "sudo systemctl start docker   - start it" \
    "sudo journalctl -u docker -n 50   - why it does not start"
}

require_running() {
  engine_ok && [ -n "$(dc ps -q api 2>/dev/null)" ] ||
    die "Deployer is not running." "sudo deployer start"
}

mongo_on() { [[ $(env_get COMPOSE_PROFILES) == *mongodb* ]]; }

# The address Caddy answers on from this server: DEPLOYER_BIND unless that is every interface.
health_host() { case $BIND in 0.0.0.0|127.0.0.1) echo 127.0.0.1 ;; *) echo "$BIND" ;; esac; }
local_url() { if [ "$BIND" = 127.0.0.1 ] || [ "$BIND" = 0.0.0.0 ]; then echo "http://localhost:$PORT"; else echo "http://$BIND:$PORT"; fi; }

health_body() { curl -fsS --max-time 5 "http://$(health_host):$PORT/v1/health" 2>/dev/null; }
setup_status() { curl -fsS --max-time 5 "http://$(health_host):$PORT/v1/setup/status" 2>/dev/null; }

wait_health() {
  local deadline=$((SECONDS + $1))
  while [ "$SECONDS" -lt "$deadline" ]; do
    health_body >/dev/null && return 0
    sleep 5
  done
  return 1
}

# One line per service instead of the raw /v1/health JSON.
print_health() {
  local status version services pair name val pairs
  status=$(json_val status "$1")
  version=$(json_val version "$1")
  if [ "$status" = ok ]; then ok "Health: ok (version $version)"; else warn "Health: ${status:-unknown} (version $version)"; fi
  services=$(sed -n 's/.*"services":{\([^}]*\)}.*/\1/p' <<<"$1")
  IFS=, read -ra pairs <<<"$services"
  for pair in ${pairs[@]+"${pairs[@]}"}; do
    name=${pair%%:*}; name=${name//\"/}; val=${pair#*:}
    case $val in true) val=up ;; false) val=DOWN ;; null) val='switched off (no AVX, or a kernel MongoDB 8 refuses: deployer actions)' ;; esac
    info "  $(printf '%-8s' "$name"): $val"
  done
}

lan_ips() {
  ip -4 -o addr show scope global 2>/dev/null |
    awk '$2 !~ /^(docker|br-|veth|virbr|cni|flannel|lxc)/ { split($4, a, "/"); print a[1] }'
}

server_addr() {
  local ip
  ip=$(lan_ips | head -n 1)
  echo "${ip:-$(hostname)}"
}

# The SSH command that brings this server's dashboard to the user's own computer.
ssh_cmd() {
  local target
  target=$(health_host)
  [ "$target" = 127.0.0.1 ] && target=localhost
  printf 'ssh -L %s:%s:%s %s@%s' "$PORT" "$target" "$PORT" "${SUDO_USER:-$(id -un)}" "$(server_addr)"
}

unit_enabled() { [ -f "$UNIT_PATH" ] && systemctl is-enabled deployer.service >/dev/null 2>&1; }
has_lid() { compgen -G '/proc/acpi/button/lid/*/state' >/dev/null; }
sleep_masked() { [ "$(systemctl is-enabled sleep.target 2>/dev/null)" = masked ]; }

latest_release() {
  local tag
  tag=$(curl -fsSL --max-time 20 -H 'User-Agent: deployer-installer' "https://api.github.com/repos/$1/releases/latest" 2>/dev/null |
    sed -n 's/^ *"tag_name": *"\([^"]*\)".*/\1/p' | head -n 1) || true
  printf '%s' "${tag:-main}"
}

image_version() {
  if [[ $1 =~ ^v?([0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?)$ ]]; then echo "${BASH_REMATCH[1]}"; else echo latest; fi
}

port_users() { # port_users FIRST [LAST]: names of programs listening there
  command -v ss >/dev/null || return 0
  ss -Hltnp "( sport >= :$1 and sport <= :${2:-$1} )" 2>/dev/null |
    sed -n 's/.*users:(("\([^"]*\)".*/\1/p' | sort -u | paste -sd, -
}

check_port() {
  [[ $1 =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ] ||
    die "'$1' is not a port number (1-65535)." "e.g. --port 8090"
  [ "$1" -ge "$APP_PORT_FIRST" ] && [ "$1" -le "$APP_PORT_LAST" ] &&
    die "Port $1 is inside $APP_PORT_FIRST-$APP_PORT_LAST, which Deployer keeps for deployed apps." "Choose another port, e.g. 8090"
  return 0
}

diagnostics() {
  warn 'Container status:'
  dc ps --all || true
  # mongodb is behind a compose profile: naming it here fails on installs without AVX.
  warn 'Last log lines (migrate, api, worker, caddy, mariadb, redis):'
  dc logs --no-color --tail 40 migrate api worker caddy mariadb redis || true
}

# --- Files and images -----------------------------------------------------------------------------

fetch_source() { # fetch_source REPO REF WORKDIR -> SRC_ROOT
  local url="https://github.com/$1/archive/$2.tar.gz"
  info "Downloading $url"
  curl -fsSL --retry 3 --retry-delay 3 --connect-timeout 30 "$url" | tar -xz -C "$3" --no-same-owner ||
    die "Could not download Deployer '$2' from github.com/$1." "Check the --ref/--repo values and this server's internet connection"
  SRC_ROOT=$(find "$3" -mindepth 1 -maxdepth 1 -type d | head -n 1)
  [ -f "$SRC_ROOT/deploy/docker-compose.yml" ] || die "The downloaded archive does not contain deploy/docker-compose.yml."
  # A version from before Linux support has no installer/deployer.sh: installing it would remove this command.
  [ -f "$SRC_ROOT/installer/deployer.sh" ] ||
    die "Deployer '$2' predates Linux support (no installer/deployer.sh), so it cannot be installed here." "sudo deployer update   - the latest version"
}

# Deploy files, management scripts and image sources into INSTALL_DIR. Never touches .env, backups or logs.
copy_files() {
  local root=$1 c
  tar -C "$root/deploy" --exclude=.env -cf - . | tar -C "$INSTALL_DIR" --no-same-owner -xf -
  # A new folder renamed into place: this script may be the one running from installer/ (bash keeps
  # reading the old file, which stays intact).
  rm -rf "$INSTALL_DIR/installer.new"
  mkdir -p "$INSTALL_DIR/installer.new"
  tar -C "$root/installer" --exclude=./windows/bin --exclude=./windows/obj -cf - . |
    tar -C "$INSTALL_DIR/installer.new" --no-same-owner -xf -
  chmod 755 "$INSTALL_DIR/installer.new/deployer.sh"
  rm -rf "$INSTALL_DIR/installer"
  mv "$INSTALL_DIR/installer.new" "$INSTALL_DIR/installer"
  for c in api dashboard deploy; do
    [ -d "$root/$c" ] || continue
    rm -rf "$INSTALL_DIR/src/$c"
    mkdir -p "$INSTALL_DIR/src/$c"
    tar -C "$root/$c" --exclude=node_modules --exclude=.venv --exclude=venv --exclude=dist --exclude=__pycache__ \
      --exclude=.pytest_cache --exclude=.mypy_cache --exclude=.ruff_cache --exclude=.env -cf - . |
      tar -C "$INSTALL_DIR/src/$c" --no-same-owner -xf -
  done
  ln -sfn "$INSTALL_DIR/installer/deployer.sh" "$BIN_LINK"
}

# Whether MongoDB 8 itself refuses to start on this computer. Asks the real image: MongoDB 8 refuses Linux
# kernels 6.19 to 7.0.13 (MongoDB SERVER-121912, fixed by kernel 7.0.14), e.g. Ubuntu 26.04's 7.0 kernel,
# and its rule may change, so no kernel table is kept here.
# 0 = it refuses (prints MongoDB's reason), 1 = it starts, 2 = could not tell (the image would not pull or
# run: offline, rate limit, disk full), which must not be mistaken for a refusal.
mongo_refuses() {
  local image out msg
  image=$(env_get MONGODB_IMAGE)
  image=${image:-mongo:8.0}
  out=$(docker run --rm --network none --entrypoint mongod "$image" --version 2>&1) && return 1
  msg=$(sed -n 's/.*"msg":"\([^"]*\)".*/\1/p' <<<"$out" | head -n 1)
  if [ -z "$msg" ]; then
    warn "Could not run $image to check MongoDB: $(grep -v '^[[:space:]]*$' <<<"$out" | tail -n 1)" >&2
    return 2
  fi
  printf '%s' "$msg"
}

# Whether a compose file starts MongoDB from ${MONGODB_IMAGE} (A-143 and later).
# shellcheck disable=SC2016
compose_has_mongo_image() { grep -q '\${MONGODB_IMAGE' "$1" 2>/dev/null; }

# Creates or upgrades .env. Secrets are only added, never rotated.
init_env() { # init_env PORT MONGO(0|1) REPO REF BIND SET_PORT(0|1)
  local is_new=0 old_url
  if [ ! -f "$ENV_FILE" ]; then
    is_new=1
    (
      umask 077
      printf '%s\n' '# Deployer configuration - generated on this computer by the installer.' \
        "# Created $(date '+%Y-%m-%d %H:%M:%S'). Every secret below is random and local to this install." \
        '# Keep a copy of this file (especially MASTER_KEY) with your backups. See .env.example for documentation.' '' >"$ENV_FILE"
    )
  fi
  env_set PUBLIC_URL "http://localhost:$1" missing
  env_set DEPLOYER_HTTP_PORT "$1" missing
  env_set MARIADB_DATABASE deployer missing
  env_set MARIADB_USER deployer missing
  env_set MARIADB_PASSWORD "$(secret 32)" missing
  env_set MARIADB_ROOT_PASSWORD "$(secret 32)" missing
  env_set MONGO_ROOT_USERNAME admin missing
  env_set MONGO_ROOT_PASSWORD "$(secret 32)" missing
  env_set REDIS_PASSWORD "$(secret 32)" missing
  env_set JWT_SECRET "$(secret 64)" missing
  env_set MASTER_KEY "$(head -c 32 /dev/urandom | base64)" missing
  for k in GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET GITHUB_CLIENT_ID GITHUB_CLIENT_SECRET; do env_set "$k" '' missing; done
  env_set ALLOW_SIGNUP false missing
  env_set DEPLOYER_BIND "$5"
  env_set DEPLOYER_IMAGE_PREFIX "ghcr.io/$(cut -d/ -f1 <<<"${3,,}")/deployer"
  env_set DEPLOYER_VERSION "$(image_version "$4")"
  env_set DEPLOYER_SOURCE_DIR ./src
  env_set DEPLOYER_REPO "$3"
  if [ "$2" = 1 ]; then
    env_set COMPOSE_PROFILES mongodb
    env_set MANAGED_MONGODB_ENABLED true
  else
    env_set COMPOSE_PROFILES ''
    env_set MANAGED_MONGODB_ENABLED false
  fi
  if [ "$6" = 1 ] && [ "$is_new" = 0 ]; then
    env_set DEPLOYER_HTTP_PORT "$1"
    old_url=$(env_get PUBLIC_URL)
    [[ -z $old_url || $old_url =~ ^http://(localhost|127\.0\.0\.1)(:[0-9]+)?/?$ ]] && env_set PUBLIC_URL "http://localhost:$1"
  fi
  # A new install has no MongoDB 5.0 data (docs/BACKUPS.md "MongoDB versions").
  [ "$is_new" = 1 ] && compose_has_mongo_image "$INSTALL_DIR/docker-compose.yml" && env_set MONGODB_IMAGE mongo:8.0
  [ "$is_new" = 1 ]
}

# Pulls the published images; builds them from ./src when they are not available.
images() {
  if [ "$FROM_SOURCE" = 0 ]; then
    info 'Downloading container images...'
    if dc pull; then IMAGE_MODE=pulled; return 0; fi
    warn 'Prebuilt Deployer images could not be pulled (not published for this version yet, private, or offline).'
    warn 'Building them on this server instead. This can take 10-30 minutes on an older computer.'
  fi
  [ -d "$INSTALL_DIR/src/api" ] || die 'Source code for building the images is missing (src/api).' "Run the installer again"
  dc pull --ignore-buildable || true
  dc build --progress=plain ||
    die 'Building the Deployer images failed.' \
      "Docker's buildx plugin is needed: sudo apt install docker-buildx-plugin (Docker's repository) or docker-buildx (Ubuntu's)" \
      "The output above names the step that failed; run the same command again after fixing it"
  IMAGE_MODE=built
}

# A-143: MongoDB opens data only from its own major or the one before; lift it one major at a time
# with the compose `mongodb-upgrade-*` one-off services (Update-DeployerMongo in common.ps1).
update_mongo() {
  compose_has_mongo_image "$INSTALL_DIR/docker-compose.yml" || return 0
  local code=0 major=8
  dc stop -t 60 mongodb >/dev/null 2>&1 || true
  dc --profile mongodb-upgrade run --rm -T mongodb-upgrade-8 || code=$?
  if [ "$code" = 3 ]; then
    info 'Upgrading the managed MongoDB data from 5.0 to 8.0, one version at a time...'
    for major in 6 7 8; do
      code=0
      dc --profile mongodb-upgrade run --rm -T "mongodb-upgrade-$major" || code=$?
      [ "$code" = 0 ] || break
    done
  fi
  [ "$code" = 0 ] || die "Upgrading the managed MongoDB data failed at step mongodb-upgrade-$major (exit code $code). Its data is unchanged since the last finished step." \
    "Run the same command again" "See docs/BACKUPS.md \"MongoDB versions\""
  env_set MONGODB_IMAGE mongo:8.0
  ok 'Managed MongoDB data is ready for MongoDB 8.0'
}

up_and_wait() { # up_and_wait TIMEOUT
  dc up -d --remove-orphans || { diagnostics; die 'docker compose up failed.' "sudo deployer logs api   - what went wrong"; }
  wait_health "$1" && return 0
  # A container Docker brought back after a daemon restart can lose its published port; recreating the
  # web server fixes that.
  warn 'The site is not answering; recreating the web server container...'
  dc up -d --force-recreate caddy || true
  wait_health 120
}

# --- systemd ----------------------------------------------------------------------------------------

install_unit() {
  [ -d /run/systemd/system ] || { warn 'systemd is not running here, so Deployer cannot be set to start at boot. Docker still restarts its containers when the Docker service starts.'; return 0; }
  # Docker's own unit: docker.service from packages, snap.docker.dockerd.service from the snap.
  local docker_unit='' u
  for u in docker.service snap.docker.dockerd.service; do
    systemctl cat "$u" >/dev/null 2>&1 && { docker_unit=$u; break; }
  done
  cat >"$UNIT_PATH" <<EOF
# Managed by Deployer (installer/deployer.sh): starts the stack at boot, stops it cleanly at shutdown.
[Unit]
Description=Deployer (self-hosted backend and deployment platform)
Documentation=https://github.com/$(env_get DEPLOYER_REPO)
${docker_unit:+Requires=$docker_unit}
After=${docker_unit:+$docker_unit }network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
Environment=DEPLOYER_HOME=$INSTALL_DIR
ExecStart=$INSTALL_DIR/installer/deployer.sh start --background
ExecStop=$INSTALL_DIR/installer/deployer.sh stop --background
TimeoutStartSec=20min
TimeoutStopSec=5min

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  # shellcheck disable=SC2086
  systemctl enable $docker_unit deployer.service >/dev/null 2>&1 ||
    warn "Could not enable the services: sudo systemctl enable ${docker_unit:+$docker_unit }deployer.service"
  # Active now, so its ExecStop (a clean `compose stop`, MongoDB gets 60 s) runs at the next shutdown.
  systemctl start deployer.service || warn 'The deployer service did not start: sudo journalctl -u deployer -n 50'
}

remove_unit() {
  [ -f "$UNIT_PATH" ] || return 0
  systemctl disable deployer.service >/dev/null 2>&1 || true
  rm -f "$UNIT_PATH"
  systemctl daemon-reload 2>/dev/null || true
}

set_keepawake() { # set_keepawake 1|0
  if [ "$1" = 1 ]; then
    sleep_masked && { ok 'Sleep is already switched off on this computer'; return 0; }
    systemctl mask "${SLEEP_TARGETS[@]}" >/dev/null
    touch "$INSTALL_DIR/keepawake"
    ok 'This computer no longer suspends or hibernates (also when a laptop lid is closed)'
  else
    [ -f "$INSTALL_DIR/keepawake" ] || { ok 'Deployer did not change the sleep settings; nothing to restore'; return 0; }
    systemctl unmask "${SLEEP_TARGETS[@]}" >/dev/null
    rm -f "$INSTALL_DIR/keepawake"
    ok 'Sleep settings restored'
  fi
}

# --- Commands -------------------------------------------------------------------------------------

cmd_help() {
  cat <<EOF

${C_STEP}Deployer management CLI (Linux)${C_OFF}

  Start here
    deployer guide                     First steps on a new server (a short tutorial)
    deployer actions                   What to do next, worked out from this install's state

  Everyday
    deployer status                    Containers, health, remote access
    deployer start | stop              Start or stop the stack
    deployer restart [service]         Restart everything or one service (api, worker, caddy, ...)
    deployer logs [service] [--follow] Logs (--tail N lines, default 200)
    deployer open                      The dashboard address, and how to reach it from your computer
    deployer config                    Settings (secrets hidden)

  Maintenance
    deployer update [--ref v0.2.0] [--from-source]
                                       Offer a backup, then new deploy files and images; .env and data are kept
    deployer backup                    MariaDB/MongoDB dumps + a copy of .env in backups/<timestamp>
    deployer restore <folder>          Load a backup back in (replaces the databases; asks first)
    deployer uninstall [--keep-data]   Remove Deployer (asks first)
    deployer compose -- <args>         Any docker compose command, e.g. deployer compose -- ps -a

  Settings
    deployer set-port <port>           Change the dashboard port (not 8100-8199: deployed apps use those)
    deployer lan on [ip] | off         Let other devices connect directly (all interfaces, or one address)
    deployer autostart on|off          Start Deployer when this server boots (systemd)
    deployer keepawake on|off          Never suspend (laptops: also with the lid closed)

  Accounts and devices
    deployer oauth status [--json]     Google/GitHub sign-in apps and the callback URLs to register
    deployer oauth set google|github   Save a Client ID and secret (asks, or reads DEPLOYER_OAUTH_CLIENT_ID/_SECRET)
    deployer oauth clear google|github Remove a sign-in app
    deployer reset-password [email]    Forgot a password? Set a new one (default: the owner account)
    deployer device status             Host device link, connection and hosted databases
    deployer device detach [--force]   Forget the main Deployer this computer is attached to

  Options: --yes skips questions and confirmations (scripts). Commands run with sudo by themselves.
  Install directory: $INSTALL_DIR

EOF
}

cmd_guide() {
  load_ctx
  local base
  base=$(local_url)
  cat <<EOF

${C_STEP}Deployer on a Linux server - first steps${C_OFF}

  1. Open the dashboard from your own computer
     Deployer answers on $base on this server only. From your laptop, tunnel to it over SSH:
       $(ssh_cmd)
     keep that window open, browse to http://localhost:$PORT/setup and create the owner account
     (or choose "Restore from export" to bring over another installation).

  2. Let people reach it from any device - a browser is all they need
     a) Your own domain (recommended): in the dashboard open Settings -> Domains & remote access,
        link your Cloudflare account with an API token (the page lists the four permissions and has a
        pre-filled link), then add a hostname such as deployer.example.com. Deployer creates the
        tunnel and the DNS record: https://deployer.example.com then works from any phone or PC,
        with no open ports on this server and no certificates to manage.
     b) Your network only: sudo deployer lan on   (http://<this server's IP>:$PORT)
        On a server with a public IP that means the internet, and Docker bypasses ufw/firewalld
        rules: prefer (a), or sudo deployer lan on <LAN IP> to listen on one address only.

  3. Invite people: a project's Members tab -> Invite. Invite links use the
     public URL, so set up step 2 first.

  4. Optional sign-in with Google or GitHub (your own OAuth apps):
       sudo deployer oauth status          the callback URLs to register
       sudo deployer oauth set github      save the Client ID and secret

  5. Deploy an app: a project -> Deploys -> New app -> Connect GitHub, pick a repository.
     Apps answer on ports $APP_PORT_FIRST-$APP_PORT_LAST here (tunnel them like step 1, e.g. -L 8100:localhost:8100)
     and on their own hostnames once Cloudflare is linked.

  6. Keep it safe
       sudo deployer backup                database dumps + a copy of .env
       Copy $ENV_FILE off this server: its MASTER_KEY decrypts every secret Deployer stores.
       sudo deployer autostart on          start at boot (the installer does this unless --no-autostart)

  Day to day: deployer status | deployer actions | deployer logs api | deployer update
  Forgot the owner password: sudo deployer reset-password

EOF
}

cmd_actions() {
  load_ctx
  local items=() st='' pub code newest latest ref free root
  add() { items+=("$1"$'\n'"$2"); }
  if ! engine_ok; then
    add 'Start Docker, then Deployer' 'sudo systemctl start docker && sudo deployer start'
  elif ! health_body >/dev/null; then
    add 'Start Deployer: it is not answering' 'sudo deployer start   (still failing? sudo deployer logs api)'
  else
    st=$(setup_status || true)
  fi
  if [ -n "$st" ]; then
    json_true initialized "$st" ||
      add 'Finish the setup wizard: create the owner account' "From your computer: $(ssh_cmd), then open http://localhost:$PORT/setup"
    pub=$(json_val public_url "$st")
    if ! json_true reachable_elsewhere "$st"; then
      add 'Make Deployer reachable from any device (now: this server only)' \
        'Dashboard: Settings -> Domains & remote access (your Cloudflare domain, HTTPS, no open ports). Or: sudo deployer lan on'
    elif [[ $pub == https://* ]]; then
      code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$pub/v1/health" || true)
      [ "$code" = 200 ] ||
        add "Your public address $pub does not answer (HTTP ${code:-none})" \
          'sudo deployer logs tunnel; dashboard: Settings -> Domains & remote access shows the tunnel state'
    fi
    json_true google "$st" || json_true github "$st" ||
      add 'Optional: let people sign in with Google or GitHub' 'sudo deployer oauth status (callback URLs), then: sudo deployer oauth set github'
    json_true allow_signup "$st" &&
      add 'Open sign-up is on: anyone who reaches Deployer can create an account and run websites here' \
        'Dashboard: Settings -> Instance settings -> General: turn sign-up off, and invite people instead'
  fi
  [ "$BIND" = 0.0.0.0 ] &&
    add 'Deployer listens on every network interface (with a public IP: the whole internet; Docker bypasses ufw)' \
      'sudo deployer lan on <this server'"'"'s LAN IP>   (one address)   or   sudo deployer lan off'
  unit_enabled || [ ! -d /run/systemd/system ] || add 'Start Deployer when this server boots' 'sudo deployer autostart on'
  [ "$(env_get MANAGED_MONGODB_ENABLED)" = false ] && grep -qw avx /proc/cpuinfo &&
    add "Managed MongoDB is off: MongoDB 8 does not start on Linux kernels 6.19 to 7.0.13 (this one: $(uname -r))" \
      'Update the kernel to 7.0.14 or newer and reboot, then: sudo deployer update (turns it back on). Meanwhile projects can use an external MongoDB such as Atlas'
  has_lid && ! sleep_masked &&
    add 'This computer has a lid: closing it suspends Linux and takes Deployer down' 'sudo deployer keepawake on'
  newest=$(find "$INSTALL_DIR/backups" -mindepth 1 -maxdepth 1 -type d -mtime -7 2>/dev/null | head -n 1 || true)
  [ -n "$newest" ] ||
    add 'No command-line backup in the last 7 days (the dashboard also keeps automatic database versions)' \
      'sudo deployer backup   (then copy the folder off this server)'
  ref=$(env_get DEPLOYER_REF)
  latest=$(env_get DEPLOYER_REPO)
  latest=$(latest_release "${latest:-$DEFAULT_REPO}")
  [ "$latest" != main ] && [ "$latest" != "$ref" ] && add "Deployer $latest is available (this server runs ${ref:-unknown})" 'sudo deployer update'
  if engine_ok; then
    root=$(docker info -f '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)
    free=$(df -Pk "$root" 2>/dev/null | awk 'NR == 2 { print int($4 / 1048576) }')
    [ -n "$free" ] && [ "$free" -lt 5 ] &&
      add "Only $free GB free for Docker ($root)" "Remove old folders in $INSTALL_DIR/backups; sudo docker builder prune frees build cache"
  fi

  step 'Suggested actions'
  if [ ${#items[@]} -eq 0 ]; then
    ok 'Nothing to do: Deployer is set up, reachable and backed up.'
  else
    local i=0 item
    for item in "${items[@]}"; do
      i=$((i + 1))
      printf '    %2d. %s\n        %s\n' "$i" "${item%%$'\n'*}" "${item#*$'\n'}"
    done
  fi
  info ''
  info "Tip: keep a copy of $ENV_FILE off this server (MASTER_KEY decrypts the secrets Deployer stores)."
}

cmd_install() {
  [ -n "$SOURCE_ROOT" ] && [ -f "$SOURCE_ROOT/deploy/docker-compose.yml" ] ||
    die 'deployer install is run by installer/install.sh, which downloads Deployer first.' \
      "curl -fsSL https://raw.githubusercontent.com/$DEFAULT_REPO/main/installer/install.sh | sudo bash"
  REPO=${REPO:-$DEFAULT_REPO}
  REF=${REF:-local}
  mkdir -p "$INSTALL_DIR/logs"
  chmod 700 "$INSTALL_DIR/logs"
  local log is_upgrade=0 set_port=0 bind mongo=1 created mem disk users code problem
  log="$INSTALL_DIR/logs/install-$(date +%Y%m%d-%H%M%S).log"
  exec > >(tee >(sed -u 's/\x1b\[[0-9;]*m//g' >>"$log")) 2>&1

  printf '\n%sDeployer installer (Linux)%s - every password and key is generated on this computer.\n' "$C_STEP" "$C_OFF"
  [ -f "$ENV_FILE" ] && is_upgrade=1 && info "Existing installation found in $INSTALL_DIR - upgrading it (your .env and data are kept)."
  if [ -n "$PORT_ARG" ]; then
    PORT=$PORT_ARG; set_port=1
  else
    PORT=$(env_get DEPLOYER_HTTP_PORT); [[ $PORT =~ ^[0-9]+$ ]] || PORT=8080
  fi
  check_port "$PORT"

  step '1/8 Checking this computer'
  [ "$(uname -s)" = Linux ] || die 'This installer is for Linux. On Windows use DeployerSetup.exe or installer/install.ps1.'
  # The api image, cloudflared and managed MongoDB are amd64-only.
  [ "$(uname -m)" = x86_64 ] || die "Deployer supports Intel/AMD 64-bit (x86_64) computers only; this one is $(uname -m)."
  # shellcheck disable=SC1091
  ok "$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-Linux}") on x86_64, kernel $(uname -r)"
  grep -qi microsoft /proc/version 2>/dev/null && warn 'This looks like WSL. On a Windows PC, DeployerSetup.exe sets Deployer up (and keeps it running) for you.'
  mem=$(awk '/MemTotal/ { printf "%.1f", $2 / 1048576 }' /proc/meminfo)
  if awk -v m="$mem" 'BEGIN { exit !(m < 3.6) }'; then
    warn "Only $mem GB RAM, below the 4 GB minimum: expect at most 1 small app; builds may fail with 'exit code 137'."
  else
    ok "$mem GB RAM"
  fi
  disk=$(df -Pk /var/lib 2>/dev/null | awk 'NR == 2 { printf "%.1f", $4 / 1048576 }')
  if [ -n "$disk" ] && awk -v d="$disk" 'BEGIN { exit !(d < 10) }'; then
    warn "Only $disk GB free under /var/lib (Docker keeps images and databases there). At least 10 GB is recommended."
  elif [ -n "$disk" ]; then
    ok "$disk GB free under /var/lib"
  fi
  if grep -qw avx /proc/cpuinfo; then
    ok 'CPU supports AVX: managed MongoDB 8.0 will be enabled'
  else
    mongo=0
    warn 'This CPU has no AVX, which MongoDB 8.0 needs: managed MongoDB is turned off. Projects can still'
    info 'attach an external MongoDB such as a free MongoDB Atlas cluster (https://www.mongodb.com/atlas).'
  fi
  if ! command -v curl >/dev/null; then
    command -v apt-get >/dev/null || die 'curl is needed. Install it with your package manager and run the installer again.'
    apt-get update -q && apt-get install -y -q curl ca-certificates
  fi

  # Questions first, so the long steps run unattended.
  if [ -n "$LAN" ]; then
    bind=$([ "$LAN" = 1 ] && echo 0.0.0.0 || echo 127.0.0.1)
  elif [ "$is_upgrade" = 1 ]; then
    bind=$(env_get DEPLOYER_BIND); bind=${bind:-127.0.0.1}
  else
    step 'Optional settings'
    info 'Deployer answers on this server only unless you let other devices connect to it directly. Most'
    info 'servers should say no and use an SSH tunnel, or a Cloudflare domain set up from the dashboard.'
    info 'At home, yes lets you open the setup page from your laptop: do that right after the install,'
    info 'because whoever opens /setup first becomes the owner.'
    bind=127.0.0.1
    ask 'Let other devices on your network connect directly (with a public IP: the internet)?' n && bind=0.0.0.0
  fi
  BIND=$bind
  [ "$bind" = 127.0.0.1 ] || [ "$is_upgrade" = 1 ] ||
    warn 'Other devices can connect before the owner account exists: open /setup yourself right after the install.'

  step '2/8 Docker Engine'
  if ! command -v docker >/dev/null; then
    local id ubuntu
    # shellcheck disable=SC1091
    id=$(. /etc/os-release && echo "${ID:-}") ubuntu=$(. /etc/os-release && echo "${UBUNTU_CODENAME:-}")
    # setup-engine.sh uses Docker's apt repository: Debian, Ubuntu and Ubuntu-based distributions.
    if [ "$id" = ubuntu ] || [ "$id" = debian ] || [ -n "$ubuntu" ]; then
      ask 'Docker is not installed. Install the free Docker Engine from download.docker.com now?' y ||
        die 'Deployer needs Docker.' 'Install it yourself: https://docs.docker.com/engine/install/ - then run the installer again'
      bash "$SOURCE_ROOT/installer/wsl/setup-engine.sh" --host || die 'Installing Docker Engine failed (see the output above).'
    else
      die "Docker is not installed, and the installer only sets it up on Debian and Ubuntu (this is ${id:-unknown})." \
        'Install Docker Engine and its compose plugin: https://docs.docker.com/engine/install/ - then run the installer again'
    fi
  fi
  if ! engine_ok && [ -d /run/systemd/system ]; then systemctl enable --now docker >/dev/null 2>&1 || true; fi
  ensure_engine
  ok "Docker $(docker version -f '{{.Server.Version}}' 2>/dev/null) is running"
  docker compose version >/dev/null 2>&1 ||
    die 'The Docker Compose v2 plugin (docker compose) is missing.' \
      "sudo apt install docker-compose-plugin   (Docker's repository)   or   docker-compose-v2   (Ubuntu's docker.io)"
  code=$(docker compose version --short 2>/dev/null || echo 0)
  code=${code#v}
  [ "${code%%.*}" -gt 2 ] 2>/dev/null || { [ "${code%%.*}" = 2 ] && [ "$(cut -d. -f2 <<<"$code")" -ge 20 ]; } ||
    die "Docker Compose $code is too old; Deployer needs 2.20 or newer." "Update Docker: https://docs.docker.com/engine/install/"
  ok "Docker Compose $code"
  if [ "$mongo" = 1 ]; then
    info 'Checking that MongoDB 8 can start on this kernel (downloads the MongoDB image once)...'
    code=0
    problem=$(mongo_refuses) || code=$?
    if [ "$code" = 2 ]; then
      info 'Keeping managed MongoDB on; if the image cannot be downloaded, the next steps say so.'
    elif [ "$code" = 0 ]; then
      mongo=0
      warn "Managed MongoDB is turned off: MongoDB 8 cannot start here ($problem)."
      info "MongoDB 8 refuses Linux kernels 6.19 to 7.0.13 (this one is $(uname -r)); kernel 7.0.14 or newer fixes it,"
      info 'then "sudo deployer update" turns it back on. Its data (if any) stays in its Docker volume. Projects'
      info 'can attach an external MongoDB such as a free MongoDB Atlas cluster meanwhile.'
      # An upgrade's MongoDB container would only restart in a loop; its volume is kept.
      [ "$is_upgrade" = 0 ] || dc --profile mongodb rm -sf mongodb >/dev/null 2>&1 || true
    else
      ok 'MongoDB 8 starts on this kernel'
    fi
  fi
  # Ports: an upgrade whose stack runs holds its own ports already; a new --port must still be free.
  if [ "$is_upgrade" = 0 ] || [ -z "$(dc ps -q caddy 2>/dev/null)" ]; then
    users=$(port_users "$PORT")
    [ -z "$users" ] || die "Port $PORT is already used by: $users." "Close that program, or install with --port 8090"
    users=$(port_users "$APP_PORT_FIRST" "$APP_PORT_LAST")
    [ -z "$users" ] || die "Ports $APP_PORT_FIRST-$APP_PORT_LAST are kept for deployed apps, but these use some of them: $users." "Close those programs, then run the installer again"
    ok "Port $PORT and app ports $APP_PORT_FIRST-$APP_PORT_LAST are free"
  elif [ "$PORT" != "$(env_get DEPLOYER_HTTP_PORT)" ]; then
    users=$(port_users "$PORT")
    [ -z "$users" ] || die "Port $PORT is already used by: $users." "Choose another port with --port"
  fi

  step '3/8 Getting Deployer files'
  mkdir -p "$INSTALL_DIR"
  chmod 755 "$INSTALL_DIR"
  copy_files "$SOURCE_ROOT"
  ok "Files copied to $INSTALL_DIR; the deployer command is $BIN_LINK"

  step '4/8 Writing configuration'
  if init_env "$PORT" "$mongo" "$REPO" "$REF" "$bind" "$set_port"; then created=1; else created=0; fi
  env_set DEPLOYER_REF "$REF"
  mkdir -p "$INSTALL_DIR/backups"
  chmod 700 "$INSTALL_DIR/backups" "$INSTALL_DIR/logs"
  if [ "$created" = 1 ]; then ok '.env created with freshly generated secrets (readable by root only)'; else ok '.env kept; new settings merged in'; fi

  step '5/8 Downloading container images'
  images
  [ "$mongo" = 1 ] && update_mongo

  step '6/8 Starting Deployer'
  dc up -d --remove-orphans || { diagnostics; die 'docker compose up failed.' "sudo deployer logs api   - what went wrong"; }

  step '7/8 Waiting for Deployer to be ready'
  info "Waiting for $(local_url)/v1/health (the first start runs database migrations)..."
  if ! wait_health "$([ "$IMAGE_MODE" = built ] && echo 600 || echo 420)"; then
    diagnostics
    die "Deployer did not become healthy. The logs above usually say why (saved in $log)." \
      'sudo deployer logs api   - more' 'Fix it and run the installer again: it continues where it stopped and keeps .env'
  fi
  ok 'Deployer is up'
  print_health "$(health_body)"

  step '8/8 Start at boot'
  if [ "$AUTOSTART" = 1 ]; then
    install_unit
    unit_enabled && ok 'systemd service deployer.service starts Deployer at boot and stops it cleanly at shutdown'
  else
    remove_unit
    info 'Not starting at boot (you chose --no-autostart). Docker still restarts running containers when it starts.'
  fi
  [ "$PREVENT_SLEEP" = 1 ] && set_keepawake 1

  printf '\n    %sDeployer is installed and running.%s\n\n' "$C_OK" "$C_OFF"
  info "Dashboard      $(local_url)   (on this server)"
  [ "$bind" = 0.0.0.0 ] && for ip in $(lan_ips); do info "Other devices  http://$ip:$PORT"; done
  info "Install dir    $INSTALL_DIR"
  info "Version        $REF"
  info "NoSQL          $([ "$mongo" = 1 ] && echo 'managed MongoDB 8.0 enabled' || echo 'managed MongoDB off (see above) - use an external MongoDB such as Atlas')"
  info "Install log    $log"
  warn "Back up $ENV_FILE (it holds MASTER_KEY) together with your backups."
  if [ "$bind" = 0.0.0.0 ] && [ -n "$(lan_ips)" ]; then
    set -- "1. Now, before anyone else does: open http://$(server_addr):$PORT/setup from your computer and create the owner account"
  else
    set -- "1. On your own computer run:  $(ssh_cmd)" "   then open http://localhost:$PORT/setup and create the owner account"
  fi
  next "$@" \
    "2. Reach it from any device with your domain: dashboard Settings -> Domains & remote access (Cloudflare)" \
    "3. sudo deployer guide     - the whole walkthrough" \
    "   sudo deployer actions   - what is left to do, checked against this server"
}

cmd_status() {
  load_ctx
  local body st pub code
  step 'Deployer status'
  info "Install dir : $INSTALL_DIR"
  info "Version     : $(env_get DEPLOYER_REF) (images: $(env_get DEPLOYER_VERSION))"
  info "URL         : $(local_url)$([ "$BIND" = 127.0.0.1 ] && echo '  (this server only)')"
  [ "$BIND" != 127.0.0.1 ] && info "Listening on: $BIND (other devices can connect)"
  if unit_enabled; then info "Autostart   : systemd deployer.service ($(systemctl is-active deployer.service 2>/dev/null || true))"; else info 'Autostart   : off'; fi
  if ! engine_ok; then
    warn 'Docker engine: not reachable.'
    next 'sudo systemctl start docker, then: sudo deployer start'
    return 0
  fi
  ok 'Docker engine reachable'
  dc ps
  body=$(curl -sS --max-time 5 "http://$(health_host):$PORT/v1/health" 2>/dev/null || true)
  if [[ $body != *'"services"'* ]]; then
    warn "Health endpoint $(local_url)/v1/health is not answering."
    next 'sudo deployer start        - start it' 'sudo deployer logs api     - why the API is down'
    return 0
  fi
  print_health "$body"
  st=$(setup_status || true)
  pub=$(json_val public_url "$st")
  if [[ $pub == https://* ]]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$pub/v1/health" || true)
    if [ "$code" = 200 ]; then ok "Remote access: $pub answers"; else warn "Remote access: $pub does not answer (HTTP ${code:-none}); see: sudo deployer logs tunnel"; fi
  elif [ -n "$pub" ]; then
    info "Public URL  : $pub"
  fi
  if json_true initialized "$st"; then
    next 'sudo deployer actions   - anything left to do'
  else
    next "Finish setup: on your computer run $(ssh_cmd), then open http://localhost:$PORT/setup"
  fi
}

cmd_start() {
  load_ctx
  step 'Starting Deployer'
  ensure_engine
  if up_and_wait "$([ "$BACKGROUND" = 1 ] && echo 300 || echo 180)"; then
    ok "Running at $(local_url)"
    next 'sudo deployer status    - containers and health' 'sudo deployer actions   - what is left to set up'
  else
    warn "Started, but $(local_url)/v1/health is not answering yet."
    next 'sudo deployer logs api   - why' 'sudo deployer status     - which container is not running'
  fi
}

cmd_stop() {
  load_ctx
  step 'Stopping Deployer'
  if engine_ok; then
    dc stop || die 'docker compose stop failed.'
  else
    info 'The Docker engine is not running; nothing to stop.'
  fi
  ok 'Stopped.'
  next "sudo deployer start   - start it again$(unit_enabled && echo ' (it also starts at the next boot)')"
}

cmd_restart() {
  load_ctx
  ensure_engine
  if [ ${#POS[@]} -gt 0 ]; then
    dc restart "${POS[0]}" || die "Restarting ${POS[0]} failed." 'sudo deployer status   - the service names'
    ok "Restarted ${POS[0]}"
    next "sudo deployer logs ${POS[0]} --follow   - watch it come up"
    return 0
  fi
  dc stop || true
  cmd_start
}

cmd_logs() {
  load_ctx
  local a=(logs --tail "$TAIL")
  [ "$FOLLOW" = 1 ] && a+=(--follow)
  [ ${#POS[@]} -gt 0 ] && a+=("${POS[0]}")
  dc "${a[@]}"
}

cmd_compose() {
  load_ctx
  [ ${#POS[@]} -gt 0 ] || die 'Usage: deployer compose -- <docker compose arguments>' 'deployer compose -- ps -a'
  dc "${POS[@]}"
}

cmd_open() {
  load_ctx
  local st pub
  step 'Opening the dashboard'
  info "On this server: $(local_url)"
  st=$(setup_status || true)
  pub=$(json_val public_url "$st")
  [ -n "$pub" ] && json_true reachable_elsewhere "$st" && info "From any device: $pub"
  [ "$BIND" = 0.0.0.0 ] && for ip in $(lan_ips); do info "On your network: http://$ip:$PORT"; done
  info "From your computer through SSH: $(ssh_cmd), then http://localhost:$PORT"
}

cmd_config() {
  load_ctx
  local line key val
  step 'Deployer configuration'
  info "Install dir            $INSTALL_DIR"
  info "Autostart              $(unit_enabled && echo on || echo off)"
  info "Keep awake             $([ -f "$INSTALL_DIR/keepawake" ] && echo on || echo off)"
  printf '\n'
  info "$ENV_FILE - secrets hidden:"
  while IFS= read -r line; do
    [[ $line =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=(.*)$ ]] || continue
    key=${BASH_REMATCH[1]} val=${BASH_REMATCH[2]}
    [[ $key =~ PASSWORD|SECRET|MASTER_KEY|TOKEN ]] && val=$([ -n "$val" ] && echo '********' || echo '(empty)')
    info "$(printf '%-24s %s' "$key" "$val")"
  done <"$ENV_FILE"
}

cmd_backup() {
  load_ctx
  ensure_engine
  local stamp dir dump
  stamp=$(date +%Y%m%d-%H%M%S)
  dir=$INSTALL_DIR/backups/$stamp
  mkdir -p "$dir"
  chmod 700 "$INSTALL_DIR/backups"
  step "Backing up to $dir"
  cp "$ENV_FILE" "$dir/env.backup"
  chmod 600 "$dir/env.backup"
  ok '.env copied (contains MASTER_KEY - keep this folder private)'
  # Dumped inside the container, then copied out. The passwords are read inside the container.
  # shellcheck disable=SC2016
  dump='export MYSQL_PWD=$MARIADB_ROOT_PASSWORD; exec mariadb-dump -uroot --all-databases --single-transaction --quick --routines --events --triggers --hex-blob --result-file=/tmp/deployer-mariadb.sql'
  dc exec -T mariadb sh -c "$dump" || die 'mariadb-dump failed. Is the stack running?' 'sudo deployer start'
  local rc=0
  dc cp mariadb:/tmp/deployer-mariadb.sql "$dir/mariadb.sql" || rc=$?
  dc exec -T mariadb rm -f /tmp/deployer-mariadb.sql >/dev/null 2>&1 || true
  [ "$rc" = 0 ] || die 'Copying the MariaDB dump failed.'
  ok 'MariaDB dumped to mariadb.sql'
  if mongo_on; then
    # shellcheck disable=SC2016
    dump='exec mongodump --quiet --username=$MONGO_INITDB_ROOT_USERNAME --password=$MONGO_INITDB_ROOT_PASSWORD --authenticationDatabase=admin --gzip --archive=/tmp/deployer-mongodb.archive.gz'
    dc exec -T mongodb sh -c "$dump" || die 'mongodump failed.' 'sudo deployer logs mongodb'
    rc=0
    dc cp mongodb:/tmp/deployer-mongodb.archive.gz "$dir/mongodb.archive.gz" || rc=$?
    dc exec -T mongodb rm -f /tmp/deployer-mongodb.archive.gz >/dev/null 2>&1 || true
    [ "$rc" = 0 ] || die 'Copying the MongoDB dump failed.'
    ok 'MongoDB dumped to mongodb.archive.gz'
  else
    info 'Managed MongoDB is off; skipped.'
  fi
  cat >"$dir/README.txt" <<EOF
Deployer backup $stamp

env.backup           copy of .env (MASTER_KEY decrypts secrets stored in MariaDB)
mariadb.sql          mariadb-dump --all-databases
mongodb.archive.gz   mongodump --gzip --archive (if managed MongoDB is on)

Restore (replaces the current databases; offers a backup of them first):
  sudo deployer restore $stamp
It only goes back onto this install (same MASTER_KEY and database passwords as env.backup).

For moving to another computer, use the encrypted export in the dashboard (Settings > Export & import).
EOF
  ok "Backup complete: $dir"
  LAST_BACKUP=$stamp
  local who=${SUDO_USER:-root} home
  home=$(getent passwd "$who" | cut -d: -f6)
  next "sudo deployer restore $stamp   - load it back in later" \
    'Copy it off this server (root-only; it holds MASTER_KEY, so keep the copy private):' \
    "  sudo tar -czf $home/deployer-backup-$stamp.tgz -C $INSTALL_DIR/backups $stamp && sudo chown $who $home/deployer-backup-$stamp.tgz" \
    "  then on your computer: scp $who@$(server_addr):deployer-backup-$stamp.tgz ." \
    'Moving to another computer? Dashboard: Settings -> Export & import'
}

assert_restore_folder() {
  local folder=$1 key old now
  [ -f "$folder/mariadb.sql" ] || die "$folder is not a Deployer backup folder (mariadb.sql is missing)." "ls $INSTALL_DIR/backups   - the backups on this server"
  [ -f "$folder/env.backup" ] || return 0
  # The dumps carry the database accounts, so a backup from another install would lock Deployer out of
  # its own databases. --force does not skip this.
  for key in MARIADB_USER MARIADB_PASSWORD MARIADB_ROOT_PASSWORD MONGO_ROOT_USERNAME MONGO_ROOT_PASSWORD; do
    old=$(ENV_FILE=$folder/env.backup env_get "$key")
    now=$(env_get "$key")
    [ -z "$old" ] || [ "$old" = "$now" ] ||
      die "This backup comes from another install: its $key differs from $ENV_FILE. A backup only goes back onto the install that made it." \
        'To move to another computer, use the encrypted export: dashboard Settings -> Export & import'
  done
  old=$(ENV_FILE=$folder/env.backup env_get MASTER_KEY)
  now=$(env_get MASTER_KEY)
  [ -z "$old" ] || [ "$old" = "$now" ] || [ "$FORCE" = 1 ] ||
    die 'This backup was taken with a different MASTER_KEY, so the secrets in it could not be decrypted.' \
      "Copy the MASTER_KEY line from $folder/env.backup into $ENV_FILE, run sudo deployer restart, then restore again" \
      'Or add --force to restore anyway'
}

cmd_restore() {
  [ ${#POS[@]} -gt 0 ] || die 'Usage: deployer restore <backup folder or its backups/<timestamp> name> [--yes] [--force]' "ls $INSTALL_DIR/backups   - the backups on this server"
  load_ctx
  local folder load
  if [ -d "${POS[0]}" ]; then folder=$(cd "${POS[0]}" && pwd); else folder=$INSTALL_DIR/backups/${POS[0]}; fi
  assert_restore_folder "$folder"
  step "Restore Deployer from $folder"
  warn 'This REPLACES every database in this Deployer (MariaDB, and MongoDB if the backup has it) with the backup.'
  confirm RESTORE || return 0
  ensure_engine
  if ask 'Back up the current databases first?' y; then NESTED=1; cmd_backup; NESTED=0; fi
  dc cp "$folder/mariadb.sql" mariadb:/tmp/deployer-restore.sql || die 'Copying mariadb.sql into the container failed. Is the stack running?' 'sudo deployer start'
  # shellcheck disable=SC2016
  load='export MYSQL_PWD=$MARIADB_ROOT_PASSWORD; mariadb -uroot < /tmp/deployer-restore.sql && mariadb-admin -uroot flush-privileges; rc=$?; rm -f /tmp/deployer-restore.sql; exit $rc'
  dc exec -T mariadb sh -c "$load" || die 'Loading mariadb.sql failed.' 'sudo deployer logs mariadb'
  ok 'MariaDB restored from mariadb.sql'
  if [ -f "$folder/mongodb.archive.gz" ]; then
    if mongo_on; then
      dc cp "$folder/mongodb.archive.gz" mongodb:/tmp/deployer-restore.archive.gz || die 'Copying mongodb.archive.gz into the container failed.'
      # shellcheck disable=SC2016
      load='mongorestore --quiet --drop --gzip --archive=/tmp/deployer-restore.archive.gz --username=$MONGO_INITDB_ROOT_USERNAME --password=$MONGO_INITDB_ROOT_PASSWORD --authenticationDatabase=admin; rc=$?; rm -f /tmp/deployer-restore.archive.gz; exit $rc'
      dc exec -T mongodb sh -c "$load" || die 'mongorestore failed.' 'sudo deployer logs mongodb'
      ok 'MongoDB restored from mongodb.archive.gz'
    else
      warn 'The backup has mongodb.archive.gz but managed MongoDB is off here; skipped.'
    fi
  fi
  ok 'Restored.'
  next 'sudo deployer restart   - every service picks up the restored data'
}

update_recovery() {
  local back=$PREV_REF
  [ -n "$back" ] && [ "$back" != local ] || back='<the version you had, e.g. v0.1.0>'
  next 'sudo deployer logs api   - why it failed' \
    "$( if mongo_on && [ "$PREV_MONGO8" = 0 ] && [ -n "$(env_get MONGODB_IMAGE)" ]; then
          echo "sudo deployer update   - retry. The MongoDB data is now on 8.0, which $back cannot open (docs/BACKUPS.md \"MongoDB versions\")"
        else
          echo "sudo deployer update --ref $back   - go back to the version that ran before"
        fi )" \
    "$( if [ -n "$LAST_BACKUP" ]; then echo "sudo deployer restore $LAST_BACKUP   - if the new version already migrated the database (after going back)"
        else echo 'No backup was taken before this update, so a database the new version already migrated cannot be put back.'; fi )"
}

cmd_update() {
  load_ctx
  local repo target work bind
  repo=$(env_get DEPLOYER_REPO); repo=${repo:-$DEFAULT_REPO}
  PREV_REF=$(env_get DEPLOYER_REF)
  target=${REF:-$(latest_release "$repo")}
  step "Updating Deployer from $repo (${PREV_REF:-unknown} -> $target)"
  ensure_engine
  exec > >(tee >(sed -u 's/\x1b\[[0-9;]*m//g' >>"$INSTALL_DIR/logs/deployer.log")) 2>&1
  if ask 'Take a backup before updating?' y; then NESTED=1; cmd_backup; NESTED=0; fi
  work=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$work'" EXIT
  fetch_source "$repo" "$target" "$work"
  compose_has_mongo_image "$INSTALL_DIR/docker-compose.yml" || PREV_MONGO8=0
  UPDATING=1
  copy_files "$SRC_ROOT"
  bind=$BIND
  # Managed MongoDB: wanted with AVX, and only where MongoDB 8 can start (a kernel update can change both ways).
  local mongo=0 problem='' code=0
  if grep -qw avx /proc/cpuinfo; then
    problem=$(mongo_refuses) || code=$?
    case $code in
      1) mongo=1 ;;
      0)
        warn "Managed MongoDB stays off: MongoDB 8 cannot start here ($problem; kernel $(uname -r), see docs/SETUP.md)."
        dc --profile mongodb rm -sf mongodb >/dev/null 2>&1 || true
        ;;
      *)
        # Could not tell: keep what this install had.
        mongo_on && mongo=1
        info "Managed MongoDB stays $([ "$mongo" = 1 ] && echo on || echo off) (could not check whether MongoDB 8 starts here)."
        ;;
    esac
  fi
  init_env "$PORT" "$mongo" "$repo" "$target" "$bind" 0 || true
  ok 'Deploy files updated; .env kept'
  images
  mongo_on && update_mongo
  up_and_wait "$([ "$IMAGE_MODE" = built ] && echo 600 || echo 420)" || { diagnostics; die 'Deployer did not become healthy after the update.'; }
  UPDATING=0
  env_set DEPLOYER_REF "$target"
  ok "Updated to $target"
  # The new version writes its own service definition (this process runs the old script).
  unit_enabled && { "$INSTALL_DIR/installer/deployer.sh" autostart on --background || warn 'The systemd service was not refreshed: sudo deployer autostart on'; }
  docker image prune -f >/dev/null 2>&1 || true
  next 'sudo deployer status    - check every service' 'sudo deployer actions   - anything new to set up'
}

cmd_uninstall() {
  load_ctx
  local name ids
  step 'Uninstall Deployer'
  if [ "$KEEP_DATA" = 1 ]; then
    info 'Containers, the systemd service and program files will be removed.'
    info 'Kept: the databases (Docker volumes), .env and backups.'
  else
    warn 'This PERMANENTLY deletes all Deployer databases and settings on this computer:'
    warn 'containers, Docker volumes, .env and backups.'
    info 'Tip: run "sudo deployer backup" or export from the dashboard first, or use --keep-data.'
  fi
  confirm UNINSTALL || return 0
  cd /
  if [ -f "$UNIT_PATH" ]; then remove_unit; ok 'systemd service removed'; fi
  [ -f "$INSTALL_DIR/keepawake" ] && set_keepawake 0
  if engine_ok; then
    # Deployed apps run outside compose (docs/DEPLOYMENTS.md); their containers hold its networks.
    ids=$(docker ps -aq --filter label=deployer.app; docker ps -aq --filter label=deployer.cohost_app)
    if [ -n "$ids" ]; then
      # shellcheck disable=SC2086
      if [ "$KEEP_DATA" = 1 ]; then docker stop $ids >/dev/null; else docker rm -f $ids >/dev/null; fi
    fi
    if [ "$KEEP_DATA" = 1 ]; then dc --profile mongodb down --remove-orphans || true; else dc --profile mongodb down --remove-orphans --volumes || true; fi
    ok 'Containers removed'
  else
    warn 'Docker engine not reachable; containers were not removed.'
  fi
  [ "$(readlink "$BIN_LINK" 2>/dev/null)" = "$INSTALL_DIR/installer/deployer.sh" ] && rm -f "$BIN_LINK"
  for name in "$INSTALL_DIR"/* "$INSTALL_DIR"/.[!.]*; do
    [ -e "$name" ] || continue
    if [ "$KEEP_DATA" = 1 ]; then case ${name##*/} in .env|backups) continue ;; esac; fi
    rm -rf "$name"
  done
  [ "$KEEP_DATA" = 1 ] || rmdir "$INSTALL_DIR" 2>/dev/null || true
  ok 'Deployer has been uninstalled.'
  info 'Docker itself was not removed (sudo apt remove docker-ce docker-ce-cli containerd.io if you no longer need it).'
  [ "$KEEP_DATA" = 1 ] && next "Install again later and the databases, $ENV_FILE and backups are picked up again"
  return 0
}

restart_for_settings() {
  if ! engine_ok; then info 'Deployer is not running; the change applies the next time it starts.'; return 0; fi
  dc up -d --remove-orphans || die 'docker compose up failed.' 'sudo deployer logs caddy'
  if wait_health 240; then ok "Running at $(local_url)"; else warn "$(local_url)/v1/health is not answering yet. Check: sudo deployer logs caddy"; fi
}

on_off() {
  case "${POS[0]:-}" in
    on) return 0 ;;
    off) return 1 ;;
    *) die "Usage: deployer $CMD on|off" ;;
  esac
}

cmd_set_port() {
  local new=${POS[0]:-} old_url users
  [ -n "$new" ] || die 'Usage: deployer set-port <port>' 'e.g. sudo deployer set-port 8090'
  check_port "$new"
  load_ctx
  [ "$new" = "$PORT" ] && { ok "Deployer already uses port $new"; return 0; }
  step "Changing the port from $PORT to $new"
  users=$(port_users "$new")
  [ -z "$users" ] || die "Port $new is already used by: $users." 'Choose a different port'
  env_set DEPLOYER_HTTP_PORT "$new"
  old_url=$(env_get PUBLIC_URL)
  if [[ -z $old_url || $old_url =~ ^http://(localhost|127\.0\.0\.1)(:[0-9]+)?/?$ ]]; then
    env_set PUBLIC_URL "http://localhost:$new"
  else
    warn "PUBLIC_URL is $old_url and was left unchanged."
  fi
  ok '.env updated'
  PORT=$new
  restart_for_settings
  next 'sudo deployer oauth status   - Google/GitHub callback URLs change with the port: register the new ones' \
    "$(ssh_cmd)   - the SSH tunnel with the new port"
}

cmd_lan() {
  load_ctx
  local bind ip st
  if on_off; then
    bind=${POS[1]:-0.0.0.0}
    [[ $bind =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || die "'$bind' is not an IPv4 address." "ip -4 addr   - this server's addresses"
    [ "$bind" = 0.0.0.0 ] || lan_ips | grep -qx "$bind" || die "$bind is not an address of this server." "Choose one of: $(lan_ips | paste -sd' ' -)"
    # The setup wizard is first come, first served: whoever opens /setup first becomes the owner.
    st=$(setup_status || true)
    if [ -n "$st" ] && ! json_true initialized "$st"; then
      warn 'There is no owner account yet: once other devices can connect, whoever opens /setup first owns this server.'
      [ "$YES" = 1 ] || ask 'Let other devices connect anyway?' n ||
        die 'Nothing was changed.' "Create the owner first: on your computer run $(ssh_cmd), then open http://localhost:$PORT/setup" \
          'Then run: sudo deployer lan on'
    fi
    step "Letting other devices connect ($bind:$PORT and apps on $APP_PORT_FIRST-$APP_PORT_LAST)"
    warn 'Docker publishes these ports past ufw/firewalld rules. With a public IP and 0.0.0.0 that is the whole internet.'
  else
    bind=127.0.0.1
    step 'Blocking other devices (this server only)'
  fi
  env_set DEPLOYER_BIND "$bind"
  BIND=$bind
  restart_for_settings
  if [ "$bind" = 127.0.0.1 ]; then
    ok 'Deployer is reachable from this server only'
    next "$(ssh_cmd)   - reach it from your computer" 'Dashboard: Settings -> Domains & remote access   - reach it from anywhere with your domain'
  else
    if [ "$bind" = 0.0.0.0 ]; then for ip in $(lan_ips); do ok "Other devices: http://$ip:$PORT"; done; else ok "Other devices: http://$bind:$PORT"; fi
    next 'Finish the setup wizard first if you have not: whoever opens /setup first becomes the owner' \
      'Dashboard: Settings -> Instance settings -> Public URL   - set it to the address people use, so invite links work' \
      "sudo deployer lan on <LAN IP>   - listen on one address only (e.g. not the public one)"
  fi
}

cmd_autostart() {
  load_ctx
  if on_off; then
    install_unit
    unit_enabled && ok 'Deployer starts when this server boots (systemd deployer.service)'
    next 'systemctl status deployer   - the service state'
  else
    remove_unit
    ok 'Deployer no longer starts at boot'
    next 'Docker still restarts containers that were running when the server went down; run sudo deployer stop before a reboot to keep it down'
  fi
}

cmd_keepawake() {
  load_ctx
  [ -d /run/systemd/system ] || die 'Keep awake needs systemd.'
  if on_off; then set_keepawake 1; else set_keepawake 0; fi
}

cmd_device() {
  load_ctx
  local sub=${POS[0]:-} a
  [ "$sub" = status ] || [ "$sub" = detach ] || die 'Usage: deployer device status | deployer device detach [--force] [--yes]'
  require_running
  a=(exec -T api python -m app.cli device "$sub")
  if [ "$sub" = detach ]; then
    step 'Detach this computer from its main Deployer'
    warn 'This computer forgets the main Deployer it is attached to. The main Deployer shows it as offline'
    warn 'until its owner removes it there. Databases hosted here are kept (nothing is deleted).'
    [ "$FORCE" = 1 ] || info 'Detaching is refused while this computer still hosts databases; move them first or add --force.'
    confirm DETACH || return 0
    [ "$FORCE" = 1 ] && a+=(--force)
  fi
  dc "${a[@]}" || die "deployer device $sub failed."
}

# Runs the API's CLI with JSON on stdin (secrets never go on a command line); prints its stdout.
api_cli() { # api_cli STDIN ARGS...
  local input=$1 out errf code=0
  shift
  errf=$(mktemp)
  out=$(printf '%s' "$input" | dc exec -T api python -m app.cli "$@" 2>"$errf") || code=$?
  if [ "$code" != 0 ]; then
    [ -n "$out" ] || out=$(grep -v '^[[:space:]]*$' "$errf" | tail -n 1)
    rm -f "$errf"
    die "${out:-exit code $code}"
  fi
  rm -f "$errf"
  printf '%s\n' "$out"
}

cmd_oauth() {
  load_ctx
  local sub=${POS[0]:-} provider=${POS[1]:-} id secret input='' out
  provider=${provider,,}
  if ! [[ $sub =~ ^(status|set|clear)$ ]] || { [ "$sub" != status ] && ! [[ $provider =~ ^(google|github)$ ]]; }; then
    die 'Usage: deployer oauth status [--json] | deployer oauth set google|github | deployer oauth clear google|github'
  fi
  if [ "$sub" = set ]; then
    if [[ -v DEPLOYER_OAUTH_CLIENT_ID ]]; then
      id=$DEPLOYER_OAUTH_CLIENT_ID secret=${DEPLOYER_OAUTH_CLIENT_SECRET:-}
    else
      { : </dev/tty; } 2>/dev/null || die 'Set DEPLOYER_OAUTH_CLIENT_ID and DEPLOYER_OAUTH_CLIENT_SECRET, or run this in a terminal.'
      printf '    %s Client ID: ' "$provider" >/dev/tty
      IFS= read -r id </dev/tty || id=''
      read_secret 'Client secret (leave empty to keep the saved one)'
      secret=$REPLY
    fi
    input="{\"client_id\":$(json_str "$id"),\"client_secret\":$(json_str "$secret")}"
  fi
  require_running
  if [ "$sub" != status ]; then
    out=$(api_cli "$input" oauth "$sub" --provider "$provider")
    ok "$out"
    [ "$sub" = set ] && next "Test it: open the dashboard's sign-in page and choose \"Continue with ${provider^}\""
    return 0
  fi
  out=$(api_cli '' oauth status)
  [ "$JSON" = 1 ] && { printf '%s\n' "$out"; return 0; }
  # `oauth status` prints indented JSON: one "key": value per line under each provider.
  awk -F'"' '
    /^  "(google|github)": \{/ { p = $2 }
    p && /"client_id"/ { id[p] = ($0 ~ /null/) ? "" : $4 }
    p && /"configured"/ { conf[p] = ($0 ~ /true/) }
    p && /"callback_url"/ { cb[p] = $4 }
    END {
      split("google github", names, " ")
      for (i = 1; i <= 2; i++) {
        n = names[i]
        state = conf[n] ? "configured (Client ID " id[n] ")" : (id[n] ? "Client secret missing" : "not configured")
        printf "\n  %s%s: %s\n    Callback URL: %s\n", toupper(substr(n, 1, 1)), substr(n, 2), state, cb[n]
      }
    }' <<<"$out"
  printf '\n'
  next 'Register each callback URL in that provider'"'"'s OAuth app, then: sudo deployer oauth set google|github' \
    'Guided setup with deep links: dashboard Settings -> Instance settings -> Sign in with Google/GitHub'
}

cmd_reset_password() {
  load_ctx
  local email=${POS[0]:-} password again a out
  if [[ -v DEPLOYER_NEW_PASSWORD ]]; then
    password=$DEPLOYER_NEW_PASSWORD
  else
    read_secret 'New password (at least 10 characters)' || die 'Set DEPLOYER_NEW_PASSWORD, or run this in a terminal.'
    password=$REPLY
    read_secret 'Type it again'
    again=$REPLY
    [ "$password" = "$again" ] || die 'The two passwords are different. Nothing was changed.'
  fi
  require_running
  a=(user reset-password)
  [ -n "$email" ] && a+=(--email "$email")
  out=$(api_cli "{\"password\":$(json_str "$password")}" "${a[@]}")
  ok "$out"
  next 'Sign in with the new password; other sessions of that account were signed out'
}

case "$CMD" in
  help|-h|--help) cmd_help ;;
  guide|tutorial) cmd_guide ;;
  actions|todo) cmd_actions ;;
  install) cmd_install ;;
  status) cmd_status ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  logs) cmd_logs ;;
  update) cmd_update ;;
  backup) cmd_backup ;;
  restore) cmd_restore ;;
  open) cmd_open ;;
  config) cmd_config ;;
  compose) cmd_compose ;;
  uninstall) cmd_uninstall ;;
  set-port) cmd_set_port ;;
  lan) cmd_lan ;;
  autostart) cmd_autostart ;;
  keepawake) cmd_keepawake ;;
  device) cmd_device ;;
  oauth) cmd_oauth ;;
  reset-password) cmd_reset_password ;;
  *)
    err "Unknown command '$CMD'."
    cmd_help
    exit 2
    ;;
esac
