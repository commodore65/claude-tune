# Phase 02 — Hooks Audit

## TOC

1. Goal
2. What is a Claude Code hook
3. The "silently broken" failure modes
4. Static check rubric (default mode)
5. Live firing test (opt-in)
6. Verdict categories
7. Severity mapping
8. Report table shape
9. Cleanup actions (per verdict)
10. False positive list

## 1. Goal

Find hooks that are registered in `~/.claude/settings.json` but do not actually
do what they claim to do — the single highest-value finding this skill produces,
because a silently-broken hook is otherwise invisible.

## 2. What is a Claude Code hook

A hook is a shell command registered under `settings.json` → `hooks` →
`<Event>` → `[{matcher, hooks: [{type, command}]}]`. Events include
`PreToolUse`, `PostToolUse`, `Stop`, `UserPromptSubmit`, `SessionStart`,
`SessionEnd`. The harness invokes the registered command when the event fires
and pipes a JSON payload on stdin describing the triggering tool call.

Payload example (PostToolUse for Edit):

```json
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/path/to/foo.ts",
    "old_string": "...",
    "new_string": "..."
  }
}
```

The hook's stdout is fed back into the assistant's context as an additional
system reminder. A zero exit code means "no alert"; non-zero blocks the tool
call (in PreToolUse) or signals an error.

## 3. The "silently broken" failure modes

### 3a. Env-var assumption (the Claude Code 2.x bug)

Older hook templates read the file path from `$CLAUDE_FILE_PATH` or similar
env vars. Claude Code 2.x stopped setting these — the payload is stdin-only
now. Scripts that still rely on env vars exit silently with `-z` checks and
never run. The registered hook appears to be "installed" but does literally
nothing.

Detection: grep the script for `CLAUDE_FILE_PATH` or `CLAUDE_TOOL_INPUT` AND
check whether it reads stdin. Env var reference without stdin reader → 🔴.

### 3b. Missing script file

The path referenced in `command` does not exist on disk. Happens after the
user moves or deletes a project. Harness logs a silent error; the hook never
fires. Detection: `os.path.isfile(path)` on the extracted path.

### 3c. Matcher mismatch

A hook registered for `PreToolUse` with `matcher: "Edit|Write"` that actually
only checks tool name `Bash` in its body — it runs but always early-returns.
Hard to detect statically; flagged as `UNKNOWN` if the script contains
`tool_name` comparisons that do not include any of the matcher's tools.

### 3d. Noisy hooks

Hooks on `Stop` or `UserPromptSubmit` fire on every turn. If they print
non-trivial output (prose reminders, checklists), that output is injected into
context every turn. Even a working hook of this type is a smell unless the
user explicitly wants per-turn reminders. Flag as 🟠 NOISY.

## 4. Static check rubric (default mode)

For each `(event, matcher, command)` triple:

1. Extract the script path from `command` (regex: first token ending in
   `.sh|.py|.js|.rb|.pl`).
2. `os.path.isfile(path)` → if false, verdict = BROKEN, note "script not found".
3. Read the script (text mode, replace errors). If unreadable → UNKNOWN.
4. Check for stdin handling. Patterns: `INPUT=$(cat`, `$(cat`, `read FOO`,
   `sys.stdin`, `STDIN`. Presence → `reads_stdin = True`.
5. Check for env-var assumption. Patterns: `CLAUDE_FILE_PATH`,
   `CLAUDE_TOOL_INPUT`. Presence → `uses_env_file_path_bug = True`.
6. Combine:
   - `uses_env_file_path_bug == True` AND `reads_stdin == False` → **BROKEN**
     (the telltale 2.x silently-broken case).
   - `reads_stdin == False` and `hook_type == "command"` → **UNKNOWN**
     (may rely on env vars we don't recognize).
7. If verdict still OK AND event in `{Stop, UserPromptSubmit}` → downgrade to
   **NOISY**.

## 5. Live firing test (opt-in)

Default is OFF. The skill must ask the user before enabling it:

> Some of your hooks may have side effects (write logs, send Slack messages,
> fire network calls) when we send mock JSON. Enable live firing test?
> Y) Yes — probe each hook with a mock payload
> N) No — static checks only

