#!/bin/sh
# Deployer tunnel sidecar supervisor (docs/REMOTE_ACCESS.md).
#
# Polls $TUNNEL_STATE_DIR/desired.json (written by the API):
#   {"mode":"off"} | {"mode":"cloudflare","token":"..."} | {"mode":"quick"}
# and keeps exactly one matching cloudflared process running, restarting it with exponential backoff.
# Reports {"mode","running","pid","started_at","quick_url","last_error","updated_at"} in status.json
# (atomic replace; rewritten on every change and at least every 15 s as a heartbeat).
#
# The connector token reaches cloudflared only through the TUNNEL_TOKEN environment variable of the
# child process, never on its command line, and is never printed.
set -u

STATE_DIR="${TUNNEL_STATE_DIR:-/tunnel}"
CLOUDFLARED="${CLOUDFLARED_BIN:-/usr/local/bin/cloudflared}"
ORIGIN_URL="${TUNNEL_ORIGIN_URL:-http://caddy:8081}"
POLL_SECONDS="${TUNNEL_POLL_SECONDS:-3}"
METRICS_ADDR="${TUNNEL_METRICS_ADDR:-127.0.0.1:20241}"
LOG_FILE="${TUNNEL_LOG_FILE:-/tmp/cloudflared.log}"
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

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [supervisor] $*"
}

now_iso() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

now_epoch() {
    date +%s
}

# True while the child exists and is not a zombie.
child_alive() {
    [ -n "$child_pid" ] || return 1
    [ -r "/proc/$child_pid/stat" ] || return 1
    state=$(sed -n 's/^.*) \(.\).*$/\1/p' "/proc/$child_pid/stat" 2>/dev/null)
    [ -n "$state" ] && [ "$state" != "Z" ] && [ "$state" != "X" ]
}

# Sets want_mode / want_token; returns 1 (keeping the current state) if desired.json is unusable.
read_desired() {
    want_mode="off"
    want_token=""
    desired_error=""
    [ -e "$DESIRED" ] || return 0
    if ! want_mode=$(jq -er '.mode | strings' "$DESIRED" 2>/dev/null); then
        desired_error="desired.json is unreadable or invalid"
        return 1
    fi
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

forward_logs() {
    [ -f "$LOG_FILE" ] || return 0
    total=$(wc -l <"$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$total" -lt "$printed_lines" ]; then
        printed_lines=0
    fi
    if [ "$total" -gt "$printed_lines" ]; then
        sed -n "$((printed_lines + 1)),${total}p" "$LOG_FILE"
        printed_lines=$total
    fi
    size=$(wc -c <"$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$size" -gt "$LOG_MAX_BYTES" ]; then
        # The child appends (O_APPEND), so truncating in place is safe.
        : >"$LOG_FILE"
        printed_lines=0
    fi
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

write_status() {
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
        '{mode: $mode, running: $running,
          pid: (if $pid == "" then null else ($pid | tonumber) end),
          started_at: (if $running and $started != "" then $started else null end),
          quick_url: (if $running and $url != "" then $url else null end),
          last_error: (if $err == "" then null else $err end)}') || return 0
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

    forward_logs
    capture_quick_url
    write_status

    sleep "$POLL_SECONDS" &
    sleep_pid=$!
    wait "$sleep_pid" 2>/dev/null
    sleep_pid=""
done
