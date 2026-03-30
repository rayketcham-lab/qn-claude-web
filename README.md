# QN Code Assistant

**Self-hosted web UI for Claude Code CLI — access AI-powered development from any browser**

Python + Flask + xterm.js. No build step. Vendored dependencies. One command to run.

[![Watch Demo](https://img.shields.io/badge/%E2%96%B6_Watch_Demo-in_browser-d40000?style=for-the-badge&logo=asciinema)](https://rayketcham-lab.github.io/qn-claude-web/demo.html)

---

### Project Health

[![CI](https://github.com/rayketcham-lab/qn-claude-web/actions/workflows/ci.yml/badge.svg)](https://github.com/rayketcham-lab/qn-claude-web/actions/workflows/ci.yml)
[![Security Scans](https://github.com/rayketcham-lab/qn-claude-web/actions/workflows/security.yml/badge.svg)](https://github.com/rayketcham-lab/qn-claude-web/actions/workflows/security.yml)
[![Version](https://img.shields.io/badge/version-1.6.1-blue?logo=semver&logoColor=white)](https://github.com/rayketcham-lab/qn-claude-web/releases)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Vendored Deps](https://img.shields.io/badge/dependencies-vendored-brightgreen?logo=python&logoColor=white)](vendor/)
[![No Build Step](https://img.shields.io/badge/build%20step-none-brightgreen)](https://github.com/rayketcham-lab/qn-claude-web)

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Remote Servers](#remote-servers)
- [Architecture](#architecture)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Disclaimer](#disclaimer)
- [License](#license)

---

## Overview

QN Code Assistant is a self-hosted web interface that wraps the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code), giving you browser-based access from any device on your network — laptops, phones, tablets.

**Why this exists:** Claude Code is a powerful CLI tool, but it chains you to a local terminal. QN Code Assistant breaks that constraint. Run it on a server and work from any browser, on any device, from anywhere on your network.

Key capabilities:

- **Browser-based Claude Code access** — full PTY-backed terminal emulation via xterm.js, with tmux session persistence that survives disconnects and browser refreshes
- **AI agent team deployment** — launch and orchestrate 20+ specialized Claude Code agents (Architect, Builder, Tester, SecOps, DevOps) directly from the UI
- **Autonomous mode** — unattended Claude Code sessions with configurable auto-restart and task management
- **Remote server management** — guided 5-step SSH wizard for adding remote hosts, with autonomous key generation and exchange
- **Multi-user auth with RBAC** — password-protected access, multiple user accounts, role-based permissions
- **Pure Python, zero Node.js** — 14 Python packages vendored in `vendor/`, no pip install at runtime, no npm, no build step

---

## Quick Start

```bash
# 1. Download
curl -O https://your-server/qn-code-assistant-v1.6.1.sh

# 2. Install
bash qn-code-assistant-v1.6.1.sh

# 3. Access
# Open http://your-server:5001 in your browser
```

Or clone and run directly:

```bash
git clone https://github.com/rayketcham-lab/qn-claude-web.git
cd qn-claude-web
python3 app.py
```

Open `http://localhost:5001`. For LAN access: `http://<server-ip>:5001`

---

## Features

### Terminal

| Feature | Description |
|---------|-------------|
| **PTY Terminal** | Full xterm.js terminal with PTY support and multiple tabs |
| **tmux Persistence** | Sessions survive browser disconnects and page refreshes |
| **Autonomous Mode** | Unattended Claude Code sessions with auto-restart |
| **Agent Teams** | Launch Architect, Builder, Tester, SecOps, DevOps agents |
| **Git Integration** | Branch and status display in the terminal toolbar |

### Chat Interface

| Feature | Description |
|---------|-------------|
| **Persistent Sessions** | Conversations saved to disk, searchable by content |
| **Streaming** | Responses stream in real time with markdown rendering |
| **Export** | Save any chat session as a markdown file |
| **Session Search** | Full-text search across all saved conversations |

### Project & File Management

| Feature | Description |
|---------|-------------|
| **Project Browser** | Directory navigation with auto-detection of project types |
| **File Browser** | Syntax-highlighted file viewing with breadcrumb navigation |
| **CLAUDE.md Wizard** | One-click deploy of project instructions and agent configs |

### Infrastructure

| Feature | Description |
|---------|-------------|
| **Remote Servers** | SSH and mount-based remote host support with guided setup wizard |
| **Multi-user Auth** | Password-protected access with RBAC — admin and user roles |
| **HTTPS** | Auto-generated self-signed certs or custom certificate paths |
| **PWA** | Installable as a standalone app on mobile devices |
| **Themes** | Dark, Midnight Blue, Solarized Dark, Light |
| **Usage Tracking** | Token usage monitoring with weekly reset counters |

---

## Requirements

- **Python 3.10+** — `python3 --version`
- **tmux** — `tmux -V` (for session persistence)
- **Claude Code CLI** — installed and available in `PATH`

The Python dependencies are vendored — no additional pip installs required.

---

## Installation

### Self-Extracting Installer (Recommended)

```bash
curl -O https://your-server/qn-code-assistant-v1.6.1.sh
bash qn-code-assistant-v1.6.1.sh
```

The installer verifies SHA-256 hashes for all files, extracts to `/opt/claude-web`, and runs interactive setup.

### Manual Setup

```bash
git clone https://github.com/rayketcham-lab/qn-claude-web.git /opt/claude-web
python3 /opt/claude-web/app.py
```

### Systemd Service

```bash
sudo cp /opt/claude-web/qn-code-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable qn-code-assistant
sudo systemctl start qn-code-assistant
```

Check logs:

```bash
sudo journalctl -u qn-code-assistant -f
```

---

## Configuration

Settings are managed through the web UI (Settings icon in the sidebar) and persisted in `config.json`.

### Key Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `port` | `5001` | Server listening port |
| `projects_root` | `/opt` | Root directory for project browsing |
| `allowed_paths` | `["/opt"]` | Directories allowed for file access |
| `max_concurrent_terminals` | `5` | Maximum simultaneous terminal sessions |
| `max_concurrent_chats` | `10` | Maximum simultaneous chat processes |
| `process_timeout_minutes` | `60` | Watchdog timeout for stale processes |
| `auth.enabled` | `false` | Enable password authentication |
| `ssl_enabled` | `false` | Enable HTTPS |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `QN_SECRET_KEY` | Flask session secret key — **set this in production** |
| `QN_PORT` | Override server port (also settable in `config.json`) |
| `QN_CONFIG_PATH` | Path to `config.json` (default: `config.json` in app directory) |

**Production note:** Always set `QN_SECRET_KEY` to a long random value. Do not rely on the auto-generated key across restarts if you need session continuity.

```bash
export QN_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python3 /opt/claude-web/app.py
```

---

## Remote Servers

Add remote hosts via **Settings > Remote Hosts > Add Remote Host**. The 5-step wizard handles:

1. **Method** — Choose SSH or mount-based connection
2. **Connect** — Enter host details or import from `~/.ssh/config`
3. **SSH Key Setup** — Auto-generates an ed25519 key and pushes it via sshpass
4. **Verify** — Tests the SSH connection and detects Claude CLI on the remote host
5. **Save** — One-click save with auto-suggested display name

Two connection modes are supported:

- **SSH mode** — runs Claude Code on the remote host over SSH
- **Mount mode** — runs local Claude Code on a remotely mounted filesystem

---

## Architecture

```
+----------------------------------------------------------+
|                 Browser (Any Device)                     |
|     xterm.js Terminal  |  Chat UI  |  File Browser       |
+----------------------------------------------------------+
|                  WebSocket (SocketIO)                    |
+----------------------------------------------------------+
|                   Flask + SocketIO                       |
|               async_mode='threading'                     |
+---------------+----------+-------------+----------------+
| PTY / tmux    | Claude   | SSH Manager | File API       |
| Terminal Mgr  | Code CLI | Remote Hosts| Project Detect |
+---------------+----------+-------------+----------------+
|              Vendored Python Packages                    |
|     Flask, SocketIO, Werkzeug, MarkupSafe, ...          |
+----------------------------------------------------------+
```

### Stack

- **Backend:** Flask + Flask-SocketIO (`async_mode='threading'`), single-file `app.py`
- **Frontend:** Vanilla JS (`ClaudeCodeWeb` class in `static/js/app.js`), no framework, no build step
- **Terminal:** xterm.js with PTY backend (`pty.fork()` + `select`), tmux for session persistence
- **Dependencies:** 14 Python packages vendored in `vendor/` — no runtime pip installs

### Directory Structure

```
qn-claude-web/
├── app.py                     # Flask backend + WebSocket handlers
├── templates/
│   ├── index.html             # Single-page app
│   └── login.html             # Auth page
├── static/
│   ├── css/style.css          # Themed styling
│   ├── js/app.js              # Client-side application
│   ├── sw.js                  # Service worker (PWA)
│   └── manifest.json          # PWA manifest
├── .claude/                   # Claude Code project configuration
│   ├── agents/                # Agent definitions
│   ├── rules/                 # Language and project standards
│   └── settings.json          # Permission and environment config
├── vendor/                    # Vendored Python dependencies
├── tests/                     # Unit and integration tests
├── sessions/                  # Saved chat sessions (gitignored)
├── config.json                # Runtime configuration (gitignored)
├── build-installer.sh         # Installer generator with SHA-256 hashes
├── build-release.sh           # Self-extracting installer builder
└── qn-code-assistant.service  # systemd unit file
```

---

## Security

| Control | Implementation |
|---------|---------------|
| **Authentication** | bcrypt-hashed passwords, multi-user, RBAC |
| **Rate Limiting** | 10 login attempts per 5 minutes per IP |
| **Security Headers** | CSP, X-Frame-Options, X-Content-Type-Options, HSTS, Referrer-Policy |
| **Cookie Security** | HttpOnly, SameSite=Lax, Secure flag with SSL |
| **XSS Prevention** | HTML sanitization, escaped output, Content Security Policy |
| **Path Traversal** | Null byte rejection, symlink resolution, allowed-path enforcement |
| **App Directory** | Excluded from file browser — config, source, and session files cannot be accessed via the API |
| **SSH Sanitization** | Hostname/username character filtering, port range validation |
| **CSRF Protection** | SameSite cookies + origin checking on WebSocket connections |
| **Message Limits** | Chat messages capped at 1MB |
| **Thread Safety** | Lock-protected session storage and terminal registry |
| **Version Hiding** | Server header reports `QN Code Assistant` — no framework or Python version exposed |
| **systemd Hardening** | `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem`, capability restrictions |
| **Disconnect Handling** | 30-second grace period with browser correlation, orphan PTY cleanup |

To report a security vulnerability, open a GitHub issue marked **[SECURITY]** or contact the maintainer directly.

---

## Troubleshooting

**Port already in use:**
```bash
lsof -ti:5001 | xargs kill -9
```

**Claude command not found:**
```bash
which claude
# Add to PATH if missing:
export PATH="$PATH:/path/to/claude"
```

**Service won't start:**
```bash
sudo journalctl -u qn-code-assistant -n 50
```

**tmux sessions not persisting:**
```bash
tmux -V   # confirm tmux is installed
which tmux
```

**SSL certificate errors in browser:**

Self-signed certificates require a browser trust exception. For production use, configure a real certificate via `ssl_cert_path` and `ssl_key_path` in `config.json`.

---

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Anthropic, PBC. "Claude" and "Claude Code" are trademarks of Anthropic, PBC. This is an independent, community-developed web interface that works with the Claude Code CLI. Use requires a valid Claude subscription and the Claude Code CLI installed locally.

---

## License

Apache-2.0 — see [LICENSE](LICENSE).
