# Safety Model

## TOC

1. The hierarchy of trust
2. Snapshot pattern
3. Safe vs destructive ops (the classification)
4. Approval grammar — Mode A single-gate
5. Approval grammar — Mode B per-phase
6. Rollback semantics
7. Non-rollbackable actions
8. Dry-run mode

## 1. The hierarchy of trust

claude-tune operates under a strict hierarchy:

1. **Read** — always allowed. Audits produce findings without any writes.
2. **Snapshot** — always allowed before any write. Nothing mutates the
   filesystem until its target has been copied to
   `~/.claude/backups/claude-tune/<run-ts>/`.
3. **Safe mutation** — a value flip or a regenerable-file deletion that
   the skill has proven cannot break the user's state. Applied after ONE
   combined approval in Mode A; per-item approval in Mode B.
4. **Destructive mutation** — any `rm`, any JSON key deletion, any `kill`.
   ALWAYS per-item approval, even in Mode A. Never bundled.

The skill must never cross a level without explicit user consent for that
level. If the user approves "safe mutations only" in Mode A, the skill
stops at level 3 and reports destructive items as "declined".

## 2. Snapshot pattern

Before any mutation of any file, call `scripts/snapshot.sh <target>`.

Snapshot path convention:

```
~/.claude/backups/claude-tune/<run-ts>/<flat-basename>.bak
```

Where:

- `<run-ts>` is a single UTC timestamp per run, stored in
  `/tmp/claude-tune-run-ts` on first call and re-used across snapshots
  within the same run.
- `<flat-basename>` is the target's absolute path with `/` replaced by
  `__`, stripping the leading `~/` or `$HOME/` prefix.

Examples:

| Target                                   | Flat basename                                  |
| ---------------------------------------- | ---------------------------------------------- |
| `~/.claude/settings.json`                | `.claude__settings.json.bak`                   |
| `~/.claude.json`                         | `.claude.json.bak`                             |
| `~/Desktop/cc/foo/.claude/settings.json` | `Desktop__cc__foo__.claude__settings.json.bak` |

If the same target is snapshotted twice in one run (e.g., `settings.json`
mutated for hooks and then again for permissions), the second snapshot
appends `.1`, `.2`, etc.

On successful snapshot, `snapshot.sh` prints two lines to stdout:

```
SNAPSHOT: <absolute snapshot path>
ROLLBACK: cp -p <snapshot path> <target>
```

The skill MUST capture both lines, propagate the ROLLBACK line to the
rollback cookbook, and only THEN execute the mutation.

## 3. Safe vs destructive ops

### Safe (Mode A autopilot may apply after one combined approval)

- **JSON value flip**: `enabled: true → false` for a plugin in
  `settings.json`. No data is deleted, only a boolean toggles.
- **Telemetry failed-batch deletion**: `rm ~/.claude/telemetry/*failed*.json`.
  Files are first-party event batches that failed to upload and have not
  changed for weeks. They are regenerable and the deletion does not
  affect future telemetry.
- **JSON whitespace normalization**: rewriting a JSON file with
  pretty-printed indentation. No data change.

### Destructive (always per-item approval)

- **Any `rm`** of any file EXCEPT telemetry failed batches.
- **JSON key deletion** in settings.json or ~/.claude.json. Distinct from
  value flips: deleting an entire `mcpServers.<name>` entry is destructive
  (data is gone), flipping `enabled: false` is not.
- **`kill` of any process** unless ALL these conditions hold:
  1. Process parent is gone (PPID == 1)
  2. Process age is > 5 minutes
  3. Process name matches a generic orphan regex (from Phase 1's pattern
     list, not user-specific)
  4. No other process of the same name is in the "mine" set (current
     claude tree)
     Even then, the user must confirm per-PID. Mode A never auto-kills.
- **Recursive directory deletions** (`rm -rf`) — always per-item.

Ambiguous? Treat as destructive.

## 4. Approval grammar — Mode A single-gate

After the findings report, the skill emits ONE consolidated approval
prompt:

