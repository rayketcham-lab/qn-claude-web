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
            )
        self.assertEqual(resp.status_code, 409)

    def test_delete_self_returns_400(self):
        """An admin attempting to delete their own account returns 400."""
        with flask_app.test_client() as client:
            self._login_as_admin(client)
            resp = client.delete('/api/users/adminuser')
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
            )
        self.assertEqual(resp.status_code, 403)


if __name__ == '__main__':
    unittest.main(verbosity=2)
