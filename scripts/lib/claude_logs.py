#!/usr/bin/env python3
"""
claude-tune — shared session-log reader.

Streams ~/.claude/projects/**/*.jsonl line-by-line to count usage of skills,
agents, slash commands, and MCP tools. Session logs can be very large (>1GB),
so we never read a whole file into memory.

Public API:
    iter_session_logs()                 -> yields Path for each *.jsonl
    count_substrings(patterns, files)   -> dict: pattern -> {files: set, count: int}
    newest_mtime(files)                 -> float | None
    oldest_mtime(files)                 -> float | None
    observation_window_days(files)      -> int (0 if empty)

Patterns are checked as plain substrings (not regex). Callers pass the
exact literal strings they want to detect: e.g. '"skill":"<name>"',
'"/<name>', '"subagent_type":"<name>"', 'mcp__<server>__'.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable, Iterator


CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME", str(Path.home() / ".claude")))
PROJECTS_DIR = CLAUDE_HOME / "projects"

# Shared category rubric — used by every audit script that classifies usage.
CATEGORY_ORDER = {"HEAVY": 0, "ACTIVE": 1, "COLD": 2, "DEAD": 3}


def categorize(uses: int, window_days: int, heavy_threshold: int) -> str:
    """Return HEAVY/ACTIVE/COLD/DEAD given a use count and observation window.

    - HEAVY: uses >= heavy_threshold
    - ACTIVE: 1 <= uses < heavy_threshold
    - DEAD: uses == 0 and window_days > 0 (we have logs to be sure)
    - COLD: uses == 0 and window_days == 0 (no logs to confirm)
    """
    if uses >= heavy_threshold:
        return "HEAVY"
    if uses > 0:
        return "ACTIVE"
    if window_days > 0:
        return "DEAD"
    return "COLD"


def iter_session_logs(root: Path | None = None) -> Iterator[Path]:
    """Yield every *.jsonl path under the projects tree.

    Includes per-project logs and subagent logs in `subagents/` subdirs.
    Does NOT follow symlinks — if the user has linked in an external dir,
    we don't scan it to avoid reading unrelated content and producing
    misleading counts.
    """
    base = root or PROJECTS_DIR
    if not base.exists():
        return
    for dirpath, _dirs, files in os.walk(base, followlinks=False):
        for fname in files:
            if fname.endswith(".jsonl"):
                yield Path(dirpath) / fname


def count_substrings(
    patterns: list[str],
    files: Iterable[Path] | None = None,
) -> dict[str, dict[str, object]]:
    """Stream every jsonl file and count pattern hits.

    Returns a dict: pattern -> {"files": set[Path], "count": int, "last_mtime": float|None}
    "files" is the set of file paths containing at least one hit.
    "count" is the total number of lines containing the pattern across all files.
    "last_mtime" is the most recent mtime among hit files.

    Patterns are plain substring matches (very fast, no regex overhead).
    """
    results: dict[str, dict[str, object]] = {
        p: {"files": set(), "count": 0, "last_mtime": None} for p in patterns
    }

    files_iter = files if files is not None else iter_session_logs()

    for path in files_iter:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    for p in patterns:
                        if p in line:
                            info = results[p]
                            info["count"] = int(info["count"]) + 1
                            files_set: set[Path] = info["files"]  # type: ignore[assignment]
                            if path not in files_set:
                                files_set.add(path)
                                try:
                                    mtime = path.stat().st_mtime
                                except OSError:
                                    mtime = None
                                prev = info["last_mtime"]
                                if mtime is not None and (prev is None or mtime > prev):
                                    info["last_mtime"] = mtime
        except OSError:
            continue

    return results


def newest_mtime(files: Iterable[Path]) -> float | None:
    newest: float | None = None
    for path in files:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def oldest_mtime(files: Iterable[Path]) -> float | None:
    oldest: float | None = None
    for path in files:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if oldest is None or mtime < oldest:
            oldest = mtime
    return oldest


def observation_window_days(files: Iterable[Path] | None = None) -> int:
    """Return the age in days of the oldest session log — the observation window.

    A usage count of 0 only means "unused within this window". Skills or agents
    older than the window may have been used but the log was rotated.
    """
    files_list = list(files) if files is not None else list(iter_session_logs())
    if not files_list:
        return 0
    oldest = oldest_mtime(files_list)
    if oldest is None:
        return 0
    return max(0, int((time.time() - oldest) / 86400))


# CLI: python3 claude_logs.py            -> human summary on stderr
#      python3 claude_logs.py --json      -> {"session_logs": N, "observation_window_days": N}
#      python3 claude_logs.py <pattern>   -> count <pattern> across logs
if __name__ == "__main__":
    logs = list(iter_session_logs())
    if "--json" in sys.argv:
        print(
            json.dumps(
                {
                    "session_logs": len(logs),
                    "observation_window_days": observation_window_days(logs),
                }
            )
        )
    else:
        print(f"found {len(logs)} session logs", file=sys.stderr)
        print(
            f"observation window: {observation_window_days(logs)} days", file=sys.stderr
        )
        patterns = [a for a in sys.argv[1:] if not a.startswith("--")]
        if patterns:
            results = count_substrings(patterns, logs)
            for p, info in results.items():
                print(f"{p}: {info['count']} hits in {len(info['files'])} files")  # type: ignore[arg-type]
