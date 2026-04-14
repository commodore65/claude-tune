#!/usr/bin/env python3
"""
claude-tune Phase 9 — agents audit.

Walks ~/.claude/agents/*.md, counts subagent invocations across session
logs using the pattern '"subagent_type":"<name>"', categorizes each.

Emits JSON on stdout with the same HEAVY/ACTIVE/COLD/DEAD shape as skills.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from claude_logs import (  # noqa: E402
    CATEGORY_ORDER,
    categorize,
    count_substrings,
    iter_session_logs,
    observation_window_days,
)

CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME", str(Path.home() / ".claude")))
AGENTS_DIR = CLAUDE_HOME / "agents"

HEAVY_THRESHOLD = int(os.environ.get("CLAUDE_TUNE_HEAVY", "10"))


def discover_agents() -> list[tuple[str, Path]]:
    """Return [(name, path)] for every .md file under the agents dir."""
    if not AGENTS_DIR.is_dir():
        return []
    out = []
    for path in sorted(AGENTS_DIR.rglob("*.md")):
        if path.is_file():
            name = path.stem
            out.append((name, path))
    return out


def main() -> int:
    agents = discover_agents()
    if not agents:
        print(
            json.dumps(
                {
                    "agents": [],
                    "heavy": 0,
                    "active": 0,
                    "cold": 0,
                    "dead": 0,
                    "observation_window_days": 0,
                }
            )
        )
        return 0

    log_files = list(iter_session_logs())
    window_days = observation_window_days(log_files)

    patterns = [f'"subagent_type":"{n}"' for n, _ in agents]
    hits = count_substrings(patterns, log_files)

    counts = {"heavy": 0, "active": 0, "cold": 0, "dead": 0}
    results = []
    for name, path in agents:
        info = hits.get(f'"subagent_type":"{name}"', {"count": 0, "last_mtime": None})
        uses = int(info["count"])
        last_ts = info.get("last_mtime")
        last_date = None
        if last_ts:
            last_date = datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime(
                "%Y-%m-%d"
            )

        cat = categorize(uses, window_days, HEAVY_THRESHOLD)
        counts[cat.lower()] += 1

        results.append(
            {
                "name": name,
                "path": str(path),
                "uses": uses,
                "last_used_date": last_date,
                "category": cat,
            }
        )

    results.sort(key=lambda r: (CATEGORY_ORDER[r["category"]], -r["uses"]))

    print(
        json.dumps(
            {
                "agents": results,
                "heavy": counts["heavy"],
                "active": counts["active"],
                "cold": counts["cold"],
                "dead": counts["dead"],
                "observation_window_days": window_days,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
