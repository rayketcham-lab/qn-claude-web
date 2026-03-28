---
name: team
description: Full multi-agent team review using parallel subagents. Spawns Architect, SecOps, Tester, DevOps, and Verifier concurrently, then consolidates into a prioritized action plan.
argument-hint: "[description of what to review]"
user_invocable: true
tools: Read, Glob, Grep, Bash, WebFetch, WebSearch
model: inherit
---

# /team — Full Team Review

Run a multi-agent review of the current change or feature using **parallel subagents**. Each agent runs in its own context window for deep, focused analysis.

## Target

$ARGUMENTS

## Process

### Step 1 — Parallel Agent Spawn

Launch **all five review agents concurrently** using the Task tool. Each agent gets the review target as context and produces a focused assessment.

Use a single message with multiple Task tool calls:

1. **Architect** (`subagent_type: architect`, `model: "opus"`) — Think deeply about the architectural implications. Evaluate system design, module boundaries, API contracts, and dependency decisions for: $ARGUMENTS
2. **SecOps** (`subagent_type: secops`, `model: "opus"`) — Think deeply about the security implications. Enumerate all attack vectors. Security review: input validation, crypto correctness, dependency vulnerabilities, secret detection for: $ARGUMENTS
3. **Tester** (`subagent_type: tester`) — Identify test gaps, suggest edge cases, evaluate coverage for: $ARGUMENTS
4. **DevOps** (`subagent_type: devops`) — Assess build/deploy impact, CI pipeline changes, configuration updates for: $ARGUMENTS
5. **Verifier** (`subagent_type: verifier`) — Run tests, lint, and build checks. Report current pass/fail state for: $ARGUMENTS

**Note**: Architect and SecOps use extended thinking (`model: "opus"`) for deeper analysis. Tester, DevOps, and Verifier use standard model for speed.

**Handling subagent failures**: If any agent returns INCOMPLETE or ESCALATING, note it in the consolidation. Don't re-spawn — report the partial result with the agent's handoff notes.

All five agents run in parallel. Wait for all to complete before proceeding.

### Step 2 — Consolidation

After all agents return, synthesize their findings into a single prioritized report. Cross-reference findings — if SecOps flags a vulnerability and Tester is missing a test for it, link them. If Architect suggests a design change and DevOps sees a build impact, connect those.

### Step 3 — Simplification Check

If the review reveals implementation complexity, note where Simplifier could reduce it. This is advisory — don't spawn Simplifier unless the user asks.

## Output

```
# Team Review: [Subject]

## Architect
[Design assessment — API contracts, module boundaries, dependency impact]

## SecOps
[Security findings — risk level: LOW/MEDIUM/HIGH/CRITICAL]

## Tester
[Coverage assessment — gaps found, edge cases to add, recommended tests]

## DevOps
[Build/deploy impact — CI changes, config updates, infrastructure needs]

## Verifier
[Current state — tests passing/failing, lint status, build status]

## Simplification Opportunities
[Where complexity could be reduced, or "None identified"]

## Action Plan
Priority 1 (Blocking):
- [ ] [item — agent source]

Priority 2 (Should fix):
- [ ] [item — agent source]

Priority 3 (Nice to have):
- [ ] [item — agent source]
```

## When to Use

- Before merging a significant change
- Reviewing a new feature's design and implementation
- Assessing project posture or technical debt
- After a dependency update or security advisory
- Any time the user invokes `/team` with a review target
