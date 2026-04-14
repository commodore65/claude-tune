#!/usr/bin/env python3
"""
claude-tune Phase 8 — memory files audit.

Discovers memory files under ~/.claude/projects/*/memory/*.md (the typical
auto-memory location) and under ~/.claude/memory/ if present. For each:

- age_days (mtime vs now)
- stale_dates: any date strings in content that are >= 14 days in the past
               compared to today (heuristic for "Phase X due by Y" entries
               that never got updated)
- rename_suggestion: if filename contains a number ("feedback_7_services")
                     and the content mentions a different number, suggest
                     a stable name
- refs_exist: for paths mentioned in the content, whether they still exist
              (best-effort heuristic)

Emits JSON on stdout:

{
  "memory_files": [
    {"path": "...", "age_days": N, "stale_dates": ["..."],
     "rename_suggestion": "..." | null, "dead_refs": [...],
     "category": "FRESH|AGING|STALE|SUSPECT"}
  ],
  "fresh": N, "aging": N, "stale": N, "suspect": N
}

Categories:
  FRESH    age < 30 days, no stale markers
  AGING    30 <= age < 90 days, no stale markers
  STALE    age >= 90 days
  SUSPECT  any age, but has stale_dates OR rename_suggestion OR dead_refs
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME", str(Path.home() / ".claude")))
PROJECTS = CLAUDE_HOME / "projects"

AGING_DAYS = int(os.environ.get("CLAUDE_TUNE_MEM_AGING_DAYS", "30"))
STALE_DAYS = int(os.environ.get("CLAUDE_TUNE_MEM_STALE_DAYS", "90"))


def discover_memory_files() -> list[Path]:
    out: list[Path] = []
    for root in [PROJECTS, CLAUDE_HOME / "memory"]:
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            # Heuristic: only count paths under a "memory" directory
            if "memory" in path.parts:
                out.append(path)
    return sorted(set(out))


DATE_RE = re.compile(r"(20\d{2})-([0-1]\d)-([0-3]\d)")


def find_stale_dates(content: str, today: float) -> list[str]:
    """Return ISO date strings from content that are >=14 days in the past."""
    cutoff = today - (14 * 86400)
    stale: list[str] = []
    for m in DATE_RE.finditer(content):
        y, mo, d = m.groups()
        try:
            ts = time.mktime((int(y), int(mo), int(d), 0, 0, 0, 0, 0, -1))
        except Exception:
            continue
        if ts < cutoff:
            iso = f"{y}-{mo}-{d}"
            if iso not in stale:
                stale.append(iso)
    return stale


NUMBER_IN_NAME_RE = re.compile(r"_(\d+)_")


def filename_content_mismatch(path: Path, content: str) -> str | None:
    """If filename contains a number that doesn't match content, suggest rename."""
    m = NUMBER_IN_NAME_RE.search(path.stem)
    if not m:
        return None
    name_num = int(m.group(1))
    # Look for "N services", "N items", etc in first 400 chars.
    # English nouns only — no language-specific vocabulary.
    mention = re.search(
        r"\b(\d+)\b\s*(?:services|servers|items|entries|projects|tasks|rules|files)\b",
        content[:400],
    )
    if mention and int(mention.group(1)) != name_num:
        # Suggest removing the number and using a stable name
        stable = path.stem.replace(f"_{name_num}_", "_").replace(f"{name_num}_", "")
        return f"{stable}.md"
    return None


def find_dead_refs(content: str) -> list[str]:
    """Best-effort: return absolute paths mentioned in content that don't exist."""
    dead: list[str] = []
    for m in re.finditer(r"(~/[\w./+\-]+)", content):
        path = os.path.expanduser(m.group(1))
        if "*" in path or "?" in path:
            continue
        if not os.path.exists(path):
            if path not in dead:
                dead.append(path)
    return dead[:10]  # cap for report readability


def main() -> int:
    files = discover_memory_files()
    if not files:
        print(
            json.dumps(
                {
                    "memory_files": [],
                    "fresh": 0,
                    "aging": 0,
                    "stale": 0,
                    "suspect": 0,
                }
            )
        )
        return 0

    today = time.time()
    counts = {"fresh": 0, "aging": 0, "stale": 0, "suspect": 0}
    results = []

    for path in files:
        try:
            st = path.stat()
            mtime = st.st_mtime
        except OSError:
            continue
        age_days = int((today - mtime) / 86400)

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            content = ""

        stale_dates = find_stale_dates(content, today)
        rename = filename_content_mismatch(path, content)
        dead_refs = find_dead_refs(content)

        if stale_dates or rename or dead_refs:
            cat = "SUSPECT"
        elif age_days >= STALE_DAYS:
            cat = "STALE"
        elif age_days >= AGING_DAYS:
            cat = "AGING"
        else:
            cat = "FRESH"
        counts[cat.lower()] += 1

        results.append(
            {
                "path": str(path),
                "age_days": age_days,
                "stale_dates": stale_dates,
                "rename_suggestion": rename,
                "dead_refs": dead_refs,
                "category": cat,
            }
        )

    order = {"SUSPECT": 0, "STALE": 1, "AGING": 2, "FRESH": 3}
    results.sort(key=lambda r: (order[r["category"]], -r["age_days"]))

    print(
        json.dumps(
            {
                "memory_files": results,
                "fresh": counts["fresh"],
                "aging": counts["aging"],
                "stale": counts["stale"],
                "suspect": counts["suspect"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
