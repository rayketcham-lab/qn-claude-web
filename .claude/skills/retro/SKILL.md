---
name: retro
description: Post-task retrospective — capture lessons learned and store them for future sessions. Builds cumulative intelligence across sessions.
argument-hint: "[task description or 'this session']"
user_invocable: true
tools: Read, Glob, Grep, Bash
model: inherit
---

# /retro — Retrospective & Lessons Capture

After completing a task, capture what went well, what went wrong, and what to do differently. Store findings in context-store for cumulative intelligence.

## Target

$ARGUMENTS

## Process

### Step 1 — Review What Happened

Look at the work just completed:
```bash
git log --oneline -20
git diff --stat main..HEAD
```
Read MEMORY.md for task context and decisions made.

### Step 2 — Identify Lessons

For each of these categories, note anything worth remembering:

**What went well** (reinforce):
- Approaches that worked on first try
- Tools/commands that saved time
- Patterns that should become standard

**What went wrong** (prevent):
- Bugs introduced and their root cause
- Time wasted on wrong approaches
- Assumptions that turned out to be false

**What was learned** (remember):
- Codebase quirks discovered
- Configuration gotchas
- API behaviors that weren't obvious

### Step 3 — Store in Context Store

For each lesson worth preserving, call `mcp__context-store__store_context` with:
- `project`: the project name
- `category`: `lesson`
- `title`: short, searchable title
- `content`: the lesson with context
- `tags`: relevant tags for future search

For architectural decisions, also call `mcp__context-store__record_decision`.

### Step 4 — Report

```
## Retro: [Task]

### Lessons Stored
1. [lesson title] — [one-line summary]
2. [lesson title] — [one-line summary]

### Decisions Recorded
1. [decision] — [rationale in brief]

### Patterns to Watch
- [anything that might recur]
```

## When to Use

- After completing any significant task
- After a debugging session that took longer than expected
- After discovering a non-obvious codebase behavior
- Before ending a session — capture while context is fresh
- When the user says "remember this" or "don't make this mistake again"
