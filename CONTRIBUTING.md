# Contributing to QN Code Assistant

Thank you for your interest in contributing. This document covers how to set up a development environment, run tests, and submit changes.

---

## Table of Contents

- [Dev Setup](#dev-setup)
- [Running Tests](#running-tests)
- [Code Standards](#code-standards)
- [Commit Conventions](#commit-conventions)
- [PR Process](#pr-process)
- [Architecture Notes](#architecture-notes)

---

## Dev Setup

### Prerequisites

- Python 3.10+
- tmux
- Claude Code CLI installed and in PATH

### Clone and Run

```bash
git clone https://github.com/rayketcham-lab/qn-claude-web.git
cd qn-claude-web
python3 app.py
```

Dependencies are vendored in `vendor/` — no `pip install` step required.

Open `http://localhost:5001` in your browser.

### First-Time Configuration

On first run the app generates a `config.json` with defaults. To enable authentication, open Settings in the web UI and configure a password, or set the relevant fields in `config.json` directly.

For the secret key, set the environment variable before starting:

```bash
export QN_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python3 app.py
```

---

## Running Tests

Run the full test suite with:

```bash
/usr/bin/python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Or with any Python 3.10+ interpreter on your PATH:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

### Test Structure

```
tests/
├── test_app.py            # Core app routes and WebSocket handlers
├── test_auth.py           # Authentication and RBAC
├── test_config.py         # Configuration load/save/validation
├── test_file_api.py       # File browser and path validation
├── test_remote.py         # Remote server management
├── test_sessions.py       # Chat session CRUD
└── security/
    └── kali_scan.sh       # Offensive security scans (requires Kali host)
```

### Writing Tests

- New features require tests before merge.
- Bug fixes require a regression test that reproduces the bug and verifies the fix.
- Security-sensitive code requires adversarial test cases (invalid inputs, path traversal attempts, oversized payloads, etc.).
- Tests must pass cleanly with zero errors on the target Python version.

---

## Code Standards

The full standards are documented in [CLAUDE.md](CLAUDE.md) and the `.claude/rules/` directory. Key points:

### Python (Backend)

- Python 3.10+ required. Type hints on all public functions and methods.
- All backend logic lives in `app.py` — keep it organized by section (routes, WebSocket handlers, config, auth, SSL, usage).
- Threading model: `async_mode='threading'`. No eventlet/gevent. No `async`/`await`. Use `chat_sessions_lock` for shared state.
- Use `load_config()` / `save_config()` for all persistent settings.
- Error handling is mandatory — no silent failures, no bare `except` clauses.
- Functions over 50 lines should be reviewed for decomposition.

### Vendored Dependencies

- **Never** add packages via `pip install`. Vendor manually by copying the package into `vendor/` and preserving all `.dist-info` directories.
- Run `bash build-installer.sh` after any file changes to update SHA-256 hashes.

### JavaScript (Frontend)

- No framework, no bundler. Vanilla JS using the `ClaudeCodeWeb` class in `static/js/app.js`.
- Use event delegation on parent containers for all dynamic lists — never attach listeners directly to dynamic elements.
- No inline scripts or styles (CSP policy).

### General

- No hardcoded secrets or credentials in source code.
- Input validation at all trust boundaries.
- No TODO/FIXME added without a linked issue.
- No debug or temporary code left in committed changes.

---

## Commit Conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/).

### Prefixes

| Prefix | Use for |
|--------|---------|
| `feat:` | New features |
| `fix:` | Bug fixes |
| `refactor:` | Code restructuring without behavior change |
| `test:` | Adding or updating tests |
| `docs:` | Documentation changes |
| `ci:` | CI/CD pipeline changes |
| `security:` | Security fixes or hardening |

### Format

```
<prefix>: short summary in imperative mood (max 72 chars)

Optional body explaining why, not what. Reference issues with #123.
```

### Examples

```
feat: add SSH key rotation support for remote hosts

fix: prevent path traversal via null bytes in file API

security: scope terminal output to owning WebSocket session

test: add regression test for config lock race condition
```

One logical change per commit. If you find yourself writing "and" in the summary, split it.

---

## PR Process

1. **Fork** the repository and create a branch from `main`.
   - Branch naming: `feat/short-description`, `fix/issue-123`, `security/cve-description`

2. **Implement** your change following the code standards above.

3. **Test** — run the full test suite and confirm it passes cleanly:
   ```bash
   /usr/bin/python3 -m unittest discover -s tests -p 'test_*.py' -v
   ```

4. **Update hashes** if any files changed:
   ```bash
   bash build-installer.sh
   ```

5. **Open a PR** against `main`. Use the PR template — it includes a checklist covering tests, security, and documentation.

6. **Review** — at least one maintainer review is required. Security-adjacent changes require SecOps review before merge.

7. **Merge** — squash merges are preferred for small changes. Feature branches with meaningful commit history may be merged as-is.

### What Gets Reviewed

- Correctness and test coverage
- Security implications (path handling, auth, input validation, dependency changes)
- Code style consistency with the existing codebase
- No new warnings or linting errors
- Documentation updated if public-facing behavior changed

---

## Architecture Notes

If you are new to the codebase, these are the most important things to know:

- **Single-file backend.** All server logic lives in `app.py`. It is organized into logical sections — look for section header comments.
- **PTY + tmux.** Terminal sessions use `pty.fork()` for PTY allocation and wrap everything in tmux for persistence. The reconnect flow has a TOCTOU guard — be careful when touching terminal session code.
- **Vendored deps.** The `vendor/` directory is part of the release artifact and its SHA-256 hashes are baked into the installer. Changes to vendored packages require rebuilding the installer.
- **Thread safety.** The app uses threading mode. Any mutation of `chat_sessions` must be done under `chat_sessions_lock`. Config reads/writes use `config_lock`.
- **Security boundary.** `validate_file_path()` is the primary file access control. Changes to it, or to the app directory exclusion logic, are security-critical and require review.

For deeper context, read [CLAUDE.md](CLAUDE.md).
