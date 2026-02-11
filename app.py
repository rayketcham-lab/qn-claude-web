#!/usr/bin/env python3
"""
QN Code Assistant
A full-featured web frontend for Claude Code CLI
"""

import os
import sys
import json
import pty
import re
import select
import shlex
import subprocess
import tempfile
import threading
import uuid
import signal
import atexit
import time
from functools import wraps
from datetime import datetime, timedelta
from pathlib import Path

# Use vendored dependencies if available (self-contained mode)
_vendor_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vendor')
if os.path.isdir(_vendor_dir):
    sys.path.insert(0, _vendor_dir)

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins=None, async_mode='threading')

# Version info
VERSION = "1.4.0"
START_TIME = datetime.now()

# ============== Rate Limiting ==============
# Simple in-memory rate limiter: {endpoint_key: [(timestamp, ip), ...]}
_rate_limit_store = {}
_rate_limit_lock = threading.Lock()


def _clean_rate_limits():
    """Remove expired entries from rate limit store"""
    now = time.time()
    with _rate_limit_lock:
        for key in list(_rate_limit_store.keys()):
            _rate_limit_store[key] = [
                (ts, ip) for ts, ip in _rate_limit_store[key]
                if now - ts < 3600  # Keep entries up to 1 hour
            ]
            if not _rate_limit_store[key]:
                del _rate_limit_store[key]


def check_rate_limit(endpoint, ip, max_attempts, window_seconds):
    """Check if IP has exceeded rate limit for an endpoint.
    Returns True if request is allowed, False if rate-limited."""
    now = time.time()
    key = endpoint

    with _rate_limit_lock:
        if key not in _rate_limit_store:
            _rate_limit_store[key] = []

        # Count attempts from this IP within the window
        recent = [
            (ts, addr) for ts, addr in _rate_limit_store[key]
            if addr == ip and now - ts < window_seconds
        ]

        if len(recent) >= max_attempts:
            return False

        _rate_limit_store[key].append((now, ip))
        return True

# Configuration
CONFIG_FILE = Path(__file__).parent / 'config.json'

def load_config():
    """Load config from disk, merging with defaults"""
    defaults = {
        'host': '0.0.0.0',
        'port': 5001,
        'projects_root': '/opt',
        'process_timeout_minutes': 60,
        'max_concurrent_terminals': 5,
        'max_concurrent_chats': 10,
        'default_flags': [],
        'favorites': [],
        'remote_hosts': [],
        'allowed_paths': ['/opt'],
        'allow_full_browsing': False,
        'auth': {
            'enabled': False,
            'username': '',
            'password_hash': '',
        },
        'ssl_enabled': False,
        'ssl_cert': '',
        'ssl_key': '',
        'chat_cwd': '/opt/claude',
        'persistent_session_id': '',
        'theme': 'dark',
        'users': [],
        'active_agents': ['architect', 'builder', 'tester', 'secops', 'devops'],
        'custom_agents': [],
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                file_config = json.load(f)
            defaults.update(file_config)
        except Exception as e:
            print(f"[Config] Error loading config: {e}")

    # Type-validate critical config values (coerce or reset to defaults)
    for key, expected_type, fallback in [
        ('port', int, 5001),
        ('process_timeout_minutes', int, 60),
        ('max_concurrent_terminals', int, 5),
        ('max_concurrent_chats', int, 10),
        ('session_timeout_hours', int, 24),
    ]:
        try:
            defaults[key] = expected_type(defaults.get(key, fallback))
        except (TypeError, ValueError):
            defaults[key] = fallback
    for key, fallback in [('favorites', []), ('remote_hosts', []), ('default_flags', []),
                          ('allowed_paths', ['/opt']), ('users', []),
                          ('active_agents', ['architect', 'builder', 'tester', 'secops', 'devops']),
                          ('custom_agents', [])]:
        if not isinstance(defaults.get(key), list):
            defaults[key] = fallback

    defaults['projects_root'] = os.path.expanduser(defaults['projects_root'])
    return defaults

def save_config(config_dict):
    """Save config to disk"""
    to_save = {k: v for k, v in config_dict.items()
               if k not in ('sessions_dir', 'backup_dir')}
    # Convert Path objects to strings for JSON
    for k, v in to_save.items():
        if isinstance(v, Path):
            to_save[k] = str(v)
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(to_save, f, indent=2)
    except Exception as e:
        print(f"[Config] Error saving config: {e}")

CONFIG = load_config()
CONFIG['sessions_dir'] = Path(__file__).parent / 'sessions'
CONFIG['backup_dir'] = Path(__file__).parent / 'backups'

# Persistent secret key (survives restarts so sessions aren't lost)
if 'secret_key' not in CONFIG:
    CONFIG['secret_key'] = os.urandom(24).hex()
    save_config(CONFIG)
app.secret_key = CONFIG['secret_key']

# Secure cookie configuration
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
if CONFIG.get('ssl_enabled', False):
    app.config['SESSION_COOKIE_SECURE'] = True


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # Content-Security-Policy: allow CDN scripts for xterm, socketio, marked, hljs
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.socket.io; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "connect-src 'self' ws: wss:; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "frame-ancestors 'self'"
    )
    response.headers['Content-Security-Policy'] = csp

    # HSTS only when SSL is enabled
    if CONFIG.get('ssl_enabled', False):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    # Remove server version info from response level too
    response.headers.pop('Server', None)

    return response


# Usage tracking
USAGE_FILE = Path(__file__).parent / 'usage.json'

