#!/bin/sh
# Deployer tunnel sidecar supervisor (docs/REMOTE_ACCESS.md).
#
# Polls $TUNNEL_STATE_DIR/desired.json (written by the API):
#   {"mode":"off"} | {"mode":"cloudflare","token":"..."} | {"mode":"quick"}, each optionally with
#   "apps_token":"..." (docs/COHOSTING.md "Websites on both PCs": a second connector, for the apps tunnel)
# and keeps exactly one matching cloudflared process running (plus the apps connector when asked),
# restarting each with exponential backoff. Both honour TUNNEL_TRANSPORT_PROTOCOL (inherited).
# Reports {"mode","running","pid","started_at","quick_url","last_error","apps","updated_at"} in
# status.json, `apps` = {"running","started_at","last_error"} or null (atomic replace; rewritten on
# every change and at least every 15 s as a heartbeat).
#
# Connector tokens reach cloudflared only through the TUNNEL_TOKEN environment variable of the child
# process, never on its command line, and are never printed.
set -u

STATE_DIR="${TUNNEL_STATE_DIR:-/tunnel}"
CLOUDFLARED="${CLOUDFLARED_BIN:-/usr/local/bin/cloudflared}"
ORIGIN_URL="${TUNNEL_ORIGIN_URL:-http://caddy:8081}"
POLL_SECONDS="${TUNNEL_POLL_SECONDS:-3}"
METRICS_ADDR="${TUNNEL_METRICS_ADDR:-127.0.0.1:20241}"
LOG_FILE="${TUNNEL_LOG_FILE:-/tmp/cloudflared.log}"
APPS_METRICS_ADDR="${TUNNEL_APPS_METRICS_ADDR:-127.0.0.1:20242}"
APPS_LOG_FILE="${TUNNEL_APPS_LOG_FILE:-/tmp/cloudflared-apps.log}"
HEARTBEAT_SECONDS=15
BACKOFF_MAX=60
STABLE_SECONDS=60
LOG_MAX_BYTES=1048576

DESIRED="$STATE_DIR/desired.json"
STATUS="$STATE_DIR/status.json"

umask 077

child_pid=""
current_sig=""
current_mode="off"
current_token=""
started_at=""
started_epoch=0
quick_url=""
last_error=""
exit_error=""
backoff=1
next_start=0
printed_lines=0
last_json=""
last_write_epoch=0
sleep_pid=""
apps_pid=""
apps_token=""
apps_started_at=""
apps_started_epoch=0
apps_exit_error=""
apps_backoff=1
apps_next_start=0
apps_printed=0

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [supervisor] $*"
}

now_iso() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

now_epoch() {
    date +%s
}

# True while process $1 exists and is not a zombie.
pid_alive() {
    [ -n "$1" ] || return 1
    [ -r "/proc/$1/stat" ] || return 1
    state=$(sed -n 's/^.*) \(.\).*$/\1/p' "/proc/$1/stat" 2>/dev/null)
    [ -n "$state" ] && [ "$state" != "Z" ] && [ "$state" != "X" ]
}

child_alive() {
    pid_alive "$child_pid"
}

# Sets want_mode / want_token; returns 1 (keeping the current state) if desired.json is unusable.
read_desired() {
    want_mode="off"
    want_token=""
    want_apps_token=""
    desired_error=""
    [ -e "$DESIRED" ] || return 0
    if ! want_mode=$(jq -er '.mode | strings' "$DESIRED" 2>/dev/null); then
        desired_error="desired.json is unreadable or invalid"
        return 1
    fi
    want_apps_token=$(jq -r '.apps_token // "" | strings' "$DESIRED" 2>/dev/null) || want_apps_token=""
    case "$want_mode" in
        off | quick) ;;
        cloudflare)
            want_token=$(jq -r '.token // "" | strings' "$DESIRED" 2>/dev/null) || want_token=""
            ;;
        *)
            desired_error="desired.json has an unknown mode"
            return 1
            ;;
    esac
    return 0
}

# forward_file FILE COUNTER_VARIABLE: prints the lines of FILE not printed yet.
forward_file() {
    file=$1
    eval "printed=\$$2"
    [ -f "$file" ] || return 0
    total=$(wc -l <"$file" 2>/dev/null || echo 0)
    if [ "$total" -lt "$printed" ]; then
        printed=0
    fi
    if [ "$total" -gt "$printed" ]; then
        sed -n "$((printed + 1)),${total}p" "$file"
        printed=$total
    fi
    size=$(wc -c <"$file" 2>/dev/null || echo 0)
    if [ "$size" -gt "$LOG_MAX_BYTES" ]; then
        # The child appends (O_APPEND), so truncating in place is safe.
        : >"$file"
        printed=0
    fi
    eval "$2=\$printed"
}

