#!/usr/bin/env python3
"""
claude-tune Phase 11 — ~/.claude.json projects section audit.

Walks .projects in ~/.claude.json, classifies each entry as:
  - dead   : path no longer exists on disk
  - home   : legitimate but not a "project" (home dir, Desktop, Downloads)
  - alive  : path exists and looks like an actual project

Emits JSON on stdout:
{
  "dead":  [{path, size_bytes}],
  "home":  [{path, size_bytes}],
  "alive": [{path, size_bytes}],
  "total": N
}
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CLAUDE_JSON = Path(os.environ.get("CLAUDE_JSON", str(Path.home() / ".claude.json")))

HOME = str(Path.home())
# Paths that are legitimate but NOT projects (they'll be flagged as "home")
HOME_LIKE = {
    HOME,
    f"{HOME}/Desktop",
    f"{HOME}/Downloads",
    f"{HOME}/Documents",
}


def main() -> int:
    if not CLAUDE_JSON.is_file():
        print(json.dumps({"dead": [], "home": [], "alive": [], "total": 0}))
        return 0
    try:
        d = json.load(open(CLAUDE_JSON))
    except Exception as e:
        print(
            json.dumps(
                {
                    "dead": [],
                    "home": [],
                    "alive": [],
                    "total": 0,
                    "error": f"parse failed: {e}",
                }
            )
        )
        return 0

    projects = d.get("projects") or {}
    dead: list[dict] = []
    home: list[dict] = []
    alive: list[dict] = []

    for path, entry in projects.items():
        size_bytes = len(json.dumps(entry))
        record = {"path": path, "size_bytes": size_bytes}
        if not os.path.isdir(path):
            dead.append(record)
        elif path in HOME_LIKE:
            home.append(record)
        else:
            alive.append(record)

    # Sort each bucket by size desc
    for bucket in (dead, home, alive):
        bucket.sort(key=lambda r: -r["size_bytes"])

    print(
        json.dumps(
            {
                "dead": dead,
                "home": home,
                "alive": alive,
                "total": len(projects),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
