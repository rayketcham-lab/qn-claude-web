# Project Intelligence

## Context Window Management — MANDATORY

### Sentinel Agent (Compaction Watchdog)
Context window management is owned by the **Sentinel** agent (`.claude/agents/sentinel.md`). Sentinel is NOT a working agent — it is a background watchdog that monitors context utilization and forces compaction when thresholds are hit.

**Sentinel has override authority over all other agents.** When Sentinel calls for compaction, all work stops immediately.

| Utilization | Sentinel Action |
|-------------|----------------|
| < 50% | Silent — no action |
| 50-60% | Advisory — notifies active agent compaction is approaching |
| 60-75% | **Mandatory compact** — interrupts work, executes compaction, verifies continuity |
| > 75% | **Emergency compact** — hard stop, aggressive compaction, essentials only |

**Sentinel monitors at these boundaries:**
- After every tool call with substantial output
- After every agent transition
- Every 3-5 conversational exchanges
- Before any large task begins (preemptive assessment)

**Rules (non-negotiable):**
- NO agent may defer, delay, or skip a Sentinel compaction call
- Sentinel's checkpoint is the source of truth for session continuity
- Running out of context mid-task is catastrophic — premature compaction is always preferable
- After compaction, the interrupted agent must restate their next step to prove continuity
- See `.claude/agents/sentinel.md` for full compaction procedure and checkpoint format

---

## Team Agent Architecture

This project uses a five-agent team model. Each agent has a distinct role, perspective, and set of responsibilities. When working on tasks, consider which agent perspectives are relevant and invoke them appropriately.

### Agent Roster

| Agent | Invoke With | Primary Responsibility |
|-------|-------------|----------------------|
| **Sentinel** | Always active (background) | Context window watchdog — monitors utilization, forces compaction, preserves continuity |
| Architect | `@architect` or `/agents/architect.md` | System design, API contracts, dependency decisions, architecture reviews |
| Builder | `@builder` or `/agents/builder.md` | Feature implementation, refactoring, code generation |
| Tester | `@tester` or `/agents/tester.md` | Test creation, coverage analysis, edge case identification, fuzzing |
| SecOps | `@secops` or `/agents/secops.md` | Security review, vulnerability analysis, compliance, crypto validation |
| DevOps | `@devops` or `/agents/devops.md` | CI/CD, build systems, deployment, infrastructure, containerization |

> **Sentinel runs passively at all times.** It is not invoked — it self-activates at threshold. The five working agents below are task-driven.

### When to Engage Multiple Agents

- **New feature**: Architect → Builder → Tester → SecOps (review)
- **Bug fix**: Builder → Tester (regression test) → SecOps (if security-adjacent)
- **Refactor**: Architect (approve approach) → Builder → Tester (verify no regressions)
- **Release prep**: DevOps → Tester (full suite) → SecOps (final audit)
- **Dependency update**: Architect (compatibility) → SecOps (advisory check) → Tester → DevOps (build verify)
- **Security incident**: SecOps (lead) → Builder (patch) → Tester (verify) → DevOps (deploy)

### Conventions

- All agents operate under the same project context and share this CLAUDE.md
- Agents should cross-reference each other's findings when relevant
- SecOps has **veto authority** on merge-blocking security issues
- Architect has **veto authority** on design/API contract changes
- Builder defers to Tester on test adequacy questions
- DevOps owns the final say on build/deploy configuration

## Project Standards

### Code Quality
- No warnings in CI. Treat warnings as errors.
- Every public API must have documentation.
- Functions over 50 lines should be reviewed for decomposition.
- Error handling is mandatory — no silent failures, no unwrap-without-context.

### Commit Discipline
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `security:`
- One logical change per commit.
- Reference issue/ticket numbers where applicable.

### Security Baseline
- No secrets in code or config. Use environment variables or secret managers.
- All cryptographic operations must use well-vetted libraries — no hand-rolled crypto.
- Dependencies must be audited before adoption (SecOps).
- Input validation at all trust boundaries.

### Testing Requirements
- New features require tests before merge.
- Bug fixes require a regression test proving the fix.
- Critical paths require both unit and integration tests.
- Security-sensitive code requires negative/adversarial test cases.

## Language-Specific Notes

### Python (Backend — Flask + SocketIO)
- Python 3.10+ (system Python: `/usr/bin/python3`). Type hints on public interfaces.
- No formal linter/type-checker in pipeline — code review is the quality gate.
- Uses `os.path` patterns throughout (established convention — do not migrate to `pathlib`).
- Dependencies are **vendored** in `vendor/` — no pip install at runtime. See Project Context below.
- `async_mode='threading'` — no eventlet/gevent. Thread safety via `chat_sessions_lock`.