def load_usage():
    """Load usage data from disk"""
    defaults = {'sessions': {}, 'weekly': {}, 'total': {'input_tokens': 0, 'output_tokens': 0}}
    if USAGE_FILE.exists():
        try:
            with open(USAGE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return defaults

def save_usage(usage):
    """Save usage data to disk"""
    try:
        with open(USAGE_FILE, 'w') as f:
            json.dump(usage, f, indent=2)
    except Exception as e:
        print(f"[Usage] Error saving: {e}")

def get_week_key():
    """Get ISO week key like '2026-W06'"""
    now = datetime.now()
    return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"


# ============== Authentication ==============

def login_required(f):
    """Decorator to require authentication on routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_config = CONFIG.get('auth', {})
        if not auth_config.get('enabled', False):
            return f(*args, **kwargs)
        if not session.get('authenticated'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

# Active terminal sessions: {session_id: {'pid': int, 'fd': int, 'thread': Thread, 'started': datetime}}
active_terminals = {}

# Active chat processes: {session_id: {'process': Popen, 'started': datetime}}
active_chat_processes = {}

# Chat sessions storage: {session_id: {'messages': [], 'project': str, 'flags': []}}
chat_sessions = {}
chat_sessions_lock = threading.Lock()

# Watchdog thread
watchdog_running = True


def cleanup_old_processes():
    """Kill processes that have been running too long"""
    timeout = timedelta(minutes=CONFIG['process_timeout_minutes'])
    now = datetime.now()

    # Clean up terminals
    for tid, term in list(active_terminals.items()):
        if now - term.get('started', now) > timeout:
            print(f"[Watchdog] Killing stale terminal {tid}")
            try:
                os.kill(term['pid'], signal.SIGTERM)
            except OSError:
                pass
            active_terminals.pop(tid, None)

    # Clean up chat processes
    for sid, chat in list(active_chat_processes.items()):
        if now - chat.get('started', now) > timeout:
            print(f"[Watchdog] Killing stale chat process {sid}")
            try:
                chat['process'].terminate()
            except OSError:
                pass
            active_chat_processes.pop(sid, None)


def watchdog_thread():
    """Background thread that monitors and cleans up processes"""
    while watchdog_running:
        try:
            cleanup_old_processes()
            # Save all sessions periodically
            backup_all_sessions()
            # Clean up expired rate limit entries
            _clean_rate_limits()
        except Exception as e:
            print(f"[Watchdog] Error: {e}")
        time.sleep(60)  # Check every minute


def backup_all_sessions():
    """Backup all active sessions to disk"""
    for session_id in list(chat_sessions.keys()):
        try:
            save_session(session_id)
        except Exception as e:
            print(f"[Backup] Error saving session {session_id}: {e}")


def shutdown_cleanup():
    """Clean up all processes on shutdown"""
    global watchdog_running
    watchdog_running = False
    print("[Shutdown] Cleaning up processes...")

    # Save all sessions
    backup_all_sessions()

    # Kill all terminals
    for tid, term in list(active_terminals.items()):
        try:
            os.kill(term['pid'], signal.SIGTERM)
        except OSError:
            pass

    # Kill all chat processes
    for sid, chat in list(active_chat_processes.items()):
        try:
            chat['process'].terminate()
        except OSError:
            pass

    print("[Shutdown] Cleanup complete")


# Register cleanup on exit
atexit.register(shutdown_cleanup)


def get_projects(root_path=None):
    """Scan for potential project directories"""
    root = Path(root_path or CONFIG['projects_root']).expanduser().resolve()
    projects = []

    if not root.exists():
        return projects

    # Add current directory as a selectable option (marked special)
    is_git = (root / '.git').exists()
    is_claude = (root / '.claude').exists()
    has_package = (root / 'package.json').exists()
    has_pyproject = (root / 'pyproject.toml').exists()
    has_cargo = (root / 'Cargo.toml').exists()

    projects.append({
        'name': f'. (current: {root.name})',
        'path': str(root),
        'is_git': is_git,
        'is_claude': is_claude,
        'type': 'current',
        'indicators': {
            'git': is_git,
            'claude': is_claude,
            'node': has_package,
            'python': has_pyproject,
            'rust': has_cargo,
        }
    })

    try:
        for item in root.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name != 'venv' and item.name != '__pycache__' and item.name != 'node_modules':
                # Check for indicators of a project
                is_git = (item / '.git').exists()
                is_claude = (item / '.claude').exists()
                has_package = (item / 'package.json').exists()
                has_pyproject = (item / 'pyproject.toml').exists()
                has_cargo = (item / 'Cargo.toml').exists()

                projects.append({
                    'name': item.name,
                    'path': str(item),
                    'is_git': is_git,
                    'is_claude': is_claude,
                    'type': 'git' if is_git else 'folder',
                    'indicators': {
                        'git': is_git,
                        'claude': is_claude,
                        'node': has_package,
                        'python': has_pyproject,
                        'rust': has_cargo,
                    }
                })
    except PermissionError as e:
        print(f"Permission error reading {root}: {e}")
    except Exception as e:
        print(f"Error reading {root}: {e}")

    # Sort: current first, then claude projects, then git, then alphabetical
    projects.sort(key=lambda p: (p['type'] != 'current', not p['is_claude'], not p['is_git'], p['name'].lower()))
    return projects


def _sanitize_model_name(model):
    """Validate model name contains only safe characters"""
    if not model:
        return None
    # Allow alphanumeric, hyphens, dots, colons, underscores, brackets (for [1m] suffix)
    if not re.match(r'^[a-zA-Z0-9._:\[\]\-]+$', model):
        return None
    return model


# ============== Agent Library ==============
# 20 predefined agent templates for Claude Code agent teams.
# Sentinel is always active (locked). Users select up to 5 others.

def _load_agent_file(filename, fallback=''):
    """Load agent definition from .claude/agents/ directory."""
    path = os.path.join(os.path.dirname(__file__), '.claude', 'agents', filename)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return f.read()
    return fallback

AGENT_LIBRARY = {
    'sentinel': {
        'id': 'sentinel', 'name': 'Sentinel', 'category': 'core',
        'description': 'Context window watchdog — monitors utilization, forces compaction',
        'icon': '&#x1F6E1;', 'locked': True, 'filename': 'sentinel.md',
        'content': _load_agent_file('sentinel.md', '# Sentinel Agent\n\nContext window watchdog. Monitors utilization and forces compaction at thresholds.\n'),
    },
    'architect': {
        'id': 'architect', 'name': 'Architect', 'category': 'core',
        'description': 'System design, API contracts, dependency decisions',
        'icon': '&#x1F3D7;', 'locked': False, 'filename': 'architect.md',
        'content': _load_agent_file('architect.md', '# Architect Agent\n\nSystem design authority.\n'),
    },
    'builder': {
        'id': 'builder', 'name': 'Builder', 'category': 'core',
        'description': 'Feature implementation, refactoring, code generation',
        'icon': '&#x1F528;', 'locked': False, 'filename': 'builder.md',
        'content': _load_agent_file('builder.md', '# Builder Agent\n\nPrimary implementation engine.\n'),
    },
    'tester': {
        'id': 'tester', 'name': 'Tester', 'category': 'core',
        'description': 'Test creation, coverage analysis, edge case identification',
        'icon': '&#x1F9EA;', 'locked': False, 'filename': 'tester.md',
        'content': _load_agent_file('tester.md', '# Tester Agent\n\nQuality gatekeeper.\n'),
    },
    'secops': {
        'id': 'secops', 'name': 'SecOps', 'category': 'core',
        'description': 'Security review, vulnerability analysis, compliance',
        'icon': '&#x1F512;', 'locked': False, 'filename': 'secops.md',
        'content': _load_agent_file('secops.md', '# SecOps Agent\n\nSecurity authority.\n'),
    },
    'devops': {
        'id': 'devops', 'name': 'DevOps', 'category': 'core',
        'description': 'CI/CD, build systems, deployment, infrastructure',
        'icon': '&#x2699;', 'locked': False, 'filename': 'devops.md',
        'content': _load_agent_file('devops.md', '# DevOps Agent\n\nBuild and deploy authority.\n'),
    },
    'researcher': {
        'id': 'researcher', 'name': 'Researcher', 'category': 'specialist',
        'description': 'Deep codebase exploration, technology evaluation, API research',
        'icon': '&#x1F50D;', 'locked': False, 'filename': 'researcher.md',
        'content': _load_agent_file('researcher.md', '# Researcher Agent\n\nInvestigation specialist.\n'),
    },
    'documenter': {
        'id': 'documenter', 'name': 'Documenter', 'category': 'specialist',
        'description': 'Documentation writing, API docs, README generation',
        'icon': '&#x1F4DD;', 'locked': False, 'filename': 'documenter.md',
        'content': _load_agent_file('documenter.md', '# Documenter Agent\n\nTechnical writer.\n'),
    },
    'code-reviewer': {
        'id': 'code-reviewer', 'name': 'Code Reviewer', 'category': 'specialist',
        'description': 'Systematic code review, style enforcement, quality metrics',
        'icon': '&#x1F440;', 'locked': False, 'filename': 'code-reviewer.md',
        'content': _load_agent_file('code-reviewer.md', '# Code Reviewer Agent\n\nQuality inspector.\n'),
    },
    'debugger': {
        'id': 'debugger', 'name': 'Debugger', 'category': 'specialist',
        'description': 'Bug hunting, root cause analysis, reproduction steps',
        'icon': '&#x1F41B;', 'locked': False, 'filename': 'debugger.md',
        'content': _load_agent_file('debugger.md', '# Debugger Agent\n\nBug detective.\n'),
    },
    'optimizer': {
        'id': 'optimizer', 'name': 'Optimizer', 'category': 'specialist',
        'description': 'Performance profiling, memory optimization, algorithmic improvements',
        'icon': '&#x26A1;', 'locked': False, 'filename': 'optimizer.md',
        'content': _load_agent_file('optimizer.md', '# Optimizer Agent\n\nPerformance engineer.\n'),
    },
    'migrator': {
        'id': 'migrator', 'name': 'Migrator', 'category': 'specialist',
        'description': 'Version migrations, framework upgrades, deprecation handling',
        'icon': '&#x1F4E6;', 'locked': False, 'filename': 'migrator.md',
        'content': _load_agent_file('migrator.md', '# Migrator Agent\n\nUpgrade specialist.\n'),
    },
    'frontend': {
        'id': 'frontend', 'name': 'Frontend', 'category': 'domain',
        'description': 'UI/UX implementation, CSS, accessibility, browser compatibility',
        'icon': '&#x1F3A8;', 'locked': False, 'filename': 'frontend.md',
        'content': _load_agent_file('frontend.md', '# Frontend Agent\n\nUI/UX engineer.\n'),
    },
    'backend': {
        'id': 'backend', 'name': 'Backend', 'category': 'domain',
        'description': 'Server logic, middleware, business rules, service architecture',
        'icon': '&#x1F5A5;', 'locked': False, 'filename': 'backend.md',
        'content': _load_agent_file('backend.md', '# Backend Agent\n\nServer-side engineer.\n'),
    },
    'database': {
        'id': 'database', 'name': 'Database', 'category': 'domain',
        'description': 'Schema design, query optimization, migration scripts, indexing',
        'icon': '&#x1F4BE;', 'locked': False, 'filename': 'database.md',
        'content': _load_agent_file('database.md', '# Database Agent\n\nData architect.\n'),
    },
    'api-designer': {
        'id': 'api-designer', 'name': 'API Designer', 'category': 'domain',
        'description': 'REST/GraphQL API design, versioning, documentation',
        'icon': '&#x1F310;', 'locked': False, 'filename': 'api-designer.md',
        'content': _load_agent_file('api-designer.md', '# API Designer Agent\n\nInterface architect.\n'),
    },
    'data-engineer': {
        'id': 'data-engineer', 'name': 'Data Engineer', 'category': 'domain',
        'description': 'ETL pipelines, data modeling, data quality, warehousing',
        'icon': '&#x1F4CA;', 'locked': False, 'filename': 'data-engineer.md',
        'content': _load_agent_file('data-engineer.md', '# Data Engineer Agent\n\nPipeline architect.\n'),
    },
    'ml-engineer': {
        'id': 'ml-engineer', 'name': 'ML Engineer', 'category': 'domain',
        'description': 'Model training, evaluation, deployment, MLOps',
        'icon': '&#x1F916;', 'locked': False, 'filename': 'ml-engineer.md',
        'content': _load_agent_file('ml-engineer.md', '# ML Engineer Agent\n\nMachine learning specialist.\n'),
    },
    'mobile': {
        'id': 'mobile', 'name': 'Mobile', 'category': 'domain',
        'description': 'iOS/Android development, cross-platform, responsive design',
        'icon': '&#x1F4F1;', 'locked': False, 'filename': 'mobile.md',
        'content': _load_agent_file('mobile.md', '# Mobile Agent\n\nMobile application engineer.\n'),
    },
    'infra': {
        'id': 'infra', 'name': 'Infrastructure', 'category': 'domain',
        'description': 'Cloud architecture, networking, scaling, cost optimization',
        'icon': '&#x2601;', 'locked': False, 'filename': 'infra.md',
        'content': _load_agent_file('infra.md', '# Infrastructure Agent\n\nCloud and systems architect.\n'),
    },
}


def deploy_agents(project_path, active_agent_ids, custom_agents):
    """Write active agent .md files to the project's .claude/agents/ directory.
    Sentinel is always deployed. Returns list of deployed filenames."""
    agents_dir = os.path.join(project_path, '.claude', 'agents')
    os.makedirs(agents_dir, exist_ok=True)

    deployed = []
    # Always deploy sentinel
    sentinel = AGENT_LIBRARY.get('sentinel')
    if sentinel:
        filepath = os.path.join(agents_dir, sentinel['filename'])
        with open(filepath, 'w') as f:
            f.write(sentinel['content'])
        deployed.append(sentinel['filename'])

    # Deploy active predefined agents
    for agent_id in active_agent_ids:
        agent = AGENT_LIBRARY.get(agent_id)
        if agent and agent_id != 'sentinel':
            filepath = os.path.join(agents_dir, agent['filename'])
            with open(filepath, 'w') as f:
                f.write(agent['content'])
            deployed.append(agent['filename'])

    # Deploy custom agents
    for i, custom in enumerate(custom_agents or []):
        if custom.get('content'):
            filename = f"custom-{i + 1}.md"
            filepath = os.path.join(agents_dir, filename)
            with open(filepath, 'w') as f:
                f.write(custom['content'])
            deployed.append(filename)

    return deployed


def build_claude_env(flags):
    """Build environment variables dict for Claude process.
    Starts from current env and adds Claude-specific vars based on flags."""
    env = os.environ.copy()

    # Extended thinking: MAX_THINKING_TOKENS
    if flags.get('extended_thinking'):
        tokens = flags.get('thinking_tokens', 31999)
        try:
            tokens = max(1024, min(63999, int(tokens)))
        except (ValueError, TypeError):
            tokens = 31999
        env['MAX_THINKING_TOKENS'] = str(tokens)

    # Auto-compact threshold override
    autocompact = flags.get('autocompact_threshold')
    if autocompact is not None:
        try:
            autocompact = max(50, min(100, int(autocompact)))
            env['CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'] = str(autocompact)
        except (ValueError, TypeError):
            pass

    # Agent teams experimental flag
    if flags.get('agent_teams'):
        env['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'] = '1'

    return env


def build_claude_command(project_path, flags, prompt=None, remote_host=None):
    """Build the claude command, optionally wrapping for SSH.
    All user inputs are sanitized through shlex.quote() for shell safety."""
    cmd = ['claude']

    if flags.get('resume'):
        cmd.append('-r')
    if flags.get('continue'):
        cmd.append('-c')

    # Permission mode (replaces dangerously_skip_permissions)
    perm_mode = flags.get('permission_mode', '')
    if perm_mode:
        allowed_modes = ('default', 'acceptEdits', 'plan', 'dontAsk', 'bypassPermissions')
        if perm_mode in allowed_modes:
            cmd.extend(['--permission-mode', perm_mode])
    elif flags.get('dangerously_skip_permissions'):
        # Backward compat for old saved sessions
        cmd.append('--dangerously-skip-permissions')

    if flags.get('verbose'):
        cmd.append('--verbose')
    if flags.get('model'):
        sanitized_model = _sanitize_model_name(flags['model'])
        if sanitized_model:
            cmd.extend(['--model', sanitized_model])

    # Effort level
    effort = flags.get('effort_level')
    if effort and effort in ('low', 'medium', 'high'):
        cmd.extend(['--effort', effort])

    # Fallback model
    fallback = flags.get('fallback_model')
    if fallback:
        sanitized_fallback = _sanitize_model_name(fallback)
        if sanitized_fallback:
            cmd.extend(['--fallback-model', sanitized_fallback])

    # Tool restrictions
    allowed_tools = flags.get('allowed_tools', '')
    if allowed_tools:
        tools = ','.join(t.strip() for t in str(allowed_tools).split(',')
                         if t.strip() and re.match(r'^[a-zA-Z0-9._-]+$', t.strip()))
        if tools:
            cmd.extend(['--allowedTools', tools])

    disallowed_tools = flags.get('disallowed_tools', '')
    if disallowed_tools:
        tools = ','.join(t.strip() for t in str(disallowed_tools).split(',')
                         if t.strip() and re.match(r'^[a-zA-Z0-9._-]+$', t.strip()))
        if tools:
            cmd.extend(['--disallowedTools', tools])

    # Additional directories
    add_dirs = flags.get('add_dirs', '')
    if add_dirs:
        for d in str(add_dirs).strip().splitlines():
            d = d.strip()
            if d and not any(c in d for c in (';', '&', '|', '`', '$')):
                cmd.extend(['--add-dir', d])

    # MCP server config
    mcp_config = flags.get('mcp_config', '')
    if mcp_config:
        mcp_config = str(mcp_config).strip()
        if mcp_config and not any(c in mcp_config for c in (';', '&', '|', '`', '$')):
            cmd.extend(['--mcp-config', mcp_config])

    # System prompt append
    system_prompt = flags.get('system_prompt', '')
    if system_prompt:
        system_prompt = str(system_prompt)[:10000]
        cmd.extend(['--append-system-prompt', system_prompt])

    # Print mode (-p): one-shot query
    if flags.get('print_mode'):
        cmd.insert(1, '-p')  # -p goes right after 'claude'
        print_prompt = flags.get('print_prompt', '')
        if print_prompt:
            print_prompt = str(print_prompt)[:10000]
            cmd.append(print_prompt)
    elif prompt:
        cmd.append(prompt)

    # Wrap in SSH if remote host specified
    if remote_host and remote_host.get('mode') == 'ssh':
        # Build env var prefix for remote command
        env_prefix = ''
        if flags.get('extended_thinking'):
            tokens = flags.get('thinking_tokens', 31999)
            try:
                tokens = max(1024, min(63999, int(tokens)))
            except (ValueError, TypeError):
                tokens = 31999
            env_prefix = f'MAX_THINKING_TOKENS={tokens} '

        autocompact = flags.get('autocompact_threshold')
        if autocompact is not None:
            try:
                autocompact = max(50, min(100, int(autocompact)))
                env_prefix += f'CLAUDE_AUTOCOMPACT_PCT_OVERRIDE={autocompact} '
            except (ValueError, TypeError):
                pass

        if flags.get('agent_teams'):
            env_prefix += 'CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 '

        remote_cmd = f'cd {shlex.quote(project_path)} && {env_prefix}' + ' '.join(
            shlex.quote(c) for c in cmd
        )

        # Validate and sanitize SSH port
        try:
            ssh_port = int(remote_host.get('port', 22))
            if not (1 <= ssh_port <= 65535):
                ssh_port = 22
        except (ValueError, TypeError):
            ssh_port = 22

        # Sanitize SSH username and hostname (reject shell metacharacters)
        ssh_username = re.sub(r'[^a-zA-Z0-9._@-]', '', str(remote_host.get('username', '')))
        ssh_hostname = re.sub(r'[^a-zA-Z0-9._:-]', '', str(remote_host.get('hostname', '')))

        if not ssh_username or not ssh_hostname:
            raise ValueError("Invalid SSH username or hostname")

        ssh_cmd = [
            'ssh', '-o', 'BatchMode=yes',
            '-o', 'StrictHostKeyChecking=accept-new',
            '-p', str(ssh_port),
        ]
        ssh_key = remote_host.get('ssh_key_path', '')
        if ssh_key:
            expanded_key = os.path.expanduser(str(ssh_key))
            if os.path.isfile(expanded_key):
                ssh_cmd.extend(['-i', expanded_key])
            else:
                print(f"[SSH] Warning: key file not found: {expanded_key}, falling back to default keys")
        # Allocate PTY for interactive terminal sessions
        if not prompt:
            ssh_cmd.append('-t')
        ssh_cmd.append(f"{ssh_username}@{ssh_hostname}")
        ssh_cmd.append(remote_cmd)
        return ssh_cmd

    return cmd


# ============== Routes ==============

@app.route('/')
@login_required
def index():
    """Main dashboard"""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    auth_config = CONFIG.get('auth', {})
    if not auth_config.get('enabled', False):
        return redirect('/')

    if request.method == 'POST':
        # Rate limit: 10 attempts per IP per 5 minutes
        client_ip = request.remote_addr or '0.0.0.0'
        if not check_rate_limit('login', client_ip, max_attempts=10, window_seconds=300):
            if request.is_json:
                return jsonify({'success': False, 'error': 'Too many login attempts. Try again later.'}), 429
            return render_template('login.html', error='Too many login attempts. Try again later.'), 429

        data = request.json if request.is_json else request.form
        username = data.get('username', '')
        password = data.get('password', '')

        # Check multi-user list first
        users = CONFIG.get('users', [])
        authenticated = False
        user_role = 'admin'

        for u in users:
            if u['username'] == username and check_password_hash(u['password_hash'], password):
                authenticated = True
                user_role = u.get('role', 'user')
                break

        # Fallback to legacy single-user auth
        if not authenticated:
            if (username == auth_config.get('username', '') and
                    auth_config.get('password_hash') and
                    check_password_hash(auth_config['password_hash'], password)):
                authenticated = True
                user_role = 'admin'

        if authenticated:
            session['authenticated'] = True
            session['username'] = username
            session['role'] = user_role
            session['user_id'] = str(uuid.uuid4())
            if request.is_json:
                return jsonify({'success': True})
            return redirect('/')
        if request.is_json:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        return render_template('login.html', error='Invalid username or password')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    return redirect('/login')


@app.route('/api/auth/status')
def auth_status():
    """Public endpoint - check auth state"""
    auth_config = CONFIG.get('auth', {})
    return jsonify({
        'auth_enabled': auth_config.get('enabled', False),
        'needs_setup': not auth_config.get('password_hash', ''),
        'authenticated': session.get('authenticated', False),
    })


@app.route('/api/auth/setup', methods=['POST'])
def auth_setup():
    """First-run account setup"""
    # Rate limit: 5 attempts per IP per hour
    client_ip = request.remote_addr or '0.0.0.0'
    if not check_rate_limit('auth_setup', client_ip, max_attempts=5, window_seconds=3600):
        return jsonify({'error': 'Too many setup attempts. Try again later.'}), 429

    auth_config = CONFIG.get('auth', {})
    if auth_config.get('enabled') and auth_config.get('password_hash'):
        # Already set up - require auth to change
        if not session.get('authenticated'):
            return jsonify({'error': 'Already configured. Login first to change.'}), 403

    data = request.json
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400

    pw_hash = generate_password_hash(password)
    CONFIG['auth'] = {
        'enabled': True,
        'username': username,
        'password_hash': pw_hash,
    }

    # Also add/update in users list
    users = CONFIG.get('users', [])
    existing = next((u for u in users if u['username'] == username), None)
    if existing:
        existing['password_hash'] = pw_hash
        existing['role'] = 'admin'
    else:
        users.append({'username': username, 'password_hash': pw_hash, 'role': 'admin'})
    CONFIG['users'] = users
    save_config(CONFIG)

    # Auto-login after setup
    session['authenticated'] = True
    session['username'] = username
    session['role'] = 'admin'
    session['user_id'] = str(uuid.uuid4())

    return jsonify({'success': True})


@app.route('/api/projects')
@login_required
def api_projects():
    """Get list of projects"""
    root = request.args.get('root', CONFIG['projects_root'])

    # Enforce path restrictions unless full browsing is enabled
    if not CONFIG.get('allow_full_browsing', False):
        allowed = CONFIG.get('allowed_paths', ['/opt'])
        resolved = str(Path(root).resolve())
        if not any(resolved == a or resolved.startswith(a + '/') for a in allowed):
            # Default to first allowed path
            root = allowed[0] if allowed else '/opt'

    projects = get_projects(root)

    # Determine parent, restricting to allowed paths
    parent = None
    if root != '/':
        parent_path = str(Path(root).parent)
        if CONFIG.get('allow_full_browsing', False):
            parent = parent_path
        else:
            allowed = CONFIG.get('allowed_paths', ['/opt'])
            resolved_parent = str(Path(parent_path).resolve())
            if any(resolved_parent == a or resolved_parent.startswith(a + '/') or
                   a.startswith(resolved_parent + '/') or a == resolved_parent for a in allowed):
                parent = parent_path

    return jsonify({
        'projects': projects,
        'root': root,
        'parent': parent
    })


@app.route('/api/projects/root', methods=['POST'])
@login_required
def set_projects_root():
    """Set the projects root directory"""
    data = request.json or {}
    new_root = data.get('root')
    if new_root and Path(new_root).is_dir():
        # Enforce path restrictions
        if not CONFIG.get('allow_full_browsing', False):
            allowed = CONFIG.get('allowed_paths', ['/opt'])
            resolved = str(Path(new_root).resolve())
            if not any(resolved == a or resolved.startswith(a + '/') for a in allowed):
                return jsonify({'success': False, 'error': f'Path not allowed. Allowed: {", ".join(allowed)}'}), 403
        CONFIG['projects_root'] = new_root
        save_config(CONFIG)
        return jsonify({'success': True, 'root': new_root})
    return jsonify({'success': False, 'error': 'Invalid directory'}), 400


@app.route('/api/config', methods=['GET'])
@login_required
def api_get_config():
    """Get current configuration"""
    return jsonify({
        'projects_root': CONFIG.get('projects_root', ''),
        'process_timeout_minutes': CONFIG.get('process_timeout_minutes', 60),
        'max_concurrent_terminals': CONFIG.get('max_concurrent_terminals', 5),
        'max_concurrent_chats': CONFIG.get('max_concurrent_chats', 10),
        'favorites': CONFIG.get('favorites', []),
        'remote_hosts': CONFIG.get('remote_hosts', []),
        'chat_cwd': CONFIG.get('chat_cwd', '/opt/claude'),
        'ssl_enabled': CONFIG.get('ssl_enabled', False),
        'ssl_cert': CONFIG.get('ssl_cert', ''),
        'ssl_key': CONFIG.get('ssl_key', ''),
        'allowed_paths': CONFIG.get('allowed_paths', ['/opt']),
        'allow_full_browsing': CONFIG.get('allow_full_browsing', False),
        'theme': CONFIG.get('theme', 'dark'),
        'active_agents': CONFIG.get('active_agents', []),
        'custom_agents': CONFIG.get('custom_agents', []),
    })


@app.route('/api/config', methods=['POST'])
@login_required
def api_update_config():
    """Update configuration and persist"""
    data = request.json or {}
    allowed_keys = [
        'projects_root', 'process_timeout_minutes',
        'max_concurrent_terminals', 'max_concurrent_chats',
        'default_flags', 'favorites', 'remote_hosts',
        'ssl_enabled', 'ssl_cert', 'ssl_key', 'chat_cwd',
        'allowed_paths', 'allow_full_browsing', 'theme',
        'active_agents', 'custom_agents'
    ]
    # Validate agent config before saving
    if 'active_agents' in data:
        valid_ids = set(AGENT_LIBRARY.keys()) - {'sentinel'}
        agents = [a for a in data.get('active_agents', []) if a in valid_ids]
        data['active_agents'] = agents[:5]  # Max 5
    if 'custom_agents' in data:
        customs = data.get('custom_agents', [])
        if not isinstance(customs, list):
            customs = []
        customs = customs[:2]  # Max 2
        for c in customs:
            if isinstance(c, dict):
                c['content'] = str(c.get('content', ''))[:10000]
                c['name'] = str(c.get('name', 'Custom Agent'))[:50]
        data['custom_agents'] = [c for c in customs if isinstance(c, dict)]
    for key in allowed_keys:
        if key in data:
            CONFIG[key] = data[key]
    if 'projects_root' in data:
        new_root = os.path.expanduser(data['projects_root'])
        if os.path.isdir(new_root):
            CONFIG['projects_root'] = new_root
        else:
            return jsonify({'success': False, 'error': f'Invalid directory: {data["projects_root"]}'}), 400
    save_config(CONFIG)
    return jsonify({'success': True})


@app.route('/api/agents/library')
@login_required
def api_agents_library():
    """Return agent library metadata (without full content)"""
    library = []
    for agent_id, agent in AGENT_LIBRARY.items():
        library.append({
            'id': agent['id'],
            'name': agent['name'],
            'description': agent['description'],
            'category': agent['category'],
            'icon': agent['icon'],
            'locked': agent.get('locked', False),
        })
    return jsonify({'agents': library})


@app.route('/api/remote/test', methods=['POST'])
@login_required
def api_test_remote():
    """Test connectivity to a remote host"""
    data = request.json or {}
    mode = data.get('mode', 'ssh')

    if mode == 'mount':
        mount_path = os.path.expanduser(data.get('mount_path', ''))
        if not mount_path:
            return jsonify({'success': False, 'error': 'Mount path required'}), 400
        if os.path.isdir(mount_path):
            try:
                contents = os.listdir(mount_path)
                return jsonify({
                    'success': True,
                    'message': f'Path accessible ({len(contents)} items)'
                })
            except PermissionError:
                return jsonify({'success': False, 'error': 'Permission denied'}), 403
        return jsonify({'success': False, 'error': 'Path does not exist'}), 400

    elif mode == 'ssh':
        hostname = data.get('hostname', '')
        username = data.get('username', '')
        ssh_key_path = data.get('ssh_key_path', '')

        # Validate port as integer
        try:
            port = int(data.get('port', 22))
            if not (1 <= port <= 65535):
                port = 22
        except (ValueError, TypeError):
            port = 22

        if not hostname or not username:
            return jsonify({'success': False, 'error': 'Hostname and username required'}), 400
        if ssh_key_path and not os.path.isfile(os.path.expanduser(ssh_key_path)):
            return jsonify({'success': False, 'error': f'SSH key not found: {ssh_key_path}'}), 400

        cmd = [
            'ssh', '-o', 'ConnectTimeout=5', '-o', 'BatchMode=yes',
            '-o', 'StrictHostKeyChecking=accept-new',
            '-p', str(port),
        ]
        if ssh_key_path:
            cmd.extend(['-i', os.path.expanduser(ssh_key_path)])
        cmd.extend([f'{username}@{hostname}', 'echo', 'CONNECTION_OK'])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and 'CONNECTION_OK' in result.stdout:
                cmd_claude = cmd[:-2] + ['which', 'claude']
                result_claude = subprocess.run(cmd_claude, capture_output=True, text=True, timeout=10)
                claude_available = result_claude.returncode == 0
                return jsonify({
                    'success': True,
                    'message': 'Connection successful',
                    'claude_available': claude_available,
                    'claude_path': result_claude.stdout.strip() if claude_available else None
                })
            return jsonify({'success': False, 'error': f'SSH failed: {result.stderr.strip()}'})
        except subprocess.TimeoutExpired:
            return jsonify({'success': False, 'error': 'Connection timed out'}), 408
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': False, 'error': 'Invalid mode'}), 400


@app.route('/api/remote/ssh-config')
@login_required
def api_ssh_config():
    """Parse ~/.ssh/config and return list of discovered hosts"""
    ssh_config_path = Path.home() / '.ssh' / 'config'
    if not ssh_config_path.exists():
        return jsonify({'hosts': [], 'message': 'No ~/.ssh/config found'})

    hosts = []
    current_host = None

    try:
        with open(ssh_config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue

                key = parts[0].lower()
                value = parts[1].strip()

                if key == 'host':
                    if '*' in value or '?' in value:
                        current_host = None
                        continue
                    current_host = {
                        'alias': value,
                        'hostname': value,
                        'port': 22,
                        'username': '',
                        'identity_file': '',
                    }
                    hosts.append(current_host)
                elif key == 'match':
                    current_host = None
                elif current_host:
                    if key == 'hostname':
                        current_host['hostname'] = value
                    elif key == 'port':
                        try:
                            current_host['port'] = int(value)
                        except ValueError:
                            pass
                    elif key == 'user':
                        current_host['username'] = value
                    elif key == 'identityfile':
                        current_host['identity_file'] = os.path.expanduser(value)

        hosts = [h for h in hosts if h.get('hostname')]

        existing = set()
        for rh in CONFIG.get('remote_hosts', []):
            if rh.get('mode') == 'ssh':
                existing.add(f"{rh.get('username', '')}@{rh.get('hostname', '')}:{rh.get('port', 22)}")

        for h in hosts:
            h['already_imported'] = f"{h.get('username', '')}@{h['hostname']}:{h.get('port', 22)}" in existing

    except Exception as e:
        return jsonify({'hosts': [], 'error': str(e)})

    return jsonify({'hosts': hosts})


@app.route('/api/remote/ssh-setup', methods=['GET', 'POST'])
@login_required
def api_ssh_setup():
    """GET: Return SSH public key info. POST: Generate new SSH key."""
    if request.method == 'POST':
        ssh_dir = Path.home() / '.ssh'
        key_path = ssh_dir / 'id_ed25519'

        if key_path.exists():
            pub_key = key_path.with_suffix('.pub').read_text().strip()
            return jsonify({
                'success': True,
                'already_existed': True,
                'public_key': pub_key,
                'key_path': str(key_path),
                'message': 'SSH key already exists'
            })

        try:
            ssh_dir.mkdir(mode=0o700, exist_ok=True)
            result = subprocess.run(
                ['ssh-keygen', '-t', 'ed25519', '-N', '', '-f', str(key_path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                pub_key = key_path.with_suffix('.pub').read_text().strip()
                return jsonify({
                    'success': True,
                    'already_existed': False,
                    'public_key': pub_key,
                    'key_path': str(key_path),
                    'message': 'SSH key generated successfully'
                })
            return jsonify({'success': False, 'error': result.stderr.strip()})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    # GET - return existing key info
    ssh_dir = Path.home() / '.ssh'
    pub_key = None
    key_path = None

    for key_name in ['id_ed25519.pub', 'id_rsa.pub', 'id_ecdsa.pub']:
        candidate = ssh_dir / key_name
        if candidate.exists():
            pub_key = candidate.read_text().strip()
            key_path = str(candidate.with_suffix(''))
            break

    if not pub_key:
        return jsonify({
            'has_key': False,
            'message': 'No SSH key found.',
            'generate_command': 'ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519'
        })

    import socket
    local_hostname = socket.gethostname()
    local_user = os.environ.get('USER', 'unknown')

    return jsonify({
        'has_key': True,
        'public_key': pub_key,
        'key_path': key_path,
        'local_user': local_user,
        'local_hostname': local_hostname,
    })


@app.route('/api/remote/push-key', methods=['POST'])
@login_required
def api_push_key():
    """Push SSH key to a remote host using ssh-copy-id or manual append"""
    data = request.json or {}
    hostname = data.get('hostname', '')
    username = data.get('username', '')
    password = data.get('password', '')

    # Validate port
    try:
        port = int(data.get('port', 22))
        if not (1 <= port <= 65535):
            port = 22
    except (ValueError, TypeError):
        port = 22

    if not hostname or not username:
        return jsonify({'success': False, 'error': 'Hostname and username required'}), 400

    # Find public key
    ssh_dir = Path.home() / '.ssh'
    pub_key_file = None
    for key_name in ['id_ed25519.pub', 'id_rsa.pub', 'id_ecdsa.pub']:
        candidate = ssh_dir / key_name
        if candidate.exists():
            pub_key_file = str(candidate)
            break

    if not pub_key_file:
        return jsonify({'success': False, 'error': 'No SSH public key found on this server'}), 400

    pub_key = Path(pub_key_file).read_text().strip()

    # Use sshpass + ssh to push the key if password provided
    if password:
        remote_cmd = (
            f'mkdir -p ~/.ssh && chmod 700 ~/.ssh && '
            f'echo {shlex.quote(pub_key)} >> ~/.ssh/authorized_keys && '
            f'chmod 600 ~/.ssh/authorized_keys && '
            f'echo KEY_INSTALLED'
        )
        cmd = [
            'sshpass', '-p', password,
            'ssh', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'ConnectTimeout=10',
            '-p', str(port),
            f'{username}@{hostname}',
            remote_cmd
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if 'KEY_INSTALLED' in result.stdout:
                return jsonify({'success': True, 'message': 'SSH key installed successfully'})
            return jsonify({
                'success': False,
                'error': result.stderr.strip() or 'Key installation failed. Is sshpass installed?'
            })
        except FileNotFoundError:
            return jsonify({
                'success': False,
                'error': 'sshpass not installed. Install with: sudo apt install sshpass'
            })
        except subprocess.TimeoutExpired:
            return jsonify({'success': False, 'error': 'Connection timed out'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    else:
        # No password - return the manual command
        return jsonify({
            'success': False,
            'manual_required': True,
            'command': f'echo {shlex.quote(pub_key)} | ssh -p {port} {username}@{hostname} "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"',
            'error': 'Password required for automated key push, or use the manual command'
        })


@app.route('/api/remote/<host_id>/projects')
@login_required
def api_remote_projects(host_id):
    """List projects on a remote host"""
    remote_host = next(
        (h for h in CONFIG.get('remote_hosts', []) if h['id'] == host_id), None
    )
    if not remote_host:
        return jsonify({'error': 'Remote host not found'}), 404

    if remote_host['mode'] == 'mount':
        root = remote_host.get('mount_path', '')
        projects = get_projects(root)
        return jsonify({'projects': projects, 'root': root, 'mode': 'mount', 'host_id': host_id})

    elif remote_host['mode'] == 'ssh':
        remote_path = remote_host.get('default_path', '~')
        # Sanitize remote path to prevent command injection in the Python string
        safe_remote_path = remote_path.replace("'", "").replace('"', '').replace('\\', '')
        # Validate SSH port
        try:
            ssh_port = int(remote_host.get('port', 22))
            if not (1 <= ssh_port <= 65535):
                ssh_port = 22
        except (ValueError, TypeError):
            ssh_port = 22
        ssh_cmd = [
            'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
            '-p', str(ssh_port),
        ]
        if remote_host.get('ssh_key_path'):
            key_path = os.path.expanduser(remote_host['ssh_key_path'])
            if os.path.isfile(key_path):
                ssh_cmd.extend(['-i', key_path])
            else:
                print(f"[SSH] Warning: key file not found: {key_path}")
        ssh_cmd.append(f"{remote_host['username']}@{remote_host['hostname']}")
        remote_script = f'''python3 -c "
import os, json
root = os.path.expanduser('{safe_remote_path}')
result = []
for item in sorted(os.listdir(root)):
    full = os.path.join(root, item)
    if os.path.isdir(full) and not item.startswith('.'):
        result.append(dict(
            name=item, path=full,
            is_git=os.path.isdir(os.path.join(full, '.git')),
            is_claude=os.path.isdir(os.path.join(full, '.claude')),
            type='git' if os.path.isdir(os.path.join(full, '.git')) else 'folder',
            indicators=dict(
                git=os.path.isdir(os.path.join(full, '.git')),
                claude=os.path.isdir(os.path.join(full, '.claude')),
                node=os.path.isfile(os.path.join(full, 'package.json')),
                python=os.path.isfile(os.path.join(full, 'pyproject.toml')),
                rust=os.path.isfile(os.path.join(full, 'Cargo.toml')),
            )
        ))
print(json.dumps(result))
"'''
        ssh_cmd.append(remote_script)
        try:
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                projects = json.loads(result.stdout)
                return jsonify({'projects': projects, 'root': remote_path, 'mode': 'ssh', 'host_id': host_id})
            return jsonify({'error': f'SSH error: {result.stderr.strip()}'}), 500
        except subprocess.TimeoutExpired:
            return jsonify({'error': 'Timed out listing remote projects'}), 408
        except json.JSONDecodeError:
            return jsonify({'error': 'Failed to parse remote directory listing'}), 500

    return jsonify({'error': 'Invalid remote host mode'}), 400


@app.route('/api/session/persistent')
@login_required
def get_persistent_session():
    """Get or create the single persistent chat session"""
    session_id = CONFIG.get('persistent_session_id', '')
    chat_cwd = CONFIG.get('chat_cwd', '/opt/claude')

    # Try to load existing persistent session
    if session_id and session_id in chat_sessions:
        return jsonify(chat_sessions[session_id])

    if session_id:
        load_session(session_id)
        if session_id in chat_sessions:
            return jsonify(chat_sessions[session_id])

    # Create new persistent session
    session_id = str(uuid.uuid4())
    chat_sessions[session_id] = {
        'id': session_id,
        'project': chat_cwd,
        'project_name': 'Claude',
        'flags': {},
        'remote_host_id': None,
        'messages': [],
        'created': datetime.now().isoformat(),
        'status': 'ready'
    }
    CONFIG['persistent_session_id'] = session_id
    save_config(CONFIG)
    save_session(session_id)

    return jsonify(chat_sessions[session_id])


@app.route('/api/session/new', methods=['POST'])
@login_required
def new_chat_session():
    """Create a new chat session"""
    data = request.json or {}
    session_id = str(uuid.uuid4())

    chat_sessions[session_id] = {
        'id': session_id,
        'project': data.get('project', ''),
        'project_name': Path(data.get('project', '')).name,
        'flags': data.get('flags', {}),
        'remote_host_id': data.get('remote_host_id'),
        'messages': [],
        'created': datetime.now().isoformat(),
        'status': 'ready'
    }

    # Save to disk
    save_session(session_id)

    return jsonify(chat_sessions[session_id])


@app.route('/api/session/<session_id>')
@login_required
def get_session(session_id):
    """Get session details"""
    if session_id not in chat_sessions:
        load_session(session_id)

    if session_id in chat_sessions:
        return jsonify(chat_sessions[session_id])
    return jsonify({'error': 'Session not found'}), 404


@app.route('/api/sessions')
@login_required
def list_sessions():
    """List all saved sessions"""
    sessions = []
    sessions_dir = CONFIG['sessions_dir']

    if sessions_dir.exists():
        for f in sessions_dir.glob('*.json'):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    sessions.append({
                        'id': data['id'],
                        'project_name': data.get('project_name', 'Unknown'),
                        'created': data.get('created', ''),
                        'message_count': len(data.get('messages', []))
                    })
            except (json.JSONDecodeError, OSError, KeyError):
                pass

    sessions.sort(key=lambda s: s.get('created', ''), reverse=True)
    return jsonify({'sessions': sessions})


def save_session(session_id):
    """Save session to disk (snapshot under lock, write outside lock)"""
    with chat_sessions_lock:
        if session_id not in chat_sessions:
            return
        session_copy = json.loads(json.dumps(chat_sessions[session_id]))
    sessions_dir = CONFIG['sessions_dir']
    sessions_dir.mkdir(exist_ok=True)
    with open(sessions_dir / f'{session_id}.json', 'w') as f:
        json.dump(session_copy, f, indent=2)


def load_session(session_id):
    """Load session from disk"""
    session_file = CONFIG['sessions_dir'] / f'{session_id}.json'
    if session_file.exists():
        with open(session_file) as f:
            data = json.load(f)
        with chat_sessions_lock:
            chat_sessions[session_id] = data


# ============== WebSocket Handlers ==============

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    auth_config = CONFIG.get('auth', {})
    if auth_config.get('enabled', False) and not session.get('authenticated'):
        return False  # Reject unauthenticated SocketIO connections
    emit('connected', {'status': 'ok'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection - clean up orphaned terminals"""
    sid = request.sid
    # Kill terminals owned by this WebSocket session
    for tid, term in list(active_terminals.items()):
        if term.get('ws_sid') == sid:
            try:
                os.kill(term['pid'], signal.SIGTERM)
            except OSError:
                pass
            active_terminals.pop(tid, None)


@socketio.on('terminal_create')
def handle_terminal_create(data):
    """Create a new terminal session with Claude Code"""
    # Check concurrent terminal limit
    if len(active_terminals) >= CONFIG['max_concurrent_terminals']:
        emit('terminal_error', {'error': 'Too many concurrent terminals. Please close one first.'})
        return

    project_path = data.get('project', os.path.expanduser('~'))
    flags = data.get('flags', {})
    remote_host_id = data.get('remote_host_id')
    terminal_id = str(uuid.uuid4())

    # Validate path for local terminals (remote paths are validated on the remote host)
    if not remote_host_id and not validate_file_path(project_path):
        emit('terminal_error', {'error': 'Path not allowed'})
        return

    # Resolve remote host
    remote_host = None
    if remote_host_id:
        remote_host = next(
            (h for h in CONFIG.get('remote_hosts', []) if h['id'] == remote_host_id), None
        )

    # Deploy agents if agent teams enabled (local only)
    if flags.get('agent_teams') and not remote_host_id:
        try:
            active_agents = CONFIG.get('active_agents', [])
            custom_agents = CONFIG.get('custom_agents', [])
            deployed = deploy_agents(project_path, active_agents, custom_agents)
            print(f"[Agents] Deployed {len(deployed)} agents to {project_path}")
        except Exception as e:
            print(f"[Agents] Deploy failed: {e}")

    # Build command and environment (SSH-wrapped if remote)
    cmd = build_claude_command(project_path, flags, remote_host=remote_host)
    claude_env = build_claude_env(flags)

    # For SSH mode, don't chdir locally. For local/mount, chdir to project path
    use_local_chdir = not (remote_host and remote_host.get('mode') == 'ssh')

    # Create PTY
    pid, fd = pty.fork()

    if pid == 0:
        # Child process — set env vars before exec (safe: child has its own address space)
        try:
            for key, value in claude_env.items():
                os.environ[key] = value
            if use_local_chdir:
                os.chdir(project_path)
            os.execvp(cmd[0], cmd)
        except Exception as e:
            # execvp failed - write error to stderr so parent can read it from the PTY
            os.write(2, f"Failed to start: {e}\n".encode())
            os._exit(127)
    else:
        # Parent process
        active_terminals[terminal_id] = {
            'pid': pid,
            'fd': fd,
            'project': project_path,
            'flags': flags,
            'remote_host_id': remote_host_id,
            'started': datetime.now(),
            'ws_sid': request.sid
        }

        # Start reader thread
        def read_terminal():
            while terminal_id in active_terminals:
                try:
                    r, _, _ = select.select([fd], [], [], 0.1)
                    if r:
                        output = os.read(fd, 4096)
                        if output:
                            socketio.emit('terminal_output', {
                                'id': terminal_id,
                                'data': output.decode('utf-8', errors='replace')
                            })
                        else:
                            break
                except (OSError, IOError):
                    break

            # Terminal closed
            if terminal_id in active_terminals:
                del active_terminals[terminal_id]
            socketio.emit('terminal_closed', {'id': terminal_id})

        thread = threading.Thread(target=read_terminal, daemon=True)
        thread.start()
        active_terminals[terminal_id]['thread'] = thread

        emit('terminal_created', {'id': terminal_id, 'project': project_path})


@socketio.on('terminal_input')
def handle_terminal_input(data):
    """Send input to terminal"""
    terminal_id = data.get('id')
    input_data = data.get('data', '')

    if terminal_id in active_terminals:
        fd = active_terminals[terminal_id]['fd']
        try:
            os.write(fd, input_data.encode())
        except (OSError, IOError):
            pass


@socketio.on('terminal_resize')
def handle_terminal_resize(data):
    """Resize terminal"""
    terminal_id = data.get('id')
    cols = data.get('cols', 80)
    rows = data.get('rows', 24)

    if terminal_id in active_terminals:
        fd = active_terminals[terminal_id]['fd']
        try:
            import fcntl
            import struct
            import termios
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        except (OSError, ValueError):
            pass


@socketio.on('terminal_kill')
def handle_terminal_kill(data):
    """Kill terminal session"""
    terminal_id = data.get('id')

    if terminal_id in active_terminals:
        pid = active_terminals[terminal_id]['pid']
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        del active_terminals[terminal_id]
        emit('terminal_closed', {'id': terminal_id})


@socketio.on('chat_message')
def handle_chat_message(data):
    """Handle chat message - run claude with prompt"""
    session_id = data.get('session_id')
    message = data.get('message', '')

    # Limit message size to 1MB to prevent disk abuse
    if len(message) > 1_000_000:
        emit('chat_error', {'session_id': session_id, 'error': 'Message too large (max 1MB)'})
        return

    if session_id not in chat_sessions:
        load_session(session_id)

    if session_id not in chat_sessions:
        emit('chat_error', {'error': 'Session not found'})
        return

    sess = chat_sessions[session_id]

    # Add user message
    sess['messages'].append({
        'role': 'user',
        'content': message,
        'timestamp': datetime.now().isoformat()
    })
    sess['status'] = 'running'
    save_session(session_id)

    # Check concurrent chat limit
    if len(active_chat_processes) >= CONFIG['max_concurrent_chats']:
        emit('chat_error', {'session_id': session_id, 'error': 'Too many concurrent chats. Please wait.'})
        return

    emit('chat_status', {'session_id': session_id, 'status': 'running'})

    # Resolve remote host if any
    remote_host = None
    if sess.get('remote_host_id'):
        remote_host = next(
            (h for h in CONFIG.get('remote_hosts', []) if h['id'] == sess['remote_host_id']), None
        )

    # Build command and environment (SSH-wrapped if remote)
    cmd = build_claude_command(sess['project'], sess['flags'], message, remote_host=remote_host)
    claude_env = build_claude_env(sess['flags'])

    # For SSH mode, cwd is irrelevant (cd happens on remote)
    use_cwd = sess['project'] if not (remote_host and remote_host.get('mode') == 'ssh') else None

    def run_claude():
        process = None
        try:
            process = subprocess.Popen(
                cmd,
                cwd=use_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=claude_env
            )

            # Track the process for watchdog
            active_chat_processes[session_id] = {
                'process': process,
                'started': datetime.now()
            }

            response_text = []
            for line in iter(process.stdout.readline, ''):
                response_text.append(line)
                socketio.emit('chat_stream', {
                    'session_id': session_id,
                    'chunk': line
                })

                # Parse token usage from Claude CLI output
                usage_match = re.search(r'(\d[\d,]*)\s*input.*?(\d[\d,]*)\s*output', line, re.IGNORECASE)
                if not usage_match:
                    usage_match = re.search(r'input[:\s]*(\d[\d,]*).*output[:\s]*(\d[\d,]*)', line, re.IGNORECASE)
                if usage_match:
                    input_tokens = int(usage_match.group(1).replace(',', ''))
                    output_tokens = int(usage_match.group(2).replace(',', ''))
                    # Update global usage
                    try:
                        usage = load_usage()
                        week_key = get_week_key()
                        if week_key not in usage.get('weekly', {}):
                            usage.setdefault('weekly', {})[week_key] = {'input_tokens': 0, 'output_tokens': 0}
                        usage['weekly'][week_key]['input_tokens'] += input_tokens
                        usage['weekly'][week_key]['output_tokens'] += output_tokens
                        usage['total']['input_tokens'] += input_tokens
                        usage['total']['output_tokens'] += output_tokens
                        save_usage(usage)
                        socketio.emit('usage_update', {
                            'session_id': session_id,
                            'input_tokens': input_tokens,
                            'output_tokens': output_tokens
                        })
                    except Exception as ue:
                        print(f"[Usage] Parse error: {ue}")

            process.wait()

            # Add assistant message
            full_response = ''.join(response_text)
            sess['messages'].append({
                'role': 'assistant',
                'content': full_response,
                'timestamp': datetime.now().isoformat()
            })
            sess['status'] = 'ready'
            save_session(session_id)

            socketio.emit('chat_complete', {
                'session_id': session_id
            })

        except Exception as e:
            sess['status'] = 'error'
            save_session(session_id)
            socketio.emit('chat_error', {
                'session_id': session_id,
                'error': str(e)
            })
        finally:
            # Remove from tracking
            active_chat_processes.pop(session_id, None)

    thread = threading.Thread(target=run_claude, daemon=True)
    thread.start()


# ============== Export API ==============

@app.route('/api/session/<session_id>/export')
@login_required
def export_session(session_id):
    """Export a chat session as markdown"""
    if session_id not in chat_sessions:
        load_session(session_id)

    if session_id not in chat_sessions:
        return jsonify({'error': 'Session not found'}), 404

    sess = chat_sessions[session_id]
    lines = [
        f"# Chat Session - {sess.get('project_name', 'Claude')}",
        f"",
        f"**Project:** {sess.get('project', 'N/A')}",
        f"**Created:** {sess.get('created', 'N/A')}",
        f"**Messages:** {len(sess.get('messages', []))}",
        f"",
        f"---",
        f"",
    ]

    for msg in sess.get('messages', []):
        role = msg.get('role', 'unknown').capitalize()
        timestamp = msg.get('timestamp', '')
        content = msg.get('content', '')
        lines.append(f"### {role}")
        if timestamp:
            lines.append(f"*{timestamp}*")
        lines.append(f"")
        lines.append(content)
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

    md_content = '\n'.join(lines)
    return app.response_class(
        md_content,
        mimetype='text/markdown',
        headers={'Content-Disposition': f'attachment; filename=chat-{session_id[:8]}.md'}
    )


# ============== Session Search API ==============

@app.route('/api/sessions/search')
@login_required
def search_sessions():
    """Search through session messages"""
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify({'results': []})

    results = []
    sessions_dir = CONFIG['sessions_dir']

    if not sessions_dir.exists():
        return jsonify({'results': []})

    for f in sessions_dir.glob('*.json'):
        try:
            with open(f) as fp:
                data = json.load(fp)

            for msg in data.get('messages', []):
                content = msg.get('content', '')
                if query in content.lower():
                    # Find context snippet
                    idx = content.lower().index(query)
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(query) + 50)
                    snippet = ('...' if start > 0 else '') + content[start:end] + ('...' if end < len(content) else '')

                    results.append({
                        'session_id': data['id'],
                        'project_name': data.get('project_name', 'Unknown'),
                        'role': msg.get('role', 'unknown'),
                        'snippet': snippet,
                        'created': data.get('created', ''),
                        'message_count': len(data.get('messages', []))
                    })
                    break  # One match per session is enough
        except Exception:
            pass

        if len(results) >= 20:
            break

    results.sort(key=lambda r: r.get('created', ''), reverse=True)
    return jsonify({'results': results})


