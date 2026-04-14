---
name: claude-tune
description: "Audit and tune a Claude Code installation. Scans ~/.claude and ~/.claude.json for silently broken hooks, unused skills/plugins/MCP servers, stale memory files, orphan Claude/MCP processes, bloated telemetry, dead project entries, and contradictions in global or project CLAUDE.md. Produces a severity-ranked findings report with green/orange/red verdicts, then either auto-applies provably-safe cleanups, walks 12 audit phases interactively with per-phase approval, or runs read-only to produce only a report. Safety rails: file snapshots before any write, destructive ops always gated behind explicit approval, rollback commands generated on the fly. Trigger when the user says 'tune my claude code', 'audit claude setup', 'claude-tune', '/claude-tune', 'broken hooks', 'unused skills', 'orphan claude processes', or after terminal crashes left zombie sessions behind. Do NOT trigger for debugging project code (use health or investigate) or for creating new skills (use skill-creator)."
license: MIT — see LICENSE
---

# claude-tune — Claude Code Setup Auditor

> Install: `git clone https://github.com/commodore65/claude-tune ~/.claude/skills/claude-tune`

A staff-level auditor for your Claude Code installation. Finds silently broken hooks, unused skills and plugins, bloated MCPs, stale memory, orphan processes, and cruft in `~/.claude/`. Produces a severity-ranked findings report, gates every mutation behind explicit approval, and emits a rollback cookbook for every change.

## HARD GATES

- Do NOT delete files without explicit per-item approval, EVER — even in Autopilot mode.
- Do NOT kill any process unless its parent is gone (PPID == 1), its age is > 5 minutes, its name matches a generic orphan pattern, AND the user confirms the specific PID.
- Do NOT mutate `~/.claude/settings.json`, `~/.claude.json`, or any `CLAUDE.md` without first calling `scripts/snapshot.sh` on the target and capturing the `SNAPSHOT:` + `ROLLBACK:` lines.
- Do NOT touch anything outside `$HOME/.claude`, `$HOME/.claude.json`, or project-scoped `.claude/` / `.mcp.json` / `CLAUDE.md` files under the user's current working directory.
- Do NOT SSH, do NOT hit networks, do NOT spawn MCP servers to query them. Local-only.
- Do NOT assume the user's tech stack (Python vs. Node vs. Rust, etc.).
- Generic only: no hardcoded user paths, hostnames, or project names in any script or reference.

## When to Use

Trigger phrases: "audit claude code", "tune claude code", "claude-tune", "/claude-tune", "broken hooks", "unused skills", "orphan claude processes", "clean up claude", "claude setup audit", or after a terminal crash left zombie Claude sessions behind.

NOT for:

- **Debugging project code** — use the `health` or `investigate` skill.
- **Creating new skills** — use `skill-creator`.
- **Auditing a specific running service** — that's for a service-monitor skill, not this one.

## Three Modes

### Mode A — Safe Autopilot

Runs all 12 phases in read-only mode, produces one combined findings report, then presents ONE approval prompt listing all proposed cleanups grouped into SAFE and DESTRUCTIVE buckets. User replies with approval grammar (ALL SAFE / ALL / specific numbers / NONE / EXPLAIN). Skill executes approved items and produces a delta report with rollback cookbook.

Safe items are applied after the single approval; destructive items require per-item confirmation even in Mode A. See `references/safety.md` § "Safe vs destructive ops".

### Mode B — Guided Interactive

Runs phases one at a time. After each phase, presents findings and asks: C (continue, no action), A (act on this phase now), S (skip remaining phases and jump to report), Q (quit without delta). Acting on a phase opens a mini-approval loop scoped to that phase's items.

### Mode C — Read-only

Runs all 12 phases and produces the full findings report. Zero mutations, zero approvals, zero risk. Useful as a dry-run before committing to Mode A or B.

### Mode selection dialog

**Mandatory first step on every invocation.** Never assume a mode.

```
claude-tune — which mode?
  A) Safe Autopilot   — one combined report, one approval, one cleanup pass
  B) Guided Interactive — 12 phase gates, maximum control
  C) Read-only        — audit only, no approvals, no cleanups
```

