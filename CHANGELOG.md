# Changelog

All notable changes to QN Code Assistant.

## [1.3.2] - 2026-02-10

### Added
- **Remote Server Setup Wizard** - 5-step guided wizard for adding remote hosts
  - Import hosts from `~/.ssh/config` with one click
  - Autonomous SSH key generation and exchange (via sshpass)
  - Automated connection verification and Claude CLI detection
  - Auto-suggested friendly name and default path
- `/api/remote/ssh-config` endpoint - parses `~/.ssh/config` for host discovery
- `/api/remote/push-key` endpoint - pushes SSH public key to remote hosts
- Enhanced `/api/remote/ssh-setup` with POST method for key generation
- **Project refresh button** in sidebar
- Dynamic sidebar labels when browsing remote hosts (shows hostname with back arrow)

### Security
- **App directory exclusion** - File browser now blocks access to the application's own directory (prevents leaking `config.json` secrets, source code, and session data)
- **Server header hardened** - Replaced `Werkzeug/x.x Python/x.x` with `QN Code Assistant`
- **WebSocket path validation** - `terminal_create` now validates paths via `validate_file_path()`
- **Chat message size limit** - Messages over 1MB rejected to prevent disk abuse
- **Null request body protection** - All 8 POST endpoints guarded against `None` request body
- **Session thread safety** - Added `chat_sessions_lock` for safe concurrent access
- **Config type validation** - Integer coercion and list type checks on config load
- **SSH key path validation** - Logs warning when configured key file is missing

### Fixed
- **Disconnect handler** - Now properly kills orphaned PTY processes (was empty `pass`)
- **PTY child failure** - `os.execvp()` errors now reported to parent via stderr instead of silent death
- **Event listener leaks** - Switched to event delegation for all dynamically rendered lists (projects, favorites, remote hosts, file tree, search results)
- **Click debouncing** - Terminal create (1s) and file view (300ms) cooldowns prevent duplicate actions
- **Bare except blocks** - Replaced with specific exception types (`OSError`, `json.JSONDecodeError`, etc.)

### Changed
- Remote host inline form replaced with wizard modal
- Version bumped to 1.3.2

## [1.3.1] - 2026-02-09

### Added
- **Project Instructions Wizard** - 5-step guided questionnaire to generate CLAUDE.md files for any project
  - Auto-detects project type from package.json, pyproject.toml, Cargo.toml, go.mod
  - Pre-fills name, language, framework, build/test/dev/lint commands
  - Configurable code style (indent, line length, naming convention)
  - Preview and source editing on final step
  - Optional .claude/settings.json creation with permission levels
- `/api/project/detect` endpoint for project type auto-detection
- `/api/project/init` endpoint for writing CLAUDE.md and settings
- **Secure Installer** - `build-installer.sh` generates `install.sh` with baked SHA-256 hashes
  - Self-verifying integrity check (no phone-home)
  - Full install, verify-only, and uninstall modes
  - Prerequisite checks (Python 3.8+, pip, git)
  - Systemd service setup, file permissions hardening
- Disclaimer added to README.md

### Security
- **Rate Limiting** - Login (10/5min), auth setup (5/hour) per IP
- **Security Headers** - CSP, X-Frame-Options, X-Content-Type-Options, HSTS, Referrer-Policy
- **Secure Cookies** - HttpOnly, SameSite=Lax, Secure (when SSL enabled)
- **XSS Prevention** - HTML sanitization on markdown rendering via DOMParser
  - All user-controlled strings escaped via `_escapeHtml()` before innerHTML injection
  - Removed inline onclick handlers, replaced with data attributes + addEventListener
- **Path Traversal Hardening** - Null byte rejection, resolved-path revalidation
- **Input Validation** - Size limits on CLAUDE.md (50KB), settings.json (10KB)
- **CORS Restriction** - SocketIO restricted to same-origin only
- **SSH Sanitization** - Port validation, username/hostname character filtering

### Changed
- Version bumped to 1.3.1

## [1.3.0] - 2026-02-09

