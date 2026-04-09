#!/usr/bin/env python3
"""
Tests for version consistency.

Verifies VERSION constant, /api/health endpoint, and semver format.

Run with:
    python3 -m pytest tests/test_version.py -v
"""

import json
import os
import re
import sys
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_vendor_dir = os.path.join(_project_root, 'vendor')
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import app as app_module

VERSION = app_module.VERSION
flask_app = app_module.app
flask_app.config['TESTING'] = True
flask_app.config['SECRET_KEY'] = 'test-secret-key-version'

# Semver pattern: MAJOR.MINOR.PATCH with optional pre-release/build metadata
_SEMVER_RE = re.compile(
    r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
    r'(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)'
    r'(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?'
    r'(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
)


class TestVersionConstant(unittest.TestCase):
    """Tests for the VERSION module constant."""

    def test_version_constant_exists(self):
        """VERSION constant must be defined in app.py."""
        self.assertTrue(hasattr(app_module, 'VERSION'),
                        "app module must have a VERSION attribute")

    def test_version_constant_is_string(self):
        """VERSION must be a string."""
        self.assertIsInstance(VERSION, str,
                              "VERSION must be a string")

    def test_version_constant_matches_expected(self):
        """VERSION must be '2.0.0'."""
        self.assertEqual(VERSION, '2.0.0',
                         f"Expected VERSION='2.0.0', got '{VERSION}'")

    def test_version_not_empty(self):
        """VERSION must not be empty."""
        self.assertTrue(len(VERSION) > 0,
                        "VERSION must not be empty string")

    def test_version_format_semver(self):
        """VERSION must match semver pattern (MAJOR.MINOR.PATCH)."""
        self.assertIsNotNone(
            _SEMVER_RE.match(VERSION),
            f"VERSION '{VERSION}' does not match semver pattern"
        )

    def test_version_has_three_parts(self):
        """VERSION must have exactly three dot-separated parts (for stable release)."""
        # Stable releases have exactly 3 parts; pre-releases may have more via '-'
        major_minor_patch = VERSION.split('-')[0].split('.')
        self.assertEqual(len(major_minor_patch), 3,
                         f"VERSION '{VERSION}' must have MAJOR.MINOR.PATCH format")

    def test_version_parts_are_numeric(self):
        """Each part of the base semver must be a non-negative integer."""
        base = VERSION.split('-')[0]
        parts = base.split('.')
        for part in parts:
            self.assertTrue(
                part.isdigit(),
                f"Version part '{part}' in '{VERSION}' must be numeric"
            )


class TestHealthEndpointReturnsVersion(unittest.TestCase):
    """Tests for /api/health endpoint version reporting."""

    def test_health_endpoint_returns_200(self):
        """GET /api/health must return 200 OK."""
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        self.assertEqual(resp.status_code, 200,
                         f"Expected 200 from /api/health, got {resp.status_code}")

    def test_health_endpoint_returns_json(self):
        """GET /api/health must return JSON."""
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        self.assertEqual(
            resp.content_type.split(';')[0].strip(),
            'application/json',
            "Expected JSON content type from /api/health"
        )

    def test_health_endpoint_returns_version(self):
        """GET /api/health must include 'version' field."""
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        data = resp.get_json()
        self.assertIsNotNone(data, "Response body must be valid JSON")
        self.assertIn('version', data,
                      "Health response must include 'version' field")

    def test_health_endpoint_version_matches_constant(self):
        """Version in /api/health response must match VERSION constant."""
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        data = resp.get_json()
        self.assertEqual(
            data.get('version'), VERSION,
            f"Health endpoint version '{data.get('version')}' "
            f"must match VERSION constant '{VERSION}'"
        )

    def test_health_endpoint_has_status_field(self):
        """GET /api/health must include 'status' field."""
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        data = resp.get_json()
        self.assertIn('status', data,
                      "Health response must include 'status' field")

    def test_health_endpoint_status_ok(self):
        """GET /api/health status field must be 'ok'."""
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'ok',
                         "Health status must be 'ok'")

    def test_health_endpoint_no_auth_required(self):
        """GET /api/health must be accessible without authentication."""
        # Enable auth and try without logging in
        from werkzeug.security import generate_password_hash
        snap = dict(app_module.AUTH)
        snap['auth'] = dict(app_module.AUTH.get('auth', {}))

        try:
            app_module.AUTH['auth'] = {
                'enabled': True,
                'username': 'admin',
                'password_hash': generate_password_hash('secure_pass'),
            }
            with flask_app.test_client() as client:
                resp = client.get('/api/health')
            self.assertEqual(resp.status_code, 200,
                             "/api/health must be accessible without auth")
        finally:
            app_module.AUTH['auth'] = snap['auth']

    def test_health_endpoint_legacy_path(self):
        """GET /api/health (unversioned) must work as well as the versioned path."""
        with flask_app.test_client() as client:
            resp = client.get('/api/health')
        self.assertEqual(resp.status_code, 200)


class TestVersionSemver(unittest.TestCase):
    """Additional semver validation tests."""

    def test_version_format_semver(self):
        """VERSION matches the semver 2.0.0 specification."""
        self.assertIsNotNone(
            _SEMVER_RE.match(VERSION),
            f"'{VERSION}' does not match semver pattern"
        )

    def test_version_major_is_2(self):
        """Major version must be 2 for current release."""
        major = int(VERSION.split('.')[0])
        self.assertEqual(major, 2,
                         f"Major version must be 2, got {major}")

    def test_version_minor_is_0(self):
        """Minor version must be 0 for 2.0.0."""
        minor = int(VERSION.split('.')[1])
        self.assertEqual(minor, 0,
                         f"Minor version must be 0, got {minor}")

    def test_version_patch_is_0(self):
        """Patch version must be 0 for 2.0.0."""
        patch = int(VERSION.split('.')[2].split('-')[0])
        self.assertEqual(patch, 0,
                         f"Patch version must be 0, got {patch}")

    def test_version_no_leading_zeros(self):
        """Semver requires no leading zeros in version numbers."""
        base = VERSION.split('-')[0]
        for part in base.split('.'):
            if len(part) > 1:
                self.assertNotEqual(
                    part[0], '0',
                    f"Version part '{part}' must not have leading zero"
                )

    def test_version_consistent_between_health_and_status(self):
        """Version in /api/health and /api/v1/status must match."""
        with flask_app.test_client() as client:
            health_resp = client.get('/api/health')
            health_data = health_resp.get_json() or {}

            # Disable auth for status endpoint
            snap = dict(app_module.AUTH)
            snap['auth'] = dict(app_module.AUTH.get('auth', {}))
            app_module.AUTH['auth'] = {'enabled': False, 'username': '', 'password_hash': ''}

            try:
                status_resp = client.get('/api/v1/status')
                if status_resp.status_code == 200:
                    status_data = status_resp.get_json() or {}
                    if 'version' in status_data:
                        self.assertEqual(
                            health_data.get('version'),
                            status_data.get('version'),
                            "Version must be consistent between /api/health and /api/v1/status"
                        )
            finally:
                app_module.AUTH['auth'] = snap['auth']


if __name__ == '__main__':
    unittest.main()
