#!/usr/bin/env bash
# claude-tune snapshot primitive.
# Copies a target file to ~/.claude/backups/claude-tune/<run-ts>/<flat>.bak
# and prints a SNAPSHOT: line and a ROLLBACK: line to stdout.
#
# Usage: snapshot.sh <absolute-or-$HOME-rooted target file>
# Exit: 0 on success, 1 on any error (caller must block the mutation on failure).

set -euo pipefail

# Resolve script dir for sourcing lib
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

target="${1:-}"
if [ -z "$target" ]; then
    ct_die "snapshot.sh: missing target file argument"
fi

if [ ! -e "$target" ]; then
    ct_die "snapshot.sh: target does not exist: $target"
fi

# Refuse to snapshot anything outside the allowed roots. Patterns are
# strictly anchored — substring matches like "*.claude*" are deliberately
# avoided so a path like "evil-dir/.claude.json.evil" cannot slip through.
allowed=0
case "$target" in
    "$HOME/.claude"/*|"$HOME/.claude") allowed=1 ;;
    "$HOME/.claude.json")              allowed=1 ;;
    "$PWD"/.claude/*|"$PWD"/.mcp.json|"$PWD"/CLAUDE.md) allowed=1 ;;
    "$PWD"/*/.claude/*|"$PWD"/*/.mcp.json|"$PWD"/*/CLAUDE.md) allowed=1 ;;
esac
if [ "$allowed" -ne 1 ]; then
    ct_die "snapshot.sh: refusing to snapshot outside allowed roots (~/.claude, ~/.claude.json, project .claude/, project .mcp.json, project CLAUDE.md): $target"
fi

ts=$(ct_run_ts)
backup_dir="$CLAUDE_TUNE_BACKUPS/$ts"

if ! mkdir -p "$backup_dir" 2>/dev/null; then
    ct_die "snapshot.sh: cannot create backup dir: $backup_dir"
fi

# Defense in depth: snapshots may inherit a readable source file mode,
# so tighten the backup tree to owner-only. Best-effort; ignore failures.
chmod 700 "$CLAUDE_TUNE_BACKUPS" 2>/dev/null || true
chmod 700 "$backup_dir" 2>/dev/null || true

# Flatten path: strip $HOME, replace / with __, strip leading __
rel="${target#$HOME/}"
flat="${rel//\//__}"
flat="${flat#__}"

# If an earlier snapshot for the same target exists in this run, append .N
base="$backup_dir/${flat}.bak"
dest="$base"
i=1
while [ -e "$dest" ]; do
    dest="${base}.${i}"
    i=$((i+1))
done

if ! cp -p "$target" "$dest" 2>/dev/null; then
    ct_die "snapshot.sh: cp failed: $target -> $dest"
fi

printf 'SNAPSHOT: %s\n' "$dest"
printf 'ROLLBACK: cp -p %q %q\n' "$dest" "$target"
