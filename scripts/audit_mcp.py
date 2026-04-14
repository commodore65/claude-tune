#!/usr/bin/env python3
"""
claude-tune Phase 5 — MCP servers audit.

Reads ~/.claude.json for global and per-project mcpServers blocks, counts
tool invocations per server across session logs using the mcp__<name>__
prefix, and categorizes each server.

Emits JSON on stdout:

{
  "servers": [
    {"name": "...", "scope": "global"|"project:<path>",
     "command": "...", "uses": N, "last_used_date": "...",
     "category": "HEAVY|ACTIVE|COLD|DEAD|OVERWEIGHT"}
  ],
  "heavy": N, "active": N, "cold": N, "dead": N, "overweight": N,
  "observation_window_days": N
}

Categories:
  HEAVY       ≥ 10 uses total (uses heavy threshold)
  ACTIVE      1–9 uses
  COLD        0 uses, observation window too short
  DEAD        0 uses, observation window meaningful
  OVERWEIGHT  (independent flag) — any server whose tool namespace has been
              called so often it contributes meaningfully to context bloat,
              OR (heuristic) a server whose project-specific use pattern
              suggests it should be on-demand-loaded instead of globally
              scoped. We flag any global MCP with < HEAVY_THRESHOLD uses as
              a candidate for on-demand loading.

Note: MCP tool count (how many tools the server exposes) is NOT computed here
— that requires spawning the server to query its tool list, which is outside
the skill's local-only, no-process-spawning safety rules. The skill documents
the overweight heuristic as "globally scoped + not HEAVY".
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
CLAUDE_JSON = Path(os.environ.get("CLAUDE_JSON", str(Path.home() / ".claude.json")))

HEAVY_THRESHOLD = int(os.environ.get("CLAUDE_TUNE_HEAVY", "10"))


def load_claude_json():
    if not CLAUDE_JSON.is_file():
        return {}
    try:
        return json.load(open(CLAUDE_JSON))
    except Exception:
        return None  # distinguished from {} to signal parse error


def collect_servers(cj):
    """Return a list of (name, scope, config) tuples from global + project MCPs."""
    out = []
    for name, cfg in (cj.get("mcpServers") or {}).items():
        out.append((name, "global", cfg))
    for proj_path, proj in (cj.get("projects") or {}).items():
        for name, cfg in (proj.get("mcpServers") or {}).items():
            out.append((name, f"project:{proj_path}", cfg))
    return out


def main() -> int:
    cj = load_claude_json()
    if cj is None:
        print(
            json.dumps(
                {
                    "servers": [],
                    "heavy": 0,
                    "active": 0,
                    "cold": 0,
                    "dead": 0,
                    "overweight": 0,
                    "observation_window_days": 0,
                    "error": "~/.claude.json parse failed",
                }
            )
        )
        return 0

    servers = collect_servers(cj)
    if not servers:
        print(
            json.dumps(
                {
                    "servers": [],
                    "heavy": 0,
                    "active": 0,
                    "cold": 0,
                    "dead": 0,
                    "overweight": 0,
                    "observation_window_days": 0,
                }
            )
        )
        return 0

    log_files = list(iter_session_logs())
    window_days = observation_window_days(log_files)

    # De-duplicate names — a server might be listed in multiple scopes
    unique_names = sorted({name for (name, _, _) in servers})
    patterns = [f"mcp__{n}__" for n in unique_names]
    hits = count_substrings(patterns, log_files)

    counts = {"heavy": 0, "active": 0, "cold": 0, "dead": 0, "overweight": 0}
    results = []
    for name, scope, cfg in servers:
        pat = f"mcp__{name}__"
        info = hits.get(pat, {"count": 0, "last_mtime": None})
        uses = int(info["count"])
        last_ts = info.get("last_mtime")
        last_date = None
        if last_ts:
            last_date = datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime(
                "%Y-%m-%d"
            )

        cat = categorize(uses, window_days, HEAVY_THRESHOLD)
        counts[cat.lower()] += 1

        # Overweight heuristic: globally scoped + not HEAVY → candidate for
        # on-demand loading. Orthogonal to the main category.
        overweight = scope == "global" and cat != "HEAVY"
        if overweight:
            counts["overweight"] += 1

        results.append(
            {
                "name": name,
                "scope": scope,
                "command": cfg.get("command"),
                "args": cfg.get("args", []),
                "uses": uses,
                "last_used_date": last_date,
                "category": cat,
                "overweight": overweight,
            }
        )

    results.sort(key=lambda r: (CATEGORY_ORDER[r["category"]], -r["uses"]))

    print(
        json.dumps(
            {
                "servers": results,
                "heavy": counts["heavy"],
                "active": counts["active"],
                "cold": counts["cold"],
                "dead": counts["dead"],
                "overweight": counts["overweight"],
                "observation_window_days": window_days,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
