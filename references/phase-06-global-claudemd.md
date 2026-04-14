# Phase 06 — Global CLAUDE.md Audit (LLM read)

## TOC

1. Goal
2. Why no script
3. Procedure
4. Rubric (R1–R5)
5. Findings format
6. Cleanup actions
7. What NOT to touch

## Goal

Read `~/.claude/CLAUDE.md` and surface low-value or misleading content:

- Generalizations that are actually narrow
- Conditional `<important if="...">` tags that don't actually gate anything
- Duplicated guidance that lives more authoritatively elsewhere
- Instructions that reference removed or renamed tools

## Why no script

This phase is LLM-driven. Heuristics like "is this generalization actually
accurate for this user?" require reading the body, judging the claim, and
balancing against the user's likely stack. Scripts can't do that well.
The skill uses the Read tool and applies the rubric below.

## Procedure

1. Read `~/.claude/CLAUDE.md` via the Read tool.
2. For each section, walk the rubric (below) and classify as OK / trim /
   flag / contradict.
3. Present findings as a table. Do NOT propose edits; the user decides.

## Rubric

### R1 — Narrow generalization smell

Look for absolute statements about stack, tooling, or conventions that
might not be true for all of the user's projects. Examples of suspect
patterns:

- "Default port 5173 (Vite)" — only true if most projects are Vite.
- "Tests use vitest" — only true if most projects are JS/TS.
- "Deploy via systemd" — only true for Linux-hosted services.

Rule of thumb: if the statement implies a single stack, flag it. The user
can tell you whether their projects actually share that stack. If they
don't, suggest rewording to be stack-agnostic.

### R2 — Conditional tag inspection

`<important if="...">` blocks are meant to be conditional context. Some
harnesses respect the tag and load only when the condition matches; others
treat the tag as prose and load always. Either way, the CONTENT of the
block should genuinely be conditional on the tag's description.

Flag cases where the block's content is not actually specific to the
condition (e.g., an "if deploying to VM" block that contains unrelated
general advice).

### R3 — Duplicated guidance

If a section repeats guidance that lives in another more-authoritative
place (a skill's SKILL.md, a memory file, the platform's official docs),
suggest pruning. The rule of thumb is: CLAUDE.md should contain
user-specific overrides and project-wide policies, not general best
practices that are already baked into the harness.

### R4 — Reference rot

Look for mentions of specific tools, paths, or filenames. Check if:

- The referenced file exists (via Read or Glob)
- The mentioned tool is still installed (via `which` or the relevant
  config)
- The path uses a naming scheme that is still current

Flag any reference that has rotted.

### R5 — Tone and brevity

The CLAUDE.md file is always loaded into context. Every word costs tokens.
Flag sections that are verbose for no reason (lists of rationale, prose
explanations where bullet points suffice, historical background that
belongs in a memory file).

## Findings format

```
GLOBAL CLAUDE.md
================
Section                          Issue                              Suggested fix
-------------------------------  ---------------------------------  -------------------
Dev Server (line 23)             Narrow: assumes Vite              remove or rewrite
Deploy (line 45)                 Duplicates /deploy skill content   prune
Telegram Bots (if block)         Always-loaded, not conditional     move to memory
```

## Cleanup actions

- **trim** — propose a specific diff and show it to the user. User
  approves or rejects.
- **flag** — inform, don't propose an edit. User decides.
- **contradict** — highest priority. Surface the contradiction and ask
  the user to clarify which side is correct, then (after approval) update
  the file.

Every edit goes through `scripts/snapshot.sh` first.

## What NOT to touch

- User-specific overrides (style rules, language preferences, naming
  conventions) — these are the user's voice, never edit.
- Security rules (how to handle secrets, git signing, production gates) —
  never edit, only flag if something looks wrong.
- The file's first line — leave it intact if it's a header/title.