```
CLAUDE-TUNE — ACTIONS READY FOR YOUR APPROVAL
=============================================

SAFE CLEANUPS (provably non-destructive):
  [1] Delete <N> telemetry failed-event batches (<size>)
      from ~/.claude/telemetry/
  [2] Disable unused plugin '<name>' in settings.json
  [3] Remove <N> dead project entries from ~/.claude.json
      -> <path>  (deleted <date>)
      -> ... (list continues, or "(full list via EXPLAIN 3)")

DESTRUCTIVE ACTIONS (require explicit confirmation):
  [4] Kill <N> orphan processes:
      PID <pid> <cmd>  (parent gone, age <N>)
      ...
  [5] Delete <N> stale memory files:
      <path>  (<N> days old, dead refs <N>)
      ...
  [6] Uninstall <N> disabled plugins (disk reclaim <size>):
      <name> (<size>)
      ...

Reply with one of:
  ALL SAFE            apply [1]-[3] only
  ALL                 apply [1]-[6]
  1 2 4               apply listed items only
  NONE or SKIP        exit without changes
  EXPLAIN <n>         see full details for item <n>
```

Rules for parsing the response:

- **ALL SAFE** — apply every item under the SAFE CLEANUPS heading. Never
  applies anything under DESTRUCTIVE.
- **ALL** — apply every item under both headings. The user has explicitly
  consented to destructive actions.
- **List of numbers** — apply only those items, regardless of which
  heading they're under. Items not listed become "declined".
- **NONE / SKIP** — apply nothing, write the delta report with
  "Total actions applied: 0".
- **EXPLAIN N** — show the full detail of item N, then re-prompt.

After the action loop, the skill produces the Delta report.

## 5. Approval grammar — Mode B per-phase

After each phase block, the skill emits a continue prompt:

```
PHASE <N> — <title> — FINDINGS
==============================
<phase findings block>

Continue?
  C) Continue to next phase (no action this phase)
  A) Act on findings in this phase now
  S) Skip remaining phases and jump to report
  Q) Quit without delta report
```

On `A`, the skill enters a mini-approval loop identical to Mode A but
scoped to just this phase's items:

```
PHASE <N> — ACTIONS
===================
  [1] <item description>
  [2] ...

Reply: ALL SAFE | ALL | 1 2 | NONE | EXPLAIN <n>
```

After the mini-loop, the skill returns to the phase's continue prompt
with updated summaries (or moves to the next phase if C).

## 6. Rollback semantics

Every mutation emits a `ROLLBACK: <command>` line as it executes. These
lines are collected into the Rollback cookbook block at the end of the
delta report.

The user can:

- Copy one line and re-run it to undo one specific mutation
- Copy the entire block and run it sequentially to undo the whole run
- Look in `~/.claude/backups/claude-tune/<run-ts>/` to inspect the
  snapshots directly

After the run, the snapshot directory persists. The skill does NOT delete
it automatically. The user (or a future claude-tune run in Phase 10)
decides when to prune old snapshot dirs.

## 7. Non-rollbackable actions

Some actions have no inverse:

- **Process kills** — a killed process cannot be un-killed. If the user
  wants to restore the process, they must restart it manually. The
  approval prompt warns about this.
- **Directory deletions** — even though the skill copies the dir to the
  backup area, restoring it is a manual `cp -a` operation. The rollback
  block generates the `cp -a` command; the user runs it.
- **Deletes of files that external systems reference** — for example,
  deleting a plugin's cache dir while the plugin is still registered
  elsewhere. The skill documents this in the approval prompt.

## 8. Dry-run mode

Set `CLAUDE_TUNE_DRY_RUN=1` in the environment to make all mutations
become `echo` commands. Snapshots still happen (they're read-only for the
target). Approvals still happen. The delta report shows "Total actions
applied: 0 (dry run)".

Useful for:

- Testing the skill on a new machine
- Previewing what Mode A would do without actually applying
- CI testing of the skill itself

The skill must always check `ct_is_dry_run` (from `lib/common.sh`) before
calling any mutation command and substitute an echo if set.
