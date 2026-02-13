#!/usr/bin/env python3
"""
HTTP-level integration tests for QN Code Assistant.

Probes the running app via HTTP to verify public endpoints, security headers,
auth enforcement, rate limiting, and authenticated endpoints.

Non-destructive: uses only GET requests and POST to /login.

Configuration via environment variables:
    QN_TEST_URL       - Base URL of the running server (default: http://192.168.1.241:5001)
    QN_TEST_USERNAME  - Username for authenticated endpoint tests (optional)
    QN_TEST_PASSWORD  - Password for authenticated endpoint tests (optional)

Usage:
    python3 tests/test_integration.py
    QN_TEST_URL=http://localhost:5001 python3 tests/test_integration.py
"""

import http.cookiejar
import json
import os
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple

# Simple response container
Response = namedtuple('Response', ['status', 'headers', 'body'])


class IntegrationTestBase(unittest.TestCase):
    """Base class with shared helpers for integration tests."""

    BASE_URL = None

    @classmethod
    def setUpClass(cls):
        cls.BASE_URL = os.environ.get('QN_TEST_URL', 'http://192.168.1.241:5001').rstrip('/')

    def _request(self, path, method='GET', data=None, headers=None, opener=None):
        """Issue an HTTP request and return a Response namedtuple.

        Args:
            path: URL path (e.g. '/api/status'). Joined with BASE_URL.
            method: HTTP method (GET, POST, etc.).
            data: Dict to send as JSON body (POST only).
            headers: Optional dict of extra headers.
            opener: Optional urllib opener (for session/cookie management).

        Returns:
            Response(status, headers, body) where body is the decoded string.
        """
        url = self.BASE_URL + path
        encoded_data = None
        if data is not None:
            encoded_data = json.dumps(data).encode('utf-8')

        req = urllib.request.Request(url, data=encoded_data, method=method)
        req.add_header('User-Agent', 'QN-Integration-Test/1.0')
        if encoded_data is not None:
            req.add_header('Content-Type', 'application/json')
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)

        do_open = opener.open if opener else urllib.request.urlopen
        try:
            resp = do_open(req, timeout=15)
            return Response(
                status=resp.getcode(),
                headers=resp.headers,
                body=resp.read().decode('utf-8', errors='replace'),
            )
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode('utf-8', errors='replace')
            except Exception:
                pass
            return Response(status=e.code, headers=e.headers, body=body)
        except urllib.error.URLError as e:
            self.fail(f"Connection failed for {method} {url}: {e.reason}")


# ===================================================================
# 1. TestPublicEndpoints
# ===================================================================
class TestPublicEndpoints(IntegrationTestBase):
    """Test endpoints that should be accessible without authentication."""

    def test_auth_status_returns_json_with_auth_enabled(self):
        """/api/auth/status returns JSON with auth_enabled field."""
        resp = self._request('/api/auth/status')
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.body)
        self.assertIn('auth_enabled', data)
        self.assertIsInstance(data['auth_enabled'], bool)

    def test_login_returns_200_with_form(self):
        """/login returns 200 with HTML containing a form."""
        resp = self._request('/login')
        # When auth is disabled, /login redirects to / which may then
        # redirect back to /login. Either way we should get 200 eventually,
        # or a redirect (302). Accept both.
        self.assertIn(resp.status, (200, 302))
        if resp.status == 200:
            self.assertIn('<form', resp.body.lower())

    def test_api_status_returns_version_info(self):
        """/api/status returns version info (200 if no auth, 401 if auth enabled)."""
        resp = self._request('/api/status')
        self.assertIn(resp.status, (200, 401))
        if resp.status == 200:
            data = json.loads(resp.body)
            self.assertIn('version', data)


