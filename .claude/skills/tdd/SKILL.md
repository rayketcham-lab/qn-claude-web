---
name: tdd
description: Test-Driven Development — Red/Green/Refactor cycle. Writes failing tests first from a spec, implements minimum code to pass, refactors, then verifies.
user_invocable: true
argument-hint: [feature description or requirement]
tools: Read, Write, Edit, Glob, Grep, Bash
model: inherit
---

# TDD — Red / Green / Refactor

Run a full test-driven development cycle for a feature or requirement. Tests are written **before** implementation, ensuring the design is driven by the specification rather than the code.

**Input**: A feature description, requirement, or user story passed as the skill argument.

## Phase 1 — RED (Write Failing Tests)

**Agent perspective**: Tester

1. Analyze the feature spec. Identify the behaviors, inputs, outputs, and edge cases it implies.
2. Determine the appropriate test framework and file location based on the project:
   - **Rust**: `#[cfg(test)]` module or `tests/` directory, `cargo test`
   - **Python**: `pytest` in `tests/` or `test_*.py`, `pytest -v`
   - **Shell**: BATS or inline assertion scripts
3. Write test cases that define the expected behavior. Each test should:
   - Have a descriptive name reflecting the requirement
   - Test one behavior per test
   - Cover happy path, edge cases, and error conditions
4. Run the tests. **All must fail.**
   - If any test passes → something is wrong. Either the feature already exists or the test is not actually testing the new behavior. Stop and report.
5. Record which tests were written and what specs they cover.

```
RED checkpoint: N tests written, all failing. Specs covered: [list]
```

## Phase 2 — GREEN (Implement Minimum Code)

**Agent perspective**: Builder

1. Read the failing tests carefully. They are your specification.
2. Write the **minimum code** to make all tests pass. Rules:
   - No gold-plating — if the tests don't require it, don't build it
   - No extra features, no premature abstractions
   - Favor the simplest correct implementation
3. Run the tests. **All must pass.**
   - If any test still fails → fix the implementation, not the test
   - If a test reveals an implementation design issue → fix the design, keep the test
4. Run lint/check for the language:
   - **Rust**: `cargo clippy -- -D warnings`
   - **Python**: `ruff check`
   - **Shell**: `shellcheck`

```
GREEN checkpoint: N/N tests passing. Files modified: [list]
```

## Phase 3 — REFACTOR (Simplify Without Changing Behavior)

**Agent perspective**: Simplifier

1. Review the implementation from Phase 2 for:
   - Duplicated code that can be extracted
   - Overly complex conditionals
   - Poor naming or unclear structure
   - Unnecessary allocations or inefficiencies
2. Refactor while keeping **all tests green**. Run tests after each change.
3. If no refactoring is needed, say so — don't force changes.

```
REFACTOR checkpoint: [changes made or "none needed"]. Tests still passing: YES/NO
```

## Phase 4 — VERIFY (Final Gate)

**Agent perspective**: Verifier

1. Run the full test suite (not just the new tests)
2. Run lint and build checks
3. Check for regressions — did any previously passing test break?
4. Behavioral diff: compare the change against the base state
5. Produce the final verdict

## Output Format

```
## TDD Report: [Feature]

**Cycle**: RED -> GREEN -> REFACTOR -> VERIFIED

### Red Phase
- Tests written: [N] in [file(s)]
- All failing: YES/NO
- Specs covered: [list]

### Green Phase
- Files modified: [list]
- Tests passing: [X/Y]
- Implementation approach: [brief]

### Refactor Phase
- Changes made: [list or "none needed"]
- Tests still passing: YES/NO

### Verdict: PROVEN / FAILED
```

## When to Use

- Starting a new feature where the requirements are clear enough to test
- Implementing a bug fix where you can write the regression test first
- Working on specification-driven code (protocol handlers, validators, parsers)
- When you want tighter, more focused tests than test-after produces
- Any time the user invokes `/tdd` with a feature description

## When NOT to Use

- Exploratory/prototyping work where requirements are still forming
- Pure refactors with no behavioral change (use Simplifier + Verifier instead)
- Configuration changes, documentation, or CI/CD work
