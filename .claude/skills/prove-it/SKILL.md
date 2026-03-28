---
name: prove-it
description: Prove that the current implementation works. Runs tests, diffs behavior, validates correctness. Use after implementing a feature or fix to verify before marking complete.
user_invocable: true
tools: Read, Glob, Grep, Bash
model: inherit
---

# Prove It Works

Run a comprehensive verification of the current implementation. This is the most important quality practice — "prove to me this works."

## Verification Steps

### 1. Detect What Changed
```bash
git diff --name-only HEAD~1..HEAD   # last commit
git diff --name-only                # unstaged changes
git diff --stat main..HEAD          # full branch diff
```

### 2. Run All Relevant Tests
Based on what changed, run the appropriate test suite:

**Rust files changed:**
```bash
cargo test 2>&1
cargo clippy -- -D warnings 2>&1
```

**Python files changed:**
```bash
pytest -v 2>&1
ruff check . 2>&1
```

**Shell scripts changed:**
```bash
shellcheck *.sh 2>&1
```

**Any files changed:**
```bash
# Build check — does it compile/build cleanly?
# Run the project-specific build command
```

### 3. Behavioral Diff
If this is a bug fix or refactor:
- Show the before/after behavior explicitly
- Run the specific failing case and prove it now passes
- Run related edge cases to check for regressions

### 4. Edge Case Probes
For the changed code, probe:
- Empty/null inputs
- Boundary values
- Error paths (does it fail gracefully?)
- Concurrent access (if applicable)

### 5. Verdict
Produce a clear verdict:

```
## Verification Verdict

**Status**: PROVEN / FAILED / PARTIAL

### Tests
- [Suite]: [X pass, Y fail, Z skip]

### Build
- Compile: PASS/FAIL
- Lint: PASS/FAIL (N warnings)

### Behavioral Check
- [What was verified and how]

### Regressions
- [None / List]

### Confidence
- [HIGH / MEDIUM / LOW] — [why]
```

## When to Use
- After `/commit-push-pr` to verify before the PR
- After Builder finishes any implementation
- After a bug fix to prove the fix works
- After a refactor to prove behavior is unchanged
- When you're suspicious something might be broken
