---
name: test-and-fix
description: Run the test suite, analyze failures, and auto-fix the failing code. Iterates up to 3 times until green or reports what remains broken.
user_invocable: true
argument-hint: "[optional: test file, test name pattern, or language/framework]"
tools: Read, Write, Edit, Glob, Grep, Bash
model: inherit
---

# Test and Fix

Run the test suite, identify failures, and fix them automatically. Fixes target the **source code**, not the tests — unless the tests themselves are demonstrably wrong.

**Input**: Optional arguments — a specific test file, test name pattern (e.g. `test_parse_cert`), or language/framework hint (e.g. `pytest`, `cargo`). If omitted, auto-detects everything.

## Phase 1 — Detect Project and Test Framework

Scan the project root to determine the language and test runner:

| Signal | Framework | Run Command |
|--------|-----------|-------------|
| `Cargo.toml` | Rust / cargo | `cargo test` |
| `pyproject.toml`, `pytest.ini`, `setup.py`, `requirements.txt` | Python / pytest | `pytest -v` |
| `bun.lockb`, `bunfig.toml` | TypeScript / bun | `bun test` |
| `package.json` (has `test` script) | Node / npm | `npm test` |
| `go.mod` | Go | `go test ./...` |
| `Makefile` (has `test` target) | Make-based | `make test` |
| `*.bats` files in `test/` or `tests/` | Shell / BATS | `bats test/` |

If the user provided a framework hint, use that instead of auto-detection.

If a specific test file was provided, scope the run:
- **cargo**: `cargo test --test <name>` or filter with `cargo test <pattern>`
- **pytest**: `pytest -v <file>` or `pytest -v -k "<pattern>"`
- **bun**: `bun test <file>`
- **npm**: pass pattern via `npm test -- --grep "<pattern>"` if supported
- **go**: `go test -run "<pattern>" ./...`

```
DETECT checkpoint: Language=[X], Framework=[Y], Command=[Z], Scope=[all | filtered]
```

## Phase 2 — Run Tests (Attempt 1)

Run the test suite and capture the full output.

```bash
# Example for Rust
cargo test 2>&1
# Example for Python
pytest -v 2>&1
```

Also run the linter if applicable:
- **Rust**: `cargo clippy -- -D warnings 2>&1`
- **Python**: `ruff check . 2>&1`
- **Shell**: `shellcheck <changed-scripts> 2>&1`

If **all tests pass**: skip to Phase 5 (report success).

If tests fail: record the failures and proceed to Phase 3.

```
RUN checkpoint: [X pass, Y fail, Z skip]. Failures: [list of test names]
```

## Phase 3 — Analyze and Fix

**Agent perspective**: Builder (use `subagent_type: builder` if spawning via Task tool)

For each failing test:

1. **Read the test** to understand what behavior it expects.
2. **Read the failure output** — assertion mismatches, stack traces, error messages.
3. **Trace to source** — identify the source file and function where the bug lives.
4. **Fix the source code**. Rules:
   - Fix the implementation, NOT the test — unless the test has a clear bug (wrong expected value, broken setup, outdated assertion).
   - If you must change a test, explain why and flag it in the report.
   - Minimal changes — fix only what is needed to pass. No drive-by refactoring.
   - Handle error paths properly. No silent failures or unwraps without context.
5. **Run lint** after each fix to ensure no new warnings.

```
FIX checkpoint: [N files modified]. Changes: [brief list]
```

## Phase 4 — Re-run and Iterate

Re-run the test suite after fixes.

- **All pass**: proceed to Phase 5.
- **Still failing**: return to Phase 3 with the remaining failures.
- **Maximum 3 iterations**. If tests still fail after 3 fix attempts, **escalate** — don't just report.

```
ITERATION [1|2|3]: [X pass, Y fail]. [Proceeding to fix | ESCALATING — max attempts reached]
```

### Escalation After 3 Iterations

If 3 fix attempts fail, the problem is likely deeper than a simple bug. Escalate:

1. **Spawn Architect** (`subagent_type: architect`, `model: "opus"`) with prompt:
   "Think deeply about why these tests are failing after 3 fix attempts. Analyze the test expectations vs. the implementation design. Is there a design-level issue? Review: [list of failing tests and error summaries]"
2. If Architect identifies a design issue → report to user with Architect's analysis and recommended redesign.
3. If Architect says implementation is correct and tests are wrong → fix the tests (flag clearly in report).
4. If Architect can't determine → report ESCALATING to user with full context.

## Phase 5 — Report

Produce a clear final report.

```
## Test and Fix Report

**Project**: [path]
**Framework**: [detected framework]
**Scope**: [all tests | filtered to X]

### Result: ALL PASSING / PARTIAL / FAILED

### Test Summary
- Total: [N]
- Passing: [N]
- Failing: [N]
- Skipped: [N]

### Fixes Applied
| File | Change | Tests Fixed |
|------|--------|-------------|
| `path/to/file.ext` | [what changed] | `test_name_1`, `test_name_2` |

### Tests Modified (if any)
| Test File | Change | Reason |
|-----------|--------|--------|
| (none, or list) | | |

### Remaining Failures (if any)
| Test | Error | Analysis |
|------|-------|----------|
| `test_name` | [error summary] | [why it resists fixing — missing dep, design issue, etc.] |

### Lint Status
- [tool]: PASS/FAIL ([N] warnings/errors)

### Coverage (if available)
- [coverage summary or "not configured"]

### Iterations
- Attempt 1: [X pass, Y fail]
- Attempt 2: [X pass, Y fail] (if needed)
- Attempt 3: [X pass, Y fail] (if needed)
```

## When to Use

- After pulling changes that might have broken tests
- After a refactor to catch and fix any regressions
- When CI is red and you want to auto-fix locally
- As a general "make the tests green" command
- Before `/commit-push-pr` to ensure a clean commit

## When NOT to Use

- When you want to write new tests first (use `/tdd` instead)
- When you only want to verify without fixing (use `/prove-it` instead)
- When the test failures are intentional (e.g. red phase of TDD)
