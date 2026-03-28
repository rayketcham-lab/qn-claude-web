# QN Claude Web

**Self-hosted web frontend for Claude Code CLI** — access Claude Code from any browser, any device, anywhere on your network.

Python + Flask + xterm.js. No build step. Vendored dependencies. One command to run.

---

### Project Health

<!-- CI / Testing Pipeline -->
[![CI](https://github.com/rayketcham-lab/qn-claude-web/actions/workflows/ci.yml/badge.svg)](https://github.com/rayketcham-lab/qn-claude-web/actions/workflows/ci.yml)
[![Security Scans](https://github.com/rayketcham-lab/qn-claude-web/actions/workflows/security.yml/badge.svg)](https://github.com/rayketcham-lab/qn-claude-web/actions/workflows/security.yml)

<!-- Security & Compliance -->
[![Rate Limiting](https://img.shields.io/badge/rate%20limiting-enabled-brightgreen?logo=hackthebox&logoColor=white)](https://github.com/rayketcham-lab/qn-claude-web)
[![CSP Headers](https://img.shields.io/badge/CSP-enforced-brightgreen?logo=mozilla&logoColor=white)](https://github.com/rayketcham-lab/qn-claude-web)
[![Path Traversal](https://img.shields.io/badge/path%20traversal-hardened-brightgreen?logo=shieldsdotio&logoColor=white)](https://github.com/rayketcham-lab/qn-claude-web)
[![XSS Prevention](https://img.shields.io/badge/XSS-protected-brightgreen?logo=owasp&logoColor=white)](https://github.com/rayketcham-lab/qn-claude-web)

<!-- Project Info -->
[![Version](https://img.shields.io/badge/version-1.5.1-blue?logo=semver&logoColor=white)](https://github.com/rayketcham-lab/qn-claude-web/releases)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-SocketIO-blue?logo=flask&logoColor=white)](https://flask-socketio.readthedocs.io/)
[![xterm.js](https://img.shields.io/badge/xterm.js-terminal-blue?logo=windowsterminal&logoColor=white)](https://xtermjs.org/)

<!-- Build & Quality -->
[![Vendored Deps](https://img.shields.io/badge/dependencies-vendored-brightgreen?logo=python&logoColor=white)](https://github.com/rayketcham-lab/qn-claude-web)
[![No Build Step](https://img.shields.io/badge/build%20step-none-brightgreen?logo=javascript&logoColor=white)](https://github.com/rayketcham-lab/qn-claude-web)
[![PWA](https://img.shields.io/badge/PWA-installable-blueviolet?logo=pwa&logoColor=white)](https://github.com/rayketcham-lab/qn-claude-web)
[![Themes](https://img.shields.io/badge/themes-4%20built--in-blue?logo=css3&logoColor=white)](https://github.com/rayketcham-lab/qn-claude-web)

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Remote Servers](#remote-servers)
- [API Reference](#api-reference)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Disclaimer](#disclaimer)
- [License](#license)

## Overview

QN Claude Web is a self-hosted web interface that wraps the Claude Code CLI, giving you browser-based access to Claude Code from any device on your network — laptops, phones, tablets. It provides:

- **Terminal emulator** — full PTY-backed xterm.js terminals with tmux session persistence
- **Chat interface** — persistent conversations with markdown rendering and streaming
- **Project browser** — directory navigation with auto-detection of project types
- **Remote server management** — SSH into remote hosts with guided key setup
- **File browser** — syntax-highlighted file viewing with breadcrumb navigation
- **Autonomous mode** — unattended Claude Code sessions with task management

All dependencies are vendored — no pip install, no npm build, no Docker required.

## Quick Start

```bash
# Clone and run
git clone https://github.com/rayketcham-lab/qn-claude-web.git
cd qn-claude-web
python3 app.py
```

Open `http://localhost:5001` in your browser. For LAN access: `http://<server-ip>:5001`

> **Prerequisite:** [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) must be installed and in PATH.

## Features

### Terminal & Chat

| Feature | Description |
|---------|-------------|
| **Terminal Emulator** | Full xterm.js terminal with PTY support, multiple tabs, tmux persistence |
| **Chat Interface** | Persistent sessions, markdown rendering, streaming responses |
| **Session Search** | Full-text search across all saved conversations |
| **Export** | Export chat sessions as markdown files |
| **Keyboard Shortcuts** | Ctrl+T new terminal, Ctrl+K focus chat, Ctrl+1/2/3 switch views |

### Project & File Management

| Feature | Description |
|---------|-------------|
| **Project Browser** | Browse directories, auto-detect project types (git, node, python, rust, claude) |
| **File Browser** | Directory tree, syntax highlighting, breadcrumb navigation |
| **Git Integration** | Branch and status display in terminal toolbar |
| **CLAUDE.md Wizard** | One-click deploy of project instructions and agent configs |

### Infrastructure

| Feature | Description |
|---------|-------------|
| **Remote Servers** | SSH and mount-based remote host support with guided setup wizard |
| **Authentication** | Password-protected access with multi-user support and role-based access |
| **HTTPS** | Auto-generated self-signed certs or custom certificate paths |
| **PWA** | Installable as standalone app on mobile devices |
| **Themes** | Dark, Midnight Blue, Solarized Dark, Light |
| **Usage Tracking** | Token usage monitoring with weekly reset counters |
| **Autonomous Mode** | Unattended Claude Code sessions with auto-restart and task management |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Browser (Any Device)                       │
│          xterm.js Terminal  │  Chat UI  │  File Browser       │
├──────────────────────────────────────────────────────────────┤
│                     WebSocket (SocketIO)                      │
├──────────────────────────────────────────────────────────────┤
│                      Flask + SocketIO                         │
│                    async_mode='threading'                      │
├────────────┬──────────────┬──────────────┬───────────────────┤
│ PTY/tmux   │ Claude Code  │ SSH Manager  │ File API          │
│ Terminal   │ CLI Bridge   │ Remote Hosts │ Project Detection  │
│ Manager    │ Chat Sessions│ Key Exchange │ Path Validation    │
├────────────┴──────────────┴──────────────┴───────────────────┤
│                   Vendored Python Packages                    │
│        Flask, SocketIO, Werkzeug, MarkupSafe, ...            │
└──────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
qn-claude-web/
├── app.py                  # Flask backend + WebSocket handlers (~2500 lines)
├── templates/
│   ├── index.html          # Main dashboard (single-page app)
│   └── login.html          # Login/setup page
├── static/
│   ├── css/style.css       # Themed styling (dark theme default)
│   ├── js/app.js           # Client-side JavaScript (ClaudeCodeWeb class)
│   ├── sw.js               # Service worker (PWA offline support)
│   └── manifest.json       # PWA manifest
├── .claude/                # Claude Code project configuration
│   ├── agents/             # Agent definitions (architect, builder, secops, ...)
│   ├── rules/              # Language and project standards
│   ├── skills/             # Slash command skills
│   └── settings.json       # Permission and environment config
├── vendor/                 # Vendored Python dependencies (14 packages)
├── sessions/               # Saved chat sessions (JSON, gitignored)
├── config.json             # Runtime configuration (gitignored)
├── build-installer.sh      # Installer generator with SHA-256 hashes
├── build-release.sh        # Self-extracting installer builder
└── qn-code-assistant.service  # systemd unit file
```

## Installation

### Self-Extracting Installer (Recommended)

Download the latest release and run:

```bash
chmod +x qn-claude-web-v1.5.1.sh
./qn-claude-web-v1.5.1.sh
```

The installer verifies SHA-256 hashes, extracts files, and runs interactive setup.

### Manual Setup

```bash
git clone https://github.com/rayketcham-lab/qn-claude-web.git /opt/claude-web
cd /opt/claude-web
python3 app.py
```

Dependencies are vendored — no `pip install` needed.

### Systemd Service

```bash
sudo cp qn-code-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable qn-code-assistant
sudo systemctl start qn-code-assistant
```

Monitor logs:
```bash
sudo journalctl -u qn-code-assistant -f
```

## Configuration

Settings are managed through the web UI (Settings icon). Configuration is persisted in `config.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `port` | `5001` | Server port |
| `projects_root` | `/opt` | Root directory for project browsing |
| `allowed_paths` | `["/opt"]` | Directories allowed for file access |
| `max_concurrent_terminals` | `5` | Max simultaneous terminal sessions |
| `max_concurrent_chats` | `10` | Max simultaneous chat processes |
| `process_timeout_minutes` | `60` | Watchdog timeout for stale processes |
| `auth.enabled` | `false` | Enable password authentication |
| `ssl_enabled` | `false` | Enable HTTPS |

## Remote Servers

Add remote hosts via **Settings > Remote Hosts > Add Remote Host**. The 5-step wizard handles:

1. **Method** — Choose SSH or mount-based connection
2. **Connect** — Enter host details or import from `~/.ssh/config`
3. **SSH Key Setup** — Auto-generates ed25519 key and pushes via sshpass
4. **Verify** — Tests SSH connection and detects Claude CLI on remote
5. **Save** — One-click save with auto-suggested name

Supports two modes:
- **SSH mode** — runs Claude Code on the remote host
- **Mount mode** — runs local Claude Code on a mounted remote filesystem

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard |
| `/login` | GET/POST | Authentication |
| `/api/projects` | GET | List projects in root directory |
| `/api/projects/root` | POST | Set projects root path |
| `/api/config` | GET/POST | Read/write configuration |
| `/api/files` | GET | Browse directory contents |
| `/api/files/read` | GET | Read file with syntax detection |
| `/api/session/*` | GET/POST | Session CRUD operations |
| `/api/sessions` | GET | List all saved sessions |
| `/api/sessions/search` | GET | Full-text search across sessions |
| `/api/remote/test` | POST | Test remote host connection |
| `/api/remote/ssh-config` | GET | Parse SSH config file |
| `/api/remote/ssh-setup` | GET/POST | SSH key management |
| `/api/remote/push-key` | POST | Push SSH key to remote host |
| `/api/remote/<id>/projects` | GET | Browse remote host projects |
| `/api/project/detect` | GET | Auto-detect project type |
| `/api/project/init` | POST | Generate CLAUDE.md for project |
| `/api/users` | GET/POST/PUT | User management |
| `/api/usage` | GET | Token usage statistics |
| `/api/status` | GET | Health check endpoint |

## Security

| Control | Implementation |
|---------|---------------|
| **Authentication** | Password-based login with bcrypt hashing, multi-user support |
| **Rate Limiting** | 10 login attempts per 5 minutes per IP |
| **Security Headers** | CSP, X-Frame-Options, X-Content-Type-Options, HSTS, Referrer-Policy |
| **Cookie Security** | HttpOnly, SameSite=Lax, Secure flag (when SSL enabled) |
| **XSS Prevention** | HTML sanitization, escaped output, Content Security Policy |
| **Path Traversal** | Null byte rejection, symlink resolution, allowed-path enforcement |
| **App Directory** | Excluded from file browser — protects config, source, sessions |
| **SSH Sanitization** | Hostname/username character filtering, port range validation |
| **Message Limits** | Chat messages capped at 1MB |
| **Thread Safety** | Lock-protected session storage and terminal registry |
| **Version Hiding** | Server header stripped of framework/language identifiers |
| **Disconnect Handling** | 30-second grace period with browser correlation, orphan PTY cleanup |

## Troubleshooting

**Port already in use:**
```bash
lsof -ti:5001 | xargs kill -9
```

**Claude command not found:**
```bash
which claude
# Add to PATH if needed:
export PATH="$PATH:/path/to/claude"
```

**Service won't start:**
```bash
sudo journalctl -u qn-code-assistant -n 50
```

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Anthropic, PBC.
"Claude" and "Claude Code" are trademarks of Anthropic, PBC.
This is an independent, community-developed web interface that works with
the Claude Code CLI tool. Use requires a valid Claude subscription and
installed Claude Code CLI.

## License

License TBD. Currently for personal/internal use.
