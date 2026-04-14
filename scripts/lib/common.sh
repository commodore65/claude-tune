#!/usr/bin/env bash
# claude-tune — shared bash helpers
# Sourced by every bash script in scripts/.
# Pure POSIX where possible; one or two bashisms (arrays) accepted.

# -------- Paths --------
: "${CLAUDE_HOME:=$HOME/.claude}"
: "${CLAUDE_JSON:=$HOME/.claude.json}"
: "${CLAUDE_TUNE_BACKUPS:=$CLAUDE_HOME/backups/claude-tune}"
: "${CLAUDE_TUNE_RUN_TS_FILE:=/tmp/claude-tune-run-ts}"

# -------- Run timestamp (stable within one run) --------
ct_run_ts() {
    if [ -r "$CLAUDE_TUNE_RUN_TS_FILE" ]; then
        cat "$CLAUDE_TUNE_RUN_TS_FILE"
        return 0
    fi
    local ts
    ts=$(date -u +"%Y-%m-%dT%H-%M-%SZ")
    printf '%s' "$ts" > "$CLAUDE_TUNE_RUN_TS_FILE"
    printf '%s' "$ts"
}

# -------- Severity emoji --------
ct_emoji_ok()   { printf '🟢'; }
ct_emoji_warn() { printf '🟠'; }
ct_emoji_bad()  { printf '🔴'; }

# -------- JSON emit helpers (stdout JSON without jq) --------
# ct_json_str <value>   → JSON-escaped string literal, quotes included
ct_json_str() {
    local s="$1"
    # Strip C0 control chars except the three we explicitly escape below.
    # Avoids emitting invalid JSON when upstream data (e.g. ps output) contains
    # bell, backspace, or NUL bytes.
    s=$(printf '%s' "$s" | tr -d '\000-\010\013\014\016-\037')
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\n'/\\n}
    s=${s//$'\r'/\\r}
    s=${s//$'\t'/\\t}
    printf '"%s"' "$s"
}

# -------- Error helpers --------
ct_die() {
    printf 'claude-tune: %s\n' "$*" >&2
    exit 1
}

ct_warn() {
    printf 'claude-tune: %s\n' "$*" >&2
}

# -------- Environment probes --------
ct_have() {
    command -v "$1" >/dev/null 2>&1
}

# -------- Cross-platform stat helpers (BSD/macOS vs GNU/Linux) --------
if stat --version >/dev/null 2>&1; then
    ct_file_size()  { stat -c '%s' "$1" 2>/dev/null; }
    ct_file_mtime() { stat -c '%Y' "$1" 2>/dev/null; }
else
    ct_file_size()  { stat -f '%z' "$1" 2>/dev/null; }
    ct_file_mtime() { stat -f '%m' "$1" 2>/dev/null; }
fi

# Dry-run support: callers check this and skip mutations if set
ct_is_dry_run() {
    [ "${CLAUDE_TUNE_DRY_RUN:-0}" = "1" ]
}
