# Report Templates

## TOC

1. Emoji legend
2. Baseline report
3. Findings report (per-phase block)
4. Combined findings report (Mode A and C)
5. Delta report (Mode A and B)
6. Rollback cookbook block

## 1. Emoji legend

Fixed across every report. Never introduce new symbols:

- 🟢 **OK** — no action, reported for inventory
- 🟠 **Attention** — informational or proposed review
- 🔴 **Broken / dead** — proposed cleanup, disable, or removal
- ⚪ **Disabled / inactive** — present but not currently doing anything

## 2. Baseline report

Run exactly once per invocation, after `scripts/baseline.sh` completes.

```
CLAUDE-TUNE — BASELINE
======================

Run:      <run timestamp in UTC>
Mode:     <Safe Autopilot | Guided Interactive | Read-only>
Version:  Claude Code <version or "unknown">
Scope:    ~/.claude, ~/.claude.json, CLAUDE.md files under current cwd

Inventory               Count
---------------------   ------
Skills (global)             <N>
Agents                      <N>
Hooks (global)              <N>
Plugins (enabled)           <N>
MCP servers (global)        <N>
Memory files                <N>
Project entries             <N>

Disk (top 10, ~/.claude)
Path                              Size
--------------------------------  ---------
<path>                            <human size>
...

Observation window (session logs): <N> days
Snapshot directory: ~/.claude/backups/claude-tune/<run ts>/
```

Implementation: the LLM reads `baseline.json` from the snapshot dir, pulls
each value into the template, formats disk bytes as human-readable
(KB/MB/GB), and emits the text block.

## 3. Findings report (per-phase block)

Each phase produces one block with this shape:

```
PHASE <N> — <title> — <short rubric>
====================================

<table with columns specific to the phase>

Summary: <heavy count> heavy, <active count> active, <cold count> cold, <dead count> dead
```

Tables use fixed-width columns so they render in monospace terminals.
Severity emoji is the FIRST column in every table.

### Shared table shell (most phases)

```
Category   Name                       Uses   Last used    Detail
--------   ------------------------   ----   ----------   -----------------------
🟢 HEAVY   <name>                     <N>    <YYYY-MM-DD> <short detail>
🟢 ACTIVE  <name>                     <N>    <YYYY-MM-DD> <short detail>
🟠 COLD    <name>                     <N>    —            <short detail>
🔴 DEAD    <name>                     <N>    —            <short detail>
```

### Phase 1 (processes) table

```
Type       Pid        Ppid    Age       Command
--------   --------   -----   -------   --------------------------------
🔴 ORPHAN  <pid>         1    <age>     <cmd>
🟠 HEAVY   <pid>     <ppid>   <cpu%>    <cmd>
🟢 MINE    <pid>         —    —         <cmd>
```

### Phase 2 (hooks) table

```
Verdict      Event            Matcher          Script                                  Notes
----------   -------------    --------------   -------------------------------------   -------------
🟢 OK        <event>          <matcher>        <flat path>                             —
🔴 BROKEN    <event>          <matcher>        <flat path>                             <reason>
🟠 NOISY     <event>          <matcher>        <flat path>                             <reason>
🟠 UNKNOWN   <event>          <matcher>        <flat path>                             inspect manually
```

## 4. Combined findings report (Mode A and C)

In Mode A and Mode C, all 12 phase blocks are concatenated under a single
header, with a summary table at the top and per-phase blocks below:

```
CLAUDE-TUNE — FINDINGS
======================
Run: <timestamp>
Mode: <Mode A or C>

Summary
-------
Phase                  Items   Attention   Broken
--------------------   -----   ---------   ------
1. Processes             <N>         <N>      <N>
2. Hooks                 <N>         <N>      <N>
...
12. Settings             <N>         <N>      <N>
--------------------   -----   ---------   ------
Total                    <N>         <N>      <N>

<Phase 1 block>

<Phase 2 block>

...

<Phase 12 block>
```

In Mode C the report ends here. In Mode A the combined findings report is
followed by the single-gate approval prompt (see `safety.md`).

## 5. Delta report (Mode A and B)

Produced after any cleanups are applied. Shows before/after counts and
byte deltas.

```
CLAUDE-TUNE — DELTA
===================
Run: <timestamp>
Mode: <Mode A or B>

Category               Before    After    Δ
--------------------   ------    -----    ---------
Hooks broken               <N>      <N>   <Δ>
Plugins enabled            <N>      <N>   <Δ>  (disabled)
MCP overweight             <N>      <N>   <Δ>  (stashed)
Memory suspect             <N>      <N>   <Δ>
Projects dead              <N>      <N>   <Δ>  (removed)
Disk: telemetry          <MB>    <MB>     <Δ MB>
Disk: old backups        <MB>    <MB>     <Δ MB>

Total actions applied:  <N>
Total bytes reclaimed:  <N MB>
Snapshots stored:       ~/.claude/backups/claude-tune/<run ts>/

<Rollback cookbook block (see §6)>

Items still outstanding (declined or ambiguous):
- <list of user-declined items>
```

The "before" column is pulled from `baseline.json`. The "after" column is
computed by re-running each audit script (or reading in-memory state the
skill kept during execution). Δ is `after - before` (usually negative for
cleanups).

## 6. Rollback cookbook block

Emitted at the end of every Delta report. Lists every ROLLBACK line
collected during execution, plus notes on non-rollbackable actions.

```
ROLLBACK COOKBOOK
=================
To undo every reversible change from this run:

  cp -p <snapshot> <target>
  cp -p <snapshot> <target>
  ...

Non-rollbackable actions (no undo possible):
  - killed PID <pid> (<command>)
  - deleted file <path> (kept in <backup dir>)

To replay just the claude.json mutations:
  cp -p ~/.claude/backups/claude-tune/<ts>/.claude.json.bak ~/.claude.json
```

The rollback block is always present in the Delta report, even if no
mutations happened (it prints "No mutations this run.").