forward_logs() {
    forward_file "$LOG_FILE" printed_lines
    forward_file "$APPS_LOG_FILE" apps_printed
}

capture_quick_url() {
    [ "$current_mode" = "quick" ] && [ -f "$LOG_FILE" ] || return 0
    url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_FILE" 2>/dev/null | grep -v '^https://api\.' | tail -n 1)
    if [ -n "$url" ] && [ "$url" != "$quick_url" ]; then
        quick_url=$url
        log "quick tunnel URL: $quick_url"
    fi
}

start_child() {
    : >"$LOG_FILE"
    printed_lines=0
    quick_url=""
    case "$current_mode" in
        cloudflare)
            if [ -z "$current_token" ]; then
                last_error="desired.json has no tunnel token"
                return 0
            fi
            TUNNEL_TOKEN="$current_token" "$CLOUDFLARED" tunnel --no-autoupdate --metrics "$METRICS_ADDR" run \
                >>"$LOG_FILE" 2>&1 </dev/null &
            child_pid=$!
            ;;
        quick)
            env -u TUNNEL_TOKEN "$CLOUDFLARED" tunnel --no-autoupdate --metrics "$METRICS_ADDR" --url "$ORIGIN_URL" \
                >>"$LOG_FILE" 2>&1 </dev/null &
            child_pid=$!
            ;;
        *)
            return 0
            ;;
    esac
    started_at=$(now_iso)
    started_epoch=$(now_epoch)
    log "started cloudflared (mode $current_mode, pid $child_pid)"
}

stop_child() {
    [ -n "$child_pid" ] || return 0
    if child_alive; then
        log "stopping cloudflared (pid $child_pid)"
        kill -TERM "$child_pid" 2>/dev/null
        i=0
        while child_alive && [ "$i" -lt 20 ]; do
            sleep 0.5
            i=$((i + 1))
        done
        if child_alive; then
            kill -KILL "$child_pid" 2>/dev/null
        fi
    fi
    wait "$child_pid" 2>/dev/null
    forward_logs
    child_pid=""
    started_at=""
    quick_url=""
}

start_apps() {
    : >"$APPS_LOG_FILE"
    apps_printed=0
    TUNNEL_TOKEN="$apps_token" "$CLOUDFLARED" tunnel --no-autoupdate --metrics "$APPS_METRICS_ADDR" run \
        >>"$APPS_LOG_FILE" 2>&1 </dev/null &
    apps_pid=$!
    apps_started_at=$(now_iso)
    apps_started_epoch=$(now_epoch)
    log "started the apps tunnel connector (pid $apps_pid)"
}

stop_apps() {
    [ -n "$apps_pid" ] || return 0
    if pid_alive "$apps_pid"; then
        log "stopping the apps tunnel connector (pid $apps_pid)"
        kill -TERM "$apps_pid" 2>/dev/null
        i=0
        while pid_alive "$apps_pid" && [ "$i" -lt 20 ]; do
            sleep 0.5
            i=$((i + 1))
        done
        if pid_alive "$apps_pid"; then
            kill -KILL "$apps_pid" 2>/dev/null
        fi
    fi
    wait "$apps_pid" 2>/dev/null
    forward_logs
    apps_pid=""
    apps_started_at=""
}

# Keeps the apps connector running while desired.json has an apps_token (same backoff as above).
supervise_apps() {
    [ -n "$apps_token" ] || return 0
    now=$(now_epoch)
    if [ -n "$apps_pid" ] && ! pid_alive "$apps_pid"; then
        wait "$apps_pid" 2>/dev/null
        code=$?
        forward_logs
        detail=$(grep ' ERR ' "$APPS_LOG_FILE" 2>/dev/null | tail -n 1 | cut -c1-300)
        if [ $((now - apps_started_epoch)) -ge "$STABLE_SECONDS" ]; then
            apps_backoff=1
        fi
        apps_exit_error="apps tunnel connector exited with code $code${detail:+: $detail}"
        log "$apps_exit_error; restarting in ${apps_backoff}s"
        apps_next_start=$((now + apps_backoff))
        apps_backoff=$((apps_backoff * 2))
        [ "$apps_backoff" -le "$BACKOFF_MAX" ] || apps_backoff=$BACKOFF_MAX
        apps_pid=""
        apps_started_at=""
    elif pid_alive "$apps_pid" && [ -n "$apps_exit_error" ] && [ $((now - apps_started_epoch)) -ge "$STABLE_SECONDS" ]; then
        apps_exit_error=""
        apps_backoff=1
    fi
    if [ -z "$apps_pid" ] && [ "$now" -ge "$apps_next_start" ]; then
        start_apps
    fi
}

