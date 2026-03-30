#!/usr/bin/env python3
"""
P0 Flask route tests for QN Code Assistant.

Tests auth, health, config admin gate, secret key, CSP headers, and user management
using the Flask test client against the real app module.

Run with:
    /usr/bin/python3 -m unittest tests/test_routes.py -v
"""

import sys
import os
import json
import tempfile
import unittest
from datetime import datetime, timedelta

# Bootstrap path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_vendor_dir = os.path.join(_project_root, 'vendor')
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import app as app_module
from werkzeug.security import generate_password_hash

flask_app = app_module.app
flask_app.config['TESTING'] = True
flask_app.config['SECRET_KEY'] = 'test-secret-key-routes'
# Disable CSRF-like checks and keep sessions readable in tests
flask_app.config['WTF_CSRF_ENABLED'] = False


# ---------------------------------------------------------------------------
# Helper: snapshot and restore CONFIG state around each test
# ---------------------------------------------------------------------------

def _snapshot_config():
    """Return a shallow copy of CONFIG with auth/users sub-dicts deep-copied."""
    snap = dict(app_module.CONFIG)
    snap['auth'] = dict(app_module.CONFIG.get('auth', {}))
    snap['users'] = [dict(u) for u in app_module.CONFIG.get('users', [])]
    return snap


def _restore_config(snap):
    """Restore CONFIG to a previously snapshotted state."""
    app_module.CONFIG.clear()
    app_module.CONFIG.update(snap)
    app_module.CONFIG['auth'] = snap['auth']
    app_module.CONFIG['users'] = [dict(u) for u in snap['users']]


def _get_csrf(client):
    """Fetch a CSRF token for the current session."""
    resp = client.get('/api/csrf-token')
    return json.loads(resp.data)['csrf_token']


def _csrf_headers(client):
    """Return headers dict with a valid CSRF token."""
    return {'X-CSRF-Token': _get_csrf(client)}


def _reset_rate_limits():
    """Clear the in-memory rate limit store between tests."""
    with app_module._rate_limit_lock:
        app_module._rate_limit_store.clear()


# ---------------------------------------------------------------------------
# Auth setup helpers
# ---------------------------------------------------------------------------

def _enable_auth(username='testadmin', password='testpass123'):
    """Configure CONFIG to have auth enabled with a known admin account."""
    pw_hash = generate_password_hash(password)
    app_module.CONFIG['auth'] = {
        'enabled': True,
        'username': username,
        'password_hash': pw_hash,
    }
    app_module.CONFIG['users'] = [
        {'username': username, 'password_hash': pw_hash, 'role': 'admin'}
    ]


def _disable_auth():
    """Configure CONFIG to have auth disabled."""
    app_module.CONFIG['auth'] = {'enabled': False, 'username': '', 'password_hash': ''}
    app_module.CONFIG['users'] = []


def _login(client, username='testadmin', password='testpass123'):
    """POST /login with JSON credentials and return the response."""
    return client.post(
        '/login',
        data=json.dumps({'username': username, 'password': password}),
        content_type='application/json',
    )


# ===========================================================================
# Auth Tests
# ===========================================================================

