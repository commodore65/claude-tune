# Phase 01 — Processes Audit

## TOC

1. Goal
2. Two thresholds
3. Pattern lists
4. Current-session exclusion
5. Heavy process reporting
6. Report table shape
7. Severity
8. Cleanup actions
9. False positives

## Goal

Find long-lived processes that are probably orphans — leftover from crashed
terminals, backgrounded sessions, or daemons the user forgot — and classify
them as either "orphan to kill" or "mine, leave alone".

## Two thresholds

Different process classes deserve different staleness thresholds:

| Class                               | Threshold  | Why                                                                                            |
| ----------------------------------- | ---------- | ---------------------------------------------------------------------------------------------- |
| Dev servers (vite, uvicorn, etc.)   | 30 minutes | Forgotten work sessions are common; 30 min catches them without flagging legitimate active dev |
| Tooling (claude, codex, mcp-server) | 48 hours   | A Claude session open for a few hours is normal; only multi-day survivors are orphans          |

Both thresholds are configurable via env:

- `CLAUDE_TUNE_DEV_STALE_MIN` (default 30)
- `CLAUDE_TUNE_TOOL_STALE_MIN` (default 2880)

## Pattern lists

Generic regex strings, **no user-specific binary names**. The script matches
`ps` output against each:

- **Dev patterns:** `uvicorn|vite|next-router-worker|next dev|bun .*(dev|server|run)|nodemon|tsx watch|cloudflared tunnel|ngrok|localtunnel|webpack.dev|parcel|turbopack|fastapi|flask run|gunicorn.*reload|hugo server|gatsby develop`
- **Tooling patterns:** `claude --dangerously|codex app-server|app-server-broker.mjs|mcp-server|-mcp\b|/mcp-[a-zA-Z0-9]`

The MCP-related regex is intentionally generic: it matches any command
that looks like an MCP server binary (name ends in `-mcp`, contains
`mcp-server`, or starts with `mcp-` after a path separator). This avoids
hardcoding specific MCP server names.

## Current-session exclusion

The script walks up from its own `$PPID` until it finds a `claude` ancestor,
then collects all descendants of that ancestor. Those PIDs are reported as
`mine` (🟢) and excluded from the orphan list. This protects against false
alarms on the live session that invoked the audit, and its MCP children.

If no `claude` ancestor is found (script invoked outside a Claude session),
the exclusion set is empty — every match becomes an orphan candidate.

## Heavy process reporting

Independent of the orphan list, the script also reports the top 5 processes
by CPU% (excluding the current claude tree). These are not proposed for
action — they're informational. A legitimately busy process is not an error.

## Report table shape

```
PROCESSES
=========

ORPHANS (dev stale > 30m, tooling stale > 48h)
Pid        Ppid    Age      Command
-------    ----    ------   ----------------------------------------------
 12345        1    3d02h    claude --dangerously-skip-permissions
 12346    12345    3d02h    node .../mcp-server/index.js
  5421        1    4h17m    vite dev --port 5173

HEAVY (top 5 by CPU, informational)
Pid      CPU%   MEM%   Command
------   ----   ----   ------------------------------------------
 3421    42.1   1.8    python3 some-script.py
 ...

🟢 MINE: current claude session PID 12999 + 4 children (excluded from report)
```

## Severity

- **Orphan with PPID=1 (parent gone)** → 🔴, propose kill with explicit
  per-PID approval.
- **Orphan with live PPID** → 🟠, report but do NOT propose kill. The
  process has a live parent; killing it could break the parent's
  expectations. User must investigate.
- **Heavy processes** → 🟠, informational only. No action.

## Cleanup actions

The skill never auto-kills. For each orphan with PPID=1:

1. Show PID, age, and full command.
2. Ask user to confirm: "Kill PID <pid>?"
3. On approval: `kill <pid>`, wait 2s, `kill -9 <pid>` if still alive.
4. No rollback possible for kill; document this in the approval prompt.

## False positives

- **Long-running legitimate processes** (e.g., a developer's own daemon). Add
  an allow-list via env var `CLAUDE_TUNE_ORPHAN_ALLOW_PIDS="1234,5678"` — the
  script skips any PID in the list.
- **Nested claude sessions** (user has multiple claude tabs open in the same
  terminal). The exclusion walks up from `$PPID`, so it only excludes the
  session that invoked the audit. Other live sessions will show up as
  orphans. Mitigation: before proposing kill on a `claude --dangerously-*`
  match, the skill must double-check the user: "Is this another tab you
  have open? (y/n)".
