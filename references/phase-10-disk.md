# Phase 10 — Disk Hygiene

## Goal

Report `~/.claude/` disk usage, identify the two specific classes of files
that are safe to delete without user-visible consequences, and flag old
claude-tune backup runs for pruning.

## What the script does

1. `du -sh` top 10 subdirs under `~/.claude/` for inventory.
2. Count files under `~/.claude/telemetry/` whose name contains "failed" —
   these are first-party telemetry batches that failed to upload. The
   telemetry server will re-try current sessions, but old failed batches
   are effectively regenerable: if a batch didn't upload after a few days,
   it won't, and the data is already staged elsewhere.
3. Walk `~/.claude/backups/claude-tune/` for run directories older than
   `CLAUDE_TUNE_BACKUP_MAX_AGE` days (default 14). Report them for prune.

## The "safe auto-delete" category

Only ONE type of file qualifies:

**Failed telemetry event batches** — `~/.claude/telemetry/*failed*.json`
files. They are first-party (1p) event batches that failed to upload and
have been sitting unchanged for weeks. Deleting them:

- Does not affect future telemetry (new batches use fresh files)
- Does not affect user-visible state
- Does not affect anything Claude Code needs to function

The skill in Mode A MAY auto-delete these after one combined approval.
In Mode B it's proposed per-item.

## The "never auto-delete" categories

- **`~/.claude/projects/*.jsonl`** — session logs. These contain your entire
  conversation history. The skill never proposes deleting these unless the
  user explicitly asks ("delete session logs older than N days"). Even
  then, it's a destructive operation with per-item approval.
- **`~/.claude/plugins/cache/`** — plugin packages. Deletion means
  re-downloading from the marketplace. Only proposed when the user
  explicitly chooses to uninstall a plugin (Phase 4).
- **`~/.claude/backups/claude-tune/` recent runs** — the skill's own
  backups. Too valuable to auto-delete. Only prunes runs older than 14 days
  AND after explicit per-item approval.

## Old backup pruning

claude-tune accumulates a new backup directory per run. Over many runs
these add up. The phase flags any run directory older than
`CLAUDE_TUNE_BACKUP_MAX_AGE` days (default 14) as a prune candidate. The
user approves pruning on a per-directory basis.

A pruned backup cannot be restored. The skill reminds the user before
proposing deletion.

## Report table shape

```
DISK (~/.claude, total 632 MB)
==============================
Top 10:
Size    Path
-----   ---------------------------------
470M    ~/.claude/projects
 92M    ~/.claude/plugins
 31M    ~/.claude/telemetry
 15M    ~/.claude/file-history
  5M    ~/.claude/shell-snapshots
  ...

Failed telemetry batches: 47 files (12.3 MB)    🟢 safe auto-delete
Old claude-tune backups (>14d): 3 runs (8.1 MB)  🟠 prune with approval
```

## Cleanup actions

- **Failed telemetry:** `rm ~/.claude/telemetry/*failed*.json`. Mode A can
  apply this after the combined approval; Mode B asks per-item.
- **Old backups:** `rm -rf <backup-run-dir>`. Per-item approval, even in
  Mode A. The skill notes: "cannot be restored".
- **Everything else:** informational. No action proposed.