# ============== Git Integration API ==============

@app.route('/api/git/status')
@login_required
def api_git_status():
    """Get git status for a project path"""
    path = request.args.get('path', '')
    if not path or '\x00' in path or not Path(path).is_dir():
        return jsonify({'error': 'Invalid path'}), 400

    # Validate path is within allowed directories
    if not validate_file_path(path):
        return jsonify({'error': 'Path not allowed'}), 403

    git_dir = Path(path) / '.git'
    if not git_dir.exists():
        return jsonify({'is_git': False})

    result_data = {'is_git': True}

    try:
        # Current branch
        branch_result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=path, capture_output=True, text=True, timeout=5
        )
        result_data['branch'] = branch_result.stdout.strip() if branch_result.returncode == 0 else 'unknown'

        # Status (modified/untracked count)
        status_result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=path, capture_output=True, text=True, timeout=5
        )
        if status_result.returncode == 0:
            status_lines = [l for l in status_result.stdout.strip().split('\n') if l]
            result_data['modified_count'] = len(status_lines)
            result_data['dirty'] = len(status_lines) > 0
        else:
            result_data['modified_count'] = 0
            result_data['dirty'] = False

        # Recent commits
        log_result = subprocess.run(
            ['git', 'log', '--oneline', '-5'],
            cwd=path, capture_output=True, text=True, timeout=5
        )
        if log_result.returncode == 0:
            result_data['recent_commits'] = [
                line.strip() for line in log_result.stdout.strip().split('\n') if line.strip()
            ]
        else:
            result_data['recent_commits'] = []

        # Branch list
        branches_result = subprocess.run(
            ['git', 'branch', '--no-color'],
            cwd=path, capture_output=True, text=True, timeout=5
        )
        if branches_result.returncode == 0:
            result_data['branches'] = [
                b.strip().lstrip('* ') for b in branches_result.stdout.strip().split('\n') if b.strip()
            ]
        else:
            result_data['branches'] = []

    except subprocess.TimeoutExpired:
        result_data['error'] = 'Git command timed out'
    except Exception as e:
        app.logger.error('Git status error: %s', e)
        result_data['error'] = 'Git status failed'

    return jsonify(result_data)


