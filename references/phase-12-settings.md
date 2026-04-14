# Phase 12 — Settings sanity

## Goal

Surface low-risk, low-reward cruft in `~/.claude/settings.json`:

- Permission allow-list entries the harness already auto-allows
- Env vars pointing to paths that don't exist
- Deprecated top-level keys that have been moved or removed in newer
  Claude Code versions

## What the phase does NOT touch

The skill intentionally stays away from:

- `theme`, `model`, `language` — user preferences
- `keybindings` — user customization
- `effortLevel`, `voiceEnabled`, `skipDangerousModePermissionPrompt` — UX
  toggles
- `extraKnownMarketplaces` — marketplace config, may be referenced by
  plugin infrastructure
- `hooks` — handled by Phase 2
- `enabledPlugins` — handled by Phase 4

Anything in those areas is a user decision, not cruft.

## Auto-allowed tools

The harness allows these tools without explicit permission:

- `Read`
- `Glob`
- `Grep`
- `Agent`

If any of these appear in `permissions.allow`, they're cruft. Removing them
has no effect on behavior — the harness would allow them anyway — but it
keeps the allow-list readable.

Entries with forms like `Bash(*:*)` or `mcp__name__*` are legitimate
customizations and never flagged.

## Stale env vars

The `env` block in settings.json can set env vars that are injected into
every claude session. If an entry's value is an absolute path that no
longer exists on disk, the env var is dead weight. Flag for review, not
auto-removal — the user may have plans to restore that path.

## Deprecated keys

Keys that have been superseded across Claude Code versions. The list
in `audit_settings.py` is small and should be updated quarterly as
Claude Code releases new versions:

- `disableAutoupdater` → use `DISABLE_AUTOUPDATER=1` env var
- `telemetryDisabled` → use `DISABLE_TELEMETRY=1` env var

If new deprecations appear, add them to the `DEPRECATED_KEYS` dict in
`audit_settings.py`.

## Report table shape

```
SETTINGS SANITY
===============
Allow-list cruft: 4
  - Read       (auto-allowed)
  - Glob       (auto-allowed)
  - Grep       (auto-allowed)
  - Agent      (auto-allowed)

Stale env vars: 0

Deprecated keys: 0
```

## Cleanup actions

- **Allow-list cruft:** propose removal (snapshot, Python/jq mutation of
  the allow array). Mode A applies after approval; Mode B per-item.
- **Stale env vars:** inform only. Don't propose action; user may have
  plans for the path.
- **Deprecated keys:** propose migration. Show the replacement (env var or
  new key). User approves and manually sets the replacement — the skill
  does not auto-migrate.

## False positives

- **Tool forms that LOOK bare but encode scope**: e.g.
  `Agent(some_specific_agent)` is not the same as the auto-allowed `Agent`.
  The script only matches entries whose prefix before `(` is exactly one
  of the auto-allowed names.
- **Env vars whose paths are created at runtime** (e.g. a path in `/tmp`
  that a launcher creates). These will show as stale when audited cold.
  The script never auto-removes; the user reviews.
