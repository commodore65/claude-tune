#!/usr/bin/env python3
"""
claude-tune Phase 4 — plugins audit.

Reads enabledPlugins from ~/.claude/settings.json and walks
~/.claude/plugins/cache/ for disk footprint. Counts tool/skill usage
per plugin by scanning session logs for the plugin prefix.

Emits JSON on stdout:

{
  "plugins": [
    {"name": "...", "enabled": true|false,
     "disk_bytes": N, "uses": N, "category": "HEAVY|ACTIVE|COLD|DEAD|DISABLED"}
  ],
  "enabled_count": N, "disabled_count": N, "total_disk_bytes": N,
  "observation_window_days": N
}

Category for ENABLED plugins: same HEAVY/ACTIVE/COLD/DEAD rules as skills.
Category for DISABLED plugins: always "DISABLED".
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from claude_logs import count_substrings, iter_session_logs, observation_window_days  # noqa: E402

CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME", str(Path.home() / ".claude")))
SETTINGS = CLAUDE_HOME / "settings.json"
PLUGINS_CACHE = CLAUDE_HOME / "plugins" / "cache"

HEAVY_THRESHOLD = int(os.environ.get("CLAUDE_TUNE_HEAVY", "10"))


def load_enabled() -> dict[str, bool]:
    if not SETTINGS.is_file():
        return {}
    try:
        d = json.load(open(SETTINGS))
    except Exception:
        return {}
    return d.get("enabledPlugins") or {}


def dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = Path(root) / f
            try:
                total += fp.stat().st_size
            except OSError:
                continue
    return total


def plugin_disk_sizes() -> dict[str, int]:
    """Return {short_name: bytes} for everything under plugins/cache/*/*."""
    sizes: dict[str, int] = {}
    if not PLUGINS_CACHE.is_dir():
        return sizes
    for marketplace in PLUGINS_CACHE.iterdir():
        if not marketplace.is_dir():
            continue
        for plugin_dir in marketplace.iterdir():
            if not plugin_dir.is_dir():
                continue
            name = plugin_dir.name
            sizes[name] = dir_size_bytes(plugin_dir)
    return sizes


def short_plugin_name(full: str) -> str:
    """Strip @marketplace suffix from 'name@marketplace' → 'name'."""
    return full.split("@", 1)[0]


def main() -> int:
    enabled = load_enabled()
    sizes = plugin_disk_sizes()

    all_names: set[str] = set()
    all_names.update(short_plugin_name(n) for n in enabled.keys())
    all_names.update(sizes.keys())

    log_files = list(iter_session_logs())
    window_days = observation_window_days(log_files)

    # Usage counting — plugin tools appear as mcp__plugin_<name>_<server>__
    # or via skill:"<plugin>:<skillname>" for plugin-bundled skills.
    patterns = []
    for n in sorted(all_names):
        patterns.append(f"plugin_{n}_")
        patterns.append(f'"skill":"{n}:')
    hits = count_substrings(patterns, log_files)

    counts = {"heavy": 0, "active": 0, "cold": 0, "dead": 0, "disabled": 0}
    results = []
    total_disk = 0

    # Map enabled keys back to short names, preserving the @suffix state
    enabled_by_short: dict[str, bool] = {}
    for full, val in enabled.items():
        enabled_by_short[short_plugin_name(full)] = bool(val)

    for name in sorted(all_names):
        is_enabled = enabled_by_short.get(name, False)
        disk = sizes.get(name, 0)
        total_disk += disk

        tool_hits = int(hits.get(f"plugin_{name}_", {}).get("count", 0))
        skill_hits = int(hits.get(f'"skill":"{name}:', {}).get("count", 0))
        uses = tool_hits + skill_hits

        if not is_enabled:
            cat = "DISABLED"
        elif uses >= HEAVY_THRESHOLD:
            cat = "HEAVY"
        elif uses > 0:
            cat = "ACTIVE"
        elif window_days > 0:
            cat = "DEAD"
        else:
            cat = "COLD"
        counts[cat.lower()] += 1

        results.append(
            {
                "name": name,
                "enabled": is_enabled,
                "disk_bytes": disk,
                "uses": uses,
                "category": cat,
            }
        )

    order = {"HEAVY": 0, "ACTIVE": 1, "COLD": 2, "DEAD": 3, "DISABLED": 4}
    results.sort(key=lambda r: (order[r["category"]], -r["disk_bytes"]))

    print(
        json.dumps(
            {
                "plugins": results,
                "heavy": counts["heavy"],
                "active": counts["active"],
                "cold": counts["cold"],
                "dead": counts["dead"],
                "disabled": counts["disabled"],
                "enabled_count": sum(1 for v in enabled.values() if v),
                "disabled_count": sum(1 for v in enabled.values() if not v),
                "total_disk_bytes": total_disk,
                "observation_window_days": window_days,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
