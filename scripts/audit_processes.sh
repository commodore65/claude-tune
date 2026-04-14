#!/usr/bin/env bash
# claude-tune Phase 1 — live processes audit.
#
# Finds orphan claude sessions, orphan MCP children, long-running codex
# app-server brokers, stale dev servers, and generic "my session vs orphan"
# classification.
#
# The current claude session's process tree is EXCLUDED from orphan reporting
# by walking up from the hook's own $PPID until we find a `claude` ancestor,
# then collecting its descendants.
#
# Emits JSON on stdout:
# {
#   "orphans": [{pid, ppid, etime, command}],
#   "heavy":   [{pid, ppid, cpu, mem, command}],
#   "mine":    [{pid, command}]
# }

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

# --- Orphan detection patterns (generic; no user-specific binaries) ---
# Dev servers with meaningful default threshold
DEV_PATTERNS='uvicorn|vite|next-router-worker|next dev|bun .*(dev|server|run)|nodemon|tsx watch|cloudflared tunnel|ngrok|localtunnel|webpack\.dev|parcel|turbopack|fastapi|flask run|gunicorn.*reload|hugo server|gatsby develop'
# Tooling (Claude/Codex/MCP) with longer threshold
TOOL_PATTERNS='claude --dangerously|codex app-server|app-server-broker\.mjs|mcp-server|-mcp\b|/mcp-[a-zA-Z0-9]'

DEV_THRESHOLD_MIN="${CLAUDE_TUNE_DEV_STALE_MIN:-30}"
TOOL_THRESHOLD_MIN="${CLAUDE_TUNE_TOOL_STALE_MIN:-2880}"  # 48h

# Optional comma-separated PID allow-list — these PIDs are never reported
# as orphans even if they match a stale pattern. See phase-01-processes.md.
ALLOW_PIDS_RAW="${CLAUDE_TUNE_ORPHAN_ALLOW_PIDS:-}"
if [ -n "$ALLOW_PIDS_RAW" ] && ! [[ "$ALLOW_PIDS_RAW" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
    ct_warn "ignoring malformed CLAUDE_TUNE_ORPHAN_ALLOW_PIDS: $ALLOW_PIDS_RAW"
    ALLOW_PIDS_RAW=""
fi

# --- Find current claude tree to exclude from orphan reporting ---
find_current_claude() {
    local p="$PPID"
    while [ -n "$p" ] && [ "$p" -gt 1 ]; do
        local comm
        comm=$(ps -o comm= -p "$p" 2>/dev/null | awk '{print $1}')
        if [ "$(basename "${comm:-}")" = "claude" ]; then
            printf '%s' "$p"
            return
        fi
        p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
        [ -z "$p" ] && break
    done
}

collect_descendants() {
    printf '%s\n' "$1"
    local c
    for c in $(pgrep -P "$1" 2>/dev/null || true); do
        collect_descendants "$c"
    done
}

EXCLUDE=""
CURR=$(find_current_claude || true)
if [ -n "${CURR:-}" ]; then
    EXCLUDE=" $(collect_descendants "$CURR" | tr '\n' ' ') "
fi

# --- Collect process rows ---
orphans_json=""
heavy_json=""
mine_json=""

etime_to_minutes() {
    local et="$1"
    local days h m s
    if [[ "$et" == *-* ]]; then
        days="${et%%-*}"
        local rest="${et#*-}"
        IFS=: read -r h m s <<<"$rest"
        echo $((days * 1440 + 10#$h * 60 + 10#$m))
    elif [ "$(echo "$et" | tr -cd ':' | wc -c | tr -d ' ')" -eq 2 ]; then
        IFS=: read -r h m s <<<"$et"
        echo $((10#$h * 60 + 10#$m))
    else
        IFS=: read -r m s <<<"$et"
        echo $((10#$m))
    fi
}

append_orphan() {
    if [ -n "$orphans_json" ]; then orphans_json="$orphans_json,"; fi
    orphans_json="$orphans_json$1"
}
append_heavy() {
    if [ -n "$heavy_json" ]; then heavy_json="$heavy_json,"; fi
    heavy_json="$heavy_json$1"
}
append_mine() {
    if [ -n "$mine_json" ]; then mine_json="$mine_json,"; fi
    mine_json="$mine_json$1"
}

while IFS= read -r line; do
    [ -z "$line" ] && continue
    etime=$(echo "$line" | awk '{print $1}')
    pid=$(echo "$line"  | awk '{print $2}')
    ppid=$(echo "$line" | awk '{print $3}')
    cmd=$(echo "$line"  | awk '{for(i=4;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ *$//')

    # Check exclusion
    if [ -n "$EXCLUDE" ] && [[ "$EXCLUDE" == *" $pid "* ]]; then
        append_mine "$(printf '{"pid": %s, "command": %s}' "$pid" "$(ct_json_str "$cmd")")"
        continue
    fi

    # User-supplied allow-list
    if [ -n "$ALLOW_PIDS_RAW" ] && [[ ",$ALLOW_PIDS_RAW," == *",$pid,"* ]]; then
        continue
    fi

    # Match against patterns
    if echo "$cmd" | grep -Eq "$TOOL_PATTERNS"; then
        threshold=$TOOL_THRESHOLD_MIN
    elif echo "$cmd" | grep -Eq "$DEV_PATTERNS"; then
        threshold=$DEV_THRESHOLD_MIN
    else
        continue
    fi

    total_min=$(etime_to_minutes "$etime")
    if [ "$total_min" -ge "$threshold" ]; then
        entry=$(printf '{"pid": %s, "ppid": %s, "etime_min": %s, "command": %s}' \
            "$pid" "$ppid" "$total_min" "$(ct_json_str "$cmd")")
        append_orphan "$entry"
    fi
done < <(ps -eo etime,pid,ppid,command 2>/dev/null | tail -n +2 | grep -v grep)

# Heavy CPU/mem processes (top 5 by CPU, excluding system stuff we can't help)
while IFS= read -r line; do
    pid=$(echo "$line"   | awk '{print $1}')
    cpu=$(echo "$line"   | awk '{print $2}')
    mem=$(echo "$line"   | awk '{print $3}')
    cmd=$(echo "$line"   | awk '{for(i=4;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ *$//')
    # Skip our own exclusion tree
    if [ -n "$EXCLUDE" ] && [[ "$EXCLUDE" == *" $pid "* ]]; then continue; fi
    entry=$(printf '{"pid": %s, "cpu": %s, "mem": %s, "command": %s}' \
        "$pid" "$cpu" "$mem" "$(ct_json_str "$cmd")")
    append_heavy "$entry"
done < <(ps -axo pid,%cpu,%mem,command 2>/dev/null | sort -k2 -rn | head -6 | tail -5)

printf '{\n'
printf '  "orphans": [%s],\n' "$orphans_json"
printf '  "heavy":   [%s],\n' "$heavy_json"
printf '  "mine":    [%s]\n'  "$mine_json"
printf '}\n'
