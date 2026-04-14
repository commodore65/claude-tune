#!/usr/bin/env python3
"""
claude-tune Phase 12 — settings.json sanity audit.

Looks for cruft in ~/.claude/settings.json:

1. Permissions allow-list entries that are already auto-allowed by the
   harness (Read, Glob, Grep, Agent). Listing them is harmless but adds
   noise.
2. Env vars in settings.json that are stale (point to paths that don't
   exist).
3. Keys that look deprecated (schema drift across Claude Code versions).

Emits JSON on stdout:
{
  "allow_cruft": [...],
  "stale_env": [...],
  "deprecated": [...],
  "total_issues": N
}

NOTE: this phase is intentionally conservative. It never proposes changing
keys the user may have set intentionally (theme, model, keybindings, etc.).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME", str(Path.home() / ".claude")))
SETTINGS = CLAUDE_HOME / "settings.json"

# Tools the harness auto-allows without explicit permission
AUTO_ALLOWED = {"Read", "Glob", "Grep", "Agent"}

# Deprecated or moved keys across Claude Code versions
DEPRECATED_KEYS = {
    # Historical examples — extend quarterly based on release notes
    "disableAutoupdater": "use env var DISABLE_AUTOUPDATER=1 instead",
    "telemetryDisabled": "use env var DISABLE_TELEMETRY=1 instead",
}


def main() -> int:
    if not SETTINGS.is_file():
        print(
            json.dumps(
                {
                    "allow_cruft": [],
                    "stale_env": [],
                    "deprecated": [],
                    "total_issues": 0,
                }
            )
        )
        return 0
    try:
        d = json.load(open(SETTINGS))
    except Exception as e:
        print(
            json.dumps(
                {
                    "allow_cruft": [],
                    "stale_env": [],
                    "deprecated": [],
                    "total_issues": 0,
                    "error": f"parse failed: {e}",
                }
            )
        )
        return 0

    # 1. Allow-list cruft
    allow_cruft = []
    allow = (d.get("permissions") or {}).get("allow") or []
    for entry in allow:
        # Match bare tool names OR tool:* forms
        bare = entry.split("(", 1)[0].strip()
        if bare in AUTO_ALLOWED:
            allow_cruft.append(
                {"entry": entry, "reason": f"{bare} is auto-allowed by the harness"}
            )

    # 2. Stale env vars
    stale_env = []
    env = d.get("env") or {}
    if isinstance(env, dict):
        for k, v in env.items():
            if isinstance(v, str) and v.startswith("/") and not os.path.exists(v):
                stale_env.append(
                    {"name": k, "value": v, "reason": "path does not exist"}
                )

    # 3. Deprecated keys
    deprecated = []
    for key, advice in DEPRECATED_KEYS.items():
        if key in d:
            deprecated.append({"key": key, "advice": advice})

    total = len(allow_cruft) + len(stale_env) + len(deprecated)
    print(
        json.dumps(
            {
                "allow_cruft": allow_cruft,
                "stale_env": stale_env,
                "deprecated": deprecated,
                "total_issues": total,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
