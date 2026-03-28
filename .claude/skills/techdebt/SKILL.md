---
name: techdebt
description: Scan for technical debt and fix it. Uses Simplifier to identify dead code, duplication, complexity, and inconsistencies, then Verifier to confirm no regressions.
argument-hint: "[file, directory, or '.' for whole project]"
user_invocable: true
tools: Read, Write, Edit, Glob, Grep, Bash
model: inherit
---

# /techdebt — Find and Fix Technical Debt

Scan a file, directory, or entire project for technical debt. Identify issues, fix what can be fixed safely, and report what remains.

**Input**: Optional path (file, directory, or `.` for the whole project). Defaults to `.` if no argument given.

**Target**: $ARGUMENTS

## Phase 1 — SCAN (Identify Debt)

**Agent perspective**: Simplifier (`subagent_type: simplifier`)

Analyze the target for the following categories of technical debt, ordered by severity:

### Category A — Correctness Risk
- Missing error handling (silent failures, bare `unwrap()`, empty `except:`)
- TODO/FIXME/HACK comments indicating known broken or incomplete code
- Unreachable code paths that mask bugs

### Category B — Maintainability
- Duplicated logic (3+ lines repeated in 2+ places) that should be extracted
- Overly complex functions (50+ lines or 4+ levels of nesting)
- Inconsistent naming or patterns within the same module
- Dead code and unused imports

### Category C — Code Hygiene
- Magic numbers/strings that should be constants
- Outdated comments that no longer match the code
- Unnecessary type conversions or redundant operations
- Import ordering and formatting inconsistencies

**How to scan:**
1. Use Glob and Grep to find the files in scope
2. Use Grep to search for debt signals:
   ```
   TODO|FIXME|HACK|XXX|NOCOMMIT
   unwrap()  (Rust — without context)
   except:   (Python — bare except)
   # shellcheck disable  (Shell — suppressed warnings)
   ```
3. Use Read to examine flagged files for the deeper categories (duplication, complexity, naming)
4. For each finding, record: `file:line`, category (A/B/C), and a one-line description

```
SCAN checkpoint: [N] findings across [M] files. Breakdown: [A: X, B: Y, C: Z]
```

## Phase 2 — FIX (Safe Remediation)

**Agent perspective**: Simplifier (`subagent_type: simplifier`)

Fix what can be fixed safely. Rules:

1. **Category A fixes** — Always fix. Missing error handling and dead code are correctness risks.
2. **Category B fixes** — Fix if the change is mechanical (extract function, rename, remove dead code). Skip if it requires design decisions.
3. **Category C fixes** — Fix only if trivial (add constants, fix imports). Skip anything cosmetic that touches many files.

For each fix:
- Make the change
- Run the relevant lint/test command for the language
- If tests fail, revert the change and move the item to the "Deferred" list

```
FIX checkpoint: [N] items fixed, [M] deferred. Files modified: [list]
```

## Phase 3 — VERIFY (Confirm No Regressions)

**Agent perspective**: Verifier (`subagent_type: verifier`)

1. Run the full test suite for affected languages
2. Run lint checks (clippy, ruff, shellcheck as appropriate)
3. Confirm all previously passing tests still pass
4. If anything regressed, report it and revert the offending fix

## Output Format

```
## Tech Debt Report: [Target]

**Scanned**: [N files, M lines]
**Found**: [X issues] — A: [n], B: [n], C: [n]
**Fixed**: [Y issues]
**Deferred**: [Z issues]

### Fixed
1. `path/file.ext:42` — [Category A] Added error handling for unchecked Result
2. `path/file.ext:87` — [Category B] Extracted duplicated validation into `validate_input()`
...

### Deferred (Requires Design Decision)
1. `path/file.ext:150` — [Category B] Function `process_all` is 120 lines; needs decomposition plan
2. `path/file.ext:33` — [Category A] TODO: "rewrite when upstream API stabilizes"
...

### Verification
- Tests: [X pass, Y fail, Z skip]
- Lint: PASS/FAIL
- Regressions: [None / List]

### Recommended Next Steps
- [ ] [Highest priority deferred item — why it matters]
- [ ] [Second priority — estimated effort]
```

## When to Use

- Regular codebase hygiene — run periodically on active projects
- Before a release to clean up accumulated debt
- After a large feature merge to catch rushed code
- When onboarding to an unfamiliar codebase to understand its weak spots
- Any time the user invokes `/techdebt` with an optional target

## When NOT to Use

- During active feature development (use `/tdd` instead)
- For security-specific audits (use SecOps agent directly)
- For design/architecture review (use Architect agent or `/team`)