### Added
- **Keyboard Shortcuts**: Global shortcuts (Ctrl+1/2/3 views, Ctrl+T new terminal, Ctrl+W close, Ctrl+K focus chat, Ctrl+, settings, ? help overlay)
- **Export to Markdown**: Export chat sessions as `.md` files via download button in chat header
- **Notification Sounds**: Web Audio API tones on chat completion/error (plays when tab is hidden, toggle in chat controls)
- **Apache Reverse Proxy Config**: Ready-to-use `apache-proxy.conf` with WebSocket support
- **PWA Support**: Service worker, manifest.json, installable as standalone app on mobile
- **Custom Themes**: 4 built-in themes (Dark, Midnight Blue, Solarized Dark, Light) selectable in Settings
- **Session Search**: Search across all saved sessions with instant results dropdown in chat header
- **Git Integration**: Displays current branch and dirty/clean status badge in terminal toolbar
- **File Browser**: New "Files" view tab with directory tree, file viewer with syntax highlighting, breadcrumb navigation
- **Multi-User Support**: User management with admin/user roles, per-user access control, Users tab in Settings
- `/api/session/<id>/export` endpoint for markdown export
- `/api/sessions/search?q=` endpoint for session search
- `/api/git/status?path=` endpoint for git branch/status info
- `/api/files` and `/api/files/read` endpoints for file browsing
- `/api/users` CRUD endpoints for user management
- `/api/auth/whoami` endpoint for current user info
- SVG favicon and app icon

### Changed
- Version bumped to 1.3.0
- Settings General tab now includes Theme selector
- Settings modal has new Users tab (admin only)
- Terminal toolbar shows git branch badge
- Chat header includes search bar and export button
- Login supports multi-user authentication with role-based access

### Fixed
- View tab switching now properly initializes file browser on first open

## [1.2.0] - 2026-02-06

### Added
- **Authentication**: Password-protected access with login page and first-run setup
- **HTTPS Support**: Auto-generated self-signed certificates or custom cert paths
- **Terminal Tabs**: Multiple concurrent terminal sessions with tab switching
- **Usage Tracking**: Token usage monitoring with weekly reset counters
- Login page with session-based authentication (`/login`, `/logout`)
- Auth & SSL settings tab in Settings panel
- SSL certificate auto-generation via OpenSSL
- `/api/usage` endpoint for token consumption data
- `/api/terminals` endpoint for active terminal listing
- `/api/auth/status` and `/api/auth/setup` endpoints
- `/api/session/persistent` endpoint for single persistent chat
- Usage display in sidebar with weekly token counts and reset countdown
- Logout button in sidebar header (visible when auth enabled)
- **Directory Browsing Restrictions**: Limit project browsing to `/opt` by default with configurable allowed paths
- `allowed_paths` and `allow_full_browsing` config options in General settings

### Changed
- **Chat simplified**: Single persistent session replacing multi-tab chat
- Chat always uses configured working directory (`/opt/claude` by default)
- Persistent secret key in config (sessions survive server restarts)
- Terminal new button moved to terminal tab bar
- Version bumped to 1.2.0

### Fixed
- Scroll-to-top bug on message completion (min-height lock during markdown reflow)
- Session loss on server restart (random secret key replaced with persistent key)

### Removed
- Multi-session chat tabs (replaced with single persistent session)
- Sessions sidebar tab (projects only now)

## [1.1.0] - 2026-02-05

### Added
- Health check `/api/status` with version, uptime, claude CLI version
- Stream buffering (50ms) to prevent DOM thrashing
- Double-RAF scroll fix + auto-follow toggle
- CSS `content-visibility` + `overflow-anchor` for performance
- Settings panel (gear icon): General, Favorites, Remote Hosts tabs
- Config persistence with `config.json`
- Favorites: sidebar section, add/remove in settings
- Remote hosts - Mount mode and SSH mode
- API endpoints: `/api/config`, `/api/remote/test`, `/api/remote/<id>/projects`

## [1.0.0] - 2026-02-05

### Initial Release

#### Features
- Project browser with directory navigation
- Auto-detection of project types (git, claude, node, python, rust)
- Full terminal emulation via xterm.js with PTY backend
- Chat interface with markdown rendering
- Streaming responses in both terminal and chat modes
- Session persistence to JSON files
- Flag toggles: `-r`, `-c`, `--dangerously-skip-permissions`, `--verbose`
- Model selection (sonnet, opus, haiku)
- Mobile-responsive design
- Dark theme UI
- WebSocket-based real-time communication

---

## Planned Features

- [ ] File editing in browser
- [ ] Collaborative multi-user sessions
- [ ] Plugin system
- [ ] CI/CD integration
