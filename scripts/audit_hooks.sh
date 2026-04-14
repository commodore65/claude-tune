#!/usr/bin/env bash
# claude-tune Phase 2 — hooks audit.
#
# Default: STATIC analysis only — checks each registered hook for existence,
# whether the script reads stdin JSON (vs the common Claude Code 2.x bug of
# expecting CLAUDE_FILE_PATH env var), and whether the event/matcher combo
# looks sensible.
#
# Live firing test is OPT-IN via --live flag, which the SKILL sets only AFTER
# the user explicitly confirms they accept that it may trigger real side
# effects (Slack notifications, file writes, network calls) in their hook
# scripts.
#
# Emits JSON on stdout: { "hooks": [{name, event, matcher, path, exists,
# reads_stdin, uses_env_file_path, verdict, notes}], "broken": N, "noisy": N }
#
# Verdict categories:
#   OK        — exists, looks correct, unlikely to be broken
#   BROKEN    — script missing, or stdin handling likely wrong for Claude Code 2.x
#   NOISY     — Stop or UserPromptSubmit event with prose echo; runs on every turn
#   UNKNOWN   — script exists but we can't tell (not a shell script, binary, etc.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

LIVE_FIRE=0
if [ "${1:-}" = "--live" ]; then
    LIVE_FIRE=1
fi

SETTINGS="$CLAUDE_HOME/settings.json"
if [ ! -r "$SETTINGS" ]; then
    printf '{"hooks": [], "broken": 0, "noisy": 0, "error": "settings.json not readable"}\n'
    exit 0
fi

# Use python to parse settings.json and walk hooks — bash + jq is brittle
# and jq may not be installed on every machine.
python3 - "$SETTINGS" "$LIVE_FIRE" <<'PY'
import json, os, re, stat, subprocess, sys

settings_path = sys.argv[1]
live_fire = sys.argv[2] == "1"

try:
    settings = json.load(open(settings_path))
except Exception as e:
    print(json.dumps({"hooks": [], "broken": 0, "noisy": 0,
                      "error": f"parse failed: {e}"}))
    sys.exit(0)

hooks_conf = settings.get("hooks") or {}
results = []
broken = 0
noisy = 0

# Noisy events: fire on every turn, cheap to spam the context
NOISY_EVENTS = {"Stop", "UserPromptSubmit"}

def script_reads_stdin(path):
    """Best-effort check: does the script use stdin at all?

    Returns True if script contains $(cat), "INPUT=$(cat)", read, python sys.stdin,
    or similar patterns. False if it only uses env vars.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError:
        return None
    patterns = [
        r"INPUT=\$\(cat", r"\$\(cat\b", r"\bcat\s*\|", r"\bread\s+[A-Za-z_]",
        r"sys\.stdin", r"stdin\.", r"STDIN",
    ]
    for pat in patterns:
        if re.search(pat, content):
            return True
    return False

def script_uses_env_file_path(path):
    """Detects the common Claude Code 2.x bug: script expects CLAUDE_FILE_PATH
    or similar env var that the harness no longer sets (JSON is via stdin now).
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError:
        return None
    return bool(re.search(r"CLAUDE_FILE_PATH|CLAUDE_TOOL_INPUT", content))

def extract_path_from_command(cmd):
    """Grab the first script-like path from a 'command' string."""
    m = re.search(r"(/[^\s]+\.(?:sh|py|js|rb|pl))", cmd)
    return m.group(1) if m else None

def resolve_home(p):
    return os.path.expanduser(p) if p else p

def try_live_fire(path, event, matcher):
    """Opt-in: send mock JSON stdin matching the event type, capture output/exit.

    Respects the script's own interpreter:
      - `.sh` files are run with `bash`
      - Everything else is executed directly so the OS honors the shebang
    This avoids the common failure where a Python/Ruby/Node hook gets
    sourced by bash and errors out in confusing ways.
    """
    if not os.path.isfile(path):
        return {"ran": False, "reason": "not a file"}
    mock = {
        "tool_name": "Edit" if matcher and "Edit" in matcher else "Bash",
        "tool_input": {"file_path": "/tmp/claude-tune-probe.txt",
                       "command": "true"},
        "hook_event_name": event,
    }
    if path.endswith(".sh"):
        argv = ["bash", path]
    else:
        # Must be executable so the OS can honor the shebang.
        if not os.access(path, os.X_OK):
            return {"ran": False, "reason": "not executable (non-.sh scripts must be chmod +x)"}
        argv = [path]
    try:
        proc = subprocess.run(
            argv,
            input=json.dumps(mock),
            capture_output=True, text=True, timeout=5,
        )
        return {"ran": True, "exit": proc.returncode,
                "stdout_len": len(proc.stdout), "stderr_len": len(proc.stderr)}
    except subprocess.TimeoutExpired:
        return {"ran": True, "error": "timeout", "exit": -1}
    except Exception as e:
        return {"ran": False, "reason": str(e)}

for event, hook_list in hooks_conf.items():
    for item in (hook_list or []):
        matcher = item.get("matcher", "*")
        for h in (item.get("hooks") or []):
            cmd = h.get("command", "")
            hook_type = h.get("type", "command")
            script_path = resolve_home(extract_path_from_command(cmd))
            exists = bool(script_path and os.path.isfile(script_path))
            reads = script_reads_stdin(script_path) if exists else None
            env_bug = script_uses_env_file_path(script_path) if exists else None

            verdict = "OK"
            notes = []

            if script_path is None:
                # Inline command with no script path (e.g. `echo done`).
                # Can't statically inspect — report as UNKNOWN, not BROKEN.
                verdict = "UNKNOWN"
                notes.append("inline command, no script path to inspect")
            elif not exists:
                verdict = "BROKEN"
                notes.append(f"script not found: {script_path}")
            elif env_bug and not reads:
                verdict = "BROKEN"
                notes.append("relies on CLAUDE_FILE_PATH env var (broken in CC 2.x, must read stdin JSON)")
            elif reads is False and hook_type == "command":
                # SessionStart and SessionEnd hooks legitimately don't need stdin —
                # they fire outside a tool call, so no meaningful payload exists.
                if event in {"SessionStart", "SessionEnd"}:
                    pass  # stay OK
                else:
                    verdict = "UNKNOWN"
                    notes.append("script does not appear to read stdin; may rely on env vars")

            if event in NOISY_EVENTS and verdict == "OK":
                verdict = "NOISY"
                notes.append(f"fires on every {event}; contributes to per-turn context")

            live = None
            if live_fire and exists and verdict != "BROKEN":
                live = try_live_fire(script_path, event, matcher)

            if verdict == "BROKEN":
                broken += 1
            if verdict == "NOISY":
                noisy += 1

            results.append({
                "event": event,
                "matcher": matcher,
                "type": hook_type,
                "command": cmd,
                "path": script_path,
                "exists": exists,
                "reads_stdin": reads,
                "uses_env_file_path_bug": env_bug,
                "verdict": verdict,
                "notes": notes,
                "live_fire": live,
            })

print(json.dumps({
    "hooks": results,
    "broken": broken,
    "noisy": noisy,
    "live_fire_enabled": live_fire,
}, indent=2))
PY
