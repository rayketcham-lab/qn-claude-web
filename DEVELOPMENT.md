# QN Code Assistant - Development Guide

## Project Background

This project provides a web-based interface for Claude Code CLI, enabling:
- Access from any device (phone, tablet, laptop)
- Persistent sessions that survive disconnects
- Easy project switching and flag management
- Both terminal and chat-style interactions
- Remote server management via SSH

## Design Decisions

### Why Flask + SocketIO?

- **Flask**: Lightweight, simple routing, good templating
- **SocketIO**: Bidirectional real-time communication for terminal I/O and streaming
- **Threading mode**: `async_mode='threading'` - no eventlet/gevent needed
- **No frontend framework**: Keeps it simple, fast to load, easy to modify

### Why Vendored Dependencies?

- All Python deps are in `vendor/` with `.dist-info` directories preserved
- No pip install needed, no virtualenv required
- `sys.path.insert()` adds vendor dir at startup
- `.dist-info` dirs MUST be kept (werkzeug uses `importlib.metadata`)

### Why PTY for Terminal?

- Full terminal emulation (colors, cursor movement, etc.)
- Claude Code CLI works exactly as in a real terminal
- Supports interactive features (prompts, confirmations)

### Why Subprocess for Chat?

- Simpler than PTY for one-shot prompts
- Easier to capture and stream output
- Claude Code runs with prompt as argument

## File Structure

### app.py (~2300 lines)

Key components:
- `CONFIG` dict + `load_config()`/`save_config()` - persistent config with type validation
- `active_terminals` - PTY session tracking with per-WebSocket ownership (`ws_sid`)
- `chat_sessions` + `chat_sessions_lock` - thread-safe chat session state
- `validate_file_path()` - path security (null bytes, symlinks, allowed paths, app dir exclusion)
- `build_claude_command()` - constructs CLI command with SSH wrapping for remote hosts
- WebSocket handlers: `terminal_create`, `terminal_input`, `terminal_resize`, `terminal_kill`, `chat_message`
- Disconnect handler kills orphaned PTY processes

### static/js/app.js (~2900 lines)

`ClaudeCodeWeb` class handles:
- Socket.IO connection management with auto-reconnect
- xterm.js terminal initialization and tab management
- Project/file/favorites list rendering via event delegation (no listener leaks)
- Remote Server Setup Wizard (5-step modal)
- Project Instructions Wizard (CLAUDE.md generator)
- Chat UI with streaming, markdown rendering, auto-follow
- Debounced actions (terminal create, file view)
- Settings modal with General, Favorites, Remote Hosts, Auth/SSL, Users tabs

### static/css/style.css (~2000 lines)

- CSS custom properties for 4 themes (dark, midnight, solarized, light)
- Mobile-first responsive design (`@media max-width: 768px`)
- Wizard modal styles (project init wizard, remote server wizard)

## Building & Releasing

### After any code change:

```bash
# 1. Rebuild installer (updates SHA-256 hashes)
bash build-installer.sh

# 2. Build self-extracting installer
bash build-release.sh

# 3. Deploy to website (optional)
sudo cp qn-code-assistant-v1.3.2.sh /var/www/html/
```

### Installer Notes

- Vendor hash uses **relative paths** (`cd` to project dir, `find vendor/`)
- Vendor hash excludes `__pycache__/`
- Self-extracting installer is base64-encoded ZIP (no tar dependency)
- Installer has `--verify-only` mode for integrity checking

## Security Architecture

### Authentication
- Session-based auth with Flask sessions
- Rate limiting: 10 login attempts per 5 minutes per IP
- Multi-user support with admin/user roles
- Secure cookies: HttpOnly, SameSite=Lax, Secure (when SSL)

### Path Security
- `validate_file_path()` enforces allowed paths list
- Null byte injection blocked
- Symlinks resolved before path checking
- Application directory (`/opt/claude-web/`) always excluded from file browser
- Prevents leaking config.json (secrets), source code, and session data

### Input Validation
- SSH hostname/username character filtering
- Chat message size limit (1MB)
- Config values type-validated on load
- CLAUDE.md content size limit (50KB)

### Headers
- CSP restricting script/style sources
- X-Frame-Options: SAMEORIGIN
- Server version header replaced with `QN Code Assistant`

## Testing

### Running the Server

```bash
# Use system Python (vendor/ dir has all deps)
/usr/bin/python3 /opt/claude-web/app.py

# Kill existing instance
lsof -ti:5001 | xargs kill -9
```

### Manual Testing Checklist

- [ ] Project browser loads directories
- [ ] Terminal creates, receives I/O, resizes, kills
- [ ] Multiple terminal tabs work
- [ ] Chat sends messages and streams responses
- [ ] File browser navigates and displays files
- [ ] Remote host wizard completes full flow
- [ ] SSH key generation and exchange works
- [ ] Authentication login/logout cycle
- [ ] Settings save and persist across restarts
- [ ] Favorites add/remove
- [ ] Session search returns results
- [ ] Export produces valid markdown
- [ ] Mobile layout works
- [ ] All keyboard shortcuts function

### Security Testing

```bash
# Path traversal
curl -s "http://localhost:5001/api/files?path=/etc"
# Expected: {"error":"Path not allowed"}

# App directory access
curl -s "http://localhost:5001/api/files/read?path=/opt/claude-web/config.json"
# Expected: {"error":"Path not allowed"}

# Rate limiting
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5001/login \
    -H "Content-Type: application/json" -d '{"username":"x","password":"wrong"}'
done
# Expected: 401s then 429s after ~8 attempts
```
