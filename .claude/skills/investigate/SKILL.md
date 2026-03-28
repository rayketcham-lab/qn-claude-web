---
name: investigate
description: Debug and investigate issues — trace symptoms to root cause. Use when something is broken, a test fails mysteriously, or behavior is unexpected.
argument-hint: "[error message | symptom | 'why is X broken']"
user_invocable: true
tools: Read, Glob, Grep, Bash, WebSearch
model: inherit
---

# /investigate — Root Cause Analysis

Given a symptom, systematically trace it to root cause and propose a fix.

## Target

$ARGUMENTS

## Process

### Step 1 — Reproduce

Confirm the problem exists and is reproducible:
- Run the failing command/test and capture exact output
- Note: error message, exit code, stack trace, log lines
- If intermittent, run 3 times and note frequency

### Step 2 — Locate

Find where the error originates:
- Search codebase for the error message text
- Trace the call chain: who calls the failing function? What calls that?
- Check recent changes: `git log --oneline -20 -- <relevant files>`
- Check if this worked before: `git log --all -S "<error string>" --oneline`

### Step 3 — Hypothesize (Extended Thinking)

Think deeply and step by step about potential causes. Consider second-order effects, timing issues, and non-obvious interactions.

Form 2-3 hypotheses ranked by likelihood:
1. Most likely cause (based on evidence)
2. Alternative explanation
3. Long-shot possibility

For each, identify what evidence would confirm or rule it out.

### Step 4 — Test Hypotheses

For each hypothesis (most likely first):
- Read the relevant code
- Check the specific condition that would cause this failure
- If possible, add temporary debug output to confirm
- Stop at the first confirmed hypothesis

**Hard cap: 5 hypotheses total.** If you've tested 5 hypotheses without confirming a root cause:
1. Report what you've ruled out and what evidence you have
2. Return status: **ESCALATING** — "Root cause not confirmed after 5 hypotheses. User context may be needed."
3. Include your best guess with confidence level

### Step 5 — Root Cause + Fix

```
## Investigation: [Symptom]

**Root Cause**: [One sentence — what's actually wrong]
**Location**: `file:line`
**Evidence**: [What confirmed this diagnosis]

### Fix
[Concrete code change or configuration fix]

### Regression Test
[Test that would catch this if it recurred]

### Related Risks
[Anything else that might have the same problem]
```

## Principles

- Evidence over intuition. Read the code, don't guess.
- Binary search: narrow the scope by half each step.
- Check the obvious first: config, permissions, dependencies, typos.
- "It worked before" → find the commit that broke it with `git bisect` or log search.
- Don't fix symptoms. Find the actual cause.
