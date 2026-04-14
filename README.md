# claude-tune

**Audit and tune your Claude Code setup** — hooks, skills, plugins, MCPs, memory, processes, disk.

Safety-railed, three modes, snapshot-and-rollback on every mutation.

---

## What it does

claude-tune is a Claude Code skill that walks your installation through 12 audit phases and surfaces:

- 🔴 **Silently broken hooks** — scripts the harness "runs" but that exit early because they rely on removed env vars from Claude Code 1.x
- 🟠 **Unused skills, plugins, MCP servers, and agents** — categorized HEAVY / ACTIVE / COLD / DEAD with a session-log observation window
- 🟠 **Stale memory files** — dead references, filename/content mismatches, past-due dates
- 🔴 **Orphan Claude/MCP processes** — left behind by crashed terminals, classified as "mine vs orphan"
- 🟢 **Disk cruft in `~/.claude/`** — telemetry failed-batch buildups, old claude-tune backups
- 🔴 **Dead project entries in `~/.claude.json`** — paths that no longer exist on disk
- 🟠 **Contradictions in global or project `CLAUDE.md`** — narrow generalizations, static lists inside dynamic-discovery blocks
- 🟠 **Bloated MCP servers** — globally-scoped but rarely used; proposes an on-demand loading pattern

For each finding it produces a severity-ranked table and, if you approve, applies provably-safe cleanups. Every mutation emits a `ROLLBACK:` command alongside.

---

## Install

```bash
git clone https://github.com/commodore65/claude-tune ~/.claude/skills/claude-tune
```

Open a new Claude Code session and say one of:

- `claude-tune`
- `audit my claude code`
- `tune claude code`
- `clean up claude setup`
- `broken hooks`
- `unused skills`
- `orphan claude processes`

The first thing the skill does is ask which mode to run.

---

## Three modes

| Mode                       | Description                                                                                                       | When to use                                               |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| **A — Safe Autopilot**     | Runs all 12 phases, produces one combined findings report, asks for one approval, applies provably-safe cleanups. | Quick periodic tune-up                                    |
| **B — Guided Interactive** | Runs phases one at a time, pauses after each for `continue / act / skip / quit`.                                  | First-time audit, post-crash recovery, unfamiliar install |
| **C — Read-only**          | Runs all phases and produces the findings report only. Zero mutations, zero approvals.                            | Dry-run before committing to a cleanup pass               |

---

## 12 audit phases

| #   | Phase                     | What it finds                                                            |
| --- | ------------------------- | ------------------------------------------------------------------------ |
| 1   | Live processes            | Orphan Claude/MCP/codex processes, stale dev servers, heavy CPU hogs     |
| 2   | Hooks                     | Silently broken hooks, env-var bugs, per-turn noise — the killer feature |
| 3   | Skills                    | HEAVY / ACTIVE / COLD / DEAD usage categorization                        |
| 4   | Plugins                   | Enabled but unused, disk footprint, propose disable candidates           |
| 5   | MCP servers               | Globally-scoped servers rarely used, on-demand stash pattern             |
| 6   | Global CLAUDE.md          | Narrow generalizations, duplicated guidance, reference rot               |
| 7   | Project CLAUDE.md         | Static lists inside dynamic-discovery blocks, contradictions             |
| 8   | Memory files              | Stale dates, filename/content mismatches, dead path references           |
| 9   | Agents                    | Subagent usage categorization                                            |
| 10  | Disk hygiene              | Top-10 subdirs, telemetry failed-batch pruning, backup cleanup           |
| 11  | `~/.claude.json` projects | Dead-path detection and cleanup                                          |
| 12  | Settings sanity           | Permission allow-list cruft, stale env vars, deprecated keys             |

Phases 1–5 and 8–12 are driven by deterministic scripts (bash and Python 3 stdlib). Phases 6 and 7 are LLM-driven heuristic reads.

---

## Safety model

Every mutation follows the same five-step pattern:

1. **Snapshot first.** `scripts/snapshot.sh <target>` copies the target into `~/.claude/backups/claude-tune/<run-ts>/<flat-basename>.bak` with mode `700`.
2. **Prove safety.** Value flips and telemetry batch deletions are classified as "safe"; key deletions, `rm`, and `kill` are "destructive" and require **per-item approval even in Autopilot mode**.
3. **Apply.** Run the mutation. In dry-run mode (`CLAUDE_TUNE_DRY_RUN=1`), mutations become `echo`s.
4. **Verify.** Re-parse JSON after any write; restore from snapshot on failure.
5. **Record.** Emit a `ROLLBACK: <command>` line for every mutation, collected into a final delta report.

The skill **never** SSHes, **never** hits networks, **never** spawns MCP servers to query them, **never** runs as root, and **never** assumes a specific tech stack. It is local-only and generic.

---

## Requirements

- Claude Code 2.x
- bash 3.2+ (macOS default) or bash 4.x+
- Python 3.9+ — standard library only, no `pip install` required
- POSIX utilities: `find`, `du`, `ps`, `pgrep`, `cp`, `awk`, `grep`, `sort`

Tested on macOS. Linux works too — the `stat` portability shim handles BSD vs GNU differences automatically.

---

## Tuning

Override thresholds via environment variables:

| Variable                        | Default          | Purpose                                                     |
| ------------------------------- | ---------------- | ----------------------------------------------------------- |
| `CLAUDE_TUNE_HEAVY`             | `10`             | Usage count required for HEAVY category                     |
| `CLAUDE_TUNE_DEV_STALE_MIN`     | `30`             | Dev-server stale threshold (minutes)                        |
| `CLAUDE_TUNE_TOOL_STALE_MIN`    | `2880`           | Claude/MCP tool stale threshold (minutes; default 48 hours) |
| `CLAUDE_TUNE_MEM_AGING_DAYS`    | `30`             | Memory-file aging threshold (days)                          |
| `CLAUDE_TUNE_MEM_STALE_DAYS`    | `90`             | Memory-file stale threshold (days)                          |
| `CLAUDE_TUNE_BACKUP_MAX_AGE`    | `14`             | Old-backup prune threshold (days)                           |
| `CLAUDE_TUNE_ORPHAN_ALLOW_PIDS` | _(empty)_        | Comma-separated PIDs to never flag as orphans               |
| `CLAUDE_TUNE_DRY_RUN`           | `0`              | Set to `1` to echo every mutation instead of applying       |
| `CLAUDE_HOME`                   | `~/.claude`      | Alternative Claude Code home directory                      |
| `CLAUDE_JSON`                   | `~/.claude.json` | Alternative `~/.claude.json` location                       |

---

## Contributing

Issues and pull requests welcome. The skill is intentionally generic — patches that hardcode specific server names, project layouts, or stack assumptions will be declined.

---

## License

MIT. See [`LICENSE`](LICENSE).
