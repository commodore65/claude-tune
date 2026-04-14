# Phase 07 — Project CLAUDE.md Audit (LLM read)

## Goal

Walk the user's project-scoped CLAUDE.md files (each project's own
`CLAUDE.md` at the repo root) and surface the same classes of issues as
the global audit, plus two project-specific smells:

1. **Static lists inside dynamic-discovery blocks** — a section that says
   "Do not hardcode X; discover dynamically" but contains a hardcoded
   list immediately after.
2. **Contradictions with reality** — claims about paths, services, users,
   or configurations that don't match the actual current state.

## Project discovery

The skill does NOT crawl the filesystem. It reads candidate project paths
from two places:

1. The user's current working directory (`$PWD`) — if it has a `CLAUDE.md`
   at the root, audit it.
2. `~/.claude.json` → `projects` → all entries whose path exists on disk
   (from Phase 11's "alive" bucket).

For each alive project, check for a `CLAUDE.md` at the root. If present,
read it via the Read tool.

## Rubric (project-specific additions to Phase 6 rubric)

### R6 — Static list inside dynamic block

Pattern:

> "Do NOT hardcode a list of services. Discover dynamically with this
> command: `grep -oP '(svc1|svc2|svc3|svc4)'`"

The command contains a hardcoded list, which defeats the stated intent.
Flag it; propose a rewrite that actually is dynamic (e.g. a `systemctl`
query that filters by working directory, a `find` across a canonical
location, etc.).

### R7 — Duplicated sections within a file

Same word-for-word paragraph appearing twice (e.g., a local-path
reminder repeated in two sections). Propose dedupe — keep the first,
delete the second.

### R8 — Contradictions with reality

The skill cannot reach external systems (SSH to servers, touch
production), but it CAN check:

- Paths referenced (file/dir exists?)
- GitHub repo slugs (URL format validity; don't fetch)
- Service configuration files in the project (do the referenced files
  exist?)

If the CLAUDE.md claims "foo is under user X" but the project's own
service file says "user Y", flag the contradiction.

## Report table shape

```
PROJECT CLAUDE.md FILES (5 audited)
===================================
~/Desktop/cc/some-project/CLAUDE.md
  L12: static list inside "dynamic discovery" block (flagged)
  L37: duplicate of L25 (trim)
  L60: references ~/some/missing/path (rot)

~/Desktop/cc/other-project/CLAUDE.md
  OK — no findings
```

## Cleanup actions

Same as Phase 6: propose a diff, get approval, snapshot, apply. Never
auto-edit. The skill does not SSH, does not run tests, does not verify
claims that require external network or server access.

## What NOT to touch

- Any section labeled as a warning (`<important if="danger">`, etc.)
- Lists of credentials, paths to secrets, or security-sensitive
  configuration (even if the values look stale — the user decides)
- The file's first line and any block labeled "DO NOT MODIFY"
