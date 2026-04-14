#!/usr/bin/env bash
# claude-tune Phase 10 — disk hygiene audit.
#
# Reports top-level dirs under ~/.claude by size, counts failed telemetry
# batches (the only "provably regenerable" auto-delete candidate), and
# flags old claude-tune backup runs.
#
# Emits JSON on stdout:
# {
#   "top": [{path, bytes}],
#   "telemetry_failed": N,
#   "telemetry_failed_bytes": N,
#   "old_backups": [{path, age_days, bytes}],
#   "total_bytes": N
# }

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

BACKUP_MAX_AGE_DAYS="${CLAUDE_TUNE_BACKUP_MAX_AGE:-14}"

[ -d "$CLAUDE_HOME" ] || { printf '{"top": [], "telemetry_failed": 0, "telemetry_failed_bytes": 0, "old_backups": [], "total_bytes": 0}\n'; exit 0; }

# Top 10 by bytes
top_json=""
while IFS=$'\t' read -r bytes path; do
    [ -z "$path" ] && continue
    entry=$(printf '{"path": %s, "bytes": %s}' "$(ct_json_str "$path")" "$bytes")
    if [ -n "$top_json" ]; then top_json="$top_json,"; fi
    top_json="$top_json$entry"
done < <(du -sk "$CLAUDE_HOME"/* 2>/dev/null | sort -rn | head -10 | awk '{printf "%d\t%s\n", $1*1024, $2}')

# Telemetry failed events (regenerable)
tel_dir="$CLAUDE_HOME/telemetry"
tel_count=0
tel_bytes=0
if [ -d "$tel_dir" ]; then
    tel_count=$(find "$tel_dir" -type f -name '*failed*' 2>/dev/null | wc -l | tr -d ' ')
    if [ "$tel_count" -gt 0 ]; then
        tel_bytes=0
        while IFS= read -r f; do
            sz=$(ct_file_size "$f")
            tel_bytes=$((tel_bytes + ${sz:-0}))
        done < <(find "$tel_dir" -type f -name '*failed*' 2>/dev/null)
    fi
fi

# Old claude-tune backup runs
old_backups_json=""
backup_root="$CLAUDE_HOME/backups/claude-tune"
if [ -d "$backup_root" ]; then
    now=$(date +%s)
    while IFS= read -r run_dir; do
        [ -z "$run_dir" ] && continue
        mtime=$(ct_file_mtime "$run_dir")
        [ -z "$mtime" ] && continue
        age_days=$(( (now - mtime) / 86400 ))
        if [ "$age_days" -ge "$BACKUP_MAX_AGE_DAYS" ]; then
            bytes=$(du -sk "$run_dir" 2>/dev/null | awk '{print $1*1024}')
            entry=$(printf '{"path": %s, "age_days": %s, "bytes": %s}' \
                "$(ct_json_str "$run_dir")" "$age_days" "${bytes:-0}")
            if [ -n "$old_backups_json" ]; then old_backups_json="$old_backups_json,"; fi
            old_backups_json="$old_backups_json$entry"
        fi
    done < <(find "$backup_root" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
fi

total_bytes=$(du -sk "$CLAUDE_HOME" 2>/dev/null | awk '{print $1*1024}')

printf '{\n'
printf '  "top": [%s],\n' "$top_json"
printf '  "telemetry_failed": %s,\n' "$tel_count"
printf '  "telemetry_failed_bytes": %s,\n' "${tel_bytes:-0}"
printf '  "old_backups": [%s],\n' "$old_backups_json"
printf '  "total_bytes": %s\n' "${total_bytes:-0}"
printf '}\n'