Only when the user says Y does the skill re-run `audit_hooks.sh --live`. The
live harness:

- Constructs a mock payload matching each hook's event type and matcher.
- Uses a throwaway path `/tmp/claude-tune-probe.txt` so even hooks that do
  real file writes target a safe target.
- Runs `bash <script>` with the mock payload on stdin, 5-second timeout.
- Captures exit code, stdout length, stderr length. Does NOT print the body
  of stdout to avoid leaking hook output into the report.
- A zero exit + non-zero stdout means "hook fired and produced output" — a
  useful confirmation for hooks whose static analysis was UNKNOWN.

Never make the live firing test the default. The user said "default static,
runtime opt-in" and that is the contract.

## 6. Verdict categories

| Verdict | Meaning                                              | Emoji |
| ------- | ---------------------------------------------------- | ----- |
| OK      | Exists, reads stdin, not on a noisy event            | 🟢    |
| NOISY   | Works but fires every turn with non-trivial output   | 🟠    |
| UNKNOWN | Exists but stdin handling unclear (inspect manually) | 🟠    |
| BROKEN  | Missing, or relies on CC 2.x env var bug             | 🔴    |

## 7. Severity mapping

- 🟢 OK — no action. Reported for inventory purposes.
- 🟠 NOISY — recommend the user move the hook to a less frequent event
  (e.g. SessionStart for once-per-session reminders), or accept the
  trade-off and leave it.
- 🟠 UNKNOWN — recommend manual inspection. Skill does not propose a fix.
- 🔴 BROKEN — propose disable (remove from `settings.json`) OR fix the script
  to read stdin. Which action depends on whether the user still wants the
  hook: ask before proposing removal.

## 8. Report table shape

```
HOOKS (N registered)
====================
Event             Matcher        Script                              Verdict     Notes
---------------   ------------   ---------------------------------   --------    ------------------------
PreToolUse        Edit|Write     ~/.claude/hooks/watchdog.sh         🟢 OK       —
PreToolUse        Bash           ~/.claude/hooks/precommit.sh        🟢 OK       —
PostToolUse       Edit|Write     ~/.claude/hooks/auto-format.sh      🔴 BROKEN   relies on CLAUDE_FILE_PATH (CC 2.x), no stdin reader
Stop              *              ~/.claude/hooks/stop-verify.sh      🟠 NOISY    fires on every Stop; injects prose reminder
SessionStart      *              ~/.claude/hooks/stale-detector.sh   🟢 OK       —
```

## 9. Cleanup actions (per verdict)

Never auto-apply. Always propose with explicit approval:

- **BROKEN (missing script):** ask user "remove registration from
  settings.json?" → if yes, snapshot settings.json, delete the hook entry
  via jq or python, rewrite.
- **BROKEN (env var bug):** show the user a diff that converts the script
  from env-var to stdin JSON pattern. Do NOT auto-apply — the user should
  read and approve each script change.
- **NOISY:** suggest "move to SessionStart?" or "suppress output and return
  early?" — propose as options, let the user decide.
- **UNKNOWN:** no action proposed. Report and move on.

## 10. False positive list

- Scripts that source an external helper (e.g. `. /path/to/lib.sh`) where the
  helper reads stdin — static check may miss this. The hook is actually
  working. Mitigation: UNKNOWN verdict (not BROKEN), let the user decide.
- Hooks written in a language other than bash/python (e.g. Go binary). The
  `reads_stdin` regex won't find anything. UNKNOWN, not BROKEN.
- Hooks that genuinely use env vars that the harness DOES still set (e.g.
  `$CLAUDE_PROJECT_DIR`). If the user has confirmed the hook is working in
  practice, add an exception note and re-run.
- Hooks registered conditionally (e.g. matcher only fires for certain file
  types). A static audit cannot reproduce the matcher's intended filter.
  Accept the reported verdict as advisory.
