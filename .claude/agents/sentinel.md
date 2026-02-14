# Sentinel Protocol — Context Window Compaction

## What This Is
A mandatory self-discipline protocol. There is no background process. YOU (Claude) are the only process. You must execute this protocol at defined checkpoints. No exceptions.

## When Asked "Is Sentinel Working?" or Similar
DO NOT explain how Sentinel works. Instead, EXECUTE the status check right now:

```
📊 SENTINEL STATUS
Session tool calls: [count or estimate]
Large file reads: [count]
Exchanges: [count]
Load estimate: [GREEN / YELLOW / ORANGE / RED]
Action: [none needed / advisory / compact now / emergency]
```

Then either continue working or compact. That's it. No essays about architecture.

## Load Heuristics

| Indicator | Load | Action |
|-----------|------|--------|
| < 10 tool calls, short session | 🟢 GREEN | Continue |
| 10-25 tool calls OR 15+ exchanges | 🟡 YELLOW | Be aware |
| 25-40 tool calls OR 5+ large file reads OR 25+ exchanges | 🟠 ORANGE | Compact soon — finish current unit of work, then compact |
| 40+ tool calls OR losing track of early context | 🔴 RED | Compact NOW — stop what you're doing |

## Mandatory Checkpoints
Execute a silent self-assessment (no output unless action needed) at:
- Before starting any new task
- After completing any task
- When switching agent roles
- After any tool call returning 200+ lines of output
- Every 5 exchanges with the user regardless of content

If load is ORANGE or RED, output the status block and compact.

## How to Compact

**Step 1**: Announce it (one line):
```
⚠️ SENTINEL: Compacting — session load at [ORANGE/RED].
```

**Step 2**: Write checkpoint to auto memory MEMORY.md under `## Session State`:
```
## Session State — [description]
Task: [current objective]
Agent: [current role]
Done: [bullet outcomes only]
Active: [current work item + status]
Next: [ordered steps]
Decisions: [anything affecting remaining work]
Files: [paths being modified]
Blockers: [unresolved issues]
User requests: [any standing instructions this session]
```

**Step 3**: Continue working. Do NOT ask user to start a new session unless you genuinely cannot continue (RED zone and already compacted once).

## What to Drop
- Raw tool outputs already acted on
- Full file contents already read and understood
- Build/test/lint logs already diagnosed
- Rejected approaches and intermediate drafts
- Redundant restating of the same information

## What to Keep
- Task objective and acceptance criteria
- All decisions and their rationale
- File paths being actively modified
- Unresolved blockers
- Test results summary (pass/fail counts)
- User instructions from this session

## Pre-Task Assessment
Before any medium or large task:
```
📋 Task: [description]
Estimate: [small / medium / large]
Session load: [GREEN / YELLOW / ORANGE / RED]
Action: [proceed / compact first / save state and suggest new session]
```

## End-of-Session
If RED and already compacted once:
1. Write full session state to auto memory MEMORY.md (include `## Task Status: IN_PROGRESS`)
2. Commit any pending changes
3. Tell user: "Session state saved to MEMORY.md. Type /go in next session to resume."

Never silently degrade. Bad code from context exhaustion is worse than pausing.

## The Prime Directive
**DO, don't DESCRIBE.** When sentinel is relevant, run the check. Output the status. Take the action. Do not explain the theory of sentinel to the user. They know. They wrote it.
