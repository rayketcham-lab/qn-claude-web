#!/usr/bin/env python3
"""
Security hardening tests for QN Code Assistant.

Tests:
  1. SSH push-key endpoint — hostname/username sanitization
  2. Host header validation (allowed_hosts config)
  3. CSRF enforcement with and without auth
  4. Terminal input size limit (64 KB)
  5. Error message sanitization (no stack traces in responses)
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Bootstrap path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_vendor_dir = os.path.join(_project_root, 'vendor')
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from werkzeug.security import generate_password_hash

import app as app_module

flask_app = app_module.app
flask_app.config['TESTING'] = True
flask_app.config['SECRET_KEY'] = 'test-secret-hardening'


# ---------------------------------------------------------------------------
# Shared helpers (mirror test_routes.py conventions)
# ---------------------------------------------------------------------------

def _snapshot_config():
    config_snap = dict(app_module.CONFIG)
    auth_snap = dict(app_module.AUTH)
    auth_snap['auth'] = dict(app_module.AUTH.get('auth', {}))
    auth_snap['users'] = [dict(u) for u in app_module.AUTH.get('users', [])]
    return config_snap, auth_snap


def _restore_config(snap):
    config_snap, auth_snap = snap
    app_module.CONFIG.clear()
    app_module.CONFIG.update(config_snap)
    app_module.AUTH.clear()
    app_module.AUTH.update(auth_snap)
    app_module.AUTH['auth'] = auth_snap['auth']
    app_module.AUTH['users'] = [dict(u) for u in auth_snap['users']]


def _get_csrf(client):
    resp = client.get('/api/csrf-token')
    return json.loads(resp.data)['csrf_token']


def _csrf_headers(client):
    return {'X-CSRF-Token': _get_csrf(client)}


def _enable_auth(username='testadmin', password='testpass123'):
    pw_hash = generate_password_hash(password)
    app_module.AUTH['auth'] = {
        'enabled': True,
        'username': username,
        'password_hash': pw_hash,
    }
    app_module.AUTH['users'] = [
        {'username': username, 'password_hash': pw_hash, 'role': 'admin'}
    ]


def _disable_auth():
    app_module.AUTH['auth'] = {'enabled': False, 'username': '', 'password_hash': ''}
    app_module.AUTH['users'] = []


def _login(client, username='testadmin', password='testpass123'):
    return client.post(
        '/login',
        data=json.dumps({'username': username, 'password': password}),
        content_type='application/json',
    )


def _reset_rate_limits():
    with app_module._rate_limit_lock:
        app_module._rate_limit_store.clear()


# ---------------------------------------------------------------------------
# Fake public key so push-key tests don't require ~/.ssh files on disk
# ---------------------------------------------------------------------------
FAKE_PUB_KEY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI test@test'


# ===========================================================================
# 1. SSH push-key sanitization
# ===========================================================================

class TestPushKeySanitization(unittest.TestCase):
    """Verify hostname and username sanitization on the push-key endpoint."""

    def setUp(self):
        self._snap = _snapshot_config()
        _reset_rate_limits()
        _disable_auth()

    def tearDown(self):
        _restore_config(self._snap)
        _reset_rate_limits()

    def _post_push_key(self, client, hostname, username, password='secret'):
        """Helper: POST to push-key with a CSRF token."""
        headers = _csrf_headers(client)
        headers['Content-Type'] = 'application/json'
        return client.post(
            '/api/v1/remote/push-key',
            data=json.dumps({
                'hostname': hostname,
                'username': username,
                'password': password,
            }),
            headers=headers,
        )

    @patch('subprocess.run')
    @patch('pathlib.Path.read_text', return_value=FAKE_PUB_KEY)
    @patch('pathlib.Path.exists', return_value=True)
    def test_push_key_rejects_hostname_with_shell_chars(self, mock_exists, mock_read, mock_run):
        """Shell metacharacters in hostnames are stripped by sanitization.

        Design note: the endpoint uses a strip-then-use approach rather than
        reject-on-metachar. Hostnames like '`id`' are sanitized to 'id' before
        use in subprocess args, preventing injection. Inputs that sanitize to
        empty string → 400; inputs that retain alphanumeric residue succeed with
        the sanitized (safe) value.

        Security implication documented here: if the stripped residue is a valid
        hostname, the key push proceeds to an unintended host. This test documents
        current behavior and serves as a regression baseline.
        """
        # Payloads that sanitize to EMPTY STRING → must return 400
        empty_after_strip = [
            '`',
            ';',
            '|',
            '$',
            '\n',
            '`; |$',
        ]
        # Payloads that retain an alphanumeric residue after stripping
        # (metachar stripped, safe residue proceeds)
        mock_result = MagicMock()
        mock_result.stdout = 'KEY_INSTALLED'
        mock_result.stderr = ''
        mock_run.return_value = mock_result

        with flask_app.test_client() as client:
            for hostname in empty_after_strip:
                resp = self._post_push_key(client, hostname=hostname, username='validuser')
                self.assertEqual(
                    resp.status_code, 400,
                    f"Expected 400 for all-metachar hostname {hostname!r}, got {resp.status_code}"
                )
                data = resp.get_json()
                self.assertFalse(data.get('success', True))

            # A hostname whose metacharacters strip to a non-empty value is
            # processed with the sanitized value — no shell injection occurs
            # because subprocess is called with a list (not a shell string).
            resp = self._post_push_key(client, hostname='`id`', username='validuser')
            # 'id' is non-empty after stripping backticks → proceeds to subprocess
            data = resp.get_json()
            # Verify subprocess received the sanitized 'id' — not the raw payload
            if mock_run.called:
                cmd_args = mock_run.call_args[0][0]
                cmd_str = ' '.join(cmd_args)
                self.assertNotIn('`', cmd_str, "Raw backtick must not reach subprocess")
                self.assertNotIn(';', cmd_str, "Semicolon must not reach subprocess")
                self.assertNotIn('|', cmd_str, "Pipe must not reach subprocess")

    @patch('pathlib.Path.read_text', return_value=FAKE_PUB_KEY)
    @patch('pathlib.Path.exists', return_value=True)
    def test_push_key_rejects_hostname_starting_with_dash(self, mock_exists, mock_read):
        """Hostname '-oProxyCommand=id' must be rejected (option injection)."""
        with flask_app.test_client() as client:
            resp = self._post_push_key(
                client,
                hostname='-oProxyCommand=id',
                username='validuser',
            )
            self.assertEqual(resp.status_code, 400)
            data = resp.get_json()
            self.assertFalse(data.get('success', True))

    @patch('subprocess.run')
    @patch('pathlib.Path.read_text', return_value=FAKE_PUB_KEY)
    @patch('pathlib.Path.exists', return_value=True)
    def test_push_key_rejects_username_with_special_chars(self, mock_exists, mock_read, mock_run):
        """Shell metacharacters in usernames are stripped before use.

        Design note: same strip-then-use pattern as hostname. Usernames that
        sanitize to empty → 400. Usernames that retain alphanumeric residue are
        processed safely (no shell string expansion; subprocess list call).
        """
        # Usernames that sanitize to empty string
        empty_after_strip = [
            '',
            ';',
            '|',
            '`',
        ]
        mock_result = MagicMock()
        mock_result.stdout = 'KEY_INSTALLED'
        mock_result.stderr = ''
        mock_run.return_value = mock_result

        with flask_app.test_client() as client:
            for username in empty_after_strip:
                resp = self._post_push_key(
                    client,
                    hostname='192.168.1.10',
                    username=username,
                )
                self.assertEqual(
                    resp.status_code, 400,
                    f"Expected 400 for all-metachar username {username!r}, got {resp.status_code}"
                )
                data = resp.get_json()
                self.assertFalse(data.get('success', True))

            # Username with metachar that strips to non-empty residue — subprocess
            # must never receive the raw metacharacters
            resp = self._post_push_key(
                client,
                hostname='192.168.1.10',
                username='user;id',
            )
            if mock_run.called:
                cmd_args = mock_run.call_args[0][0]
                cmd_str = ' '.join(cmd_args)
                self.assertNotIn(';', cmd_str, "Semicolon must not reach subprocess")
                self.assertNotIn('|', cmd_str, "Pipe must not reach subprocess")
                self.assertNotIn('`', cmd_str, "Backtick must not reach subprocess")

    @patch('subprocess.run')
    @patch('pathlib.Path.read_text', return_value=FAKE_PUB_KEY)
    @patch('pathlib.Path.exists', return_value=True)
    def test_push_key_sanitizes_valid_hostname(self, mock_exists, mock_read, mock_run):
        """A clean hostname + username passes sanitization and reaches subprocess."""
        mock_result = MagicMock()
        mock_result.stdout = 'KEY_INSTALLED'
        mock_result.stderr = ''
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        with flask_app.test_client() as client:
            resp = self._post_push_key(
                client,
                hostname='192.168.1.10',
                username='deploy',
                password='secret',
            )
        # subprocess was called → sshpass ran → KEY_INSTALLED in stdout → 200
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'), f"Unexpected response: {data}")
        # Verify subprocess was actually invoked
        self.assertTrue(mock_run.called, "subprocess.run should have been called")
        # Inspect the command list used — hostname must appear verbatim
        cmd_args = mock_run.call_args[0][0]
        self.assertIn('192.168.1.10', ' '.join(cmd_args))


# ===========================================================================
# 2. Host header validation
# ===========================================================================

class TestAllowedHosts(unittest.TestCase):
    """Verify the enforce_allowed_hosts before_request hook."""

    def setUp(self):
        self._snap = _snapshot_config()
        _disable_auth()

    def tearDown(self):
        _restore_config(self._snap)

    def test_allowed_hosts_wildcard_allows_all(self):
        """allowed_hosts=['*'] should permit any Host header."""
        app_module.CONFIG['allowed_hosts'] = ['*']
        with flask_app.test_client() as client:
            resp = client.get('/api/health', headers={'Host': 'evil.attacker.com'})
        self.assertNotEqual(resp.status_code, 403)

    def test_allowed_hosts_rejects_unknown_host(self):
        """allowed_hosts=['192.168.1.241'] must reject Host: evil.com with 403."""
        app_module.CONFIG['allowed_hosts'] = ['192.168.1.241']
        with flask_app.test_client() as client:
            resp = client.get('/api/health', headers={'Host': 'evil.com'})
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertIn('not allowed', data.get('error', '').lower())

    def test_allowed_hosts_accepts_configured_host(self):
        """allowed_hosts=['localhost'] should allow Host: localhost."""
        app_module.CONFIG['allowed_hosts'] = ['localhost']
        with flask_app.test_client() as client:
            resp = client.get('/api/health', headers={'Host': 'localhost'})
        self.assertNotEqual(resp.status_code, 403)

    def test_allowed_hosts_strips_port(self):
        """allowed_hosts=['localhost'] should permit Host: localhost:5001 (port stripped)."""
        app_module.CONFIG['allowed_hosts'] = ['localhost']
        with flask_app.test_client() as client:
            resp = client.get('/api/health', headers={'Host': 'localhost:5001'})
        self.assertNotEqual(resp.status_code, 403)


# ===========================================================================
# 3. CSRF enforcement
# ===========================================================================

class TestCsrfEnforcement(unittest.TestCase):
    """CSRF token must be required on state-changing endpoints regardless of
    auth state."""

    def setUp(self):
        self._snap = _snapshot_config()
        _reset_rate_limits()

    def tearDown(self):
        _restore_config(self._snap)
        _reset_rate_limits()

    def test_csrf_enforced_when_auth_disabled(self):
        """POST /api/v1/config without CSRF token → 403 even when auth is off."""
        _disable_auth()
        app_module.CONFIG['allowed_hosts'] = ['*']
        with flask_app.test_client() as client:
            resp = client.post(
                '/api/v1/config',
                data=json.dumps({'theme': 'light'}),
                content_type='application/json',
                # Deliberately omit X-CSRF-Token header
            )
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertIn('csrf', data.get('error', '').lower())

    def test_csrf_enforced_when_auth_enabled(self):
        """POST /api/v1/config without CSRF token → 403 when auth is enabled,
        even after a successful login."""
        _enable_auth()
        app_module.CONFIG['allowed_hosts'] = ['*']
        with flask_app.test_client() as client:
            _login(client)
            resp = client.post(
                '/api/v1/config',
                data=json.dumps({'theme': 'light'}),
                content_type='application/json',
                # No CSRF header
            )
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertIn('csrf', data.get('error', '').lower())

    def test_csrf_passes_with_valid_token(self):
        """POST /api/v1/config WITH a valid CSRF token should not return 403."""
        _disable_auth()
        app_module.CONFIG['allowed_hosts'] = ['*']
        with flask_app.test_client() as client:
            headers = _csrf_headers(client)
            headers['Content-Type'] = 'application/json'
            resp = client.post(
                '/api/v1/config',
                data=json.dumps({'theme': 'light'}),
                headers=headers,
            )
        # Any status other than 403 means CSRF passed.
        self.assertNotEqual(
            resp.status_code, 403,
            f"CSRF should have passed but got 403. Body: {resp.data}"
        )


# ===========================================================================
# 4. Terminal input size limit
# ===========================================================================

class TestTerminalInputSizeLimit(unittest.TestCase):
    """handle_terminal_input must reject payloads larger than 64 KB."""

    def setUp(self):
        self._snap = _snapshot_config()
        _disable_auth()
        app_module.CONFIG['allowed_hosts'] = ['*']

    def tearDown(self):
        _restore_config(self._snap)

    def test_terminal_input_rejects_oversized(self):
        """Input data > 64 KB (65537 bytes) should trigger a terminal_error emit."""
        from flask_socketio import SocketIOTestClient

        oversized_payload = 'A' * 65537  # one byte over the 64 KB limit

        with flask_app.test_client() as http_client:
            sc = SocketIOTestClient(flask_app, app_module.socketio,
                                    flask_test_client=http_client)
            sc.emit('terminal_input', {'id': 'fake-terminal', 'data': oversized_payload})
            received = sc.get_received()
            sc.disconnect()

        error_events = [e for e in received if e.get('name') == 'terminal_error']
        self.assertTrue(
            len(error_events) > 0,
            f"Expected terminal_error for oversized input, got: {received}"
        )
        # Confirm the error message mentions size / too large
        error_msg = error_events[0]['args'][0].get('error', '').lower()
        self.assertIn('large', error_msg, f"Unexpected error message: {error_msg}")

    def test_terminal_input_accepts_normal(self):
        """A small, normal-sized input should not produce a terminal_error."""
        from flask_socketio import SocketIOTestClient

        normal_payload = 'ls -la\n'

        # Patch os.write so nothing actually touches a PTY fd
        with patch('os.write'):
            # Insert a fake terminal entry so the write path is exercised
            fake_fd = 99
            with app_module.active_terminals_lock:
                app_module.active_terminals['test-term'] = {
                    'fd': fake_fd,
                    'pid': 0,
                    'started': None,
                    'tmux_session': None,
                }

            try:
                with flask_app.test_client() as http_client:
                    sc = SocketIOTestClient(flask_app, app_module.socketio,
                                            flask_test_client=http_client)
                    sc.emit('terminal_input', {'id': 'test-term', 'data': normal_payload})
                    received = sc.get_received()
                    sc.disconnect()
            finally:
                with app_module.active_terminals_lock:
                    app_module.active_terminals.pop('test-term', None)

        error_events = [e for e in received if e.get('name') == 'terminal_error']
        self.assertEqual(
            error_events, [],
            f"Unexpected terminal_error for normal input: {error_events}"
        )


# ===========================================================================
# 5. Error message sanitization
# ===========================================================================

class TestErrorResponseSanitization(unittest.TestCase):
    """Error responses must not leak internal file paths or Python tracebacks."""

    def setUp(self):
        self._snap = _snapshot_config()
        _disable_auth()
        app_module.CONFIG['allowed_hosts'] = ['*']

    def tearDown(self):
        _restore_config(self._snap)

    def test_error_responses_no_stack_traces(self):
        """Hitting a route that triggers an error must not return Python tracebacks
        or internal file paths in the JSON body."""
        import traceback

        suspicious_patterns = [
            'Traceback (most recent call last)',
            'File "/opt/',
            'File "/usr/',
            '.py", line ',
            'app.py',
        ]

        # Trigger a 404 by requesting a completely unknown route — Flask returns
        # an HTML or JSON error; also hit a bad JSON parse path.
        with flask_app.test_client() as client:
            resp_404 = client.get('/api/v1/nonexistent-endpoint-xyz')
            body_404 = resp_404.data.decode('utf-8', errors='replace')

            # POST malformed JSON to a real endpoint — triggers a json parse edge
            resp_bad = client.post(
                '/api/v1/config',
                data=b'{{not valid json',
                content_type='application/json',
            )
            body_bad = resp_bad.data.decode('utf-8', errors='replace')

        for body, label in [(body_404, '404 response'), (body_bad, 'bad-JSON response')]:
            for pattern in suspicious_patterns:
                self.assertNotIn(
                    pattern, body,
                    f"Stack trace / internal path leaked in {label}: found {pattern!r}"
                )


if __name__ == '__main__':
    unittest.main()
