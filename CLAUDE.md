# Project Intelligence

## Context Window Management — MANDATORY

### Sentinel Protocol
There is no background watchdog. YOU are the only process. Full protocol: `.claude/agents/sentinel.md`

**Checkpoints** (silent self-assess, output only if action needed):
- Before/after every task, on agent role switch, after large outputs, every 5 exchanges

**Heuristics**: <10 tool calls = green, 10-25 = yellow, 25-40 = orange compact soon, 40+ = red compact NOW

**If user asks about Sentinel**: Execute the status check. Do NOT explain how it works. Output the status block, take action.

**Compaction**: Write session state checkpoint to MEMORY.md (auto memory), drop processed outputs, keep decisions and file paths. Continue working unless RED and already compacted once.

**Session Continuity**: On compact or before exiting, ALWAYS update your auto memory MEMORY.md with:
- What you were working on (task, file paths, line numbers)
- What's done and what remains
- Key decisions made this session
- Next steps for the resuming session

On session start, ALWAYS check MEMORY.md for previous session state and resume from where it left off.


## Autonomous Work Mode

When given a task, work autonomously. Do not narrate plans or ask for permission to continue — just do the work.

### Decision Points — Use AskUserQuestion
When you encounter a decision point, design choice, trade-off, or ambiguity, present it as a **structured choice** using the AskUserQuestion tool:

- Provide 2-4 concrete options with clear descriptions of trade-offs
- Mark your recommended option with "(Recommended)" in the label
- Frame what each choice means for the project (performance, complexity, maintenance, etc.)
- After the user picks, immediately execute — don't re-explain

**Good question examples:**
- "Which state management approach?" with complexity/perf trade-offs
- "Found two ways to fix this bug" with risk/scope trade-offs
- "This feature could be simple or full-featured" with effort/capability trade-offs

**Bad patterns (avoid):**
- "Should I proceed?" — just proceed
- "Would you like me to continue?" — just continue
- "Is this okay?" — if you're not sure, present specific options for what to change
- Open-ended "What do you think?" — frame it as concrete choices instead

### Task Status Markers
When working in autonomous mode, maintain a `## Task Status:` line in MEMORY.md:
- `IN_PROGRESS` — actively working, will resume on restart
- `TASK_COMPLETE` — all done, builds, tests pass, deliverable ready
- `BLOCKED` — cannot continue without human help (explain why below the marker)

### Context Store Integration
Use the MCP context-store to persist important discoveries, decisions, and architectural knowledge:
- `mcp__context-store__store_context` — save project knowledge that should survive across sessions
- `mcp__context-store__search_context` — look up previously stored knowledge before re-exploring
- `mcp__context-store__record_decision` — record architectural decisions with rationale
- `mcp__context-store__project_summary` — get full project context on session start

Always check the context-store before deep-diving into code you may have already explored in a previous session.

---

## Team Agent Architecture

This project uses a five-agent team model. Each agent has a distinct role, perspective, and set of responsibilities. When working on tasks, consider which agent perspectives are relevant and invoke them appropriately.

### Agent Roster

| Agent | Invoke With | Primary Responsibility |
|-------|-------------|----------------------|
| Architect | `@architect` or `/agents/architect.md` | System design, API contracts, dependency decisions, architecture reviews |
| Builder | `@builder` or `/agents/builder.md` | Feature implementation, refactoring, code generation |
| Tester | `@tester` or `/agents/tester.md` | Test creation, coverage analysis, edge case identification, fuzzing |
| SecOps | `@secops` or `/agents/secops.md` | Security review, vulnerability analysis, compliance, crypto validation |
| DevOps | `@devops` or `/agents/devops.md` | CI/CD, build systems, deployment, infrastructure, containerization |

> **Sentinel Protocol**: Every agent has a mandatory pre/post hook to self-assess context load. See `.claude/agents/sentinel.md`. This is not a separate agent — it is a discipline embedded in all agents.

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

### Kali Linux VM (Security & CI Testing)
- **Connect**: `ssh kali "command"`
- **IP**: 192.168.1.145 (bridged on br0, same LAN as ubuntu3)
- **User**: kali
- **Tools**: nmap, nikto, sqlmap, hydra, zaproxy, full Kali toolset
- **Example**: `ssh kali "nmap -sV 192.168.1.241"` (scan this app's host)
- Any agent spawned from this host inherits the SSH config and key — `ssh kali "whatever"` just works
- Used by: SecOps (offensive testing), DevOps (CI security scans via `security.yml` workflow)
- Scan orchestrator: `tests/security/kali_scan.sh` (runs nmap/nikto/ZAP/sqlmap at 3 severity levels)

---

## Agent Domain Notes

### SecOps — Project-Specific Focus Areas
- **Command injection via PTY**: The app spawns PTY processes — audit all paths that construct shell commands, especially SSH command assembly and remote host connections.
- **SSH credential handling**: SSH key generation, exchange (via sshpass), and storage. Verify no private keys leak through logs, error messages, or API responses.
- **`validate_file_path()` bypass**: This is the primary file access control — test for path traversal, symlink following, null bytes, and encoding tricks. The app directory exclusion is security-critical.
- **Session data**: Chat sessions are persisted — verify session files don't contain sensitive data that could be exfiltrated.
- **WebSocket security**: SocketIO connections handle terminal I/O — verify origin checking and message size limits.

### DevOps — Project-Specific Focus Areas
- **CI/CD pipeline**: GitHub Actions — `ci.yml` (unit tests + build on push/PR), `security.yml` (offensive scans, manual + weekly cron). Self-hosted runner on ubuntu3 at `/opt/actions-runner-qnca/`.
- **Vendor hash integrity**: Hash computation uses relative paths (`cd` to project dir, `find vendor/`). Absolute paths break cross-directory installs. Verify after any vendor changes.
- **Systemd service**: `qn-code-assistant.service` — ensure proper restart policies, user isolation, and environment variable handling.
- **Release artifacts**: Self-extracting `.sh` installers (base64 ZIP). Verify extraction, hash validation, and interactive setup work correctly.

### Builder — Project-Specific Conventions
- **Vendored deps**: Never add packages via pip. Vendor manually and preserve `.dist-info`.
- **Threading model**: `async_mode='threading'` — no eventlet. Use `chat_sessions_lock` for shared state. No async/await patterns.
- **Event delegation**: All dynamic DOM lists use delegated event listeners on parent containers. Never attach listeners directly to dynamic elements.
- **Config pattern**: Use `load_config()` / `save_config()` for all persistent settings. Merge with defaults.
- **Single-file backend**: All backend logic lives in `app.py`. Keep it organized by section (routes, WebSocket handlers, config, auth, SSL, usage).
