# Phase 03 — Skills Audit

## Goal

Count usage of every globally-installed skill over the session-log observation
window and categorize each as HEAVY, ACTIVE, COLD, or DEAD. Surface candidates
for removal (DEAD) or review (COLD) without false-flagging skills whose logs
have simply rotated out.

## What the script does

`scripts/audit_skills.py` walks `~/.claude/skills/`, following symlinks
(many skills are symlinked in from `~/.agents/skills/*`), and for each skill
counts two substring patterns across all `~/.claude/projects/**/*.jsonl`:

- `"skill":"<name>"` — Skill tool invocations
- `"/<name>` — slash-command style invocations

It streams the log files line-by-line via `lib/claude_logs.py`, so even if
the user has gigabytes of session history, memory use stays flat.

## Thresholds

| Category | Rule                                                                   | Emoji |
| -------- | ---------------------------------------------------------------------- | ----- |
| HEAVY    | `uses_total ≥ 10`                                                      | 🟢    |
| ACTIVE   | `1 ≤ uses_total ≤ 9`                                                   | 🟢    |
| COLD     | `uses_total == 0` and observation window is too short to be conclusive | 🟠    |
| DEAD     | `uses_total == 0` and observation window covers a meaningful period    | 🔴    |

HEAVY threshold defaults to 10 and is configurable via the
`CLAUDE_TUNE_HEAVY` env var.

## Observation window — why it matters

A "DEAD" verdict means "not used in the last N days of session logs", where
N is the age in days of the oldest jsonl file under
`~/.claude/projects/`. If the user has configured aggressive log rotation and
the oldest log is only 7 days old, a skill that was used 3 weeks ago may
show `uses_total == 0`. The script reports the observation window so the
skill can caveat DEAD verdicts honestly:

> "DEAD in last 93 days of session logs."

If the window is 0 (no logs), the category is COLD, not DEAD — we cannot
distinguish "never used" from "no history to check".

## Report table shape

```
SKILLS (8 installed, observation window 90 days)
================================================
Category   Skill                       Tool   Slash   Total   Last used
--------   -------------------------   ----   -----   -----   ----------
🟢 HEAVY   example-heavy                   5      15      20   2023-06-15
🟢 ACTIVE  example-active                  3       0       3   2023-06-10
🟢 ACTIVE  another-active                  2       0       2   2023-06-08
🟠 COLD    example-cold                    0       0       0   —
🔴 DEAD    example-unused                  0       0       0   —  (in last 90d)
```

(Skill names shown are synthetic — replace with whatever your audit turns up.)

## Cleanup actions (per category)

- **HEAVY / ACTIVE** — 🟢, no action. Reported for inventory.
- **COLD** — 🟠, recommend review. Observation window is too short to be
  confident. Action: none proposed; user decides.
- **DEAD** — 🔴, propose removal. Per-item approval required even in
  Autopilot mode. The skill must NOT auto-delete.

Removal procedure:

1. Snapshot the skill directory first:
   `cp -a ~/.claude/skills/<name> ~/.claude/backups/claude-tune/<ts>/skills__<name>/`
   (Note: snapshot.sh covers single files; for a directory, use a separate
   recursive copy via the skill's cleanup routine.)
2. Delete the directory: `rm -rf ~/.claude/skills/<name>`
3. Emit `ROLLBACK: cp -a ~/.claude/backups/.../skills__<name>/ ~/.claude/skills/<name>`.

## False positives

- **Skill used but log rotated.** Mitigated by the COLD vs DEAD distinction
  and by always reporting the observation window.
- **Skill invoked with a rename mid-session.** If a skill was renamed, older
  session logs reference the old name. The new-name search returns 0 while
  the old-name search would return hits. Accept this as an edge case and
  note it in the cleanup proposal if the skill shows signs of recent rename
  (file mtime newer than its oldest session-log match).
- **Slash-command collisions.** `/health` may mean "run the health skill"
  but it may also appear in prose user messages like "let me /health check
  this first". The substring match is approximate. For DEAD candidates the
  user should glance at recent session history before approving deletion.