@app.route('/api/git/diff')
@login_required
def api_git_diff():
    """Get git diff for a project path, optionally filtered to a single file"""
    path = request.args.get('path', '')
    file_filter = request.args.get('file', '')
    staged = request.args.get('staged', '') == 'true'

    if not path or '\x00' in path or not Path(path).is_dir():
        return jsonify({'error': 'Invalid path'}), 400
    if not validate_file_path(path):
        return jsonify({'error': 'Path not allowed'}), 403

    # Re-resolve after validation to close TOCTOU symlink swap window
    try:
        path = str(Path(path).resolve())
    except (OSError, ValueError):
        return jsonify({'error': 'Invalid path'}), 400

    # Walk up to find git root (allows diff from subdirectories)
    git_root = None
    check = Path(path)
    for _ in range(50):  # depth limit
        if (check / '.git').exists():
            git_root = str(check)
            break
        parent = check.parent
        if parent == check:
            break
        check = parent
    if not git_root:
        return jsonify({'error': 'Not a git repository'}), 400
    if not validate_file_path(git_root):
        return jsonify({'error': 'Path not allowed'}), 403

    try:
        cmd = ['git', 'diff']
        if staged:
            cmd.append('--cached')
        cmd.append('--unified=3')
        if file_filter:
            # Validate file filter: no null bytes, path traversal, absolute paths, or shell metacharacters
            if '\x00' in file_filter or '..' in file_filter or file_filter.startswith('/'):
                return jsonify({'error': 'Invalid file path'}), 400
            if any(c in file_filter for c in ';&|`$\n\r'):
                return jsonify({'error': 'Invalid file path'}), 400
            cmd.extend(['--', file_filter])

        result = subprocess.run(
            cmd, cwd=git_root, capture_output=True, encoding='utf-8', errors='replace', timeout=10
        )
        if result.returncode != 0:
            app.logger.warning('Git diff failed: %s', result.stderr[:500])
            return jsonify({'error': 'Git diff failed'}), 500

        # Parse unified diff into structured data
        diffs = []
        current_file = None
        current_hunks = []
        current_hunk = None
        files_changed = 0
        insertions = 0
        deletions = 0

        current_binary = False

        for line in result.stdout.split('\n'):
            if line.startswith('diff --git'):
                if current_file:
                    entry = {'file': current_file, 'hunks': current_hunks}
                    if current_binary:
                        entry['binary'] = True
                    diffs.append(entry)
                parts = line.split(' b/')
                current_file = parts[-1] if len(parts) > 1 else line
                current_hunks = []
                current_hunk = None
                current_binary = False
                files_changed += 1
            elif line.startswith('Binary files'):
                current_binary = True
            elif line.startswith('@@'):
                current_hunk = {'header': line, 'lines': []}
                current_hunks.append(current_hunk)
            elif current_hunk is not None:
                if line.startswith('+'):
                    current_hunk['lines'].append({'type': 'add', 'content': line[1:]})
                    insertions += 1
                elif line.startswith('-'):
                    current_hunk['lines'].append({'type': 'remove', 'content': line[1:]})
                    deletions += 1
                else:
                    current_hunk['lines'].append({'type': 'context', 'content': line[1:] if line.startswith(' ') else line})

        if current_file:
            entry = {'file': current_file, 'hunks': current_hunks}
            if current_binary:
                entry['binary'] = True
            diffs.append(entry)

        return jsonify({
            'diffs': diffs[:100],  # Cap at 100 files to prevent memory exhaustion
            'stats': {'files_changed': files_changed, 'insertions': insertions, 'deletions': deletions}
        })

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Git diff timed out'}), 500
    except Exception as e:
        app.logger.error('Git diff error: %s', e)
        return jsonify({'error': 'Git diff failed'}), 500



