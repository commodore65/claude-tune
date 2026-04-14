# Phase 05 — MCP Servers Audit

## TOC

1. Goal
2. What an MCP server costs
3. Where MCP config lives
4. Usage counting
5. Category rubric
6. The "overweight" flag
7. On-demand stash pattern (proposed cleanup)
8. Report table shape
9. Cleanup actions

## 1. Goal

Find MCP servers that are globally scoped and loaded in every session even
though they are only used occasionally. Propose moving them to an on-demand
loading pattern so their tool descriptions stop consuming context in
sessions that don't need them.

## 2. What an MCP server costs

An MCP server contributes to context in three ways:

1. **Server instructions.** Many MCP servers ship a prose "instructions"
   block that the harness injects into every session's system prompt when
   the server is loaded. Can be 50–500 words.
2. **Tool descriptions.** Each tool the server exposes has a JSON Schema
   description that takes 40–120 words. A server with 30 tools can add
   2,000–4,000 words to every system prompt.
3. **Session-log footprint.** Every tool call fills the session log with
   its arguments and results. Not a per-session cost, just a disk cost.

The audit only sees cost (2) through the proxy of "how many times has this
server been called". Cost (1) is invisible without loading the server,
which the skill refuses to do.

## 3. Where MCP config lives

- **Global:** `~/.claude.json` → `mcpServers` → `{name: {command, args, env}}`
- **Per-project:** `~/.claude.json` → `projects` → `<abs-path>` → `mcpServers`
- **Project-local file (alternative):** `<project>/.mcp.json` with the same shape

The audit reads the first two. Project-local `.mcp.json` files are detected
by walking the cwd during runtime but are not part of `audit_mcp.py`'s scope
(covered by the Phase 7 CLAUDE.md audit, which already walks project dirs).

## 4. Usage counting

For each unique server name discovered, `audit_mcp.py` grep-counts the
substring `mcp__<name>__` across all `~/.claude/projects/**/*.jsonl` files.
That prefix is how Claude Code formats MCP tool names in session logs
(e.g., `mcp__<server>__<tool_name>`), so one hit equals one tool call.

The count is aggregated across all scopes of the same server name — if a
server is listed globally AND in a project scope, the usage count is shared.

## 5. Category rubric

| Category | Rule                                               |
| -------- | -------------------------------------------------- |
| HEAVY    | `uses ≥ 10` (configurable via `CLAUDE_TUNE_HEAVY`) |
| ACTIVE   | `1 ≤ uses ≤ 9`                                     |
| COLD     | `uses == 0`, observation window < meaningful       |
| DEAD     | `uses == 0`, observation window ≥ meaningful       |

Same COLD vs DEAD distinction as the skills phase — protects against false
positives from rotated logs.

## 6. The "overweight" flag

Separate from the HEAVY/ACTIVE/COLD/DEAD category, each server can be
marked `overweight: true`. The heuristic:

> Globally scoped AND not HEAVY → overweight candidate.

Rationale: globally scoped MCPs load in every session. If a server is used
fewer than 10 times across the entire observation window, it's paying
per-session tool-description cost for every session to earn its keep in the
few sessions that actually call it. Moving it to an on-demand stash pattern
(see §7) recovers that context.

HEAVY globals are legitimate (they earn their weight). Non-global MCPs are
already scoped — no action needed.

## 7. On-demand stash pattern (proposed cleanup)

When an overweight server is flagged, the skill proposes:

1. Snapshot `~/.claude.json`.
2. Create (or update) `~/.claude/mcp-stash.json`:
   ```json
   {
     "servers": {
       "<name>": {
         "scope": "global",
         "config": { ... original config ... }
       }
     }
   }
   ```
3. Remove the server from `~/.claude.json` under its original scope
   (global `mcpServers` or the project's `mcpServers`).
4. On future sessions, the user invokes the server by asking the assistant
   to "enable <name> MCP". The assistant reads the stash, reinstates the
   config in `~/.claude.json`, and tells the user to open a new session to
   pick it up. After use, the user says "done with <name>" and the
   assistant removes it again, keeping the stash intact.

The pattern applies when an MCP server's tool namespace pays per-session
context cost out of proportion to how often any session actually uses it.

The skill NEVER applies this cleanup without explicit user approval. It
proposes the pattern in the findings report and requires per-server opt-in.

## 8. Report table shape

```
MCP SERVERS (4 configured, observation window 93 days)
======================================================
Category      Scope              Name              Uses   Overweight   Last used
-----------   ----------------   ---------------   ----   ----------   ----------
🟢 HEAVY      global             core-mcp           42     no          2023-06-15
🟠 ACTIVE     project:~/foo      scoped-mcp          8     no          2023-06-12
🟠 ACTIVE     global             niche-mcp           7     YES         2023-06-08
🔴 DEAD       global             legacy-mcp          0     YES         —  (in last 93d)
```

## 9. Cleanup actions

- **HEAVY global:** no action, earn their keep.
- **HEAVY project:** no action, already scoped.
- **ACTIVE global + overweight:** propose stash pattern (per-server approval).
- **ACTIVE project:** no action.
- **COLD / DEAD global:** propose stash or full removal — user chooses.
- **COLD / DEAD project:** propose removal from the project's scope.

All mutations go through `scripts/snapshot.sh` first, and every mutation
emits a `ROLLBACK:` line.