### Web (Frontend — Vanilla JS + xterm.js)
- No build step, no bundler, no framework. Vanilla JS with `ClaudeCodeWeb` class in `static/js/app.js`.
- Dark theme CSS in `static/css/style.css`. Single-page app in `templates/index.html`.
- Event delegation on parent containers for all dynamic lists (prevents listener leaks).
- Terminal emulation via xterm.js with PTY backend.
- Accessibility: maintain keyboard navigability and screen reader compatibility.
- CSP headers should be evaluated for deployment.

---

## Project Context — QN Code Assistant

### Architecture Overview
- **What**: Web frontend for Claude Code CLI (v1.3.2)
- **Backend**: Flask + Flask-SocketIO (`async_mode='threading'`), single-file `app.py`
- **Frontend**: Vanilla JS (`static/js/app.js`), xterm.js terminal emulation
- **Terminal**: PTY via `pty.fork()` + `select` for I/O, with SSH wrapping for remote hosts

### Vendored Dependencies
The `vendor/` directory contains 14 vendored Python packages (329 files). This is auto-detected via `sys.path.insert()` in `app.py`.
- **CRITICAL**: `.dist-info` directories MUST be preserved — werkzeug uses `importlib.metadata` and breaks without them.
- Never `pip install` into vendor — manually manage vendored packages.
- `__pycache__/` is excluded from integrity hashes.

### Build & Release Pipeline
1. `build-installer.sh` — generates `install.sh` with baked SHA-256 hashes (uses **relative paths** from project dir, excludes `__pycache__/`)
2. `build-release.sh` — generates self-extracting `.sh` installer (base64-encoded ZIP, no tar)
3. Copy to website: `sudo cp qn-code-assistant-v<VERSION>.sh /var/www/html/`
4. **After ANY file changes**: run `bash build-installer.sh` then optionally `bash build-release.sh`

### Server Management
- Runs on port 5001, IP: 192.168.1.241
- Start: `/usr/bin/python3 /opt/claude-web/app.py`
- Kill: `lsof -ti:5001 | xargs kill -9`
- Service: `qn-code-assistant.service` (systemd)

### Security Architecture
- App directory excluded from `validate_file_path()` — prevents config/source/session file leaks
- Server header: `QN Code Assistant` (no Werkzeug/Python version exposure)
- Rate limiting on login: 10 attempts per 5 minutes per IP
- All `request.json` calls guarded with `or {}`
- Chat messages limited to 1MB
- Config values type-validated on load
- Disconnect handler kills orphaned PTY processes (tracks by `ws_sid`)
- SSH key paths validated with fallback warning

### Configuration
- `config.json` — persistent configuration (favorites, remote hosts, auth, SSL settings)
- `load_config()` merges defaults with `config.json`; `save_config()` persists changes
- Thread-safe session management: `chat_sessions_lock` protects session dict; `save_session()` snapshots under lock

### Remote Server Wizard
- 5-step modal wizard: Method → Connect → SSH Key Setup → Verify → Save
- Autonomous SSH key generation and exchange via sshpass
- Imports from `~/.ssh/config`

---

## Agent Domain Notes

### SecOps — Project-Specific Focus Areas
- **Command injection via PTY**: The app spawns PTY processes — audit all paths that construct shell commands, especially SSH command assembly and remote host connections.
- **SSH credential handling**: SSH key generation, exchange (via sshpass), and storage. Verify no private keys leak through logs, error messages, or API responses.
- **`validate_file_path()` bypass**: This is the primary file access control — test for path traversal, symlink following, null bytes, and encoding tricks. The app directory exclusion is security-critical.
- **Session data**: Chat sessions are persisted — verify session files don't contain sensitive data that could be exfiltrated.
- **WebSocket security**: SocketIO connections handle terminal I/O — verify origin checking and message size limits.

### DevOps — Project-Specific Focus Areas
- **No CI/CD pipeline**: Build/release is manual shell scripts, not automated CI. Focus on installer integrity (SHA-256 hashes match), self-extracting archive correctness, and systemd service reliability.
- **Vendor hash integrity**: Hash computation uses relative paths (`cd` to project dir, `find vendor/`). Absolute paths break cross-directory installs. Verify after any vendor changes.
- **Systemd service**: `qn-code-assistant.service` — ensure proper restart policies, user isolation, and environment variable handling.
- **Release artifacts**: Self-extracting `.sh` installers (base64 ZIP). Verify extraction, hash validation, and interactive setup work correctly.

### Builder — Project-Specific Conventions
- **Vendored deps**: Never add packages via pip. Vendor manually and preserve `.dist-info`.
- **Threading model**: `async_mode='threading'` — no eventlet. Use `chat_sessions_lock` for shared state. No async/await patterns.
- **Event delegation**: All dynamic DOM lists use delegated event listeners on parent containers. Never attach listeners directly to dynamic elements.
- **Config pattern**: Use `load_config()` / `save_config()` for all persistent settings. Merge with defaults.
- **Single-file backend**: All backend logic lives in `app.py`. Keep it organized by section (routes, WebSocket handlers, config, auth, SSL, usage).
