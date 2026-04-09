#!/usr/bin/env python3
"""
Tests for the Cloudflare Tunnel feature.

Covers:
  - _detect_cloudflared (installed / not installed)
  - _tunnel_status (not available, available but not running)
  - API auth gates for /api/tunnel/start and /api/tunnel/stop

Run with:
    /usr/bin/python3 -m unittest tests/test_tunnel.py -v
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
flask_app.config['SECRET_KEY'] = 'test-secret-key-tunnel'


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_routes.py)
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


def _enable_auth_admin(username='tunnelAdmin', password='adminpass123'):
    pw_hash = generate_password_hash(password)
    app_module.AUTH['auth'] = {
        'enabled': True,
        'username': username,
        'password_hash': pw_hash,
    }
    app_module.AUTH['users'] = [
        {'username': username, 'password_hash': pw_hash, 'role': 'admin'}
    ]


def _enable_auth_user(username='regularUser', password='userpass123'):
    pw_hash = generate_password_hash(password)
    app_module.AUTH['auth'] = {
        'enabled': True,
        'username': username,
        'password_hash': pw_hash,
    }
    app_module.AUTH['users'] = [
        {'username': username, 'password_hash': pw_hash, 'role': 'user'}
    ]


def _disable_auth():
    app_module.AUTH['auth'] = {'enabled': False, 'username': '', 'password_hash': ''}
    app_module.AUTH['users'] = []


def _login(client, username, password):
    return client.post(
        '/login',
        data=json.dumps({'username': username, 'password': password}),
        content_type='application/json',
    )


def _get_csrf(client):
    resp = client.get('/api/csrf-token')
    return json.loads(resp.data)['csrf_token']


def _csrf_headers(client):
    return {'X-CSRF-Token': _get_csrf(client)}


# ---------------------------------------------------------------------------
# _detect_cloudflared unit tests
# ---------------------------------------------------------------------------

class TestDetectCloudflared(unittest.TestCase):
    """Unit tests for _detect_cloudflared()."""

    def test_detect_cloudflared_not_installed(self):
        """Returns None when shutil.which finds no cloudflared binary."""
        with patch('app._shutil.which', return_value=None) as mock_which:
            result = app_module._detect_cloudflared()
        mock_which.assert_called_once_with('cloudflared')
        self.assertIsNone(result)

    def test_detect_cloudflared_installed(self):
        """Returns the binary path when shutil.which finds cloudflared."""
        fake_path = '/usr/local/bin/cloudflared'
        with patch('app._shutil.which', return_value=fake_path) as mock_which:
            result = app_module._detect_cloudflared()
        mock_which.assert_called_once_with('cloudflared')
        self.assertEqual(result, fake_path)


# ---------------------------------------------------------------------------
# _tunnel_status unit tests
# ---------------------------------------------------------------------------

class TestTunnelStatus(unittest.TestCase):
    """Unit tests for _tunnel_status()."""

    def setUp(self):
        # Reset tunnel state before each test
        app_module._tunnel_process = None
        app_module._tunnel_url = None

    def tearDown(self):
        app_module._tunnel_process = None
        app_module._tunnel_url = None

    def test_tunnel_status_not_available(self):
        """Returns available=False when cloudflared is not installed."""
        with patch('app._shutil.which', return_value=None):
            status = app_module._tunnel_status()
        self.assertFalse(status['available'])
        self.assertFalse(status['running'])
        self.assertIsNone(status['url'])

    def test_tunnel_status_available_not_running(self):
        """Returns available=True, running=False when cloudflared is installed but not running."""
        with patch('app._shutil.which', return_value='/usr/local/bin/cloudflared'):
            status = app_module._tunnel_status()
        self.assertTrue(status['available'])
        self.assertFalse(status['running'])
        self.assertIsNone(status['url'])

    def test_tunnel_status_available_and_running(self):
        """Returns running=True and the URL when a tunnel process is active."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # process is alive
        app_module._tunnel_process = mock_proc
        app_module._tunnel_url = 'https://test-tunnel.trycloudflare.com'

        with patch('app._shutil.which', return_value='/usr/local/bin/cloudflared'):
            status = app_module._tunnel_status()

        self.assertTrue(status['available'])
        self.assertTrue(status['running'])
        self.assertEqual(status['url'], 'https://test-tunnel.trycloudflare.com')

    def test_tunnel_status_process_exited(self):
        """Returns running=False if the process has exited (poll returns non-None)."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # process has exited
        app_module._tunnel_process = mock_proc
        app_module._tunnel_url = 'https://dead-tunnel.trycloudflare.com'

        with patch('app._shutil.which', return_value='/usr/local/bin/cloudflared'):
            status = app_module._tunnel_status()

        self.assertFalse(status['running'])
        self.assertIsNone(status['url'])


# ---------------------------------------------------------------------------
# API auth gate tests
# ---------------------------------------------------------------------------

class TestTunnelStartRequiresAdmin(unittest.TestCase):
    """POST /api/tunnel/start must reject non-admin and unauthenticated callers."""

    def setUp(self):
        self._snap = _snapshot_config()
        app_module._tunnel_process = None
        app_module._tunnel_url = None

    def tearDown(self):
        _restore_config(self._snap)
        app_module._tunnel_process = None
        app_module._tunnel_url = None

    def test_tunnel_start_requires_auth(self):
        """POST /api/tunnel/start returns 401 when not logged in."""
        _enable_auth_admin()
        with flask_app.test_client() as client:
            headers = _csrf_headers(client)
            resp = client.post('/api/v1/tunnel/start',
                               headers=headers,
                               content_type='application/json')
        self.assertEqual(resp.status_code, 401)

    def test_tunnel_start_requires_admin(self):
        """POST /api/tunnel/start returns 403 for a non-admin user."""
        _enable_auth_user()
        with flask_app.test_client() as client:
            _login(client, 'regularUser', 'userpass123')
            headers = _csrf_headers(client)
            resp = client.post('/api/v1/tunnel/start',
                               headers=headers,
                               content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_tunnel_start_returns_503_when_cloudflared_missing(self):
        """POST /api/tunnel/start returns 503 when cloudflared is not installed."""
        _enable_auth_admin()
        with flask_app.test_client() as client:
            _login(client, 'tunnelAdmin', 'adminpass123')
            headers = _csrf_headers(client)
            with patch('app._shutil.which', return_value=None):
                resp = client.post('/api/v1/tunnel/start',
                                   headers=headers,
                                   content_type='application/json')
        self.assertEqual(resp.status_code, 503)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_tunnel_start_no_csrf_rejected(self):
        """POST /api/tunnel/start without CSRF token returns 403."""
        _enable_auth_admin()
        with flask_app.test_client() as client:
            _login(client, 'tunnelAdmin', 'adminpass123')
            resp = client.post('/api/v1/tunnel/start',
                               data=json.dumps({}),
                               content_type='application/json')
        self.assertEqual(resp.status_code, 403)


class TestTunnelStopRequiresAdmin(unittest.TestCase):
    """POST /api/tunnel/stop must reject non-admin and unauthenticated callers."""

    def setUp(self):
        self._snap = _snapshot_config()
        app_module._tunnel_process = None
        app_module._tunnel_url = None

    def tearDown(self):
        _restore_config(self._snap)
        app_module._tunnel_process = None
        app_module._tunnel_url = None

    def test_tunnel_stop_requires_auth(self):
        """POST /api/tunnel/stop returns 401 when not logged in."""
        _enable_auth_admin()
        with flask_app.test_client() as client:
            headers = _csrf_headers(client)
            resp = client.post('/api/v1/tunnel/stop',
                               headers=headers,
                               content_type='application/json')
        self.assertEqual(resp.status_code, 401)

    def test_tunnel_stop_requires_admin(self):
        """POST /api/tunnel/stop returns 403 for a non-admin user."""
        _enable_auth_user()
        with flask_app.test_client() as client:
            _login(client, 'regularUser', 'userpass123')
            headers = _csrf_headers(client)
            resp = client.post('/api/v1/tunnel/stop',
                               headers=headers,
                               content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_tunnel_stop_no_csrf_rejected(self):
        """POST /api/tunnel/stop without CSRF token returns 403."""
        _enable_auth_admin()
        with flask_app.test_client() as client:
            _login(client, 'tunnelAdmin', 'adminpass123')
            resp = client.post('/api/v1/tunnel/stop',
                               data=json.dumps({}),
                               content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_tunnel_stop_when_not_running(self):
        """POST /api/tunnel/stop when no tunnel is running returns running=False."""
        _enable_auth_admin()
        with flask_app.test_client() as client:
            _login(client, 'tunnelAdmin', 'adminpass123')
            headers = _csrf_headers(client)
            with patch('app._shutil.which', return_value='/usr/local/bin/cloudflared'):
                resp = client.post('/api/v1/tunnel/stop',
                                   data=json.dumps({}),
                                   headers=headers,
                                   content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data['running'])
        self.assertIsNone(data['url'])


# ---------------------------------------------------------------------------
# API status endpoint
# ---------------------------------------------------------------------------

class TestTunnelStatusEndpoint(unittest.TestCase):
    """GET /api/tunnel/status endpoint tests."""

    def setUp(self):
        self._snap = _snapshot_config()
        app_module._tunnel_process = None
        app_module._tunnel_url = None

    def tearDown(self):
        _restore_config(self._snap)
        app_module._tunnel_process = None
        app_module._tunnel_url = None

    def test_status_endpoint_requires_login(self):
        """GET /api/tunnel/status returns 401 when auth is enabled and not logged in."""
        _enable_auth_admin()
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/tunnel/status')
        self.assertEqual(resp.status_code, 401)

    def test_status_endpoint_cloudflared_not_available(self):
        """GET /api/tunnel/status returns available=False when cloudflared is missing."""
        _disable_auth()
        with flask_app.test_client() as client:
            with patch('app._shutil.which', return_value=None):
                resp = client.get('/api/v1/tunnel/status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data['available'])
        self.assertFalse(data['running'])
        self.assertIsNone(data['url'])

    def test_status_endpoint_cloudflared_available_not_running(self):
        """GET /api/tunnel/status returns available=True, running=False when installed but idle."""
        _disable_auth()
        with flask_app.test_client() as client:
            with patch('app._shutil.which', return_value='/usr/local/bin/cloudflared'):
                resp = client.get('/api/v1/tunnel/status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['available'])
        self.assertFalse(data['running'])
        self.assertIsNone(data['url'])


if __name__ == '__main__':
    unittest.main()
