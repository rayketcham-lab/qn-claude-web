#!/usr/bin/env python3
"""
Tests for the pluggable AI engine adapter system.

Covers:
  - AIEngine base class
  - ClaudeEngine (detect, build_command, build_env)
  - AiderEngine (detect, build_command, build_env)
  - ENGINE_REGISTRY and get_engine()
  - GET /api/engines route
  - Backwards compatibility: build_claude_command / build_claude_env unchanged

Run with:
    /usr/bin/python3 -m unittest tests/test_engines.py -v
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

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
flask_app.config['SECRET_KEY'] = 'test-secret-key-engines'


# ---------------------------------------------------------------------------
# Helpers shared with test_routes.py conventions
# ---------------------------------------------------------------------------

def _snapshot_config():
    snap = dict(app_module.CONFIG)
    snap['_auth_snap'] = dict(app_module.AUTH)
    return snap


def _restore_config(snap):
    auth_s = snap.pop('_auth_snap', {})
    app_module.CONFIG.clear()
    app_module.CONFIG.update(snap)
    app_module.AUTH.clear()
    app_module.AUTH.update(auth_s)


def _disable_auth():
    app_module.AUTH['auth'] = {'enabled': False, 'username': '', 'password_hash': ''}
    app_module.AUTH['users'] = []


def _enable_auth(username='admin', password='adminpass1'):
    pw_hash = generate_password_hash(password)
    app_module.CONFIG['auth'] = {
        'enabled': True,
        'username': username,
        'password_hash': pw_hash,
    }
    app_module.CONFIG['users'] = [
        {'username': username, 'password_hash': pw_hash, 'role': 'admin'}
    ]


def _login(client, username='admin', password='adminpass1'):
    return client.post(
        '/login',
        data=json.dumps({'username': username, 'password': password}),
        content_type='application/json',
    )


# ============================================================
# AIEngine base class
# ============================================================

class TestAIEngineBase(unittest.TestCase):
    """AIEngine base class raises NotImplementedError for build_command."""

    def test_build_command_raises(self):
        engine = app_module.AIEngine()
        with self.assertRaises(NotImplementedError):
            engine.build_command('/some/path', {})

    def test_build_env_returns_empty_dict(self):
        engine = app_module.AIEngine()
        result = engine.build_env({})
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    def test_parse_usage_returns_none(self):
        engine = app_module.AIEngine()
        self.assertIsNone(engine.parse_usage('some line'))

    def test_detect_uses_shutil_which(self):
        """detect() returns True when shutil.which finds the binary."""
        engine = app_module.AIEngine()
        engine.binary = 'python3'
        with patch('shutil.which', return_value='/usr/bin/python3'):
            self.assertTrue(engine.detect())

    def test_detect_returns_false_when_missing(self):
        engine = app_module.AIEngine()
        engine.binary = 'no-such-binary-xyz'
        with patch('shutil.which', return_value=None):
            self.assertFalse(engine.detect())


# ============================================================
# ClaudeEngine
# ============================================================

class TestClaudeEngineDetect(unittest.TestCase):

    def test_detect_true_when_claude_found(self):
        with patch('shutil.which', return_value='/usr/local/bin/claude'):
            self.assertTrue(app_module.ClaudeEngine().detect())

    def test_detect_false_when_claude_missing(self):
        with patch('shutil.which', return_value=None):
            self.assertFalse(app_module.ClaudeEngine().detect())

    def test_binary_is_claude(self):
        self.assertEqual(app_module.ClaudeEngine().binary, 'claude')

    def test_name_is_claude(self):
        self.assertEqual(app_module.ClaudeEngine().name, 'claude')


class TestClaudeEngineBuildCommand(unittest.TestCase):
    """ClaudeEngine.build_command must produce identical output to the
    standalone build_claude_command() function — backwards compatibility."""

    def _engine(self):
        return app_module.ClaudeEngine()

    def test_basic_command_starts_with_claude(self):
        cmd = self._engine().build_command('/tmp/proj', {})
        self.assertEqual(cmd[0], 'claude')

    def test_model_flag_passed_through(self):
        cmd = self._engine().build_command('/tmp/proj', {'model': 'claude-3-5-sonnet-20241022'})
        self.assertIn('--model', cmd)
        self.assertIn('claude-3-5-sonnet-20241022', cmd)

    def test_permission_mode_flag(self):
        cmd = self._engine().build_command('/tmp/proj', {'permission_mode': 'acceptEdits'})
        self.assertIn('--permission-mode', cmd)
        self.assertIn('acceptEdits', cmd)

    def test_prompt_appended(self):
        cmd = self._engine().build_command('/tmp/proj', {}, prompt='do the thing')
        self.assertIn('do the thing', cmd)

    def test_matches_standalone_function(self):
        flags = {'model': 'claude-opus-4-5', 'verbose': True}
        expected = app_module.build_claude_command('/tmp/proj', flags, prompt='hello')
        actual = self._engine().build_command('/tmp/proj', flags, prompt='hello')
        self.assertEqual(actual, expected)

    def test_ssh_remote_wraps_in_ssh(self):
        remote = {
            'mode': 'ssh',
            'hostname': '192.168.1.10',
            'username': 'user',
            'port': 22,
        }
        cmd = self._engine().build_command('/remote/path', {}, remote_host=remote)
        self.assertEqual(cmd[0], 'ssh')


class TestClaudeEngineBuildEnv(unittest.TestCase):
    """ClaudeEngine.build_env must delegate to build_claude_env."""

    def test_returns_dict(self):
        env = app_module.ClaudeEngine().build_env({})
        self.assertIsInstance(env, dict)

    def test_thinking_tokens_in_env(self):
        flags = {'extended_thinking': True, 'thinking_tokens': 2000}
        env = app_module.ClaudeEngine().build_env(flags)
        self.assertIn('MAX_THINKING_TOKENS', env)
        self.assertEqual(env['MAX_THINKING_TOKENS'], '2000')

    def test_matches_standalone_function(self):
        flags = {'extended_thinking': True, 'thinking_tokens': 4096}
        expected = app_module.build_claude_env(flags)
        actual = app_module.ClaudeEngine().build_env(flags)
        self.assertEqual(actual, expected)


# ============================================================
# AiderEngine
# ============================================================

class TestAiderEngineDetect(unittest.TestCase):

    def test_detect_true_when_aider_found(self):
        with patch('shutil.which', return_value='/usr/local/bin/aider'):
            self.assertTrue(app_module.AiderEngine().detect())

    def test_detect_false_when_aider_missing(self):
        with patch('shutil.which', return_value=None):
            self.assertFalse(app_module.AiderEngine().detect())

    def test_binary_is_aider(self):
        self.assertEqual(app_module.AiderEngine().binary, 'aider')

    def test_name_is_aider(self):
        self.assertEqual(app_module.AiderEngine().name, 'aider')


class TestAiderEngineBuildCommand(unittest.TestCase):

    def _engine(self):
        return app_module.AiderEngine()

    def test_basic_command_starts_with_aider(self):
        cmd = self._engine().build_command('/tmp/proj', {})
        self.assertEqual(cmd[0], 'aider')

    def test_model_flag_passed(self):
        cmd = self._engine().build_command('/tmp/proj', {'model': 'gpt-4o'})
        self.assertIn('--model', cmd)
        self.assertIn('gpt-4o', cmd)

    def test_prompt_via_message_flag(self):
        cmd = self._engine().build_command('/tmp/proj', {}, prompt='fix the bug')
        self.assertIn('--message', cmd)
        self.assertIn('fix the bug', cmd)

    def test_no_prompt_no_message_flag(self):
        cmd = self._engine().build_command('/tmp/proj', {})
        self.assertNotIn('--message', cmd)

    def test_no_model_no_model_flag(self):
        cmd = self._engine().build_command('/tmp/proj', {})
        self.assertNotIn('--model', cmd)


class TestAiderEngineBuildEnv(unittest.TestCase):

    def test_returns_dict(self):
        env = app_module.AiderEngine().build_env({})
        self.assertIsInstance(env, dict)

    def test_env_is_empty_by_default(self):
        # Aider inherits from the process environment; the adapter returns
        # an empty overlay (no keys added by default).
        env = app_module.AiderEngine().build_env({})
        self.assertEqual(env, {})


# ============================================================
# ENGINE_REGISTRY and get_engine()
# ============================================================

class TestEngineRegistry(unittest.TestCase):

    def test_registry_contains_claude(self):
        self.assertIn('claude', app_module.ENGINE_REGISTRY)

    def test_registry_contains_aider(self):
        self.assertIn('aider', app_module.ENGINE_REGISTRY)

    def test_registry_claude_is_claude_engine(self):
        self.assertIsInstance(app_module.ENGINE_REGISTRY['claude'], app_module.ClaudeEngine)

    def test_registry_aider_is_aider_engine(self):
        self.assertIsInstance(app_module.ENGINE_REGISTRY['aider'], app_module.AiderEngine)


class TestGetEngine(unittest.TestCase):

    def test_default_is_claude(self):
        engine = app_module.get_engine()
        self.assertIsInstance(engine, app_module.ClaudeEngine)

    def test_none_returns_claude(self):
        engine = app_module.get_engine(None)
        self.assertIsInstance(engine, app_module.ClaudeEngine)

    def test_empty_string_returns_claude(self):
        engine = app_module.get_engine('')
        self.assertIsInstance(engine, app_module.ClaudeEngine)

    def test_get_claude_explicitly(self):
        engine = app_module.get_engine('claude')
        self.assertIsInstance(engine, app_module.ClaudeEngine)

    def test_get_aider(self):
        engine = app_module.get_engine('aider')
        self.assertIsInstance(engine, app_module.AiderEngine)

    def test_unknown_engine_falls_back_to_claude(self):
        engine = app_module.get_engine('nonexistent-engine')
        self.assertIsInstance(engine, app_module.ClaudeEngine)


# ============================================================
# GET /api/engines route
# ============================================================

class TestEnginesApiRoute(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()
        self.client = flask_app.test_client()

    def tearDown(self):
        _restore_config(self._config_snap)

    def _authenticated_client(self):
        """Return a test client already logged in as admin."""
        _enable_auth()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'
            sess['role'] = 'admin'
        return self.client

    def test_returns_200_when_authenticated(self):
        _disable_auth()
        resp = self.client.get('/api/v1/engines')
        self.assertEqual(resp.status_code, 200)

    def test_returns_engines_key(self):
        _disable_auth()
        resp = self.client.get('/api/v1/engines')
        data = json.loads(resp.data)
        self.assertIn('engines', data)

    def test_engines_is_list(self):
        _disable_auth()
        resp = self.client.get('/api/v1/engines')
        data = json.loads(resp.data)
        self.assertIsInstance(data['engines'], list)

    def test_engines_list_has_claude_and_aider(self):
        _disable_auth()
        resp = self.client.get('/api/v1/engines')
        data = json.loads(resp.data)
        names = [e['name'] for e in data['engines']]
        self.assertIn('claude', names)
        self.assertIn('aider', names)

    def test_each_engine_entry_has_required_fields(self):
        _disable_auth()
        resp = self.client.get('/api/v1/engines')
        data = json.loads(resp.data)
        for entry in data['engines']:
            self.assertIn('name', entry)
            self.assertIn('binary', entry)
            self.assertIn('available', entry)
            self.assertIn('default', entry)

    def test_default_engine_marked_correctly(self):
        _disable_auth()
        app_module.CONFIG['default_engine'] = 'claude'
        resp = self.client.get('/api/v1/engines')
        data = json.loads(resp.data)
        claude_entry = next(e for e in data['engines'] if e['name'] == 'claude')
        aider_entry = next(e for e in data['engines'] if e['name'] == 'aider')
        self.assertTrue(claude_entry['default'])
        self.assertFalse(aider_entry['default'])

    def test_available_field_reflects_detection(self):
        _disable_auth()
        with patch('shutil.which', return_value=None):
            resp = self.client.get('/api/v1/engines')
        data = json.loads(resp.data)
        for entry in data['engines']:
            self.assertFalse(entry['available'])

    def test_requires_login_when_auth_enabled(self):
        _enable_auth()
        # Fresh client with no session cookie
        fresh_client = flask_app.test_client()
        resp = fresh_client.get('/api/v1/engines')
        # Should redirect to login, not return 200
        self.assertNotEqual(resp.status_code, 200)


# ============================================================
# Config default_engine
# ============================================================

class TestDefaultEngineConfig(unittest.TestCase):

    def setUp(self):
        self._config_snap = _snapshot_config()

    def tearDown(self):
        _restore_config(self._config_snap)

    def test_default_engine_present_in_config(self):
        config = app_module.load_config()
        self.assertIn('default_engine', config)

    def test_default_engine_is_claude(self):
        config = app_module.load_config()
        self.assertEqual(config['default_engine'], 'claude')


# ============================================================
# Backwards compatibility: build_claude_command / build_claude_env
# must still work as standalone functions.
# ============================================================

class TestBackwardsCompatibility(unittest.TestCase):
    """Ensure the refactor did not break existing callers of the standalone
    build_claude_command / build_claude_env functions."""

    def test_build_claude_command_still_callable(self):
        cmd = app_module.build_claude_command('/tmp/proj', {})
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[0], 'claude')

    def test_build_claude_env_still_callable(self):
        env = app_module.build_claude_env({})
        self.assertIsInstance(env, dict)

    def test_build_claude_command_verbose(self):
        cmd = app_module.build_claude_command('/tmp/proj', {'verbose': True})
        self.assertIn('--verbose', cmd)

    def test_build_claude_command_resume(self):
        cmd = app_module.build_claude_command('/tmp/proj', {'resume': True})
        self.assertIn('-r', cmd)

    def test_build_claude_env_extended_thinking(self):
        env = app_module.build_claude_env({'extended_thinking': True, 'thinking_tokens': 8192})
        self.assertEqual(env.get('MAX_THINKING_TOKENS'), '8192')


if __name__ == '__main__':
    unittest.main()
