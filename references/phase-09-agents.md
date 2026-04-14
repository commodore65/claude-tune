# Phase 09 — Agents Audit

## Goal

Same as skills audit but for subagents (`~/.claude/agents/*.md`). Count how
often each agent type has been invoked via the Agent/Task tool and flag
unused ones.

## What is a subagent

A subagent is a named persona invoked via the Agent (or Task) tool. The
invoking session opens a sub-context for the agent, gives it a task, and
reads its final report. Agents are defined as markdown files under
`~/.claude/agents/<name>.md` with frontmatter specifying name, description,
tools, and model.

## Usage counting

Each agent is matched by the substring `"subagent_type":"<name>"` in
session logs. This pattern comes from the Agent/Task tool's JSON input
shape.

## Category rubric

Identical to the skills phase:

| Category | Rule                                |
| -------- | ----------------------------------- |
| HEAVY    | uses ≥ 10                           |
| ACTIVE   | 1 ≤ uses ≤ 9                        |
| COLD     | uses == 0, observation window short |
| DEAD     | uses == 0, observation window long  |

## Report table shape

```
AGENTS (5 installed, observation window 93 days)
================================================
Category    Agent                  Uses   Last used
---------   --------------------   ----   ----------
🟢 HEAVY    example-heavy           12    2023-06-15
🟢 ACTIVE   example-active           5    2023-06-12
🟢 ACTIVE   another-active           4    2023-06-10
🟠 COLD     example-cold             0    —
🔴 DEAD     example-unused           0    —  (in last 93d)
```

## Cleanup actions

- **HEAVY / ACTIVE** — no action.
- **COLD** — inform only. The agent might serve a purpose that simply
  hasn't come up yet. No proposed action.
- **DEAD** — propose removal. Deleting an agent means `rm <agent>.md`.
  Snapshot the file first (copy it to the backups dir), then delete. Per-
  item approval always required.

## False positives

- **Zero-use agents that exist as a "safety rail"** — e.g., a
  spec-interviewer that fires before new project code. Such agents may
  genuinely have zero invocations but serve a preventive purpose. The skill
  must never auto-delete DEAD agents; the user decides.
- **Recently-added agents.** An agent added yesterday will naturally have
  zero usage. The category will be DEAD (if window > 0) but the age can be
  checked via file mtime. The skill could refine by not proposing DEAD if
  `agent_mtime` is within the last 14 days; for now this is a manual
  consideration the user applies when reviewing the report.
