#!/usr/bin/env python3
"""
claude-tune Phase 3 — skills audit.

Walks ~/.claude/skills/ (following symlinks, because many skills are symlinked
into ~/.agents/skills/*), enumerates every installed skill, and counts usage
across session logs using two substring patterns:

  - "skill":"<name>"         → Skill tool invocations
  - "/<name>\\b"              → slash-command style invocations

Emits JSON on stdout:

{
  "skills": [
    {"name": "...", "path": "...", "uses_tool": N, "uses_slash": N,
     "uses_total": N, "last_used_ts": 1234567890 | null,
     "last_used_date": "YYYY-MM-DD" | null,
     "category": "HEAVY|ACTIVE|COLD|DEAD"}
  ],
  "heavy": N, "active": N, "cold": N, "dead": N,
  "observation_window_days": N
}

Thresholds (configurable via env):
  HEAVY   ≥ 10 total uses
  ACTIVE  1–9 uses
  COLD    0 uses but file age < observation window
  DEAD    0 uses across the entire observation window

The COLD vs DEAD distinction guards against false positives from rotated logs.
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
SKILLS_DIR = CLAUDE_HOME / "skills"

HEAVY_THRESHOLD = int(os.environ.get("CLAUDE_TUNE_HEAVY", "10"))


def discover_skills() -> list[Path]:
    """Return every skill directory under ~/.claude/skills, dereferencing symlinks."""
    if not SKILLS_DIR.is_dir():
        return []
    skills: list[Path] = []
    for entry in sorted(SKILLS_DIR.iterdir()):
        try:
            if entry.is_dir():  # is_dir() follows symlinks by default
                skills.append(entry)
        except OSError:
            continue
    return skills


def main() -> int:
    skills = discover_skills()
    if not skills:
        print(
            json.dumps(
                {
                    "skills": [],
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

    # Build patterns: two per skill
    patterns: list[str] = []
    by_skill: dict[str, tuple[str, str]] = {}
    for s in skills:
        name = s.name
        tool_pat = f'"skill":"{name}"'
        slash_pat = f'"/{name}'
        patterns.append(tool_pat)
        patterns.append(slash_pat)
        by_skill[name] = (tool_pat, slash_pat)

    # One streaming pass over all session logs
    hits = count_substrings(patterns, log_files)

    counts = {"heavy": 0, "active": 0, "cold": 0, "dead": 0}
    results = []
    for s in skills:
        name = s.name
        tool_pat, slash_pat = by_skill[name]
        t = int(hits[tool_pat]["count"])
        sl = int(hits[slash_pat]["count"])
        total = t + sl

        last_ts = max(
            (
                v
                for v in (
                    hits[tool_pat].get("last_mtime"),
                    hits[slash_pat].get("last_mtime"),
                )
                if v is not None
            ),
            default=None,
        )

        cat = categorize(total, window_days, HEAVY_THRESHOLD)
        counts[cat.lower()] += 1

        last_date = None
        if last_ts:
            last_date = datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime(
                "%Y-%m-%d"
            )

        results.append(
            {
                "name": name,
                "path": str(s),
                "uses_tool": t,
                "uses_slash": sl,
                "uses_total": total,
                "last_used_ts": last_ts,
                "last_used_date": last_date,
                "category": cat,
            }
        )

    results.sort(key=lambda r: (CATEGORY_ORDER[r["category"]], -r["uses_total"]))

    print(
        json.dumps(
            {
                "skills": results,
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
