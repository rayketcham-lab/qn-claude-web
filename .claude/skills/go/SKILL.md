---
name: go
description: Resume work from a previous session. Reads MEMORY.md and continues autonomously.
user-invocable: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch
disable-model-invocation: true
---

You are resuming work from a previous session. Follow these steps exactly:

1. **Read MEMORY.md** for saved state — task, status, what's done, what's next
2. **If recovery pointer exists**, pull MCP snapshot via `search_context`
3. **Run `git status`** to verify working tree state
4. **Check `## Deferred Work`** for pending items
5. **Start working** on the next item immediately

**Work rules**:
- Work autonomously — do not ask "should I proceed?" Just do the work.
- At decision points, use AskUserQuestion with 2-4 concrete options (mark recommended).
- Update MEMORY.md when task status changes.
- Do not summarize the plan. Start doing the next thing.
