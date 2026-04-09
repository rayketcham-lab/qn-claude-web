#!/usr/bin/env python3
"""
TDD tests for auth reload bug.

Root cause: save_auth() writes to auth.json but does NOT update the global
AUTH dict in memory.  External edits to auth.json (or save_auth calls from
non-UI paths) leave the running app with stale credentials.

These tests define the expected behaviour:
  1. save_auth() must update the in-memory AUTH dict.
  2. load_auth() must be callable to re-read auth.json at runtime.
  3. A POST /api/v1/auth/reload endpoint (admin-only) must re-read auth.json.
  4. Login must work immediately after save_auth() — no restart needed.
"""

import json
import os
import sys
import tempfile
import unittest

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
flask_app.config['SECRET_KEY'] = 'test-secret-auth-reload'


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_routes.py)
# ---------------------------------------------------------------------------

def _snapshot():
    config_snap = dict(app_module.CONFIG)
    auth_snap = dict(app_module.AUTH)
    auth_snap['auth'] = dict(app_module.AUTH.get('auth', {}))
    auth_snap['users'] = [dict(u) for u in app_module.AUTH.get('users', [])]
    return config_snap, auth_snap


def _restore(snap):
    config_snap, auth_snap = snap
    app_module.CONFIG.clear()
    app_module.CONFIG.update(config_snap)
    app_module.AUTH.clear()
    app_module.AUTH.update(auth_snap)


def _reset_rate_limits():
    with app_module._rate_limit_lock:
        app_module._rate_limit_store.clear()
    with app_module._lockout_lock:
        app_module._lockout_store.clear()


def _enable_auth(username='admin', password='oldpass'):
    pw_hash = generate_password_hash(password)
    app_module.AUTH['auth'] = {
        'enabled': True,
        'username': username,
        'password_hash': pw_hash,
        'role': 'admin',
    }
    app_module.AUTH['users'] = [
        {'username': username, 'password_hash': pw_hash, 'role': 'admin'}
    ]


def _login(client, username, password):
    return client.post(
        '/login',
        data=json.dumps({'username': username, 'password': password}),
        content_type='application/json',
    )


def _get_csrf(client):
    resp = client.get('/api/csrf-token')
    return json.loads(resp.data)['csrf_token']


# ===========================================================================
# Test Cases
# ===========================================================================

class TestSaveAuthUpdatesMemory(unittest.TestCase):
    """save_auth() must update the in-memory AUTH dict, not just the file."""

    def setUp(self):
        self._snap = _snapshot()
        _reset_rate_limits()

    def tearDown(self):
        _restore(self._snap)
        _reset_rate_limits()

    def test_save_auth_updates_in_memory_auth(self):
        """After save_auth(new_dict), AUTH should reflect the new dict."""
        _enable_auth('admin', 'oldpass')
        new_hash = generate_password_hash('newpass')

        new_auth = dict(app_module.AUTH)
        new_auth['auth'] = dict(new_auth['auth'])
        new_auth['auth']['password_hash'] = new_hash
        new_auth['users'] = [
            {'username': 'admin', 'password_hash': new_hash, 'role': 'admin'}
        ]

        app_module.save_auth(new_auth)

        # The in-memory AUTH must now have the new hash
        self.assertEqual(app_module.AUTH['auth']['password_hash'], new_hash)
        self.assertEqual(app_module.AUTH['users'][0]['password_hash'], new_hash)

    def test_login_works_after_save_auth(self):
        """Login must succeed immediately after save_auth changes the password."""
        _enable_auth('admin', 'oldpass')
        new_hash = generate_password_hash('newpass')

        new_auth = dict(app_module.AUTH)
        new_auth['auth'] = dict(new_auth['auth'])
        new_auth['auth']['password_hash'] = new_hash
        new_auth['users'] = [
            {'username': 'admin', 'password_hash': new_hash, 'role': 'admin'}
        ]
        app_module.save_auth(new_auth)

        with flask_app.test_client() as client:
            # New password should succeed
            resp = _login(client, 'admin', 'newpass')
            data = json.loads(resp.data)
            self.assertTrue(data.get('success'), f"Login with new password failed: {data}")

        with flask_app.test_client() as client:
            # Old password should fail
            resp = _login(client, 'admin', 'oldpass')
            self.assertEqual(resp.status_code, 401, "Old password still works after save_auth")


class TestAuthReloadEndpoint(unittest.TestCase):
    """POST /api/v1/auth/reload should re-read auth.json into memory."""

    def setUp(self):
        self._snap = _snapshot()
        _reset_rate_limits()

    def tearDown(self):
        _restore(self._snap)
        _reset_rate_limits()

    def test_reload_endpoint_exists(self):
        """POST /api/v1/auth/reload must return 200 for an admin."""
        _enable_auth('admin', 'testpass')
        with flask_app.test_client() as client:
            _login(client, 'admin', 'testpass')
            csrf = _get_csrf(client)
            resp = client.post('/api/v1/auth/reload',
                               headers={'X-CSRF-Token': csrf})
            self.assertEqual(resp.status_code, 200,
                             f"Expected 200 but got {resp.status_code}")

    def test_reload_requires_admin(self):
        """Non-admin users must get 403 from auth/reload."""
        _enable_auth('admin', 'testpass')
        # Add a non-admin user
        non_admin_hash = generate_password_hash('userpass')
        app_module.AUTH['users'].append(
            {'username': 'regularuser', 'password_hash': non_admin_hash, 'role': 'user'}
        )
        with flask_app.test_client() as client:
            _login(client, 'regularuser', 'userpass')
            csrf = _get_csrf(client)
            resp = client.post('/api/v1/auth/reload',
                               headers={'X-CSRF-Token': csrf})
            self.assertEqual(resp.status_code, 403)


if __name__ == '__main__':
    unittest.main()
