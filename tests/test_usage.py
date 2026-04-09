#!/usr/bin/env python3
"""
Usage analytics API tests for QN Code Assistant.

Tests cover:
- Per-user token tracking via record_token_usage()
- GET /api/usage — current user stats, admin all-users view
- GET /api/usage/summary — aggregated stats, daily trend, per-user breakdown
- Cost estimation helpers (Sonnet, Opus, Haiku)
- Authentication guard on usage endpoints

Run with:
    /usr/bin/python3 -m unittest tests/test_usage.py -v
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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
flask_app.config['SECRET_KEY'] = 'test-secret-key-usage'
flask_app.config['WTF_CSRF_ENABLED'] = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snapshot_config():
    snap = dict(app_module.CONFIG)
    snap['_auth_snap'] = dict(app_module.AUTH)
    snap['_auth_users'] = [dict(u) for u in app_module.AUTH.get('users', [])]
    return snap


def _restore_config(snap):
    auth_s = snap.pop('_auth_snap', {})
    auth_u = snap.pop('_auth_users', [])
    app_module.CONFIG.clear()
    app_module.CONFIG.update(snap)
    app_module.AUTH.clear()
    app_module.AUTH.update(auth_s)
    app_module.AUTH['users'] = auth_u


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


def _enable_auth_with_regular_user(admin='adminuser', user='regularuser',
                                   password='testpass123'):
    """Set up AUTH with one admin and one regular user."""
    pw_hash = generate_password_hash(password)
    app_module.AUTH['auth'] = {
        'enabled': True,
        'username': admin,
        'password_hash': pw_hash,
    }
    app_module.AUTH['users'] = [
        {'username': admin, 'password_hash': pw_hash, 'role': 'admin'},
        {'username': user, 'password_hash': pw_hash, 'role': 'user'},
    ]


def _disable_auth():
    app_module.AUTH['auth'] = {'enabled': False, 'username': '', 'password_hash': ''}
    app_module.AUTH['users'] = []


def _login(client, username='testadmin', role='admin'):
    """Set session directly — avoids rate limit issues in test suites."""
    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['username'] = username
        sess['role'] = role
        sess['login_time'] = datetime.now(timezone.utc).isoformat()


def _make_empty_usage():
    """Return a fresh empty usage dict matching the schema."""
    return {
        'sessions': {},
        'weekly': {},
        'daily': {},
        'total': {'input_tokens': 0, 'output_tokens': 0},
        'users': {},
    }


# ---------------------------------------------------------------------------
# estimate_cost unit tests
# ---------------------------------------------------------------------------

class TestEstimateCost(unittest.TestCase):
    """Unit tests for the estimate_cost() helper."""

    def test_cost_estimation_sonnet(self):
        """Sonnet: $3/$15 per 1M tokens."""
        cost = app_module.estimate_cost(1_000_000, 1_000_000, 'sonnet')
        self.assertAlmostEqual(cost, 18.0, places=2)

    def test_cost_estimation_sonnet_zero_tokens(self):
        cost = app_module.estimate_cost(0, 0, 'sonnet')
        self.assertEqual(cost, 0.0)

    def test_cost_estimation_opus(self):
        """Opus: $15/$75 per 1M tokens."""
        cost = app_module.estimate_cost(1_000_000, 1_000_000, 'opus')
        self.assertAlmostEqual(cost, 90.0, places=2)

    def test_cost_estimation_haiku(self):
        """Haiku: $0.25/$1.25 per 1M tokens."""
        cost = app_module.estimate_cost(1_000_000, 1_000_000, 'haiku')
        self.assertAlmostEqual(cost, 1.5, places=2)

    def test_cost_estimation_partial_model_name(self):
        """Partial model name like 'claude-sonnet-4' resolves to sonnet pricing."""
        cost_full = app_module.estimate_cost(500_000, 200_000, 'sonnet')
        cost_partial = app_module.estimate_cost(500_000, 200_000, 'claude-sonnet-4')
        self.assertAlmostEqual(cost_full, cost_partial, places=6)

    def test_cost_estimation_unknown_model_defaults_to_sonnet(self):
        """Unknown model name falls back to sonnet pricing."""
        cost_sonnet = app_module.estimate_cost(100_000, 50_000, 'sonnet')
        cost_unknown = app_module.estimate_cost(100_000, 50_000, 'unknown-model')
        self.assertAlmostEqual(cost_sonnet, cost_unknown, places=6)

    def test_cost_estimation_small_amounts(self):
        """Fractional-token costs are non-negative and reasonable."""
        cost = app_module.estimate_cost(100, 50, 'sonnet')
        self.assertGreaterEqual(cost, 0.0)
        self.assertLess(cost, 0.01)

    def test_cost_estimation_input_only(self):
        """Only input tokens, zero output."""
        cost = app_module.estimate_cost(1_000_000, 0, 'sonnet')
        self.assertAlmostEqual(cost, 3.0, places=2)

    def test_cost_estimation_output_only(self):
        """Only output tokens, zero input."""
        cost = app_module.estimate_cost(0, 1_000_000, 'opus')
        self.assertAlmostEqual(cost, 75.0, places=2)


# ---------------------------------------------------------------------------
# record_token_usage unit tests
# ---------------------------------------------------------------------------

class TestRecordTokenUsage(unittest.TestCase):
    """Tests for record_token_usage() — the single write path for usage.json."""

    def setUp(self):
        self._config_snap = _snapshot_config()
        self._tmp = tempfile.NamedTemporaryFile(
            suffix='.json', delete=False, mode='w'
        )
        self._tmp.write(json.dumps(_make_empty_usage()))
        self._tmp.flush()
        self._tmp.close()
        self._orig_usage_file = app_module.USAGE_FILE
        app_module.USAGE_FILE = type(app_module.USAGE_FILE)(self._tmp.name)

    def tearDown(self):
        app_module.USAGE_FILE = self._orig_usage_file
        _restore_config(self._config_snap)
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def test_usage_tracks_global_total(self):
        """record_token_usage increments the global total."""
        app_module.record_token_usage(1000, 500, username='alice')
        usage = app_module.load_usage()
        self.assertEqual(usage['total']['input_tokens'], 1000)
        self.assertEqual(usage['total']['output_tokens'], 500)

    def test_usage_tracks_per_user(self):
        """record_token_usage stores tokens under the correct username."""
        app_module.record_token_usage(2000, 1000, username='alice')
        app_module.record_token_usage(500, 250, username='bob')
        usage = app_module.load_usage()
        self.assertEqual(usage['users']['alice']['input_tokens'], 2000)
        self.assertEqual(usage['users']['alice']['output_tokens'], 1000)
        self.assertEqual(usage['users']['bob']['input_tokens'], 500)
        self.assertEqual(usage['users']['bob']['output_tokens'], 250)

    def test_usage_accumulates_per_user(self):
        """Multiple calls for same user accumulate correctly."""
        app_module.record_token_usage(1000, 500, username='alice')
        app_module.record_token_usage(500, 250, username='alice')
        usage = app_module.load_usage()
        self.assertEqual(usage['users']['alice']['input_tokens'], 1500)
        self.assertEqual(usage['users']['alice']['output_tokens'], 750)

    def test_usage_tracks_daily(self):
        """record_token_usage stores tokens in the daily bucket."""
        day_key = datetime.now().strftime('%Y-%m-%d')
        app_module.record_token_usage(1000, 500, username='alice')
        usage = app_module.load_usage()
        self.assertIn(day_key, usage['daily'])
        self.assertEqual(usage['daily'][day_key]['input_tokens'], 1000)

    def test_usage_tracks_weekly(self):
        """record_token_usage stores tokens in the weekly bucket."""
        week_key = app_module.get_week_key()
        app_module.record_token_usage(1000, 500, username='alice')
        usage = app_module.load_usage()
        self.assertIn(week_key, usage['weekly'])
        self.assertEqual(usage['weekly'][week_key]['input_tokens'], 1000)

    def test_usage_no_username_skips_per_user(self):
        """record_token_usage with empty username skips the users dict."""
        app_module.record_token_usage(1000, 500, username='')
        usage = app_module.load_usage()
        self.assertEqual(usage['users'], {})
        # But global total should still be updated
        self.assertEqual(usage['total']['input_tokens'], 1000)


# ---------------------------------------------------------------------------
# load_usage migration tests
# ---------------------------------------------------------------------------

class TestLoadUsageMigration(unittest.TestCase):
    """Tests that load_usage() handles legacy data without the new keys."""

    def setUp(self):
        self._config_snap = _snapshot_config()
        self._tmp = tempfile.NamedTemporaryFile(
            suffix='.json', delete=False, mode='w'
        )
        self._orig_usage_file = app_module.USAGE_FILE
        app_module.USAGE_FILE = type(app_module.USAGE_FILE)(self._tmp.name)

    def tearDown(self):
        app_module.USAGE_FILE = self._orig_usage_file
        _restore_config(self._config_snap)
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def test_legacy_data_gets_users_key(self):
        """load_usage() adds 'users' key when missing from stored data."""
        legacy = {
            'sessions': {},
            'weekly': {'2026-W13': {'input_tokens': 100, 'output_tokens': 50}},
            'total': {'input_tokens': 100, 'output_tokens': 50},
        }
        with open(self._tmp.name, 'w') as f:
            json.dump(legacy, f)
        usage = app_module.load_usage()
        self.assertIn('users', usage)
        self.assertIsInstance(usage['users'], dict)

    def test_legacy_data_gets_daily_key(self):
        """load_usage() adds 'daily' key when missing from stored data."""
        legacy = {
            'sessions': {},
            'weekly': {},
            'total': {'input_tokens': 0, 'output_tokens': 0},
        }
        with open(self._tmp.name, 'w') as f:
            json.dump(legacy, f)
        usage = app_module.load_usage()
        self.assertIn('daily', usage)
        self.assertIsInstance(usage['daily'], dict)


# ---------------------------------------------------------------------------
# GET /api/usage endpoint tests
# ---------------------------------------------------------------------------

class TestApiUsageEndpoint(unittest.TestCase):
    """Tests for GET /api/usage."""

    def setUp(self):
        self._config_snap = _snapshot_config()
        self._tmp = tempfile.NamedTemporaryFile(
            suffix='.json', delete=False, mode='w'
        )
        self._tmp.write(json.dumps(_make_empty_usage()))
        self._tmp.flush()
        self._tmp.close()
        self._orig_usage_file = app_module.USAGE_FILE
        app_module.USAGE_FILE = type(app_module.USAGE_FILE)(self._tmp.name)

    def tearDown(self):
        app_module.USAGE_FILE = self._orig_usage_file
        _restore_config(self._config_snap)
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def test_usage_api_requires_auth(self):
        """GET /api/usage returns 401 when not logged in."""
        _enable_auth()
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage')
        self.assertEqual(resp.status_code, 401)

    def test_usage_api_returns_current_user(self):
        """GET /api/usage returns per-user stats for the logged-in user."""
        _enable_auth(username='testadmin')
        # Seed some usage for testadmin
        usage = _make_empty_usage()
        usage['users']['testadmin'] = {
            'input_tokens': 1500, 'output_tokens': 750, 'sessions': 3
        }
        with open(self._tmp.name, 'w') as f:
            json.dump(usage, f)

        with flask_app.test_client() as client:
            _login(client, username='testadmin')
            resp = client.get('/api/v1/usage')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('user', data)
        self.assertEqual(data['user']['input_tokens'], 1500)
        self.assertEqual(data['user']['output_tokens'], 750)
        self.assertEqual(data['user']['sessions'], 3)

    def test_usage_api_admin_sees_all_users(self):
        """Admin GET /api/usage includes a 'users' breakdown of all users."""
        _enable_auth_with_regular_user(admin='adminuser', user='regularuser')
        usage = _make_empty_usage()
        usage['users']['adminuser'] = {
            'input_tokens': 1000, 'output_tokens': 500, 'sessions': 2
        }
        usage['users']['regularuser'] = {
            'input_tokens': 200, 'output_tokens': 100, 'sessions': 1
        }
        with open(self._tmp.name, 'w') as f:
            json.dump(usage, f)

        with flask_app.test_client() as client:
            _login(client, username='adminuser')
            resp = client.get('/api/v1/usage')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('users', data)
        self.assertIn('adminuser', data['users'])
        self.assertIn('regularuser', data['users'])

    def test_usage_summary_requires_admin_for_all_users(self):
        """GET /api/usage for a non-admin does NOT include 'users' breakdown."""
        _enable_auth_with_regular_user(admin='adminuser', user='regularuser')
        usage = _make_empty_usage()
        usage['users']['adminuser'] = {
            'input_tokens': 1000, 'output_tokens': 500, 'sessions': 2
        }
        usage['users']['regularuser'] = {
            'input_tokens': 200, 'output_tokens': 100, 'sessions': 1
        }
        with open(self._tmp.name, 'w') as f:
            json.dump(usage, f)

        with flask_app.test_client() as client:
            _login(client, username='regularuser', role='user')
            resp = client.get('/api/v1/usage')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        # Non-admin must NOT see the full user breakdown
        self.assertNotIn('users', data)
        # But must see their own stats
        self.assertIn('user', data)

    def test_usage_api_has_standard_fields(self):
        """GET /api/usage response includes weekly, total, reset_time, week_key."""
        _disable_auth()
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        for field in ('weekly', 'total', 'reset_time', 'week_key', 'user'):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_usage_api_cost_included_for_api_key_plan(self):
        """For API key users (not max/pro), response includes estimated_cost_usd."""
        _disable_auth()
        app_module.CONFIG['claude_plan'] = 'api_key'
        usage = _make_empty_usage()
        usage['users'][''] = {'input_tokens': 1_000_000, 'output_tokens': 500_000, 'sessions': 1}
        with open(self._tmp.name, 'w') as f:
            json.dump(usage, f)

        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage')

        data = resp.get_json()
        self.assertIn('estimated_cost_usd', data.get('user', {}))

    def test_usage_api_plan_shown_for_max_users(self):
        """For Max plan users, response includes 'plan' instead of cost."""
        _disable_auth()
        app_module.CONFIG['claude_plan'] = 'max'
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage')

        data = resp.get_json()
        user_data = data.get('user', {})
        self.assertIn('plan', user_data)
        self.assertNotIn('estimated_cost_usd', user_data)


# ---------------------------------------------------------------------------
# GET /api/usage/summary endpoint tests
# ---------------------------------------------------------------------------

class TestApiUsageSummaryEndpoint(unittest.TestCase):
    """Tests for GET /api/usage/summary."""

    def setUp(self):
        self._config_snap = _snapshot_config()
        self._tmp = tempfile.NamedTemporaryFile(
            suffix='.json', delete=False, mode='w'
        )
        self._tmp.write(json.dumps(_make_empty_usage()))
        self._tmp.flush()
        self._tmp.close()
        self._orig_usage_file = app_module.USAGE_FILE
        app_module.USAGE_FILE = type(app_module.USAGE_FILE)(self._tmp.name)

    def tearDown(self):
        app_module.USAGE_FILE = self._orig_usage_file
        _restore_config(self._config_snap)
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def test_summary_requires_auth(self):
        """GET /api/usage/summary returns 401 when not logged in."""
        _enable_auth()
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage/summary')
        self.assertEqual(resp.status_code, 401)

    def test_summary_has_required_fields(self):
        """GET /api/usage/summary includes expected top-level fields."""
        _disable_auth()
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage/summary')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        for field in ('total_input_tokens', 'total_output_tokens', 'daily_trend'):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_summary_daily_trend_has_7_days(self):
        """daily_trend always contains exactly 7 entries."""
        _disable_auth()
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage/summary')

        data = resp.get_json()
        self.assertEqual(len(data['daily_trend']), 7)

    def test_summary_daily_trend_ordered_oldest_first(self):
        """daily_trend entries are ordered from oldest to today."""
        _disable_auth()
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage/summary')

        data = resp.get_json()
        trend = data['daily_trend']
        dates = [e['date'] for e in trend]
        self.assertEqual(dates, sorted(dates))

    def test_summary_daily_trend_ends_today(self):
        """Last entry in daily_trend is today's date."""
        _disable_auth()
        today = datetime.now().strftime('%Y-%m-%d')
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage/summary')

        data = resp.get_json()
        self.assertEqual(data['daily_trend'][-1]['date'], today)

    def test_summary_admin_sees_all_users(self):
        """Admin GET /api/usage/summary includes 'users' dict."""
        _enable_auth_with_regular_user(admin='adminuser', user='regularuser')
        usage = _make_empty_usage()
        usage['users']['adminuser'] = {'input_tokens': 100, 'output_tokens': 50, 'sessions': 1}
        usage['users']['regularuser'] = {'input_tokens': 200, 'output_tokens': 100, 'sessions': 2}
        with open(self._tmp.name, 'w') as f:
            json.dump(usage, f)

        with flask_app.test_client() as client:
            _login(client, username='adminuser')
            resp = client.get('/api/v1/usage/summary')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('users', data)
        self.assertIn('regularuser', data['users'])

    def test_summary_non_admin_sees_only_own_stats(self):
        """Non-admin GET /api/usage/summary does NOT include 'users' breakdown."""
        _enable_auth_with_regular_user(admin='adminuser', user='regularuser')
        usage = _make_empty_usage()
        usage['users']['adminuser'] = {'input_tokens': 100, 'output_tokens': 50, 'sessions': 1}
        usage['users']['regularuser'] = {'input_tokens': 200, 'output_tokens': 100, 'sessions': 2}
        with open(self._tmp.name, 'w') as f:
            json.dump(usage, f)

        with flask_app.test_client() as client:
            _login(client, username='regularuser', role='user')
            resp = client.get('/api/v1/usage/summary')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertNotIn('users', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['input_tokens'], 200)

    def test_summary_cost_included_for_api_key_plan(self):
        """For API key users, summary includes estimated_cost_usd."""
        _disable_auth()
        app_module.CONFIG['claude_plan'] = 'api_key'
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage/summary')

        data = resp.get_json()
        self.assertIn('estimated_cost_usd', data)

    def test_summary_plan_shown_for_max_users(self):
        """For Max plan users, summary includes 'plan' instead of cost."""
        _disable_auth()
        app_module.CONFIG['claude_plan'] = 'max'
        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage/summary')

        data = resp.get_json()
        self.assertIn('plan', data)
        self.assertNotIn('estimated_cost_usd', data)

    def test_summary_reflects_recorded_daily_usage(self):
        """daily_trend contains recorded token data for today."""
        _disable_auth()
        today = datetime.now().strftime('%Y-%m-%d')
        usage = _make_empty_usage()
        usage['daily'][today] = {'input_tokens': 999, 'output_tokens': 333}
        usage['total'] = {'input_tokens': 999, 'output_tokens': 333}
        with open(self._tmp.name, 'w') as f:
            json.dump(usage, f)

        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage/summary')

        data = resp.get_json()
        today_entry = next(e for e in data['daily_trend'] if e['date'] == today)
        self.assertEqual(today_entry['input_tokens'], 999)
        self.assertEqual(today_entry['output_tokens'], 333)

    def test_summary_total_tokens_match(self):
        """total_input_tokens / total_output_tokens match usage.json totals."""
        _disable_auth()
        usage = _make_empty_usage()
        usage['total'] = {'input_tokens': 12345, 'output_tokens': 67890}
        with open(self._tmp.name, 'w') as f:
            json.dump(usage, f)

        with flask_app.test_client() as client:
            resp = client.get('/api/v1/usage/summary')

        data = resp.get_json()
        self.assertEqual(data['total_input_tokens'], 12345)
        self.assertEqual(data['total_output_tokens'], 67890)


if __name__ == '__main__':
    unittest.main(verbosity=2)
