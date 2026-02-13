# /preflight — Pre-commit / Pre-push Validation

Run all checks that should pass before committing or pushing code.

## Usage
Invoke with: `/preflight` or `/preflight [scope]` where scope is `commit`, `push`, or `full`

## Process

### Scope: commit (default)
1. **Python Syntax**: `python3 -m py_compile app.py`
2. **JS Syntax**: `node --check static/js/app.js`
3. **Ruff Lint**: Run ruff on all `.py` files in project root and tests/
4. **ShellCheck**: Run shellcheck on all `.sh` files
5. **Unit Tests**: Run `tests/test_security.py` (114 tests)
6. **Secret Scan**: Grep for common secret patterns in staged files

### Scope: push (adds to commit checks)
7. **Integration Tests**: Run `tests/test_integration.py` (requires running server)
8. **Installer Verify**: Run `install.sh --verify-only`
9. **Build Check**: Run `build-installer.sh` and verify no hash drift

### Scope: full (adds to push checks)
10. **Pentest Suite**: Run `tests/security/pentest.py` (requires running server)
11. **Git Status**: Verify no untracked files that should be committed
12. **Version Consistency**: Check version strings match across files

## Output
```
# Preflight: [scope]

| Check | Result | Time |
|-------|--------|------|
| Python syntax | PASS/FAIL | [time] |
| JS syntax | PASS/FAIL | [time] |
| Ruff | PASS/FAIL ([count] issues) | [time] |
| ShellCheck | PASS/FAIL ([count] issues) | [time] |
| Unit tests | PASS/FAIL ([count]) | [time] |
| ... | ... | ... |

**Result**: ALL CLEAR / [count] FAILURES
```