write_status() {
    if pid_alive "$apps_pid"; then
        apps_running=true
    else
        apps_running=false
    fi
    if [ -n "$apps_token" ]; then
        apps_enabled=true
    else
        apps_enabled=false
    fi
    if child_alive; then
        running=true
        pid=$child_pid
    else
        running=false
        pid=""
    fi
    error=$last_error
    [ -n "$error" ] || error=$exit_error
    json=$(jq -cn \
        --arg mode "$current_mode" \
        --argjson running "$running" \
        --arg pid "$pid" \
        --arg started "$started_at" \
        --arg url "$quick_url" \
        --arg err "$error" \
        --argjson apps_enabled "$apps_enabled" \
        --argjson apps_running "$apps_running" \
        --arg apps_started "$apps_started_at" \
        --arg apps_err "$apps_exit_error" \
        '{mode: $mode, running: $running,
          pid: (if $pid == "" then null else ($pid | tonumber) end),
          started_at: (if $running and $started != "" then $started else null end),
          quick_url: (if $running and $url != "" then $url else null end),
          last_error: (if $err == "" then null else $err end),
          apps: (if $apps_enabled then {running: $apps_running,
                   started_at: (if $apps_running and $apps_started != "" then $apps_started else null end),
                   last_error: (if $apps_err == "" then null else $apps_err end)} else null end)}') || return 0
    now=$(now_epoch)
    if [ "$json" = "$last_json" ] && [ $((now - last_write_epoch)) -lt "$HEARTBEAT_SECONDS" ]; then
        return 0
    fi
    tmp="$STATE_DIR/.status.json.$$"
    if printf '%s\n' "$json" | jq -c --arg ts "$(now_iso)" '. + {updated_at: $ts}' >"$tmp" 2>/dev/null \
        && mv -f "$tmp" "$STATUS"; then
        last_json=$json
        last_write_epoch=$now
    else
        rm -f "$tmp"
        log "could not write $STATUS"
    fi
}

shutdown() {
    log "shutting down"
    [ -n "$sleep_pid" ] && kill "$sleep_pid" 2>/dev/null
    stop_child
    stop_apps
    last_json=""
    write_status
    exit 0
}

trap shutdown TERM INT HUP

log "supervisor started (state dir $STATE_DIR, poll ${POLL_SECONDS}s)"
if [ ! -w "$STATE_DIR" ]; then
    log "WARNING: $STATE_DIR is not writable by uid $(id -u)"
fi

while :; do
    if read_desired; then
        last_error=""
        sig="$want_mode|$want_token"
        if [ "$sig" != "$current_sig" ]; then
            stop_child
            current_sig=$sig
            current_mode=$want_mode
            current_token=$want_token
            exit_error=""
            backoff=1
            next_start=0
            log "desired mode: $current_mode"
        fi
        if [ "$want_apps_token" != "$apps_token" ]; then
            stop_apps
            apps_token=$want_apps_token
            apps_exit_error=""
            apps_backoff=1
            apps_next_start=0
            if [ -n "$apps_token" ]; then
                log "apps tunnel connector: on"
            else
                log "apps tunnel connector: off"
            fi
        fi
    else
        last_error=$desired_error
    fi

    if [ "$current_mode" != "off" ]; then
        now=$(now_epoch)
        if [ -n "$child_pid" ] && ! child_alive; then
            wait "$child_pid" 2>/dev/null
            code=$?
            forward_logs
            detail=$(grep ' ERR ' "$LOG_FILE" 2>/dev/null | tail -n 1 | cut -c1-300)
            if [ $((now - started_epoch)) -ge "$STABLE_SECONDS" ]; then
                backoff=1
            fi
            exit_error="cloudflared exited with code $code${detail:+: $detail}"
            log "$exit_error; restarting in ${backoff}s"
            next_start=$((now + backoff))
            backoff=$((backoff * 2))
            [ "$backoff" -le "$BACKOFF_MAX" ] || backoff=$BACKOFF_MAX
            child_pid=""
            started_at=""
            quick_url=""
        elif child_alive && [ -n "$exit_error" ] && [ $((now - started_epoch)) -ge "$STABLE_SECONDS" ]; then
            exit_error=""
            backoff=1
        fi
        if [ -z "$child_pid" ] && [ "$now" -ge "$next_start" ]; then
            start_child
        fi
    fi

    supervise_apps
    forward_logs
    capture_quick_url
    write_status

    sleep "$POLL_SECONDS" &
    sleep_pid=$!
    wait "$sleep_pid" 2>/dev/null
    sleep_pid=""
done
