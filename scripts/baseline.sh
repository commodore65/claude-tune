#!/usr/bin/env bash
# claude-tune Phase 0 — baseline snapshot of counts and disk usage.
# Writes baseline.json under ~/.claude/backups/claude-tune/<run-ts>/
# and echoes a compact summary table on stderr.
#
# Output JSON shape:
# {
#   "run_ts": "...",
#   "counts": {"skills": N, "agents": N, "hooks_global": N, "plugins_enabled": N,
#              "mcp_global": N, "memory_files": N, "projects_json_entries": N},
#   "disk_bytes": {"<path>": N, ...},
#   "claude_version": "...",
#   "observation_window_days": N
# }

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

ts=$(ct_run_ts)
out_dir="$CLAUDE_TUNE_BACKUPS/$ts"
mkdir -p "$out_dir"
chmod 700 "$CLAUDE_TUNE_BACKUPS" 2>/dev/null || true
chmod 700 "$out_dir" 2>/dev/null || true
out_file="$out_dir/baseline.json"

count_dir() {
    # Count subdirectories under <d>, following symlinks (skills/agents are often symlinks).
    local d="$1"
    [ -d "$d" ] || { echo 0; return; }
    find -L "$d" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' '
}

count_files_recursive() {
    local d="$1" glob="$2"
    [ -d "$d" ] || { echo 0; return; }
    find "$d" -type f -name "$glob" 2>/dev/null | wc -l | tr -d ' '
}

# Counts
skills=$(count_dir "$CLAUDE_HOME/skills")
agents=$(count_files_recursive "$CLAUDE_HOME/agents" "*.md")
memory_files=$(count_files_recursive "$CLAUDE_HOME/projects" "*.md")
hooks_global=0
plugins_enabled=0
mcp_global=0
projects_json_entries=0

# Single Python pass parses both settings.json and ~/.claude.json,
# emits four numbers that we read straight into shell variables.
# Honors $CLAUDE_HOME and $CLAUDE_JSON (set by lib/common.sh).
if ct_have python3; then
    read -r hooks_global plugins_enabled mcp_global projects_json_entries < <(
        python3 - "$CLAUDE_HOME/settings.json" "$CLAUDE_JSON" <<'PY' 2>/dev/null
import json, sys

def load(path):
    try:
        return json.load(open(path))
    except Exception:
        return {}

s = load(sys.argv[1])
c = load(sys.argv[2])

hooks = sum(
    len(item.get("hooks") or [])
    for lst in (s.get("hooks") or {}).values()
    for item in (lst or [])
)
plugins = sum(1 for v in (s.get("enabledPlugins") or {}).values() if v)
mcp = len(c.get("mcpServers") or {})
projects = len(c.get("projects") or {})
print(hooks, plugins, mcp, projects)
PY
    ) || { hooks_global=0; plugins_enabled=0; mcp_global=0; projects_json_entries=0; }
fi

# Observation window — call claude_logs.py with explicit JSON output.
# (claude_logs.py honors --json and prints {"observation_window_days": N})
obs_window=0
if ct_have python3; then
    obs_window=$(python3 "$SCRIPT_DIR/lib/claude_logs.py" --json 2>/dev/null \
        | python3 -c "import json, sys; d=json.load(sys.stdin); print(d.get('observation_window_days', 0))" \
        2>/dev/null || echo 0)
fi
[ -z "$obs_window" ] && obs_window=0

# Disk usage for top dirs under ~/.claude
disk_entries=""
if [ -d "$CLAUDE_HOME" ]; then
    while IFS=$'\t' read -r bytes path; do
        [ -z "$path" ] && continue
        if [ -n "$disk_entries" ]; then disk_entries="$disk_entries,"; fi
        disk_entries=$disk_entries$(printf '%s: %s' "$(ct_json_str "$path")" "$bytes")
    done < <(du -sk "$CLAUDE_HOME"/* 2>/dev/null | sort -rn | head -10 | awk '{printf "%d\t%s\n", $1*1024, $2}')
fi

# Claude Code version (best-effort)
claude_version="unknown"
if ct_have claude; then
    claude_version=$(claude --version 2>/dev/null | head -1 | awk '{print $NF}' || echo unknown)
fi

# Emit JSON
{
    printf '{\n'
    printf '  "run_ts": %s,\n'                   "$(ct_json_str "$ts")"
    printf '  "claude_version": %s,\n'           "$(ct_json_str "$claude_version")"
    printf '  "observation_window_days": %s,\n'  "$obs_window"
    printf '  "counts": {\n'
    printf '    "skills": %s,\n'                 "$skills"
    printf '    "agents": %s,\n'                 "$agents"
    printf '    "hooks_global": %s,\n'           "$hooks_global"
    printf '    "plugins_enabled": %s,\n'        "$plugins_enabled"
    printf '    "mcp_global": %s,\n'             "$mcp_global"
    printf '    "memory_files": %s,\n'           "$memory_files"
    printf '    "projects_json_entries": %s\n'   "$projects_json_entries"
    printf '  },\n'
    printf '  "disk_bytes": { %s }\n'            "$disk_entries"
    printf '}\n'
} > "$out_file"

# Brief summary on stderr
{
    printf 'BASELINE (run %s)\n' "$ts"
    printf '  skills: %s   agents: %s   memory files: %s\n' "$skills" "$agents" "$memory_files"
    printf '  hooks: %s   enabled plugins: %s   MCP servers: %s\n' "$hooks_global" "$plugins_enabled" "$mcp_global"
    printf '  ~/.claude.json project entries: %s\n' "$projects_json_entries"
    printf '  observation window (session logs): %s days\n' "$obs_window"
    printf '  written: %s\n' "$out_file"
} >&2

# Path to baseline on stdout so callers can read it programmatically
printf '%s\n' "$out_file"