Wait for the user's response before doing anything else.

## Phase 0 — Baseline Snapshot

Before any audit work, run `bash scripts/baseline.sh`. It writes `baseline.json` into `~/.claude/backups/claude-tune/<run-ts>/` and echoes a compact summary on stderr. The JSON is the "before" side of every delta reported later.

In Mode B, also report that Phase 0 ran successfully before moving to Phase 1.

## The 12 Audit Phases

Each phase below has: a one-line goal, the script or Read invocation, expected output shape, and a pointer to the full playbook. **Read the phase reference file for every phase before executing that phase.**

### Phase 1 — Live processes

Orphan Claude/MCP/codex processes, stale dev servers, heavy CPU hogs. Current claude session tree is automatically excluded.

- Run: `bash scripts/audit_processes.sh`
- Output: `{orphans: [...], heavy: [...], mine: [...]}`
- Severity: orphans 🔴, heavy 🟠 (informational), mine 🟢.
- Full playbook: `references/phase-01-processes.md`

### Phase 2 — Hooks

The highest-value phase. Detects silently-broken hooks that the harness "runs" but that exit early because they rely on removed env vars (`CLAUDE_FILE_PATH` and similar from Claude Code 1.x).

- Run: `bash scripts/audit_hooks.sh`
- Live firing test is OPT-IN. Default is static-only. If the user wants to confirm UNKNOWN hooks actually fire, ask first ("This may trigger side effects in your hooks — OK?") and re-run with `--live`.
- Severity: BROKEN 🔴, NOISY 🟠, UNKNOWN 🟠, OK 🟢.
- Full playbook: `references/phase-02-hooks.md`

### Phase 3 — Skills

Count usage of every installed skill across session logs. Reports HEAVY / ACTIVE / COLD / DEAD with observation-window caveat.

- Run: `python3 scripts/audit_skills.py`
- Severity: HEAVY/ACTIVE 🟢, COLD 🟠, DEAD 🔴.
- Full playbook: `references/phase-03-skills.md`

### Phase 4 — Plugins

Read `enabledPlugins` from settings.json, count plugin-tool and plugin-skill invocations, report disk footprint. Propose disable for unused enabled plugins; flag large disabled plugins for uninstall.

- Run: `python3 scripts/audit_plugins.py`
- Severity: HEAVY/ACTIVE 🟢, COLD 🟠, DEAD 🔴, DISABLED ⚪.
- Full playbook: `references/phase-04-plugins.md`

### Phase 5 — MCP servers

Find globally-scoped MCP servers that are used rarely. Propose moving them to an on-demand stash pattern so their tool descriptions stop consuming context in every session.

- Run: `python3 scripts/audit_mcp.py`
- Severity: HEAVY 🟢, ACTIVE 🟢 (🟠 if overweight), COLD 🟠, DEAD 🔴.
- Full playbook: `references/phase-05-mcp.md`

### Phase 6 — Global CLAUDE.md

LLM-driven heuristic read. Use the Read tool on `~/.claude/CLAUDE.md` and apply the rubric to surface narrow generalizations, duplicated guidance, and reference rot.

- Read: `~/.claude/CLAUDE.md`
- Full rubric: `references/phase-06-global-claudemd.md`

### Phase 7 — Project CLAUDE.md

Same LLM-driven approach for each alive project's CLAUDE.md (from Phase 11's alive list + current cwd). Plus project-specific smells: static lists inside dynamic-discovery blocks, duplicated sections, contradictions with reality.

- Read: each project's `CLAUDE.md`
- Full rubric: `references/phase-07-project-claudemd.md`

### Phase 8 — Memory files

Discover memory files under `~/.claude/projects/*/memory/` (or `~/.claude/memory/`). Flag stale dates in content, filename/content number mismatches, and dead path references.

- Run: `python3 scripts/audit_memory.py`
- Severity: FRESH 🟢, AGING 🟠, STALE 🟠, SUSPECT 🔴.
- Full playbook: `references/phase-08-memory.md`

