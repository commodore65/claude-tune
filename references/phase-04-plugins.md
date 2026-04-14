# Phase 04 — Plugins Audit

## Goal

Find plugins that are enabled but rarely/never used, or disabled but still
eating disk space. Propose disable for unused enabled plugins; propose
uninstall (disk cleanup) for large disabled plugins the user is unlikely to
re-enable.

## What is a plugin

A Claude Code plugin is a marketplace-installed package that can ship
skills, MCP servers, hooks, and slash commands together under a single
namespace. Plugins are enabled/disabled via the `enabledPlugins` block in
`~/.claude/settings.json`:

```json
"enabledPlugins": {
  "some-plugin@some-marketplace": true,
  "other-plugin@some-marketplace": false
}
```

Plugin packages live under `~/.claude/plugins/cache/<marketplace>/<name>/`.

## Usage counting

Plugin-bundled tools typically appear in session logs as
`plugin_<name>_<server>_<tool>`. Plugin-bundled skills appear as
`"skill":"<name>:<subskill>"` in the Skill tool invocations. The script
counts both patterns.

Usage count is aggregated per short plugin name (strip `@marketplace`).

## Categories

| Category | Rule                                    |
| -------- | --------------------------------------- |
| HEAVY    | enabled, uses ≥ 10                      |
| ACTIVE   | enabled, 1 ≤ uses ≤ 9                   |
| COLD     | enabled, uses == 0, window short        |
| DEAD     | enabled, uses == 0, window long         |
| DISABLED | `enabled == false` (regardless of uses) |

## Disk footprint

For every plugin on disk (whether enabled or not), the script reports
`dir_size_bytes(~/.claude/plugins/cache/<marketplace>/<name>/)`. Disabled
plugins still take disk space — some can be 50 MB+. The delta report after
cleanup sums up reclaimed bytes only from actually-uninstalled plugins.

## Report table shape

```
PLUGINS (8 configured, 3 enabled, 5 disabled, 112 MB total)
===========================================================
Category     Plugin                 Enabled   Disk     Uses
----------   --------------------   -------   ------   ----
🟢 HEAVY     useful-plugin            yes     10 MB    42
🟠 DEAD      forgotten-plugin         yes      4 MB     0
⚪ DISABLED  heavy-old-plugin          no     49 MB     0
⚪ DISABLED  another-disabled          no     26 MB     0
```

## Cleanup actions

- **HEAVY, ACTIVE** → no action.
- **COLD** → inform only.
- **DEAD** → propose disable (flip `enabled: false` in settings.json, no
  disk deletion). Mode A can apply this after one combined approval since a
  disable is a trivial value flip and is snapshottable.
- **DISABLED with disk > 10 MB** → propose uninstall (`rm -rf` the plugin
  cache dir and remove from `enabledPlugins`). **Per-item approval** in both
  modes; this is a destructive operation.

Snapshot semantics: for disable, snapshot `~/.claude/settings.json`. For
uninstall, snapshot both `settings.json` AND copy the plugin dir to
`~/.claude/backups/claude-tune/<ts>/plugin__<name>/` so the user can
restore locally without re-downloading.