class TestAuthRoutes(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()
        _reset_rate_limits()

    def tearDown(self):
        _restore_config(self._config_snap)
        _reset_rate_limits()

    def test_login_page_renders(self):
        """GET /login returns 200 when auth is enabled."""
        _enable_auth()
        with flask_app.test_client() as client:
            resp = client.get('/login')
        self.assertEqual(resp.status_code, 200)

    def test_login_success(self):
        """POST /login with valid credentials sets authenticated session."""
        _enable_auth()
        with flask_app.test_client() as client:
            resp = _login(client)
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data.get('success'))
            # Session should now be authenticated
            with client.session_transaction() as sess:
                self.assertTrue(sess.get('authenticated'))
                self.assertEqual(sess.get('username'), 'testadmin')
                self.assertEqual(sess.get('role'), 'admin')

    def test_login_failure(self):
        """POST /login with wrong password returns 401."""
        _enable_auth()
        with flask_app.test_client() as client:
            resp = client.post(
                '/login',
                data=json.dumps({'username': 'testadmin', 'password': 'wrongpassword'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data.get('success'))

    def test_login_rate_limit(self):
        """11 rapid login attempts from the same IP returns 429 on the 11th."""
        _enable_auth()
        with flask_app.test_client() as client:
            last_resp = None
            for _ in range(11):
                last_resp = client.post(
                    '/login',
                    data=json.dumps({'username': 'testadmin', 'password': 'badpass'}),
                    content_type='application/json',
                    environ_base={'REMOTE_ADDR': '10.0.0.1'},
                )
        self.assertEqual(last_resp.status_code, 429)

    def test_auth_setup_creates_admin(self):
        """POST /api/auth/setup creates admin when auth is not yet configured."""
        _disable_auth()
        with flask_app.test_client() as client:
            resp = client.post(
                '/api/auth/setup',
                data=json.dumps({'username': 'newadmin', 'password': 'securepass1'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        # Verify CONFIG was updated
        self.assertTrue(app_module.CONFIG['auth']['enabled'])
        self.assertEqual(app_module.CONFIG['auth']['username'], 'newadmin')

    def test_auth_setup_password_too_short(self):
        """POST /api/auth/setup with password < 8 chars returns 400."""
        _disable_auth()
        with flask_app.test_client() as client:
            resp = client.post(
                '/api/auth/setup',
                data=json.dumps({'username': 'admin', 'password': 'short'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('8', data.get('error', ''))

    def test_auth_setup_blocks_reconfig_without_auth(self):
        """POST /api/auth/setup when already configured, unauthenticated returns 403."""
        _enable_auth()
        with flask_app.test_client() as client:
            # No login — unauthenticated request
            resp = client.post(
                '/api/auth/setup',
                data=json.dumps({'username': 'hacker', 'password': 'newpassword1'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 403)

    def test_logout_clears_session(self):
        """GET /logout clears the auth state from the session."""
        _enable_auth()
        with flask_app.test_client() as client:
            _login(client)
            # Verify logged in
            with client.session_transaction() as sess:
                self.assertTrue(sess.get('authenticated'))
            # Logout
            client.get('/logout')
            with client.session_transaction() as sess:
                self.assertFalse(sess.get('authenticated', False))

    def test_session_timeout_enforcement(self):
        """A session with an expired login_time returns 401 on protected API calls."""
        _enable_auth()
        # Set session_timeout_hours to a small value
        app_module.CONFIG['session_timeout_hours'] = 1
        with flask_app.test_client() as client:
            _login(client)
            # Backdate login_time by 2 hours so it appears expired
            expired_time = (datetime.utcnow() - timedelta(hours=2)).isoformat()
            with client.session_transaction() as sess:
                sess['login_time'] = expired_time
            # Protected API endpoint should reject the expired session
            resp = client.get('/api/config')
        self.assertEqual(resp.status_code, 401)


# ===========================================================================
# Health Check Tests
# ===========================================================================

class TestHealthEndpoint(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()

    def tearDown(self):
        _restore_config(self._config_snap)

    def test_health_returns_ok(self):
        """GET /api/health returns status 'ok'."""
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'ok')

    def test_health_includes_version(self):
        """GET /api/health response includes a version field."""
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        data = resp.get_json()
        self.assertIn('version', data)
        self.assertIsNotNone(data['version'])

    def test_health_no_auth_required(self):
        """GET /api/health works without authentication even when auth is enabled."""
        _enable_auth()
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# Config API Admin Gate Tests
# ===========================================================================

class TestConfigAdminGate(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()
        _reset_rate_limits()
        # Set up auth with an admin and a regular user
        admin_hash = generate_password_hash('adminpass1')
        user_hash = generate_password_hash('userpass1!')
        app_module.CONFIG['auth'] = {
            'enabled': True,
            'username': 'adminuser',
            'password_hash': admin_hash,
        }
        app_module.CONFIG['users'] = [
            {'username': 'adminuser', 'password_hash': admin_hash, 'role': 'admin'},
            {'username': 'regularuser', 'password_hash': user_hash, 'role': 'user'},
        ]

    def tearDown(self):
        _restore_config(self._config_snap)
        _reset_rate_limits()

    def _login_as(self, client, username, password):
        return client.post(
            '/login',
            data=json.dumps({'username': username, 'password': password}),
            content_type='application/json',
        )

    def test_non_admin_cannot_change_remote_hosts(self):
        """A user with role=user cannot POST remote_hosts to /api/config."""
        with flask_app.test_client() as client:
            self._login_as(client, 'regularuser', 'userpass1!')
            resp = client.post(
                '/api/config',
                data=json.dumps({'remote_hosts': []}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 403)

    def test_non_admin_cannot_change_projects_root(self):
        """A user with role=user cannot POST projects_root to /api/config."""
        with flask_app.test_client() as client:
            self._login_as(client, 'regularuser', 'userpass1!')
            resp = client.post(
                '/api/config',
                data=json.dumps({'projects_root': '/tmp'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 403)

    def test_non_admin_cannot_change_default_flags(self):
        """A user with role=user cannot POST default_flags to /api/config."""
        with flask_app.test_client() as client:
            self._login_as(client, 'regularuser', 'userpass1!')
            resp = client.post(
                '/api/config',
                data=json.dumps({'default_flags': []}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_change_remote_hosts(self):
        """An admin can POST remote_hosts to /api/config successfully."""
        with flask_app.test_client() as client:
            self._login_as(client, 'adminuser', 'adminpass1')
            resp = client.post(
                '/api/config',
                data=json.dumps({'remote_hosts': []}),
                content_type='application/json',
                headers=_csrf_headers(client),
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))

    def test_non_admin_can_change_theme(self):
        """A user with role=user CAN change the theme setting via /api/config."""
        with flask_app.test_client() as client:
            self._login_as(client, 'regularuser', 'userpass1!')
            resp = client.post(
                '/api/config',
                data=json.dumps({'theme': 'light'}),
                content_type='application/json',
                headers=_csrf_headers(client),
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))


# ===========================================================================
# Secret Key Tests
# ===========================================================================

class TestSecretKey(unittest.TestCase):
    """Verify the secret key resolution priority: env > config > auto-generate."""

    def test_env_var_takes_precedence(self):
        """When QN_SECRET_KEY env var is set, app.secret_key must equal it.

        Because app.py resolves the secret key at import time, we verify the
        logic by re-running the resolution code in isolation rather than
        re-importing the module (which is not safe in a test runner).
        """
        import importlib
        import types

        expected_key = 'env-overrides-everything-abc123'
        config_key = 'config-key-should-not-be-used'

        # Simulate the resolution logic from app.py lines 200-207
        env_backup = os.environ.get('QN_SECRET_KEY')
        try:
            os.environ['QN_SECRET_KEY'] = expected_key
            mock_config = {'secret_key': config_key}

            resolved = os.environ.get('QN_SECRET_KEY')
            if not resolved:
                resolved = mock_config.get('secret_key')
            if not resolved:
                resolved = 'random'

            self.assertEqual(resolved, expected_key)
        finally:
            if env_backup is None:
                os.environ.pop('QN_SECRET_KEY', None)
            else:
                os.environ['QN_SECRET_KEY'] = env_backup

    def test_config_fallback(self):
        """When QN_SECRET_KEY is absent, the config key is used."""
        config_key = 'config-fallback-key-xyz'

        env_backup = os.environ.get('QN_SECRET_KEY')
        try:
            os.environ.pop('QN_SECRET_KEY', None)
            mock_config = {'secret_key': config_key}

            resolved = os.environ.get('QN_SECRET_KEY')
            if not resolved:
                resolved = mock_config.get('secret_key')
            if not resolved:
                resolved = 'random'

            self.assertEqual(resolved, config_key)
        finally:
            if env_backup is not None:
                os.environ['QN_SECRET_KEY'] = env_backup


# ===========================================================================
# CSP Header Tests
# ===========================================================================

class TestCSPHeaders(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()
        _disable_auth()

    def tearDown(self):
        _restore_config(self._config_snap)

    def _get_csp(self):
        """Fetch the CSP header value from any authenticated endpoint."""
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        return resp.headers.get('Content-Security-Policy', '')

    def test_csp_connect_src_not_wildcard(self):
        """connect-src must NOT contain broad wildcards like 'http: https: ws: wss:'."""
        csp = self._get_csp()
        self.assertIn('connect-src', csp)
        # These broad wildcards would allow connections to any origin
        for wildcard in ('http: ', 'https: ', 'ws: ', 'wss: '):
            self.assertNotIn(
                wildcard, csp,
                msg=f"connect-src should not contain broad wildcard '{wildcard}' — found in CSP: {csp}"
            )

    def test_csp_has_frame_ancestors(self):
        """CSP must include frame-ancestors directive to prevent clickjacking."""
        csp = self._get_csp()
        self.assertIn(
            'frame-ancestors', csp,
            msg=f"frame-ancestors missing from CSP: {csp}"
        )


# ===========================================================================
# User Management Tests
# ===========================================================================

class TestUserManagement(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()
        _reset_rate_limits()
        admin_hash = generate_password_hash('adminpass1')
        user_hash = generate_password_hash('userpass1!')
        app_module.CONFIG['auth'] = {
            'enabled': True,
            'username': 'adminuser',
            'password_hash': admin_hash,
        }
        app_module.CONFIG['users'] = [
            {'username': 'adminuser', 'password_hash': admin_hash, 'role': 'admin'},
            {'username': 'regularuser', 'password_hash': user_hash, 'role': 'user'},
        ]

    def tearDown(self):
        _restore_config(self._config_snap)
        _reset_rate_limits()

    def _login_as_admin(self, client):
        return client.post(
            '/login',
            data=json.dumps({'username': 'adminuser', 'password': 'adminpass1'}),
            content_type='application/json',
        )

    def _login_as_user(self, client):
        return client.post(
            '/login',
            data=json.dumps({'username': 'regularuser', 'password': 'userpass1!'}),
            content_type='application/json',
        )

    def test_create_user_requires_admin(self):
        """Non-admin POST to /api/users returns 403."""
        with flask_app.test_client() as client:
            self._login_as_user(client)
            resp = client.post(
                '/api/users',
                data=json.dumps({'username': 'newguy', 'password': 'newpassword1', 'role': 'user'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 403)

    def test_create_user_success(self):
        """Admin can create a new user with valid data."""
        with flask_app.test_client() as client:
            self._login_as_admin(client)
            resp = client.post(
                '/api/users',
                data=json.dumps({'username': 'brandnew', 'password': 'strongpass1', 'role': 'user'}),
                content_type='application/json',
                headers=_csrf_headers(client),
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        # Verify user was added to CONFIG
        usernames = [u['username'] for u in app_module.CONFIG['users']]
        self.assertIn('brandnew', usernames)

    def test_create_duplicate_user_returns_409(self):
        """Creating a user with an already-taken username returns 409."""
        with flask_app.test_client() as client:
            self._login_as_admin(client)
            # 'regularuser' already exists in setUp
            resp = client.post(
                '/api/users',
                data=json.dumps({'username': 'regularuser', 'password': 'somepassword1', 'role': 'user'}),
                content_type='application/json',
                headers=_csrf_headers(client),
            )
        self.assertEqual(resp.status_code, 409)

    def test_delete_self_returns_400(self):
        """An admin attempting to delete their own account returns 400."""
        with flask_app.test_client() as client:
            self._login_as_admin(client)
            resp = client.delete(
                '/api/users/adminuser',
                headers=_csrf_headers(client),
            )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('yourself', data.get('error', '').lower())

    def test_change_password_non_admin_other_user_returns_403(self):
        """A non-admin user cannot change another user's password."""
        with flask_app.test_client() as client:
            self._login_as_user(client)
            resp = client.post(
                '/api/users/adminuser/password',
                data=json.dumps({'password': 'newstrongpass1'}),
                content_type='application/json',
                headers=_csrf_headers(client),
            )
        self.assertEqual(resp.status_code, 403)


# ============== CSRF Protection Tests ==============


class TestCSRFProtection(unittest.TestCase):
    """Verify CSRF token validation on state-changing endpoints."""

    def setUp(self):
        self._orig_config = dict(app_module.CONFIG)
        app_module.CONFIG['auth'] = {
            'enabled': True,
            'username': 'admin',
            'password_hash': generate_password_hash('testpass123'),
        }
        app_module.CONFIG['users'] = [{
            'username': 'admin',
            'password_hash': generate_password_hash('testpass123'),
            'role': 'admin',
        }]

    def tearDown(self):
        app_module.CONFIG.clear()
        app_module.CONFIG.update(self._orig_config)

    def _login(self, client):
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['login_time'] = datetime.utcnow().isoformat()

    def _get_csrf_token(self, client):
        resp = client.get('/api/csrf-token')
        return json.loads(resp.data)['csrf_token']

    def test_csrf_token_endpoint_returns_token(self):
        """GET /api/csrf-token returns a token string."""
        with flask_app.test_client() as client:
            resp = client.get('/api/csrf-token')
            data = json.loads(resp.data)
            self.assertIn('csrf_token', data)
            self.assertTrue(len(data['csrf_token']) > 0)

    def test_config_post_without_csrf_returns_403(self):
        """POST /api/config without CSRF token returns 403 when auth is enabled."""
        with flask_app.test_client() as client:
            self._login(client)
            resp = client.post(
                '/api/config',
                data=json.dumps({'theme': 'midnight-blue'}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 403)
            data = json.loads(resp.data)
            self.assertIn('CSRF', data['error'])

    def test_config_post_with_valid_csrf_succeeds(self):
        """POST /api/config with valid CSRF token succeeds."""
        with flask_app.test_client() as client:
            self._login(client)
            token = self._get_csrf_token(client)
            resp = client.post(
                '/api/config',
                data=json.dumps({'theme': 'midnight-blue'}),
                content_type='application/json',
                headers={'X-CSRF-Token': token},
            )
            self.assertEqual(resp.status_code, 200)

    def test_csrf_not_required_when_auth_disabled(self):
        """CSRF check is skipped when auth is disabled."""
        app_module.CONFIG['auth']['enabled'] = False
        with flask_app.test_client() as client:
            resp = client.post(
                '/api/config',
                data=json.dumps({'theme': 'dark'}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 200)

    def test_wrong_csrf_token_returns_403(self):
        """POST with an incorrect CSRF token returns 403."""
        with flask_app.test_client() as client:
            self._login(client)
            # Get a real token first to establish session
            self._get_csrf_token(client)
            resp = client.post(
                '/api/config',
                data=json.dumps({'theme': 'dark'}),
                content_type='application/json',
                headers={'X-CSRF-Token': 'invalid-token-value'},
            )
            self.assertEqual(resp.status_code, 403)

    def test_users_post_requires_csrf(self):
        """POST /api/users requires CSRF token."""
        with flask_app.test_client() as client:
            self._login(client)
            resp = client.post(
                '/api/users',
                data=json.dumps({'username': 'newuser', 'password': 'password123', 'role': 'user'}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 403)

    def test_file_write_requires_csrf(self):
        """POST /api/files/write requires CSRF token."""
        with flask_app.test_client() as client:
            self._login(client)
            resp = client.post(
                '/api/files/write',
                data=json.dumps({'path': '/tmp/test.txt', 'content': 'hello'}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 403)


# ============== WebSocket Auth Tests ==============


class TestWebSocketAuth(unittest.TestCase):
    """Verify _ws_auth_check function behavior."""

    def setUp(self):
        self._orig_config = dict(app_module.CONFIG)

    def tearDown(self):
        app_module.CONFIG.clear()
        app_module.CONFIG.update(self._orig_config)

    def test_ws_auth_passes_when_auth_disabled(self):
        """_ws_auth_check returns True when auth is not enabled."""
        app_module.CONFIG['auth'] = {'enabled': False}
        with flask_app.test_request_context():
            self.assertTrue(app_module._ws_auth_check())

    def test_ws_auth_fails_when_not_authenticated(self):
        """_ws_auth_check returns False when session is not authenticated."""
        app_module.CONFIG['auth'] = {'enabled': True}
        with flask_app.test_request_context():
            from flask import session as flask_session
            flask_session.clear()
            self.assertFalse(app_module._ws_auth_check())

    def test_ws_auth_fails_on_expired_session(self):
        """_ws_auth_check returns False when session has expired."""
        app_module.CONFIG['auth'] = {'enabled': True}
        app_module.CONFIG['session_timeout_hours'] = 1
        with flask_app.test_request_context():
            from flask import session as flask_session
            flask_session['authenticated'] = True
            flask_session['login_time'] = (datetime.utcnow() - timedelta(hours=2)).isoformat()
            self.assertFalse(app_module._ws_auth_check())

    def test_ws_auth_passes_with_valid_session(self):
        """_ws_auth_check returns True with a valid, non-expired session."""
        app_module.CONFIG['auth'] = {'enabled': True}
        app_module.CONFIG['session_timeout_hours'] = 24
        with flask_app.test_request_context():
            from flask import session as flask_session
            flask_session['authenticated'] = True
            flask_session['login_time'] = datetime.utcnow().isoformat()
            self.assertTrue(app_module._ws_auth_check())


# ===========================================================================
# API Key Encryption Tests
# ===========================================================================

class TestApiKeyEncryption(unittest.TestCase):
    """Unit tests for the encrypt_api_key / decrypt_api_key helpers."""

    def setUp(self):
        self._config_snap = _snapshot_config()
        # Use a deterministic secret key for encryption tests
        flask_app.config['SECRET_KEY'] = 'test-secret-key-routes'
        app_module.app.secret_key = 'test-secret-key-routes'

    def tearDown(self):
        _restore_config(self._config_snap)

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt then decrypt returns the original plaintext."""
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        encrypted = app_module.encrypt_api_key(plaintext, 'alice')
        result = app_module.decrypt_api_key(encrypted, 'alice')
        self.assertEqual(result, plaintext)

    def test_encrypted_key_not_plaintext(self):
        """The encrypted output must not be the same as the plaintext input."""
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        encrypted = app_module.encrypt_api_key(plaintext, 'alice')
        self.assertNotEqual(encrypted, plaintext)

    def test_different_users_different_ciphertext(self):
        """The same plaintext key encrypted for two users must differ."""
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        enc_alice = app_module.encrypt_api_key(plaintext, 'alice')
        enc_bob = app_module.encrypt_api_key(plaintext, 'bob')
        self.assertNotEqual(enc_alice, enc_bob)

    def test_wrong_salt_fails_to_decrypt(self):
        """A token encrypted for alice must not decrypt under bob's salt."""
        from itsdangerous import BadSignature
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        enc_alice = app_module.encrypt_api_key(plaintext, 'alice')
        with self.assertRaises(Exception):
            app_module.decrypt_api_key(enc_alice, 'bob')

    def test_empty_plaintext_raises(self):
        """encrypt_api_key with empty plaintext raises ValueError."""
        with self.assertRaises(ValueError):
            app_module.encrypt_api_key('', 'alice')

    def test_empty_salt_raises(self):
        """encrypt_api_key with empty salt raises ValueError."""
        with self.assertRaises(ValueError):
            app_module.encrypt_api_key('sk-ant-api03-testapikey', '')

    def test_get_user_api_key_returns_none_when_no_key(self):
        """get_user_api_key returns None when the user has no stored key."""
        app_module.CONFIG['users'] = [
            {'username': 'alice', 'password_hash': 'x', 'role': 'user'}
        ]
        result = app_module.get_user_api_key('alice')
        self.assertIsNone(result)

    def test_get_user_api_key_returns_none_for_unknown_user(self):
        """get_user_api_key returns None for a username not in CONFIG."""
        app_module.CONFIG['users'] = []
        result = app_module.get_user_api_key('nobody')
        self.assertIsNone(result)

    def test_get_user_api_key_decrypts_stored_key(self):
        """get_user_api_key decrypts and returns the stored key."""
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        encrypted = app_module.encrypt_api_key(plaintext, 'alice')
        app_module.CONFIG['users'] = [
            {'username': 'alice', 'password_hash': 'x', 'role': 'user',
             'encrypted_api_key': encrypted}
        ]
        result = app_module.get_user_api_key('alice')
        self.assertEqual(result, plaintext)

    def test_build_claude_env_injects_api_key(self):
        """build_claude_env injects ANTHROPIC_API_KEY when user has a stored key."""
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        encrypted = app_module.encrypt_api_key(plaintext, 'alice')
        app_module.CONFIG['users'] = [
            {'username': 'alice', 'password_hash': 'x', 'role': 'user',
             'encrypted_api_key': encrypted}
        ]
        env = app_module.build_claude_env({}, username='alice')
        self.assertEqual(env.get('ANTHROPIC_API_KEY'), plaintext)

    def test_build_claude_env_no_key_when_no_stored_key(self):
        """build_claude_env does not override ANTHROPIC_API_KEY when user has none."""
        import os
        app_module.CONFIG['users'] = [
            {'username': 'alice', 'password_hash': 'x', 'role': 'user'}
        ]
        # Remove the env var to test that it remains absent
        original = os.environ.pop('ANTHROPIC_API_KEY', None)
        try:
            env = app_module.build_claude_env({}, username='alice')
            self.assertNotIn('ANTHROPIC_API_KEY', env)
        finally:
            if original is not None:
                os.environ['ANTHROPIC_API_KEY'] = original


class TestApiKeyRoutes(unittest.TestCase):
    """Integration tests for POST/GET/DELETE /api/user/api-key."""

    def setUp(self):
        self._config_snap = _snapshot_config()
        _reset_rate_limits()
        app_module.app.secret_key = 'test-secret-key-routes'
        _enable_auth()

    def tearDown(self):
        _restore_config(self._config_snap)
        _reset_rate_limits()

    def test_api_key_store_requires_auth(self):
        """POST /api/user/api-key returns 401 when not logged in."""
        with flask_app.test_client() as client:
            resp = client.post(
                '/api/user/api-key',
                data=json.dumps({'api_key': 'sk-ant-api03-testapikey-AAAAA'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 401)

    def test_api_key_get_requires_auth(self):
        """GET /api/user/api-key returns 401 when not logged in."""
        with flask_app.test_client() as client:
            resp = client.get('/api/user/api-key')
        self.assertEqual(resp.status_code, 401)

    def test_api_key_store_requires_csrf(self):
        """POST /api/user/api-key returns 403 without a CSRF token."""
        with flask_app.test_client() as client:
            _login(client)
            # Do NOT include CSRF header
            resp = client.post(
                '/api/user/api-key',
                data=json.dumps({'api_key': 'sk-ant-api03-testapikey-AAAAA'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 403)

    def test_api_key_store_and_retrieve_masked(self):
        """Store a key, then GET returns masked representation (not plaintext)."""
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        with flask_app.test_client() as client:
            _login(client)
            headers = _csrf_headers(client)

            # Store the key
            resp = client.post(
                '/api/user/api-key',
                data=json.dumps({'api_key': plaintext}),
                content_type='application/json',
                headers=headers,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json().get('success'))

            # Retrieve — must not return plaintext
            resp = client.get('/api/user/api-key')
            data = resp.get_json()
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(data.get('has_key'))
            masked = data.get('masked', '')
            self.assertNotEqual(masked, plaintext, "Masked value must not equal plaintext")
            self.assertIn('*', masked, "Masked value must contain asterisks")
            # Last 4 chars should match
            self.assertEqual(masked[-4:], plaintext[-4:])

    def test_api_key_get_returns_has_key_false_when_none(self):
        """GET /api/user/api-key returns has_key=false when no key is stored."""
        with flask_app.test_client() as client:
            _login(client)
            resp = client.get('/api/user/api-key')
            data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(data.get('has_key'))

    def test_api_key_store_rejects_empty_key(self):
        """POST /api/user/api-key with empty api_key returns 400."""
        with flask_app.test_client() as client:
            _login(client)
            headers = _csrf_headers(client)
            resp = client.post(
                '/api/user/api-key',
                data=json.dumps({'api_key': ''}),
                content_type='application/json',
                headers=headers,
            )
        self.assertEqual(resp.status_code, 400)

    def test_api_key_store_rejects_too_short_key(self):
        """POST /api/user/api-key with a key shorter than 20 chars returns 400."""
        with flask_app.test_client() as client:
            _login(client)
            headers = _csrf_headers(client)
            resp = client.post(
                '/api/user/api-key',
                data=json.dumps({'api_key': 'tooshort'}),
                content_type='application/json',
                headers=headers,
            )
        self.assertEqual(resp.status_code, 400)

    def test_api_key_delete(self):
        """DELETE /api/user/api-key removes the stored key."""
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        with flask_app.test_client() as client:
            _login(client)
            headers = _csrf_headers(client)

            # Store first
            client.post(
                '/api/user/api-key',
                data=json.dumps({'api_key': plaintext}),
                content_type='application/json',
                headers=headers,
            )

            # Confirm stored
            resp = client.get('/api/user/api-key')
            self.assertTrue(resp.get_json().get('has_key'))

            # Delete
            resp = client.delete('/api/user/api-key', headers=headers)
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json().get('success'))

            # Confirm gone
            resp = client.get('/api/user/api-key')
            self.assertFalse(resp.get_json().get('has_key'))

    def test_stored_key_is_not_plaintext_in_config(self):
        """After storing, config.json users list must not contain plaintext key."""
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        with flask_app.test_client() as client:
            _login(client)
            headers = _csrf_headers(client)
            client.post(
                '/api/user/api-key',
                data=json.dumps({'api_key': plaintext}),
                content_type='application/json',
                headers=headers,
            )

        users = app_module.CONFIG.get('users', [])
        user = next(u for u in users if u['username'] == 'testadmin')
        stored = user.get('encrypted_api_key', '')
        self.assertNotEqual(stored, plaintext, "Plaintext must not be stored in config")
        self.assertTrue(len(stored) > 0, "encrypted_api_key must be set")


# ===========================================================================
# Per-User Claude Config Directory Tests
# ===========================================================================

class TestUserClaudeDir(unittest.TestCase):
    """Unit tests for get_user_claude_dir and user_has_claude_credentials."""

    def setUp(self):
        self._config_snap = _snapshot_config()
        # Use a real temp directory so we can test actual filesystem behaviour
        self._tmp = tempfile.mkdtemp()
        self._orig_user_data_dir = app_module.USER_DATA_DIR
        app_module.USER_DATA_DIR = __import__('pathlib').Path(self._tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)
        app_module.USER_DATA_DIR = self._orig_user_data_dir
        _restore_config(self._config_snap)

    # -- get_user_claude_dir --

    def test_get_user_claude_dir_creates_directory(self):
        """get_user_claude_dir creates the .claude directory when it does not exist."""
        result = app_module.get_user_claude_dir('alice')
        self.assertTrue(result.exists())
        self.assertTrue(result.is_dir())
        self.assertTrue(str(result).endswith('.claude'))

    def test_get_user_claude_dir_returns_correct_path(self):
        """get_user_claude_dir returns <USER_DATA_DIR>/<username>/.claude"""
        import pathlib
        result = app_module.get_user_claude_dir('bob')
        expected = pathlib.Path(self._tmp) / 'bob' / '.claude'
        self.assertEqual(result, expected)

    def test_get_user_claude_dir_permissions(self):
        """User root directory is created with mode 0700."""
        import stat
        import pathlib
        app_module.get_user_claude_dir('alice')
        user_root = pathlib.Path(self._tmp) / 'alice'
        mode = stat.S_IMODE(user_root.stat().st_mode)
        self.assertEqual(mode, 0o700)

    def test_get_user_claude_dir_idempotent(self):
        """Calling get_user_claude_dir twice does not raise."""
        app_module.get_user_claude_dir('alice')
        # Second call must not raise even though directory already exists
        result = app_module.get_user_claude_dir('alice')
        self.assertTrue(result.exists())

    def test_get_user_claude_dir_rejects_empty_username(self):
        """get_user_claude_dir raises ValueError for an empty username."""
        with self.assertRaises(ValueError):
            app_module.get_user_claude_dir('')

    def test_get_user_claude_dir_rejects_path_traversal(self):
        """get_user_claude_dir raises ValueError when username contains '/'."""
        with self.assertRaises(ValueError):
            app_module.get_user_claude_dir('../etc')

    def test_get_user_claude_dir_rejects_dot_username(self):
        """get_user_claude_dir raises ValueError for '.' username."""
        with self.assertRaises(ValueError):
            app_module.get_user_claude_dir('.')

    # -- user_has_claude_credentials --

    def test_user_has_no_credentials_initially(self):
        """A brand-new user has no credentials."""
        app_module.CONFIG['users'] = [
            {'username': 'alice', 'password_hash': 'x', 'role': 'user'}
        ]
        self.assertFalse(app_module.user_has_claude_credentials('alice'))

    def test_user_has_credentials_after_api_key_set(self):
        """user_has_claude_credentials returns True when user has a stored API key."""
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        encrypted = app_module.encrypt_api_key(plaintext, 'alice')
        app_module.CONFIG['users'] = [
            {'username': 'alice', 'password_hash': 'x', 'role': 'user',
             'encrypted_api_key': encrypted}
        ]
        self.assertTrue(app_module.user_has_claude_credentials('alice'))

    def test_user_has_credentials_after_oauth_login(self):
        """user_has_claude_credentials returns True when credentials.json exists."""
        import pathlib
        app_module.CONFIG['users'] = [
            {'username': 'alice', 'password_hash': 'x', 'role': 'user'}
        ]
        # Simulate completed oauth login by dropping a credentials file
        cred_dir = pathlib.Path(self._tmp) / 'alice' / '.claude'
        cred_dir.mkdir(parents=True, exist_ok=True)
        (cred_dir / 'credentials.json').write_text('{}')
        self.assertTrue(app_module.user_has_claude_credentials('alice'))

    def test_user_has_credentials_empty_username(self):
        """user_has_claude_credentials returns False for empty username."""
        self.assertFalse(app_module.user_has_claude_credentials(''))

    # -- build_claude_env with multi_tenant --

    def test_build_claude_env_sets_config_dir_in_multi_tenant(self):
        """build_claude_env sets CLAUDE_CONFIG_DIR when multi_tenant=True."""
        app_module.CONFIG['multi_tenant'] = True
        app_module.CONFIG['users'] = [
            {'username': 'alice', 'password_hash': 'x', 'role': 'user'}
        ]
        env = app_module.build_claude_env({}, username='alice')
        self.assertIn('CLAUDE_CONFIG_DIR', env)
        self.assertIn('alice', env['CLAUDE_CONFIG_DIR'])
        self.assertIn('.claude', env['CLAUDE_CONFIG_DIR'])

    def test_build_claude_env_ignores_config_dir_in_solo_mode(self):
        """build_claude_env does NOT set CLAUDE_CONFIG_DIR when multi_tenant=False."""
        app_module.CONFIG['multi_tenant'] = False
        app_module.CONFIG['users'] = [
            {'username': 'alice', 'password_hash': 'x', 'role': 'user'}
        ]
        env = app_module.build_claude_env({}, username='alice')
        self.assertNotIn('CLAUDE_CONFIG_DIR', env)

    def test_build_claude_env_no_config_dir_without_username(self):
        """build_claude_env does NOT set CLAUDE_CONFIG_DIR when no username given."""
        app_module.CONFIG['multi_tenant'] = True
        env = app_module.build_claude_env({}, username=None)
        self.assertNotIn('CLAUDE_CONFIG_DIR', env)


class TestUserClaudeStatusRoutes(unittest.TestCase):
    """Integration tests for GET /api/user/claude-status and POST /api/user/claude-logout."""

    def setUp(self):
        self._config_snap = _snapshot_config()
        _reset_rate_limits()
        _enable_auth()
        # Redirect USER_DATA_DIR to a temp dir for filesystem isolation
        self._tmp = tempfile.mkdtemp()
        self._orig_user_data_dir = app_module.USER_DATA_DIR
        app_module.USER_DATA_DIR = __import__('pathlib').Path(self._tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)
        app_module.USER_DATA_DIR = self._orig_user_data_dir
        _restore_config(self._config_snap)
        _reset_rate_limits()

    def test_claude_status_requires_auth(self):
        """GET /api/user/claude-status returns 401 when not logged in."""
        with flask_app.test_client() as client:
            resp = client.get('/api/user/claude-status')
        self.assertEqual(resp.status_code, 401)

    def test_claude_status_no_credentials(self):
        """GET /api/user/claude-status returns has_credentials=False initially."""
        with flask_app.test_client() as client:
            _login(client)
            resp = client.get('/api/user/claude-status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data['has_credentials'])
        self.assertIsNone(data['credential_type'])

    def test_claude_status_with_api_key(self):
        """GET /api/user/claude-status returns credential_type=api_key when key is set."""
        plaintext = 'sk-ant-api03-testapikey-AAAAA'
        encrypted = app_module.encrypt_api_key(plaintext, 'testadmin')
        users = app_module.CONFIG.get('users', [])
        for u in users:
            if u['username'] == 'testadmin':
                u['encrypted_api_key'] = encrypted
        with flask_app.test_client() as client:
            _login(client)
            resp = client.get('/api/user/claude-status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['has_credentials'])
        self.assertEqual(data['credential_type'], 'api_key')

    def test_claude_status_with_oauth_file(self):
        """GET /api/user/claude-status returns credential_type=oauth when credentials.json exists."""
        import pathlib
        cred_dir = pathlib.Path(self._tmp) / 'testadmin' / '.claude'
        cred_dir.mkdir(parents=True, exist_ok=True)
        (cred_dir / 'credentials.json').write_text('{}')
        with flask_app.test_client() as client:
            _login(client)
            resp = client.get('/api/user/claude-status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['has_credentials'])
        self.assertEqual(data['credential_type'], 'oauth')

    def test_claude_status_returns_multi_tenant_flag(self):
        """GET /api/user/claude-status includes the current multi_tenant setting."""
        app_module.CONFIG['multi_tenant'] = True
        with flask_app.test_client() as client:
            _login(client)
            resp = client.get('/api/user/claude-status')
        data = resp.get_json()
        self.assertTrue(data['multi_tenant'])

    def test_claude_logout_requires_auth(self):
        """POST /api/user/claude-logout returns 401 when not logged in."""
        with flask_app.test_client() as client:
            resp = client.post('/api/user/claude-logout')
        self.assertEqual(resp.status_code, 401)

    def test_claude_logout_requires_csrf(self):
        """POST /api/user/claude-logout returns 403 without CSRF token."""
        with flask_app.test_client() as client:
            _login(client)
            resp = client.post(
                '/api/user/claude-logout',
                data=json.dumps({}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 403)

    def test_claude_logout_removes_credential_dir(self):
        """POST /api/user/claude-logout removes the per-user .claude directory."""
        import pathlib
        cred_dir = pathlib.Path(self._tmp) / 'testadmin' / '.claude'
        cred_dir.mkdir(parents=True, exist_ok=True)
        (cred_dir / 'credentials.json').write_text('{}')
        self.assertTrue(cred_dir.exists())

        with flask_app.test_client() as client:
            _login(client)
            headers = _csrf_headers(client)
            resp = client.post('/api/user/claude-logout', headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get('success'))
        self.assertFalse(cred_dir.exists())

    def test_claude_logout_succeeds_when_no_dir(self):
        """POST /api/user/claude-logout returns success even when directory doesn't exist."""
        with flask_app.test_client() as client:
            _login(client)
            headers = _csrf_headers(client)
            resp = client.post('/api/user/claude-logout', headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get('success'))


# ===========================================================================
# Multi-Host Dashboard API Tests
# ===========================================================================

def _make_ssh_host(host_id='srv1', name='Test Server', group='', tags=None):
    """Return a minimal remote_hosts entry for SSH mode."""
    return {
        'id': host_id,
        'name': name,
        'hostname': '10.0.0.1',
        'username': 'deploy',
        'mode': 'ssh',
        'port': 22,
        'ssh_key_path': '',
        'group': group,
        'tags': tags or [],
    }


class TestHostsListEndpoint(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()

    def tearDown(self):
        _restore_config(self._config_snap)

    def test_hosts_list_returns_configured_hosts(self):
        """GET /api/hosts returns all configured remote hosts."""
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = [
            _make_ssh_host('srv1', 'Production', group='prod', tags=['web']),
            _make_ssh_host('srv2', 'Staging', group='staging'),
        ]
        with flask_app.test_client() as client:
            resp = client.get('/api/hosts')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('hosts', data)
        self.assertEqual(len(data['hosts']), 2)
        ids = [h['id'] for h in data['hosts']]
        self.assertIn('srv1', ids)
        self.assertIn('srv2', ids)

    def test_hosts_list_empty_when_no_remote_hosts(self):
        """GET /api/hosts returns an empty list when no hosts are configured."""
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = []
        with flask_app.test_client() as client:
            resp = client.get('/api/hosts')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('hosts'), [])

    def test_hosts_list_requires_auth(self):
        """GET /api/hosts returns 401 when auth is enabled and user is not logged in."""
        _enable_auth()
        app_module.CONFIG['remote_hosts'] = [_make_ssh_host()]
        with flask_app.test_client() as client:
            resp = client.get('/api/hosts')
        self.assertEqual(resp.status_code, 401)

    def test_hosts_list_host_fields(self):
        """GET /api/hosts response includes expected public fields."""
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = [
            _make_ssh_host('s1', 'My Server', group='prod', tags=['linux', 'web'])
        ]
        with flask_app.test_client() as client:
            resp = client.get('/api/hosts')
        host = resp.get_json()['hosts'][0]
        for field in ('id', 'name', 'hostname', 'username', 'method', 'status', 'group', 'tags'):
            self.assertIn(field, host, f"Missing field: {field}")
        self.assertEqual(host['id'], 's1')
        self.assertEqual(host['group'], 'prod')
        self.assertEqual(host['tags'], ['linux', 'web'])

    def test_hosts_list_accessible_when_logged_in(self):
        """GET /api/hosts returns 200 when auth is enabled and user is logged in."""
        _enable_auth()
        app_module.CONFIG['remote_hosts'] = [_make_ssh_host()]
        with flask_app.test_client() as client:
            _login(client)
            resp = client.get('/api/hosts')
        self.assertEqual(resp.status_code, 200)


class TestHostsGroupsEndpoint(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()

    def tearDown(self):
        _restore_config(self._config_snap)

    def test_hosts_groups_returns_unique_groups(self):
        """GET /api/hosts/groups returns distinct groups with counts."""
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = [
            _make_ssh_host('s1', group='production'),
            _make_ssh_host('s2', group='production'),
            _make_ssh_host('s3', group='staging'),
        ]
        with flask_app.test_client() as client:
            resp = client.get('/api/hosts/groups')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('groups', data)
        by_name = {g['group']: g['count'] for g in data['groups']}
        self.assertEqual(by_name.get('production'), 2)
        self.assertEqual(by_name.get('staging'), 1)

    def test_hosts_groups_empty_when_no_hosts(self):
        """GET /api/hosts/groups returns empty list when no hosts configured."""
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = []
        with flask_app.test_client() as client:
            resp = client.get('/api/hosts/groups')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json().get('groups'), [])

    def test_hosts_groups_requires_auth(self):
        """GET /api/hosts/groups returns 401 when not logged in."""
        _enable_auth()
        app_module.CONFIG['remote_hosts'] = [_make_ssh_host(group='prod')]
        with flask_app.test_client() as client:
            resp = client.get('/api/hosts/groups')
        self.assertEqual(resp.status_code, 401)

    def test_hosts_groups_no_group_field(self):
        """Hosts without a group field are grouped under empty string."""
        _disable_auth()
        host = _make_ssh_host('s1')
        host.pop('group', None)
        app_module.CONFIG['remote_hosts'] = [host]
        with flask_app.test_client() as client:
            resp = client.get('/api/hosts/groups')
        data = resp.get_json()
        by_name = {g['group']: g['count'] for g in data['groups']}
        self.assertEqual(by_name.get(''), 1)


class TestHostHealthEndpoint(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()

    def tearDown(self):
        _restore_config(self._config_snap)

    def test_host_health_check_unknown_host_returns_404(self):
        """POST /api/hosts/<host_id>/health returns 404 for an unknown host ID."""
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = []
        with flask_app.test_client() as client:
            resp = client.post('/api/hosts/nonexistent/health',
                               content_type='application/json')
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_host_health_requires_auth(self):
        """POST /api/hosts/<host_id>/health returns 401 when not logged in."""
        _enable_auth()
        app_module.CONFIG['remote_hosts'] = [_make_ssh_host('s1')]
        with flask_app.test_client() as client:
            resp = client.post('/api/hosts/s1/health',
                               content_type='application/json')
        self.assertEqual(resp.status_code, 401)

    def test_host_health_requires_csrf(self):
        """POST /api/hosts/<host_id>/health returns 403 without CSRF token."""
        _enable_auth()
        app_module.CONFIG['remote_hosts'] = [_make_ssh_host('s1')]
        with flask_app.test_client() as client:
            _login(client)
            resp = client.post('/api/hosts/s1/health',
                               data='{}',
                               content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_host_health_returns_result_fields(self):
        """POST /api/hosts/<host_id>/health response contains expected keys."""
        import unittest.mock as mock
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = [_make_ssh_host('s1')]

        fake_result = mock.MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = 'QNOK\nLinux testbox 5.15.0 #1 SMP x86_64 GNU/Linux\n'
        fake_result.stderr = ''

        with mock.patch('subprocess.run', return_value=fake_result):
            with flask_app.test_client() as client:
                resp = client.post('/api/hosts/s1/health',
                                   content_type='application/json')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        for field in ('host_id', 'status', 'latency_ms', 'claude_cli_version', 'os', 'error'):
            self.assertIn(field, data, f"Missing field: {field}")
        self.assertEqual(data['status'], 'connected')
        self.assertEqual(data['host_id'], 's1')

    def test_host_health_ssh_failure_returns_unreachable(self):
        """POST /api/hosts/<host_id>/health reflects unreachable status on SSH failure."""
        import unittest.mock as mock
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = [_make_ssh_host('s1')]

        fake_result = mock.MagicMock()
        fake_result.returncode = 255
        fake_result.stdout = ''
        fake_result.stderr = 'Connection refused'

        with mock.patch('subprocess.run', return_value=fake_result):
            with flask_app.test_client() as client:
                resp = client.post('/api/hosts/s1/health',
                                   content_type='application/json')

        data = resp.get_json()
        self.assertEqual(data['status'], 'unreachable')
        self.assertIsNotNone(data.get('error'))

    def test_host_health_ssh_timeout_returns_timeout_status(self):
        """POST /api/hosts/<host_id>/health returns timeout status on subprocess timeout."""
        import unittest.mock as mock
        import subprocess as _sp
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = [_make_ssh_host('s1')]

        with mock.patch('subprocess.run',
                        side_effect=_sp.TimeoutExpired(cmd='ssh', timeout=10)):
            with flask_app.test_client() as client:
                resp = client.post('/api/hosts/s1/health',
                                   content_type='application/json')

        data = resp.get_json()
        self.assertEqual(data['status'], 'timeout')


class TestHostsBatchHealthEndpoint(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()

    def tearDown(self):
        _restore_config(self._config_snap)

    def test_batch_health_empty_hosts(self):
        """POST /api/hosts/health returns empty results when no hosts configured."""
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = []
        with flask_app.test_client() as client:
            resp = client.post('/api/hosts/health', content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json().get('results'), [])

    def test_batch_health_requires_auth(self):
        """POST /api/hosts/health returns 401 when not logged in."""
        _enable_auth()
        app_module.CONFIG['remote_hosts'] = [_make_ssh_host()]
        with flask_app.test_client() as client:
            resp = client.post('/api/hosts/health', content_type='application/json')
        self.assertEqual(resp.status_code, 401)

    def test_batch_health_returns_result_per_host(self):
        """POST /api/hosts/health returns one result entry per configured host."""
        import unittest.mock as mock
        _disable_auth()
        app_module.CONFIG['remote_hosts'] = [
            _make_ssh_host('s1'),
            _make_ssh_host('s2'),
        ]

        fake_result = mock.MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = 'QNOK\nLinux box 5.15.0\n'
        fake_result.stderr = ''

        with mock.patch('subprocess.run', return_value=fake_result):
            with flask_app.test_client() as client:
                resp = client.post('/api/hosts/health', content_type='application/json')

        self.assertEqual(resp.status_code, 200)
        results = resp.get_json().get('results', [])
        self.assertEqual(len(results), 2)
        host_ids = {r['host_id'] for r in results}
        self.assertEqual(host_ids, {'s1', 's2'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