### Phase 9 — Agents

Same usage-count pattern as skills, but for `~/.claude/agents/*.md`. Flags unused subagents.

- Run: `python3 scripts/audit_agents.py`
- Severity: HEAVY/ACTIVE 🟢, COLD 🟠, DEAD 🔴.
- Full playbook: `references/phase-09-agents.md`

### Phase 10 — Disk hygiene

Top 10 subdirs under `~/.claude/` by size. Telemetry failed-batch count (the only "safe auto-delete" class). Old claude-tune backup runs for pruning.

- Run: `bash scripts/audit_disk.sh`
- Severity: informational 🟠 for top dirs, 🟢 for failed telemetry (safe to delete).
- Full playbook: `references/phase-10-disk.md`

### Phase 11 — `~/.claude.json` projects section

Classify each entry as dead (path gone), home (Desktop/Downloads/$HOME), or alive. Propose bulk removal of dead entries.

- Run: `python3 scripts/audit_projects_json.py`
- Severity: DEAD 🔴, HOME 🟠, ALIVE 🟢.
- Full playbook: `references/phase-11-projects-json.md`

### Phase 12 — Settings sanity

Low-risk cruft: permissions allow-list entries the harness already auto-allows, env vars with stale paths, deprecated top-level keys.

- Run: `python3 scripts/audit_settings.py`
- Severity: 🟠 for each category, all informational until approval.
- Full playbook: `references/phase-12-settings.md`

## Safety Model (summary)

Every mutation goes through a 5-step pattern:

1. **Snapshot.** Call `bash scripts/snapshot.sh <target-file>`. Capture the `SNAPSHOT:` and `ROLLBACK:` lines.
2. **Prove safety.** Classify the action as safe or destructive (see `references/safety.md`). Destructive actions always require per-item approval.
3. **Apply.** Run the mutation. In dry-run mode (`CLAUDE_TUNE_DRY_RUN=1`), echo instead.
4. **Verify.** For JSON mutations, re-parse the file and confirm it's valid. On parse failure, restore from snapshot and halt the phase.
5. **Record.** Append the ROLLBACK line to the rollback cookbook for the delta report.

Full details, approval grammar, and destructive-op classification: `references/safety.md`.

## Reporting Model (summary)

Three reports per run:

1. **Baseline** — after Phase 0. Inventory counts, top disk usage, snapshot dir path.
2. **Findings** — after all phases (Mode A/C) or after each phase (Mode B). Severity-tagged tables.
3. **Delta** — after any cleanups applied. Before/after counts, total bytes reclaimed, rollback cookbook, outstanding items.

Emoji legend (never add new symbols):

- 🟢 OK — no action
- 🟠 Attention — informational or proposed review
- 🔴 Broken / dead — proposed cleanup
- ⚪ Disabled / inactive — present but dormant

Exact markdown shells for every report type: `references/report-templates.md`.

## Rules

1. **Read-only first.** Produce the full findings report before any mutation.
2. **Snapshot before every write.** No exceptions.
3. **Mode selection is mandatory.** Never assume; always ask.
4. **Ambiguous → prompt.** The user is always the final gate on destructive actions.
5. **Generic only.** If a phase needs stack-specific or user-specific knowledge, skip it with a clear reason.
6. **No network, no SSH, no process spawning beyond shell scripts in this skill's own scripts/ dir.**
7. **Skipped phases are listed as SKIPPED, not FAILED.** A skipped phase must include the reason.
8. **Every mutation emits a rollback line.** Before executing.
9. **Numerical before/after in every delta.** No vague "cleaned up" statements.
10. **On script failure, phase is SKIPPED** with the error. Does not block other phases.
11. **If the user is running another Claude session** (detected in Phase 1 as another live `claude --dangerously` process), warn before any mutation to `settings.json` or `~/.claude.json` — those files are read at session start, and concurrent sessions may see inconsistent state.
12. **When in doubt, ask.** The approval gate is cheap; a wrong mutation is expensive.