# ============== File Browser API ==============

def validate_file_path(path_str):
    """Validate that a path is within allowed directories.
    Checks for null bytes, resolves symlinks, and validates against allowed paths.
    Also blocks access to the application's own directory (config, source, sessions)."""
    if not path_str or not isinstance(path_str, str):
        return False
    # Reject null bytes (can bypass path checks in some C-level APIs)
    if '\x00' in path_str:
        return False
    # Resolve to real path (follows symlinks) to prevent symlink-based traversal
    try:
        resolved = str(Path(path_str).resolve())
    except (OSError, ValueError):
        return False
    # Block access to the application's own directory (contains secrets, source, sessions)
    app_dir = str(Path(__file__).resolve().parent)
    if resolved == app_dir or resolved.startswith(app_dir + '/'):
        return False
    if CONFIG.get('allow_full_browsing', False):
        return True
    allowed = CONFIG.get('allowed_paths', ['/opt'])
    return any(resolved == a or resolved.startswith(a + '/') for a in allowed)


@app.route('/api/files')
@login_required
def api_list_files():
    """List files in a directory"""
    path = request.args.get('path', '')
    if not path:
        return jsonify({'error': 'Path required'}), 400
    if '\x00' in path:
        return jsonify({'error': 'Invalid path'}), 400

    path = os.path.expanduser(path)

    if not validate_file_path(path):
        return jsonify({'error': 'Path not allowed'}), 403

    # Re-resolve after validation to close TOCTOU symlink swap window
    try:
        resolved = str(Path(path).resolve())
    except (OSError, ValueError):
        return jsonify({'error': 'Invalid path'}), 400

    if not os.path.isdir(resolved):
        return jsonify({'error': 'Not a directory'}), 400

    items = []
    try:
        for entry in sorted(os.scandir(resolved), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith('.') and entry.name not in ('.gitignore', '.env.example'):
                continue
            try:
                stat = entry.stat()
                items.append({
                    'name': entry.name,
                    'path': entry.path,
                    'is_dir': entry.is_dir(),
                    'size': stat.st_size if not entry.is_dir() else None,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except (PermissionError, OSError):
                pass
    except PermissionError:
        return jsonify({'error': 'Permission denied'}), 403

    parent = str(Path(path).parent) if path != '/' else None
    if parent and not validate_file_path(parent):
        parent = None

    return jsonify({'items': items, 'path': path, 'parent': parent})


@app.route('/api/files/read')
@login_required
def api_read_file():
    """Read a file's content"""
    path = request.args.get('path', '')
    if not path:
        return jsonify({'error': 'Path required'}), 400
    if '\x00' in path:
        return jsonify({'error': 'Invalid path'}), 400

    path = os.path.expanduser(path)

    if not validate_file_path(path):
        return jsonify({'error': 'Path not allowed'}), 403

    # Re-resolve after validation to close TOCTOU symlink swap window
    try:
        resolved = str(Path(path).resolve())
    except (OSError, ValueError):
        return jsonify({'error': 'Invalid path'}), 400

    if not os.path.isfile(resolved):
        return jsonify({'error': 'Not a file'}), 400

    # Size limit: 500KB
    size = os.path.getsize(resolved)
    if size > 512000:
        return jsonify({'error': f'File too large ({size} bytes, max 500KB)', 'size': size}), 400

    # Detect binary
    try:
        with open(resolved, 'rb') as f:
            chunk = f.read(1024)
            if b'\x00' in chunk:
                return jsonify({'error': 'Binary file', 'binary': True, 'size': size}), 400
    except OSError:
        return jsonify({'error': 'Failed to read file'}), 500

    try:
        with open(resolved, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # Determine language for syntax highlighting
        ext = Path(path).suffix.lower()
        lang_map = {
            '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
            '.html': 'xml', '.htm': 'xml', '.xml': 'xml', '.svg': 'xml',
            '.css': 'css', '.json': 'json', '.md': 'markdown',
            '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash',
            '.rs': 'rust', '.go': 'go', '.java': 'java',
            '.c': 'c', '.cpp': 'cpp', '.h': 'c',
            '.rb': 'ruby', '.yml': 'yaml', '.yaml': 'yaml',
            '.toml': 'ini', '.ini': 'ini', '.conf': 'ini',
            '.sql': 'sql', '.dockerfile': 'dockerfile',
        }
        language = lang_map.get(ext, '')

        return jsonify({
            'content': content,
            'path': path,
            'name': Path(path).name,
            'size': size,
            'language': language,
            'lines': content.count('\n') + 1,
        })
    except OSError:
        return jsonify({'error': 'Failed to read file'}), 500


@app.route('/api/files/write', methods=['POST'])
@login_required
def api_write_file():
    """Write content to an existing file"""
    data = request.json or {}
    path = data.get('path', '')

    if 'content' not in data:
        return jsonify({'error': 'Content field required'}), 400
    content = data['content']
    if not isinstance(content, str):
        return jsonify({'error': 'Content must be a string'}), 400

    if not path:
        return jsonify({'error': 'Path required'}), 400
    if '\x00' in path:
        return jsonify({'error': 'Invalid path'}), 400

    path = os.path.expanduser(path)

    if not validate_file_path(path):
        return jsonify({'error': 'Path not allowed'}), 403

    # Re-resolve after validation to close TOCTOU symlink swap window
    try:
        resolved = str(Path(path).resolve())
    except (OSError, ValueError):
        return jsonify({'error': 'Invalid path'}), 400

    if not os.path.isfile(resolved):
        return jsonify({'error': 'File does not exist'}), 400

    # Size limit: 500KB
    if len(content.encode('utf-8')) > 512000:
        return jsonify({'error': 'Content too large (max 500KB)'}), 400

    # Reject binary files
    try:
        with open(resolved, 'rb') as f:
            chunk = f.read(1024)
            if b'\x00' in chunk:
                return jsonify({'error': 'Cannot edit binary files'}), 400
    except OSError:
        return jsonify({'error': 'Failed to read file'}), 500

    # Check write permission
    if not os.access(resolved, os.W_OK):
        return jsonify({'error': 'No write permission'}), 403

    try:
        # Atomic write: write to temp file then rename to prevent partial writes
        dir_name = os.path.dirname(resolved)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            # Preserve original file permissions
            st = os.stat(resolved)
            os.chmod(tmp_path, st.st_mode)
            os.replace(tmp_path, resolved)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return jsonify({'success': True, 'size': len(content)})
    except OSError:
        return jsonify({'error': 'Failed to write file'}), 500


# ============== Multi-User API ==============

def get_current_user():
    """Get current logged-in user info"""
    users = CONFIG.get('users', [])
    username = session.get('username', '')
    for u in users:
        if u['username'] == username:
            return u
    # Fallback: if using legacy auth, treat as admin
    if session.get('authenticated'):
        auth = CONFIG.get('auth', {})
        return {'username': auth.get('username', 'admin'), 'role': 'admin'}
    return None


def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


@app.route('/api/users')
@login_required
def api_list_users():
    """List all users (admin only)"""
    user = get_current_user()
    if not user or user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    users = CONFIG.get('users', [])
    # Don't return password hashes
    safe_users = [{'username': u['username'], 'role': u.get('role', 'user')} for u in users]
    return jsonify({'users': safe_users})


@app.route('/api/users', methods=['POST'])
@login_required
def api_create_user():
    """Create a new user (admin only)"""
    user = get_current_user()
    if not user or user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'user')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400
    if role not in ('admin', 'user'):
        return jsonify({'error': 'Role must be admin or user'}), 400

    users = CONFIG.get('users', [])
    if any(u['username'] == username for u in users):
        return jsonify({'error': 'Username already exists'}), 409

    users.append({
        'username': username,
        'password_hash': generate_password_hash(password),
        'role': role,
    })
    CONFIG['users'] = users
    save_config(CONFIG)

    return jsonify({'success': True})


@app.route('/api/users/<username>', methods=['DELETE'])
@login_required
def api_delete_user(username):
    """Delete a user (admin only)"""
    user = get_current_user()
    if not user or user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    if username == user['username']:
        return jsonify({'error': 'Cannot delete yourself'}), 400

    users = CONFIG.get('users', [])
    CONFIG['users'] = [u for u in users if u['username'] != username]
    save_config(CONFIG)

    return jsonify({'success': True})


@app.route('/api/users/<username>/password', methods=['POST'])
@login_required
def api_change_user_password(username):
    """Change a user's password (admin or self)"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    # Allow admin or the user themselves
    if user.get('role') != 'admin' and user['username'] != username:
        return jsonify({'error': 'Access denied'}), 403

    data = request.json or {}
    password = data.get('password', '').strip()
    if not password or len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400

    users = CONFIG.get('users', [])
    for u in users:
        if u['username'] == username:
            u['password_hash'] = generate_password_hash(password)
            CONFIG['users'] = users
            save_config(CONFIG)
            return jsonify({'success': True})

    return jsonify({'error': 'User not found'}), 404


@app.route('/api/auth/whoami')
@login_required
def api_whoami():
    """Return current user info"""
    user = get_current_user()
    if user:
        return jsonify({'username': user['username'], 'role': user.get('role', 'admin')})
    return jsonify({'username': 'anonymous', 'role': 'admin'})


# ============== Usage & Terminals API ==============

@app.route('/api/usage')
@login_required
def api_usage():
    """Get usage statistics"""
    usage = load_usage()
    week_key = get_week_key()
    weekly = usage.get('weekly', {}).get(week_key, {'input_tokens': 0, 'output_tokens': 0})

    # Calculate next Monday for weekly reset
    now = datetime.now()
    days_until_monday = (7 - now.weekday()) % 7 or 7
    reset_time = (now + timedelta(days=days_until_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()

    return jsonify({
        'weekly': weekly,
        'total': usage.get('total', {'input_tokens': 0, 'output_tokens': 0}),
        'reset_time': reset_time,
        'week_key': week_key
    })


@app.route('/api/terminals')
@login_required
def api_terminals():
    """List active terminals"""
    return jsonify({
        'terminals': [
            {'id': tid, 'project': t['project'],
             'remote_host_id': t.get('remote_host_id'),
             'started': t['started'].isoformat()}
            for tid, t in active_terminals.items()
        ]
    })


# ============== Project Instructions Wizard API ==============

@app.route('/api/project/detect')
@login_required
def api_project_detect():
    """Auto-detect project type and pre-fill wizard data"""
    path = request.args.get('path', '')
    if not path:
        return jsonify({'error': 'Path required'}), 400
    if '\x00' in path:
        return jsonify({'error': 'Invalid path'}), 400

    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return jsonify({'error': 'Not a directory'}), 400

    if not validate_file_path(path):
        return jsonify({'error': 'Path not allowed'}), 403

    result = {
        'detected_type': 'unknown',
        'name': Path(path).name,
        'description': '',
        'has_claude_md': os.path.isfile(os.path.join(path, 'CLAUDE.md')),
        'has_claude_dir': os.path.isdir(os.path.join(path, '.claude')),
        'build_command': '',
        'test_command': '',
        'dev_command': '',
        'lint_command': '',
        'top_dirs': [],
        'key_files': [],
        'is_git': os.path.isdir(os.path.join(path, '.git')),
        'framework_hints': [],
        'language': '',
        'naming_convention': 'camelCase',
    }

    # Scan top-level directories
    skip_dirs = {'node_modules', 'venv', '.venv', '__pycache__', '.git',
                 '.idea', '.vscode', 'target', 'build', 'dist', '.next'}
    try:
        for entry in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            if entry.is_dir() and entry.name not in skip_dirs and not entry.name.startswith('.'):
                result['top_dirs'].append(entry.name)
    except (PermissionError, OSError):
        pass

    # Scan key config files
    key_file_names = [
        'package.json', 'tsconfig.json', 'pyproject.toml', 'setup.py',
        'Cargo.toml', 'Makefile', 'CMakeLists.txt', 'Dockerfile',
        'docker-compose.yml', '.eslintrc.json', '.prettierrc',
        'requirements.txt', 'go.mod', 'Gemfile', 'pom.xml',
        'build.gradle', 'CLAUDE.md', '.claude/settings.json',
    ]
    for fname in key_file_names:
        fpath = os.path.join(path, fname)
        if os.path.isfile(fpath):
            result['key_files'].append(fname)

    # Detect from package.json (Node/JS/TS)
    pkg_json_path = os.path.join(path, 'package.json')
    if os.path.isfile(pkg_json_path):
        try:
            with open(pkg_json_path, 'r') as f:
                pkg = json.load(f)
            result['detected_type'] = 'node'
            result['language'] = 'TypeScript' if os.path.isfile(os.path.join(path, 'tsconfig.json')) else 'JavaScript'
            result['name'] = pkg.get('name', result['name'])
            result['description'] = pkg.get('description', '')

            scripts = pkg.get('scripts', {})
            result['build_command'] = f"npm run {next((k for k in ('build', 'compile') if k in scripts), '')}" if any(k in scripts for k in ('build', 'compile')) else ''
            result['test_command'] = f"npm run {next((k for k in ('test', 'test:unit') if k in scripts), '')}" if any(k in scripts for k in ('test', 'test:unit')) else ''
            result['dev_command'] = f"npm run {next((k for k in ('dev', 'start', 'serve') if k in scripts), '')}" if any(k in scripts for k in ('dev', 'start', 'serve')) else ''
            result['lint_command'] = f"npm run {next((k for k in ('lint', 'lint:fix') if k in scripts), '')}" if any(k in scripts for k in ('lint', 'lint:fix')) else ''

            # Detect frameworks from deps
            all_deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
            fw_map = {'react': 'React', 'vue': 'Vue', 'next': 'Next.js',
                      'express': 'Express', 'svelte': 'Svelte', '@angular/core': 'Angular'}
            for dep_name, fw_name in fw_map.items():
                if dep_name in all_deps:
                    result['framework_hints'].append(fw_name)

            result['naming_convention'] = 'camelCase'
        except (json.JSONDecodeError, OSError):
            pass

    # Detect from pyproject.toml (Python)
    pyproject_path = os.path.join(path, 'pyproject.toml')
    if os.path.isfile(pyproject_path) and result['detected_type'] == 'unknown':
        try:
            with open(pyproject_path, 'r') as f:
                content = f.read()
            result['detected_type'] = 'python'
            result['language'] = 'Python'
            result['naming_convention'] = 'snake_case'

            name_match = re.search(r'^name\s*=\s*"([^"]+)"', content, re.MULTILINE)
            if name_match:
                result['name'] = name_match.group(1)
            desc_match = re.search(r'^description\s*=\s*"([^"]+)"', content, re.MULTILINE)
            if desc_match:
                result['description'] = desc_match.group(1)

            result['test_command'] = 'pytest'
            result['lint_command'] = 'ruff check .'
            fw_hints = {'flask': 'Flask', 'django': 'Django', 'fastapi': 'FastAPI'}
            for key, fw in fw_hints.items():
                if key in content.lower():
                    result['framework_hints'].append(fw)
        except OSError:
            pass

    # Detect from Cargo.toml (Rust)
    cargo_path = os.path.join(path, 'Cargo.toml')
    if os.path.isfile(cargo_path) and result['detected_type'] == 'unknown':
        try:
            with open(cargo_path, 'r') as f:
                content = f.read()
            result['detected_type'] = 'rust'
            result['language'] = 'Rust'
            result['naming_convention'] = 'snake_case'

            name_match = re.search(r'^name\s*=\s*"([^"]+)"', content, re.MULTILINE)
            if name_match:
                result['name'] = name_match.group(1)
            desc_match = re.search(r'^description\s*=\s*"([^"]+)"', content, re.MULTILINE)
            if desc_match:
                result['description'] = desc_match.group(1)

            result['build_command'] = 'cargo build'
            result['test_command'] = 'cargo test'
        except OSError:
            pass

    # Detect from go.mod (Go)
    gomod_path = os.path.join(path, 'go.mod')
    if os.path.isfile(gomod_path) and result['detected_type'] == 'unknown':
        result['detected_type'] = 'go'
        result['language'] = 'Go'
        result['naming_convention'] = 'camelCase'
        result['build_command'] = 'go build ./...'
        result['test_command'] = 'go test ./...'

    # Detect from requirements.txt / setup.py fallback
    if result['detected_type'] == 'unknown':
        if os.path.isfile(os.path.join(path, 'requirements.txt')) or os.path.isfile(os.path.join(path, 'setup.py')):
            result['detected_type'] = 'python'
            result['language'] = 'Python'
            result['naming_convention'] = 'snake_case'
            result['test_command'] = 'pytest'

    return jsonify(result)


@app.route('/api/project/init', methods=['POST'])
@login_required
def api_project_init():
    """Write CLAUDE.md and optionally .claude/settings.json to a project"""
    data = request.json
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    path = data.get('path', '')
    if not path or not isinstance(path, str):
        return jsonify({'error': 'Path required'}), 400

    # Reject null bytes
    if '\x00' in path:
        return jsonify({'error': 'Invalid path'}), 400

    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return jsonify({'error': 'Not a directory'}), 400

    if not validate_file_path(path):
        return jsonify({'error': 'Path not allowed'}), 403

    # Verify the resolved path is still within allowed directories (prevents symlink escape)
    resolved_path = str(Path(path).resolve())
    if not validate_file_path(resolved_path):
        return jsonify({'error': 'Resolved path not allowed'}), 403

    claude_md_content = data.get('claude_md_content', '')
    if not isinstance(claude_md_content, str):
        return jsonify({'error': 'Invalid content type'}), 400
    if not claude_md_content.strip():
        return jsonify({'error': 'CLAUDE.md content cannot be empty'}), 400

    # Enforce maximum content size (50KB)
    MAX_CLAUDE_MD_SIZE = 50 * 1024  # 50KB
    if len(claude_md_content.encode('utf-8')) > MAX_CLAUDE_MD_SIZE:
        return jsonify({'error': f'CLAUDE.md content too large (max {MAX_CLAUDE_MD_SIZE // 1024}KB)'}), 400

    overwrite = data.get('overwrite', False)
    claude_md_path = os.path.join(resolved_path, 'CLAUDE.md')

    if os.path.isfile(claude_md_path) and not overwrite:
        return jsonify({'error': 'CLAUDE.md already exists. Set overwrite=true to replace.', 'exists': True}), 409

    try:
        with open(claude_md_path, 'w') as f:
            f.write(claude_md_content)
    except OSError as e:
        return jsonify({'error': f'Failed to write CLAUDE.md: {e}'}), 500

    # Optionally create .claude/settings.json
    if data.get('create_settings') and data.get('settings'):
        settings_data = data['settings']
        if not isinstance(settings_data, dict):
            return jsonify({'error': 'Settings must be a JSON object'}), 400
        # Enforce settings size limit (10KB)
        settings_json = json.dumps(settings_data, indent=2)
        if len(settings_json.encode('utf-8')) > 10 * 1024:
            return jsonify({'error': 'Settings JSON too large (max 10KB)'}), 400
        claude_dir = os.path.join(resolved_path, '.claude')
        os.makedirs(claude_dir, exist_ok=True)
        settings_path = os.path.join(claude_dir, 'settings.json')
        try:
            with open(settings_path, 'w') as f:
                f.write(settings_json)
        except OSError as e:
            return jsonify({'error': f'CLAUDE.md written but failed to write settings.json: {e}'}), 500

    return jsonify({'success': True, 'path': claude_md_path})


# ============== Maintenance API ==============

def get_claude_version():
    """Get the installed Claude CLI version"""
    try:
        result = subprocess.run(
            ['claude', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Parse version from output (e.g., "claude 1.0.0")
            version_match = re.search(r'[\d]+\.[\d]+\.[\d]+', result.stdout)
            if version_match:
                return version_match.group(0)
            return result.stdout.strip()
        return None
    except Exception:
        return None


@app.route('/api/status')
@login_required
def api_status():
    """Get system status"""
    now = datetime.now()
    uptime_delta = now - START_TIME
    uptime_seconds = int(uptime_delta.total_seconds())

    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"

    return jsonify({
        'version': VERSION,
        'claude_version': get_claude_version(),
        'active_terminals': len(active_terminals),
        'active_chats': len(active_chat_processes),
        'loaded_sessions': len(chat_sessions),
        'max_terminals': CONFIG['max_concurrent_terminals'],
        'max_chats': CONFIG['max_concurrent_chats'],
        'timeout_minutes': CONFIG['process_timeout_minutes'],
        'uptime': uptime_str,
        'start_time': START_TIME.isoformat()
    })


@app.route('/api/changelog')
@login_required
def api_changelog():
    """Return changelog content"""
    changelog_path = os.path.join(os.path.dirname(__file__), 'CHANGELOG.md')
    try:
        with open(changelog_path, 'r') as f:
            content = f.read(100000)  # Cap at 100KB
        return jsonify({'content': content})
    except OSError:
        return jsonify({'content': '# Changelog\n\nNo changelog available.'})


@app.route('/api/state')
@login_required
def api_state():
    """Get active process state for reconnection sync"""
    terminal_ids = list(active_terminals.keys())
    chat_statuses = {}
    for sid, sess in chat_sessions.items():
        chat_statuses[sid] = sess.get('status', 'ready')
    return jsonify({
        'active_terminal_ids': terminal_ids,
        'chat_sessions': chat_statuses
    })


@app.route('/api/maintenance/cleanup', methods=['POST'])
@login_required
def api_cleanup():
    """Force cleanup of old processes"""
    cleanup_old_processes()
    return jsonify({'status': 'cleanup complete'})


@app.route('/api/maintenance/backup', methods=['POST'])
@login_required
def api_backup():
    """Force backup all sessions"""
    backup_all_sessions()
    return jsonify({'status': 'backup complete', 'sessions': len(chat_sessions)})


# ============== SSL/HTTPS ==============

def ensure_ssl_certs():
    """Generate self-signed certificates if none configured"""
    cert_dir = Path(__file__).parent / 'certs'
    cert_path = cert_dir / 'self-signed.pem'
    key_path = cert_dir / 'self-signed-key.pem'

    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)

    cert_dir.mkdir(exist_ok=True)
    print("[SSL] Generating self-signed certificate...")
    subprocess.run([
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-keyout', str(key_path), '-out', str(cert_path),
        '-days', '365', '-nodes',
        '-subj', '/CN=qn-code-assistant/O=QN Code Assistant'
    ], check=True, capture_output=True)
    print(f"[SSL] Certificate generated: {cert_path}")

    return str(cert_path), str(key_path)


# ============== Main ==============

if __name__ == '__main__':
    # Start watchdog thread
    watchdog = threading.Thread(target=watchdog_thread, daemon=True)
    watchdog.start()
    print("[Watchdog] Started process monitor")

    # Check Claude CLI version at startup
    cli_version = get_claude_version()

    # HTTPS setup
    ssl_context = None
    protocol = 'http'
    port = CONFIG.get('port', 5001)
    if CONFIG.get('ssl_enabled', False):
        cert = CONFIG.get('ssl_cert', '')
        key = CONFIG.get('ssl_key', '')
        if cert and key:
            ssl_context = (cert, key)
            print(f"[SSL] Using custom certificates: {cert}")
        else:
            cert, key = ensure_ssl_certs()
            ssl_context = (cert, key)
        protocol = 'https'

    auth_status = 'ENABLED' if CONFIG.get('auth', {}).get('enabled') else 'DISABLED'

    print("=" * 50)
    print(f"QN Code Assistant v{VERSION}")
    print("=" * 50)
    print(f"Claude CLI: {cli_version or 'NOT FOUND'}")
    print(f"Auth: {auth_status}")
    print(f"Starting server on {protocol}://0.0.0.0:{port}")
    print(f"Projects root: {CONFIG['projects_root']}")
    print("=" * 50)

    # Override Werkzeug server version to prevent information leakage
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.server_version = 'QN Code Assistant'
    WSGIRequestHandler.sys_version = ''

    socketio.run(app, host='0.0.0.0', port=port,
                 debug=CONFIG.get('debug', True),
                 allow_unsafe_werkzeug=True,
                 ssl_context=ssl_context)
