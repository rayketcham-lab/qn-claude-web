---
name: save
description: Snapshot current task state to MCP for cross-session persistence. Use when switching tasks or before ending a session.
user_invocable: true
tools: Read, Write, Edit
---

# /save — Snapshot Task State

Store current working state to MCP and update MEMORY.md. No compaction — just persistence.

1. Scan conversation for deferred work (TODOs, issues to create, follow-ups)

2. Store structured snapshot to MCP:
   ```
   mcp__context-store__store_context:
     project: [project name]
     category: "task-snapshot"
     title: "[task description]"
     content: |
       TASK: [objective]
       STATUS: [IN_PROGRESS / COMPLETE / BLOCKED]
       DONE: [completed items]
       ACTIVE: [current work]
       NEXT: [remaining steps]
       FILES: [modified paths]
       DECISIONS: [choices with rationale]
       DEFERRED: [identified but not acted on]
     tags: "snapshot,[task-tag]"
   ```

3. Update MEMORY.md with current state, deferred work, and recovery pointer

4. Announce: "State saved. Recovery: `search_context(query='snapshot,[task-tag]')`"

Do NOT compact. Do NOT ask permission. Just save and report.
