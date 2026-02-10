# QN Code Assistant

A self-hosted web frontend for Claude Code CLI, allowing you to access Claude Code from any browser - laptop, phone, or tablet.

## Features

- **Project Browser** - Browse directories, auto-detect project types (git, node, python, rust, claude)
- **Terminal Emulator** - Full xterm.js terminal with PTY support, multiple tabs
- **Chat Interface** - Persistent chat with markdown rendering and streaming responses
- **Remote Servers** - SSH and mount-based remote host support with guided setup wizard
- **File Browser** - Directory tree, file viewer with syntax highlighting, breadcrumb navigation
- **Authentication** - Password-protected access with multi-user support and role-based access
- **HTTPS Support** - Auto-generated self-signed certs or custom certificate paths
- **Project Instructions Wizard** - Generate CLAUDE.md files with auto-detected project settings
- **Session Search** - Search across all saved conversations
- **Git Integration** - Branch and status display in terminal toolbar
- **Keyboard Shortcuts** - Ctrl+T new terminal, Ctrl+K focus chat, Ctrl+1/2/3 switch views, and more
- **PWA Support** - Installable as standalone app on mobile devices
- **Themes** - Dark, Midnight Blue, Solarized Dark, Light
- **Usage Tracking** - Token usage monitoring with weekly reset counters
- **Export** - Export chat sessions as markdown files

## Requirements

- Python 3.8+
- Claude Code CLI installed and in PATH
- Modern web browser

## Quick Start

```bash
cd /opt/claude-web
./start.sh
```

Then open http://localhost:5001 in your browser.

For LAN/mobile access, use your server's IP: `http://<server-ip>:5001`

## Installation

### Self-Extracting Installer

```bash
# Download and run
chmod +x qn-code-assistant-v1.3.2.sh
./qn-code-assistant-v1.3.2.sh
```

### Manual Setup

```bash
# Clone/copy to /opt/claude-web
cd /opt/claude-web

# Dependencies are vendored - no pip install needed
# Just run:
python3 app.py
```

### Systemd Service (Auto-start on boot)

```bash
sudo cp qn-code-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable qn-code-assistant
sudo systemctl start qn-code-assistant
sudo journalctl -u qn-code-assistant -f
```

## Configuration

Settings are managed through the web UI (Settings gear icon). Configuration is stored in `config.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `port` | 5001 | Server port |
| `projects_root` | `/opt` | Root directory for project browsing |
| `allowed_paths` | `["/opt"]` | Directories allowed for file browsing |
| `max_concurrent_terminals` | 5 | Max simultaneous terminal sessions |
| `max_concurrent_chats` | 10 | Max simultaneous chat processes |
| `process_timeout_minutes` | 60 | Watchdog timeout for stale processes |
| `auth.enabled` | false | Enable password authentication |
| `ssl_enabled` | false | Enable HTTPS |

## Remote Servers

Add remote hosts via **Settings > Remote Hosts > Add Remote Host**. The guided wizard handles:

1. **Import from SSH config** or enter details manually
2. **Automatic SSH key setup** - generates ed25519 key and pushes it to the remote
3. **Connection verification** - tests SSH and detects Claude CLI on remote
4. **One-click save** with auto-suggested name

Supports SSH mode (runs Claude on remote) and mount mode (local Claude on mounted filesystem).

## Architecture

```
/opt/claude-web/
├── app.py                  # Flask backend + WebSocket handlers
├── templates/
│   ├── index.html          # Main dashboard
│   └── login.html          # Login/setup page
├── static/
│   ├── css/style.css       # Themed styling
│   ├── js/app.js           # Client-side JavaScript
│   ├── sw.js               # Service worker (PWA)
│   └── manifest.json       # PWA manifest
├── sessions/               # Saved chat sessions (JSON)
├── vendor/                 # Vendored Python dependencies
├── config.json             # Configuration
├── install.sh              # Self-verifying installer
├── build-installer.sh      # Installer generator
├── build-release.sh        # Self-extracting installer generator
└── qn-code-assistant.service
```

## Security

- Rate-limited login (10 attempts per 5 minutes per IP)
- Security headers: CSP, X-Frame-Options, X-Content-Type-Options, HSTS, Referrer-Policy
- Secure cookies: HttpOnly, SameSite=Lax, Secure (when SSL enabled)
- XSS prevention: HTML sanitization, escaped user input, Content Security Policy
- Path traversal hardening: null byte rejection, symlink resolution, allowed-path enforcement
- Application directory excluded from file browser (protects config, source, sessions)
- SSH input sanitization: hostname/username character filtering, port validation
- Chat message size limit (1MB)
- Thread-safe session storage
- Server version header removed

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard |
| `/login` | GET/POST | Authentication |
| `/api/projects` | GET | List projects |
| `/api/projects/root` | POST | Set projects root |
| `/api/config` | GET/POST | Configuration |
| `/api/files` | GET | Browse directory |
| `/api/files/read` | GET | Read file contents |
| `/api/session/*` | GET/POST | Session management |
| `/api/sessions` | GET | List sessions |
| `/api/sessions/search` | GET | Search sessions |
| `/api/remote/test` | POST | Test remote connection |
| `/api/remote/ssh-config` | GET | Parse SSH config |
| `/api/remote/ssh-setup` | GET/POST | SSH key management |
| `/api/remote/push-key` | POST | Push SSH key to remote |
| `/api/remote/<id>/projects` | GET | Browse remote projects |
| `/api/project/detect` | GET | Auto-detect project type |
| `/api/project/init` | POST | Generate CLAUDE.md |
| `/api/users` | GET/POST/PUT | User management |
| `/api/usage` | GET | Token usage stats |
| `/api/status` | GET | Health check |

## Troubleshooting

### Port already in use
```bash
lsof -ti:5001 | xargs kill -9
```

### Claude command not found
```bash
which claude
# Or add to PATH in start.sh
export PATH="$PATH:/path/to/claude"
```

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Anthropic, PBC.
"Claude" and "Claude Code" are trademarks of Anthropic, PBC.
This is an independent, community-developed web interface that works with
the Claude Code CLI tool. Use requires a valid Claude subscription and
installed Claude Code CLI.

## License

License TBD. Currently for personal/internal use.
