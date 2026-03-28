---
name: status
description: Quick project health check — git state, test results, lint status, build status. One-shot overview.
argument-hint: "[optional: specific check — 'tests', 'lint', 'git', or blank for all]"
user_invocable: true
tools: Read, Glob, Grep, Bash
model: sonnet
---

# /status — Project Health Check

Run a quick health check on the current project. Reports git state, test results, lint status, and build status in one shot.

## Target

$ARGUMENTS

If `$ARGUMENTS` is empty, run all checks. If a specific check is named, run only that one.

## Checks

### 1. Git State
```bash
git status --short
git log --oneline -5
git branch --show-current
git stash list
```
Report: branch, uncommitted changes count, recent commits, any stashes.

### 2. Test Suite
Auto-detect and run the appropriate test command:
- `Cargo.toml` → `cargo test 2>&1`
- `pyproject.toml` / `pytest.ini` → `pytest -v 2>&1`
- `package.json` (test script) → `npm test 2>&1`
- `go.mod` → `go test ./... 2>&1`
- `*.bats` → `bats test/ 2>&1`

Report: pass/fail/skip counts, any failures summarized in one line each.

### 3. Lint
- Rust: `cargo clippy -- -D warnings 2>&1`
- Python: `ruff check . 2>&1`
- Shell: `shellcheck scripts/*.sh hooks/*.sh 2>&1` (if applicable)

Report: clean or number of warnings/errors.

### 4. Build
- Rust: `cargo build 2>&1`
- Python: syntax check via `python -m py_compile` on changed files
- Node: `npm run build 2>&1` (if build script exists)

Report: success or failure with error summary.

## Output

```
## Project Status: [project name]

| Check  | Status | Details |
|--------|--------|---------|
| Git    | OK/WARN | [branch], [N uncommitted], [N stashes] |
| Tests  | PASS/FAIL | [X pass, Y fail, Z skip] |
| Lint   | CLEAN/WARN | [N issues] |
| Build  | OK/FAIL | [summary] |

### Issues (if any)
1. [issue summary]
```

Keep it concise — this is a dashboard, not a deep dive. Under 30 lines of output.
