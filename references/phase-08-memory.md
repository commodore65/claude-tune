# Phase 08 — Memory Files Audit

## TOC

1. Goal
2. Memory file discovery
3. Staleness signals (age, stale dates, rename mismatch, dead refs)
4. Categories (compound)
5. Report table shape
6. Cleanup actions
7. False positives

## Goal

Find memory files that are stale — either by age alone or because their
content references facts, deadlines, or file paths that are no longer true.

## Memory file discovery

Memory files live in one of two places, depending on the user's Claude Code
setup:

1. `~/.claude/projects/<project-id>/memory/*.md` — per-project auto-memory
2. `~/.claude/memory/*.md` — global user memory (rare)

The script walks both, only counting paths whose directory includes
`memory`. If neither location has files, the phase reports zero and skips
cleanly.

## Staleness signals

Each memory file is evaluated on four axes:

### 1. Age (mtime)

| Threshold  | Category |
| ---------- | -------- |
| < 30 days  | FRESH    |
| 30–89 days | AGING    |
| ≥ 90 days  | STALE    |

Thresholds are tunable via `CLAUDE_TUNE_MEM_AGING_DAYS` and
`CLAUDE_TUNE_MEM_STALE_DAYS`.

### 2. Stale dates in content

Regex-match `YYYY-MM-DD` strings in the body. Any date that is ≥ 14 days
in the past is flagged. This catches content like:

> "Phase 2 due by 2023-06-15"

written weeks ago and never updated. If a date appears to be in the past
and the memory talks about it as a future commitment, the memory is
probably wrong about current state.

Not every past date is a mistake — memories often reference historical
incidents ("Fixed the auth bug 2023-01-10"). The rule is "flag for
review", not "delete automatically".

### 3. Filename/content number mismatch

If a filename contains a number pattern like `feedback_7_services.md` and
the content now talks about "12 services", suggest a stable rename that
drops the number — e.g. `feedback_services.md`. Numbers in filenames rot
every time the underlying count changes.

### 4. Dead references

Scan the body for `~/...` paths. For each, check whether the path exists on
disk. If not, add it to `dead_refs`. Capped at 10 per file for readability.

Paths containing `*` or `?` (globs) are skipped to avoid false positives.

## Categories (compound)

The category reflects the worst signal:

- **SUSPECT** — any of `stale_dates`, `rename_suggestion`, or `dead_refs` is
  non-empty, regardless of age.
- **STALE** — age ≥ 90 days, no other signals.
- **AGING** — 30–89 days, no other signals.
- **FRESH** — < 30 days.

## Report table shape

```
MEMORY FILES (N tracked)
========================
Category      File                                      Age     Signals
-----------   ---------------------------------------   -----   ------------------------------
🔴 SUSPECT    project_example_plan.md                    42d    stale_date=2025-01-01; dead_refs=1
🔴 SUSPECT    feedback_3_rules.md                        17d    rename→feedback_rules.md
🟠 STALE      project_old_notes.md                       92d    —
🟠 AGING      project_service_arch.md                    45d    —
🟢 FRESH      feedback_recent_tip.md                      5d    —
```

(File names shown are synthetic examples.)

## Cleanup actions

The skill NEVER auto-edits or deletes memory files. It proposes, and the
user decides:

- **SUSPECT** — surface the specific signals (stale dates, missing refs,
  rename suggestion). Ask the user: "update, rename, delete, or ignore?"
- **STALE** — 🟠, not proposed for action. Reported for awareness. Old but
  valid memories are fine.
- **AGING** → no action.
- **FRESH** → no action.

Memory updates are never textual auto-rewrites; they're surfaced as
findings for the user to act on manually in a follow-up session.

## False positives

- **Historical timestamps** (e.g. "On 2023-01-10 the auth bug was fixed")
  are legitimate retrospective markers. The script flags them; the user
  ignores them.
- **Intentionally-numbered file names** (e.g. `feedback_10_rules.md` where
  the count is stable) will trip the rename suggestion if the content uses
  any other number in the first 400 chars. Accept the false positive.
- **Template placeholders** (e.g. `~/path/to/<project>` with literal angle
  brackets) won't match the `~/...` regex since they contain invalid
  characters — no false positive here.