# ===================================================================
# 2. TestSecurityHeaders
# ===================================================================
class TestSecurityHeaders(IntegrationTestBase):
    """Verify security headers are present on responses."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Fetch a public endpoint once and reuse headers for all tests
        url = cls.BASE_URL + '/api/auth/status'
        try:
            resp = urllib.request.urlopen(url, timeout=15)
            cls._headers = resp.headers
            resp.read()
        except urllib.error.HTTPError as e:
            cls._headers = e.headers
            try:
                e.read()
            except Exception:
                pass
        except urllib.error.URLError as e:
            raise unittest.SkipTest(f"Server not reachable: {e.reason}")

    def test_x_content_type_options_nosniff(self):
        """X-Content-Type-Options must be 'nosniff'."""
        value = self._headers.get('X-Content-Type-Options')
        self.assertIsNotNone(value, 'X-Content-Type-Options header missing')
        self.assertEqual(value, 'nosniff')

    def test_x_frame_options_present(self):
        """X-Frame-Options must be DENY or SAMEORIGIN."""
        value = self._headers.get('X-Frame-Options')
        self.assertIsNotNone(value, 'X-Frame-Options header missing')
        self.assertIn(value.upper(), ('DENY', 'SAMEORIGIN'))

    def test_content_security_policy_present(self):
        """Content-Security-Policy header must be present."""
        value = self._headers.get('Content-Security-Policy')
        self.assertIsNotNone(value, 'Content-Security-Policy header missing')
        self.assertTrue(len(value) > 0)

    def test_referrer_policy_present(self):
        """Referrer-Policy header must be present."""
        value = self._headers.get('Referrer-Policy')
        self.assertIsNotNone(value, 'Referrer-Policy header missing')
        self.assertTrue(len(value) > 0)

    def test_server_header_no_werkzeug(self):
        """Server header must NOT contain 'Werkzeug'."""
        value = self._headers.get('Server', '')
        self.assertNotIn('Werkzeug', value,
                         f'Server header leaks Werkzeug: {value}')

    def test_server_header_no_python(self):
        """Server header must NOT contain 'Python'."""
        value = self._headers.get('Server', '')
        self.assertNotIn('Python', value,
                         f'Server header leaks Python version: {value}')

    def test_server_header_is_qn_code_assistant(self):
        """Server header should be 'QN Code Assistant'."""
        value = self._headers.get('Server', '').strip()
        self.assertEqual(value, 'QN Code Assistant',
                         f'Expected "QN Code Assistant", got "{value}"')


# ===================================================================
# 3. TestAuthEnforcement
# ===================================================================
class TestAuthEnforcement(IntegrationTestBase):
    """Protected endpoints must return 401 or 302 when not authenticated."""

    PROTECTED_ENDPOINTS = [
        '/api/files?path=/opt',
        '/api/files/read?path=/opt/test',
        '/api/git/status?path=/opt',
        '/api/git/diff?path=/opt',
        '/api/config',
        '/api/agents/library',
        '/api/changelog',
        '/api/usage',
        '/api/terminals',
    ]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Check if auth is even enabled — if not, skip this entire class
        url = cls.BASE_URL + '/api/auth/status'
        try:
            resp = urllib.request.urlopen(url, timeout=15)
            data = json.loads(resp.read().decode('utf-8'))
            if not data.get('auth_enabled', False):
                raise unittest.SkipTest(
                    'Auth is not enabled on the server — '
                    'auth enforcement tests are not applicable'
                )
        except urllib.error.URLError as e:
            raise unittest.SkipTest(f"Server not reachable: {e.reason}")

    def _assert_auth_required(self, path):
        """Assert that the endpoint requires authentication."""
        resp = self._request(path)
        self.assertIn(
            resp.status, (401, 302),
            f'{path} returned {resp.status}, expected 401 or 302'
        )

    def test_files_endpoint_requires_auth(self):
        self._assert_auth_required('/api/files?path=/opt')

    def test_files_read_endpoint_requires_auth(self):
        self._assert_auth_required('/api/files/read?path=/opt/test')

    def test_git_status_endpoint_requires_auth(self):
        self._assert_auth_required('/api/git/status?path=/opt')

    def test_git_diff_endpoint_requires_auth(self):
        self._assert_auth_required('/api/git/diff?path=/opt')

    def test_config_endpoint_requires_auth(self):
        self._assert_auth_required('/api/config')

    def test_agents_library_endpoint_requires_auth(self):
        self._assert_auth_required('/api/agents/library')

    def test_changelog_endpoint_requires_auth(self):
        self._assert_auth_required('/api/changelog')

    def test_usage_endpoint_requires_auth(self):
        self._assert_auth_required('/api/usage')

    def test_terminals_endpoint_requires_auth(self):
        self._assert_auth_required('/api/terminals')

    def test_tmux_sessions_endpoint_requires_auth(self):
        self._assert_auth_required('/api/tmux/sessions')


# ===================================================================
# 4. TestRateLimiting
# ===================================================================
class TestRateLimiting(IntegrationTestBase):
    """Verify that the login endpoint enforces rate limiting.

    The server allows 10 login attempts per 5 minutes per IP.
    Sending 12 rapid requests should trigger at least one 429 response.
    """

    def test_login_rate_limit_triggers_429(self):
        """Rapid failed login attempts should eventually return 429."""
        got_429 = False
        bad_creds = {'username': 'nonexistent_test_user', 'password': 'wrong_password'}

        for i in range(12):
            resp = self._request('/login', method='POST', data=bad_creds)
            if resp.status == 429:
                got_429 = True
                break

        self.assertTrue(
            got_429,
            'Expected at least one 429 (Too Many Requests) response '
            'after 12 rapid login attempts, but none received. '
            'Rate limiting may be disabled or the threshold has not been reached.'
        )


# ===================================================================
# 5. TestAuthenticatedEndpoints
# ===================================================================
class TestAuthenticatedEndpoints(IntegrationTestBase):
    """Test endpoints that require authentication.

    Skipped unless QN_TEST_USERNAME and QN_TEST_PASSWORD env vars are set.
    """

    _opener = None
    _logged_in = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        username = os.environ.get('QN_TEST_USERNAME')
        password = os.environ.get('QN_TEST_PASSWORD')
        if not username or not password:
            raise unittest.SkipTest(
                'QN_TEST_USERNAME and QN_TEST_PASSWORD env vars not set — '
                'skipping authenticated endpoint tests'
            )

        # Build an opener with cookie support for session management
        cookie_jar = http.cookiejar.CookieJar()
        cls._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar)
        )

        # Perform login
        login_url = cls.BASE_URL + '/login'
        login_data = json.dumps({
            'username': username,
            'password': password,
        }).encode('utf-8')
        req = urllib.request.Request(login_url, data=login_data, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('User-Agent', 'QN-Integration-Test/1.0')

        try:
            resp = cls._opener.open(req, timeout=15)
            body = resp.read().decode('utf-8')
            data = json.loads(body)
            if data.get('success'):
                cls._logged_in = True
            else:
                raise unittest.SkipTest(
                    f'Login failed: {data.get("error", "unknown error")}'
                )
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            raise unittest.SkipTest(f'Login request failed (HTTP {e.code}): {body}')
        except urllib.error.URLError as e:
            raise unittest.SkipTest(f'Server not reachable: {e.reason}')

    def _auth_request(self, path, method='GET', data=None):
        """Issue an authenticated request using the session opener."""
        self.assertTrue(self._logged_in, 'Not logged in — cannot run authenticated tests')
        return self._request(path, method=method, data=data, opener=self._opener)

    def test_api_status_returns_version(self):
        """GET /api/status returns 200 with 'version' field."""
        resp = self._auth_request('/api/status')
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.body)
        self.assertIn('version', data)
        self.assertTrue(len(data['version']) > 0)

    def test_api_config_returns_json(self):
        """GET /api/config returns 200 with JSON body."""
        resp = self._auth_request('/api/config')
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.body)
        self.assertIsInstance(data, dict)

    def test_api_agents_library_returns_agents_list(self):
        """GET /api/agents/library returns 200 with agents list."""
        resp = self._auth_request('/api/agents/library')
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.body)
        self.assertIn('agents', data)
        self.assertIsInstance(data['agents'], list)

    def test_api_changelog_returns_content(self):
        """GET /api/changelog returns 200 with content."""
        resp = self._auth_request('/api/changelog')
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.body)
        self.assertIn('content', data)
        self.assertTrue(len(data['content']) > 0)


# ===================================================================
# Runner
# ===================================================================
if __name__ == '__main__':
    unittest.main()
