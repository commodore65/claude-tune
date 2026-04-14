# Phase 11 — `~/.claude.json` projects section

## Goal

Find dead entries in the `projects` block of `~/.claude.json` — entries
that point to directories that no longer exist on disk — and propose
removing them.

## What the projects block is

`~/.claude.json` tracks per-project state. Each key is an absolute path
and each value is a JSON object holding session history, open tabs, IDE
integration state, MCP overrides, etc. When you start claude in a directory,
the harness looks up that directory in this block and loads its state.

Over time, entries accumulate for directories you've renamed, deleted, or
abandoned. They're invisible to the user but add up:

- Each entry is ~1–2 KB of JSON
- The harness iterates this block on every session start (cheap but not
  free)
- Stale paths make the config harder to reason about manually

## Classification

Each entry is placed in one of three buckets:

| Bucket    | Rule                                                                                           |
| --------- | ---------------------------------------------------------------------------------------------- |
| **dead**  | `os.path.isdir(path)` returns False — path is gone                                             |
| **home**  | path is `$HOME`, `~/Desktop`, `~/Downloads`, or `~/Documents` — legitimate but not a "project" |
| **alive** | path exists and is not a home-like dir                                                         |

The "home" bucket exists because those directories are often dragged in
when a user starts claude in their home or Desktop once, then never uses
that location again. They're dead weight but not strictly orphaned.

## Report table shape

```
~/.claude.json projects (N entries: X dead, Y home, Z alive)
============================================================
Status     Path                                              Size
--------   -----------------------------------------------   --------
🔴 DEAD    $HOME/projects/old-experiment                     2.2 KB
🔴 DEAD    $HOME/Desktop/deleted-project                     1.9 KB
🔴 DEAD    /ssh:user@host:/remote-path                       0.3 KB
🟠 HOME    $HOME                                             1.2 KB
🟠 HOME    $HOME/Desktop                                     1.7 KB
🟢 ALIVE   $HOME/projects/current-workspace                  2.2 KB
... (remaining alive entries summarized)
```

## Cleanup actions

- **DEAD** — propose deletion. Even though each entry points to a path
  that no longer exists, key deletion from `~/.claude.json` is classified
  as destructive by `references/safety.md`, so the skill asks for
  **per-item approval** in every mode. Mode A presents the dead entries
  under the DESTRUCTIVE bucket (not SAFE), and the user can accept with
  `ALL` or list individual numbers. Mode B asks within the phase's
  mini-approval loop.
- **HOME** — inform, don't propose. The user may legitimately use claude
  in their home dir. Let them decide.
- **ALIVE** — no action.

## Safety

Before any deletion:

1. Snapshot `~/.claude.json` via `scripts/snapshot.sh`.
2. Delete entries via `jq del(.projects."<path>")` or equivalent Python
   mutation.
3. Write the result back and emit `ROLLBACK:` line.
4. Verify the JSON is still valid before declaring success.

If JSON validation fails after mutation, the skill MUST restore from the
snapshot and abort the phase with an error.

## False positives

- **SSH-style paths** like `/ssh:user@host:/home` are always reported as
  dead (they're not real local paths). That's correct for cleanup, but the
  user should understand what they are: remote-editing session hooks from
  earlier Claude Code versions. Safe to remove.
- **Recently-deleted projects** that the user may recreate: the script
  still reports them as dead. If the user plans to recreate, they should
  decline the prompt and wait.
