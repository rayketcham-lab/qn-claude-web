#!/usr/bin/env python3
"""
Security test suite for QN Code Assistant.

Tests the P1 security-critical functions:
  1. _sanitize_model_name() - model name injection prevention
  2. validate_file_path()   - path traversal / app directory blocking
  3. build_claude_command()  - command injection prevention
  4. build_claude_env()      - environment variable safety

Uses unittest (no external dependencies).
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Bootstrap: make sure vendored deps and the project root are importable.
# ---------------------------------------------------------------------------
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_vendor_dir = os.path.join(_project_root, 'vendor')
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Import the functions under test from app.py.
# app.py has module-level side effects (Flask init, config load, agent file
# reads) so we import the whole module.
import app as app_module

_sanitize_model_name = app_module._sanitize_model_name
validate_file_path = app_module.validate_file_path
build_claude_command = app_module.build_claude_command
build_claude_env = app_module.build_claude_env
CONFIG = app_module.CONFIG
TMUX_NAME_RE = app_module.TMUX_NAME_RE
_generate_tmux_name = app_module._generate_tmux_name
_tmux_list_sessions = app_module._tmux_list_sessions
_tmux_session_exists = app_module._tmux_session_exists
_reap_tmux_sessions = app_module._reap_tmux_sessions
_pid_alive = app_module._pid_alive
_tmux_set_owner = app_module._tmux_set_owner
_tmux_get_owner = app_module._tmux_get_owner


# ===================================================================
# 1. _sanitize_model_name() tests
# ===================================================================
class TestSanitizeModelName(unittest.TestCase):
    """Validate that model name sanitisation rejects injection payloads
    while allowing legitimate Claude model identifiers."""

    # -- Valid names -------------------------------------------------
    def test_simple_valid_name(self):
        self.assertEqual(_sanitize_model_name('claude-3-opus'), 'claude-3-opus')

    def test_valid_name_with_date(self):
        self.assertEqual(
            _sanitize_model_name('claude-sonnet-4-5-20250929'),
            'claude-sonnet-4-5-20250929',
        )

    def test_valid_name_opus_46(self):
        self.assertEqual(_sanitize_model_name('claude-opus-4-6'), 'claude-opus-4-6')

    def test_valid_name_with_bracket_suffix(self):
        self.assertEqual(
            _sanitize_model_name('claude-3-opus[1m]'),
            'claude-3-opus[1m]',
        )

    def test_valid_name_with_dots(self):
        self.assertEqual(
            _sanitize_model_name('openai.gpt-4o'),
            'openai.gpt-4o',
        )

    def test_valid_name_with_colons(self):
        self.assertEqual(
            _sanitize_model_name('provider:model-name'),
            'provider:model-name',
        )

    def test_valid_name_with_underscores(self):
        self.assertEqual(
            _sanitize_model_name('my_custom_model'),
            'my_custom_model',
        )

    def test_long_valid_name(self):
        """A 250-character name composed entirely of valid chars should pass."""
        long_name = 'a' * 250
        self.assertEqual(_sanitize_model_name(long_name), long_name)

    def test_long_valid_name_mixed_chars(self):
        """200+ chars with hyphens, dots, digits - still valid."""
        long_name = ('claude-3.5-opus_' * 15)[:210]
        self.assertEqual(_sanitize_model_name(long_name), long_name)

    # -- Rejected names ----------------------------------------------
    def test_reject_semicolon_injection(self):
        self.assertIsNone(_sanitize_model_name('claude; rm -rf /'))

    def test_reject_command_substitution(self):
        self.assertIsNone(_sanitize_model_name('claude$(whoami)'))

    def test_reject_pipe_injection(self):
        self.assertIsNone(_sanitize_model_name('claude|cat /etc/passwd'))

    def test_reject_backtick_injection(self):
        self.assertIsNone(_sanitize_model_name('claude`id`'))

    def test_reject_ampersand_injection(self):
        self.assertIsNone(_sanitize_model_name('claude&echo pwned'))

    def test_reject_space(self):
        self.assertIsNone(_sanitize_model_name('claude 3 opus'))

    def test_reject_newline(self):
        self.assertIsNone(_sanitize_model_name('claude\nmalicious'))

    def test_reject_slash(self):
        self.assertIsNone(_sanitize_model_name('claude/../../etc/passwd'))

    def test_reject_empty_string(self):
        self.assertIsNone(_sanitize_model_name(''))

    def test_reject_none(self):
        self.assertIsNone(_sanitize_model_name(None))

    def test_reject_single_quote(self):
        self.assertIsNone(_sanitize_model_name("claude'--flag"))

    def test_reject_double_quote(self):
        self.assertIsNone(_sanitize_model_name('claude"--flag'))

    def test_reject_null_byte(self):
        self.assertIsNone(_sanitize_model_name('claude\x00'))

    def test_reject_curly_braces(self):
        self.assertIsNone(_sanitize_model_name('claude{test}'))


# ===================================================================
# 2. validate_file_path() tests
# ===================================================================
class TestValidateFilePath(unittest.TestCase):
    """Test the path validation gate that protects against traversal,
    null-byte injection, and app-directory access."""

    # -- Path traversal attacks --------------------------------------
    def test_reject_relative_traversal(self):
        self.assertFalse(validate_file_path('../../../etc/passwd'))

    def test_reject_traversal_through_app_dir(self):
        self.assertFalse(
            validate_file_path('/opt/claude-web/../../../etc/shadow')
        )

    def test_reject_dot_dot_in_middle(self):
        self.assertFalse(validate_file_path('/opt/legit/../../../etc/passwd'))

    # -- Null byte injection ----------------------------------------
    def test_reject_null_byte(self):
        self.assertFalse(
            validate_file_path('/opt/test/file.txt\x00/../etc/passwd')
        )

    def test_reject_null_byte_at_end(self):
        self.assertFalse(validate_file_path('/opt/test/file.txt\x00'))

    def test_reject_null_byte_at_start(self):
        self.assertFalse(validate_file_path('\x00/opt/test/file.txt'))

    # -- App directory blocking --------------------------------------
    def test_reject_app_directory_root(self):
        """The app's own directory must be blocked."""
        self.assertFalse(validate_file_path('/opt/claude-web/'))

    def test_reject_app_directory_exact(self):
        self.assertFalse(validate_file_path('/opt/claude-web'))

    def test_reject_app_py(self):
        self.assertFalse(validate_file_path('/opt/claude-web/app.py'))

    def test_reject_config_json(self):
        self.assertFalse(validate_file_path('/opt/claude-web/config.json'))

    def test_reject_sessions_subdir(self):
        self.assertFalse(validate_file_path('/opt/claude-web/sessions/abc.json'))

    # -- Valid paths (within allowed_paths) --------------------------
    def test_allow_opt_subdir(self):
        """Paths inside /opt/ but outside the app dir should pass."""
        # This creates a real temp dir under /opt to avoid false negatives
        # from resolve() on nonexistent paths.  If /opt is not writable
        # the test still works because resolve() of a non-existent path
        # returns the path itself on modern Python.
        self.assertTrue(validate_file_path('/opt/some-other-project'))

    def test_allow_opt_root(self):
        self.assertTrue(validate_file_path('/opt'))

    def test_allow_deep_opt_path(self):
        self.assertTrue(validate_file_path('/opt/foo/bar/baz/qux.py'))

    # -- Empty / None / bad types -----------------------------------
    def test_reject_empty_string(self):
        self.assertFalse(validate_file_path(''))

    def test_reject_none(self):
        self.assertFalse(validate_file_path(None))

    def test_reject_non_string(self):
        self.assertFalse(validate_file_path(12345))

    def test_reject_list(self):
        self.assertFalse(validate_file_path(['/opt']))

    # -- Symlink tests (using real temp dirs) -----------------------
    def test_reject_symlink_into_app_dir(self):
        """A symlink outside /opt/claude-web/ that points INTO it must
        be caught because validate_file_path resolves symlinks."""
        # Use /tmp (writable) and temporarily add it to allowed_paths
        original_paths = CONFIG.get('allowed_paths', [])
        try:
            CONFIG['allowed_paths'] = original_paths + ['/tmp']
            with tempfile.TemporaryDirectory() as tmpdir:
                link_path = os.path.join(tmpdir, 'sneaky_link')
                os.symlink('/opt/claude-web', link_path)
                # Even though /tmp is allowed, the symlink resolves into
                # the blocked app directory
                self.assertFalse(validate_file_path(link_path))
        finally:
            CONFIG['allowed_paths'] = original_paths

    def test_allow_symlink_within_allowed(self):
        """A symlink inside an allowed location that points to another
        allowed location should be permitted."""
        original_paths = CONFIG.get('allowed_paths', [])
        try:
            CONFIG['allowed_paths'] = original_paths + ['/tmp']
            with tempfile.TemporaryDirectory() as tmpdir:
                target = os.path.join(tmpdir, 'real_dir')
                os.makedirs(target)
                link_path = os.path.join(tmpdir, 'ok_link')
                os.symlink(target, link_path)
                self.assertTrue(validate_file_path(link_path))
        finally:
            CONFIG['allowed_paths'] = original_paths

    # -- Paths outside allowed_paths --------------------------------
    def test_reject_etc_passwd(self):
        self.assertFalse(validate_file_path('/etc/passwd'))

    def test_reject_home_dir(self):
        self.assertFalse(validate_file_path('/home/user/secret'))

    def test_reject_root_dir(self):
        self.assertFalse(validate_file_path('/'))

    # -- allow_full_browsing override --------------------------------
    def test_allow_full_browsing_flag(self):
        """When allow_full_browsing is True, paths outside allowed_paths
        should be permitted (except the app dir itself)."""
        original = CONFIG.get('allow_full_browsing')
        try:
            CONFIG['allow_full_browsing'] = True
            # /etc is outside default allowed_paths but should pass
            self.assertTrue(validate_file_path('/etc'))
            # App dir must STILL be blocked
            self.assertFalse(validate_file_path('/opt/claude-web/app.py'))
        finally:
            CONFIG['allow_full_browsing'] = original if original is not None else False


# ===================================================================
# 3. build_claude_command() tests
# ===================================================================
class TestBuildClaudeCommand(unittest.TestCase):
    """Test command construction safety: flag allowlists, input
    sanitisation, and injection prevention."""

    def _build(self, flags=None, project_path='/opt/project', prompt=None, remote_host=None):
        """Shorthand wrapper."""
        return build_claude_command(project_path, flags or {}, prompt=prompt, remote_host=remote_host)

    # -- Minimal / default command -----------------------------------
    def test_default_flags_produce_minimal_command(self):
        cmd = self._build()
        self.assertEqual(cmd, ['claude'])

    def test_empty_flags_produce_minimal_command(self):
        cmd = self._build(flags={})
        self.assertEqual(cmd, ['claude'])

    # -- Permission mode allowlist -----------------------------------
    def test_valid_permission_mode_default(self):
        cmd = self._build(flags={'permission_mode': 'default'})
        self.assertIn('--permission-mode', cmd)
        idx = cmd.index('--permission-mode')
        self.assertEqual(cmd[idx + 1], 'default')

    def test_valid_permission_mode_dontask(self):
        cmd = self._build(flags={'permission_mode': 'dontAsk'})
        self.assertIn('--permission-mode', cmd)
        idx = cmd.index('--permission-mode')
        self.assertEqual(cmd[idx + 1], 'dontAsk')

    def test_valid_permission_mode_plan(self):
        cmd = self._build(flags={'permission_mode': 'plan'})
        idx = cmd.index('--permission-mode')
        self.assertEqual(cmd[idx + 1], 'plan')

    def test_invalid_permission_mode_rejected(self):
        """Injecting shell commands via permission mode must be blocked."""
        cmd = self._build(flags={'permission_mode': "'; rm -rf /'"})
        self.assertNotIn('--permission-mode', cmd)

    def test_unknown_permission_mode_rejected(self):
        cmd = self._build(flags={'permission_mode': 'superDangerous'})
        self.assertNotIn('--permission-mode', cmd)

    # -- Effort level allowlist --------------------------------------
    def test_effort_level_low(self):
        cmd = self._build(flags={'effort_level': 'low'})
        self.assertIn('--effort', cmd)
        idx = cmd.index('--effort')
        self.assertEqual(cmd[idx + 1], 'low')

    def test_effort_level_medium(self):
        cmd = self._build(flags={'effort_level': 'medium'})
        idx = cmd.index('--effort')
        self.assertEqual(cmd[idx + 1], 'medium')

    def test_effort_level_high(self):
        cmd = self._build(flags={'effort_level': 'high'})
        idx = cmd.index('--effort')
        self.assertEqual(cmd[idx + 1], 'high')

    def test_effort_level_invalid_rejected(self):
        cmd = self._build(flags={'effort_level': 'critical'})
        self.assertNotIn('--effort', cmd)

    def test_effort_level_injection_rejected(self):
        cmd = self._build(flags={'effort_level': 'high; rm -rf /'})
        self.assertNotIn('--effort', cmd)

    def test_effort_level_empty_string_ignored(self):
        cmd = self._build(flags={'effort_level': ''})
        self.assertNotIn('--effort', cmd)

    # -- Model name passthrough with sanitisation --------------------
    def test_valid_model_passed(self):
        cmd = self._build(flags={'model': 'claude-opus-4-6'})
        self.assertIn('--model', cmd)
        idx = cmd.index('--model')
        self.assertEqual(cmd[idx + 1], 'claude-opus-4-6')

    def test_malicious_model_rejected(self):
        cmd = self._build(flags={'model': 'claude$(whoami)'})
        self.assertNotIn('--model', cmd)

    def test_empty_model_ignored(self):
        cmd = self._build(flags={'model': ''})
        self.assertNotIn('--model', cmd)

    # -- Print mode --------------------------------------------------
    def test_print_mode_adds_flag(self):
        cmd = self._build(flags={'print_mode': True, 'print_prompt': 'hello'})
        self.assertEqual(cmd[1], '-p')
        self.assertIn('hello', cmd)

    def test_print_mode_without_prompt(self):
        cmd = self._build(flags={'print_mode': True})
        self.assertEqual(cmd[1], '-p')

    # -- System prompt truncation ------------------------------------
    def test_system_prompt_truncated_at_10k(self):
        long_prompt = 'x' * 20000
        cmd = self._build(flags={'system_prompt': long_prompt})
        idx = cmd.index('--append-system-prompt')
        actual = cmd[idx + 1]
        self.assertEqual(len(actual), 10000)

    def test_system_prompt_short_preserved(self):
        cmd = self._build(flags={'system_prompt': 'Be helpful'})
        idx = cmd.index('--append-system-prompt')
        self.assertEqual(cmd[idx + 1], 'Be helpful')

    # -- Tool restrictions (regex validation) -----------------------
    def test_allowed_tools_valid(self):
        cmd = self._build(flags={'allowed_tools': 'Read,Write,Bash'})
        self.assertIn('--allowedTools', cmd)
        idx = cmd.index('--allowedTools')
        self.assertEqual(cmd[idx + 1], 'Read,Write,Bash')

    def test_allowed_tools_with_dots(self):
        cmd = self._build(flags={'allowed_tools': 'mcp.tool-name'})
        self.assertIn('--allowedTools', cmd)

    def test_allowed_tools_injection_stripped(self):
        """Tools with shell metacharacters should be silently dropped."""
        cmd = self._build(flags={'allowed_tools': 'Read,$(whoami),Write'})
        if '--allowedTools' in cmd:
            idx = cmd.index('--allowedTools')
            tools_str = cmd[idx + 1]
            self.assertNotIn('$(whoami)', tools_str)
            # Only the valid tools should remain
            self.assertEqual(tools_str, 'Read,Write')

    def test_allowed_tools_all_invalid(self):
        """If every tool name is invalid, the flag should not appear."""
        cmd = self._build(flags={'allowed_tools': '$(rm -rf /),;echo pwned'})
        self.assertNotIn('--allowedTools', cmd)

    def test_disallowed_tools_valid(self):
        cmd = self._build(flags={'disallowed_tools': 'Bash,Write'})
        self.assertIn('--disallowedTools', cmd)
        idx = cmd.index('--disallowedTools')
        self.assertEqual(cmd[idx + 1], 'Bash,Write')

    # -- Additional directories filtering ----------------------------
    def test_add_dirs_valid(self):
        cmd = self._build(flags={'add_dirs': '/opt/extra\n/opt/another'})
        self.assertIn('--add-dir', cmd)
        # Both dirs should appear
        dir_indices = [i for i, v in enumerate(cmd) if v == '--add-dir']
        self.assertEqual(len(dir_indices), 2)

    def test_add_dirs_semicolon_rejected(self):
        cmd = self._build(flags={'add_dirs': '/opt/safe\n/tmp; rm -rf /'})
        # The safe dir should pass, the injection one should be filtered
        dir_indices = [i for i, v in enumerate(cmd) if v == '--add-dir']
        for idx in dir_indices:
            self.assertNotIn(';', cmd[idx + 1])

    def test_add_dirs_pipe_rejected(self):
        cmd = self._build(flags={'add_dirs': '/tmp|cat /etc/passwd'})
        self.assertNotIn('--add-dir', cmd)

    def test_add_dirs_dollar_rejected(self):
        cmd = self._build(flags={'add_dirs': '/tmp/$HOME'})
        self.assertNotIn('--add-dir', cmd)

    def test_add_dirs_backtick_rejected(self):
        cmd = self._build(flags={'add_dirs': '/tmp/`whoami`'})
        self.assertNotIn('--add-dir', cmd)

    def test_add_dirs_ampersand_rejected(self):
        cmd = self._build(flags={'add_dirs': '/tmp & echo pwned'})
        self.assertNotIn('--add-dir', cmd)

    # -- MCP config path filtering ----------------------------------
    def test_mcp_config_valid(self):
        cmd = self._build(flags={'mcp_config': '/home/user/.mcp/config.json'})
        self.assertIn('--mcp-config', cmd)

    def test_mcp_config_injection_rejected(self):
        cmd = self._build(flags={'mcp_config': '/tmp/cfg; rm -rf /'})
        self.assertNotIn('--mcp-config', cmd)

    def test_mcp_config_dollar_rejected(self):
        cmd = self._build(flags={'mcp_config': '/tmp/$(whoami).json'})
        self.assertNotIn('--mcp-config', cmd)

    # -- Resume / continue flags ------------------------------------
    def test_resume_flag(self):
        cmd = self._build(flags={'resume': True})
        self.assertIn('-r', cmd)

    def test_continue_flag(self):
        cmd = self._build(flags={'continue': True})
        self.assertIn('-c', cmd)

    # -- Verbose flag -----------------------------------------------
    def test_verbose_flag(self):
        cmd = self._build(flags={'verbose': True})
        self.assertIn('--verbose', cmd)

    # -- Fallback model sanitised -----------------------------------
    def test_fallback_model_valid(self):
        cmd = self._build(flags={'fallback_model': 'claude-3-haiku'})
        self.assertIn('--fallback-model', cmd)
        idx = cmd.index('--fallback-model')
        self.assertEqual(cmd[idx + 1], 'claude-3-haiku')

    def test_fallback_model_injection_rejected(self):
        cmd = self._build(flags={'fallback_model': 'model$(id)'})
        self.assertNotIn('--fallback-model', cmd)

    # -- Backward compat: dangerously_skip_permissions ---------------
    def test_legacy_skip_permissions_compat(self):
        cmd = self._build(flags={'dangerously_skip_permissions': True})
        self.assertIn('--permission-mode', cmd)
        self.assertIn('acceptEdits', cmd)

    def test_permission_mode_takes_precedence(self):
        """If permission_mode is set, legacy flag should NOT appear."""
        cmd = self._build(flags={
            'permission_mode': 'dontAsk',
            'dangerously_skip_permissions': True,
        })
        # permission_mode wins — should use dontAsk, not acceptEdits
        idx = cmd.index('--permission-mode')
        self.assertEqual(cmd[idx + 1], 'dontAsk')
        self.assertIn('--permission-mode', cmd)

    # -- Prompt passthrough -----------------------------------------
    def test_prompt_appended(self):
        cmd = self._build(prompt='explain this code')
        self.assertIn('explain this code', cmd)

    def test_prompt_not_added_in_print_mode(self):
        """In print mode, regular prompt is not appended (print_prompt is used)."""
        cmd = self._build(
            flags={'print_mode': True, 'print_prompt': 'query'},
            prompt='should-not-appear',
        )
        self.assertNotIn('should-not-appear', cmd)
        self.assertIn('query', cmd)


# ===================================================================
# 4. build_claude_env() tests
# ===================================================================
class TestBuildClaudeEnv(unittest.TestCase):
    """Test environment variable construction for Claude subprocesses."""

    def test_returns_dict(self):
        env = build_claude_env({})
        self.assertIsInstance(env, dict)

    def test_inherits_os_environ(self):
        """The returned env should contain at least PATH from the parent env."""
        env = build_claude_env({})
        self.assertIn('PATH', env)

    # -- Extended thinking tokens ------------------------------------
    def test_thinking_tokens_valid(self):
        env = build_claude_env({
            'extended_thinking': True,
            'thinking_tokens': 50000,
        })
        self.assertEqual(env['MAX_THINKING_TOKENS'], '50000')

    def test_thinking_tokens_default_when_missing(self):
        env = build_claude_env({'extended_thinking': True})
        self.assertEqual(env['MAX_THINKING_TOKENS'], '31999')

    def test_thinking_tokens_non_numeric_fallback(self):
        env = build_claude_env({
            'extended_thinking': True,
            'thinking_tokens': 'not-a-number',
        })
        self.assertEqual(env['MAX_THINKING_TOKENS'], '31999')

    def test_thinking_tokens_below_minimum_clamped(self):
        env = build_claude_env({
            'extended_thinking': True,
            'thinking_tokens': 100,
        })
        self.assertEqual(env['MAX_THINKING_TOKENS'], '1024')

    def test_thinking_tokens_above_maximum_clamped(self):
        env = build_claude_env({
            'extended_thinking': True,
            'thinking_tokens': 999999,
        })
        self.assertEqual(env['MAX_THINKING_TOKENS'], '63999')

    def test_thinking_tokens_exactly_at_minimum(self):
        env = build_claude_env({
            'extended_thinking': True,
            'thinking_tokens': 1024,
        })
        self.assertEqual(env['MAX_THINKING_TOKENS'], '1024')

    def test_thinking_tokens_exactly_at_maximum(self):
        env = build_claude_env({
            'extended_thinking': True,
            'thinking_tokens': 63999,
        })
        self.assertEqual(env['MAX_THINKING_TOKENS'], '63999')

    def test_thinking_tokens_none_type_fallback(self):
        env = build_claude_env({
            'extended_thinking': True,
            'thinking_tokens': None,
        })
        # None cannot be cast to int, so fallback to 31999
        self.assertEqual(env['MAX_THINKING_TOKENS'], '31999')

    def test_no_thinking_env_when_disabled(self):
        env = build_claude_env({'extended_thinking': False})
        self.assertNotIn('MAX_THINKING_TOKENS', env)

    def test_no_thinking_env_when_absent(self):
        env = build_claude_env({})
        self.assertNotIn('MAX_THINKING_TOKENS', env)

    # -- Auto-compact threshold --------------------------------------
    def test_autocompact_valid(self):
        env = build_claude_env({'autocompact_threshold': 75})
        self.assertEqual(env['CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'], '75')

    def test_autocompact_below_minimum_clamped(self):
        env = build_claude_env({'autocompact_threshold': 10})
        self.assertEqual(env['CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'], '50')

    def test_autocompact_above_maximum_clamped(self):
        env = build_claude_env({'autocompact_threshold': 200})
        self.assertEqual(env['CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'], '100')

    def test_autocompact_exactly_at_minimum(self):
        env = build_claude_env({'autocompact_threshold': 50})
        self.assertEqual(env['CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'], '50')

    def test_autocompact_exactly_at_maximum(self):
        env = build_claude_env({'autocompact_threshold': 100})
        self.assertEqual(env['CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'], '100')

    def test_autocompact_non_numeric_ignored(self):
        clean_env = {k: v for k, v in os.environ.items()
                     if k != 'CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'}
        with patch.dict(os.environ, clean_env, clear=True):
            env = build_claude_env({'autocompact_threshold': 'abc'})
            self.assertNotIn('CLAUDE_AUTOCOMPACT_PCT_OVERRIDE', env)

    def test_autocompact_none_not_set(self):
        """When threshold is explicitly None, env var should not be set
        (the 'is not None' guard in app.py skips it)."""
        clean_env = {k: v for k, v in os.environ.items()
                     if k != 'CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'}
        with patch.dict(os.environ, clean_env, clear=True):
            env = build_claude_env({'autocompact_threshold': None})
            self.assertNotIn('CLAUDE_AUTOCOMPACT_PCT_OVERRIDE', env)

    def test_autocompact_absent_not_set(self):
        clean_env = {k: v for k, v in os.environ.items()
                     if k != 'CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'}
        with patch.dict(os.environ, clean_env, clear=True):
            env = build_claude_env({})
            self.assertNotIn('CLAUDE_AUTOCOMPACT_PCT_OVERRIDE', env)

    # -- Agent teams flag --------------------------------------------
    def test_agent_teams_enabled(self):
        env = build_claude_env({'agent_teams': True})
        self.assertEqual(env['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'], '1')

    def test_agent_teams_disabled(self):
        """When agent_teams is False, build_claude_env must not ADD the var.
        We patch os.environ to remove it if pre-existing in the test host."""
        clean_env = {k: v for k, v in os.environ.items()
                     if k != 'CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'}
        with patch.dict(os.environ, clean_env, clear=True):
            env = build_claude_env({'agent_teams': False})
            self.assertNotIn('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS', env)

    def test_agent_teams_absent(self):
        """When agent_teams flag is not in flags at all, the env var
        must not appear (assuming clean parent env)."""
        clean_env = {k: v for k, v in os.environ.items()
                     if k != 'CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'}
        with patch.dict(os.environ, clean_env, clear=True):
            env = build_claude_env({})
            self.assertNotIn('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS', env)

    # -- Combined flags ----------------------------------------------
    def test_all_flags_together(self):
        """All env-producing flags active simultaneously."""
        env = build_claude_env({
            'extended_thinking': True,
            'thinking_tokens': 40000,
            'autocompact_threshold': 80,
            'agent_teams': True,
        })
        self.assertEqual(env['MAX_THINKING_TOKENS'], '40000')
        self.assertEqual(env['CLAUDE_AUTOCOMPACT_PCT_OVERRIDE'], '80')
        self.assertEqual(env['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'], '1')


# ===================================================================
# 5. TMUX_NAME_RE validation tests
# ===================================================================
class TestTmuxNameRegex(unittest.TestCase):
    """Validate that TMUX_NAME_RE accepts only well-formed session names
    and blocks injection payloads."""

    # -- Valid names -------------------------------------------------
    def test_valid_name(self):
        self.assertRegex('qn-abcdef01', TMUX_NAME_RE)

    def test_valid_all_hex_digits(self):
        self.assertRegex('qn-0123abcd', TMUX_NAME_RE)

    def test_valid_all_zeros(self):
        self.assertRegex('qn-00000000', TMUX_NAME_RE)

    def test_valid_all_f(self):
        self.assertRegex('qn-ffffffff', TMUX_NAME_RE)

    # -- Invalid: wrong prefix --------------------------------------
    def test_reject_no_prefix(self):
        self.assertIsNone(TMUX_NAME_RE.match('abcdef01'))

    def test_reject_wrong_prefix(self):
        self.assertIsNone(TMUX_NAME_RE.match('xx-abcdef01'))

    # -- Invalid: wrong length --------------------------------------
    def test_reject_too_short(self):
        self.assertIsNone(TMUX_NAME_RE.match('qn-abcdef0'))

    def test_reject_too_long(self):
        self.assertIsNone(TMUX_NAME_RE.match('qn-abcdef012'))

    def test_reject_empty_after_prefix(self):
        self.assertIsNone(TMUX_NAME_RE.match('qn-'))

    # -- Invalid: bad characters ------------------------------------
    def test_reject_uppercase_hex(self):
        self.assertIsNone(TMUX_NAME_RE.match('qn-ABCDEF01'))

    def test_reject_special_chars(self):
        self.assertIsNone(TMUX_NAME_RE.match('qn-abc!ef01'))

    # -- Injection payloads ----------------------------------------
    def test_reject_tmux_target_syntax(self):
        """Blocks tmux target injection via colon."""
        self.assertIsNone(TMUX_NAME_RE.match('qn-abcdef01:0'))

    def test_reject_semicolon_injection(self):
        self.assertIsNone(TMUX_NAME_RE.match('qn-abcdef01;rm'))

    def test_reject_pipe_injection(self):
        self.assertIsNone(TMUX_NAME_RE.match('qn-abcdef01|cat'))

    def test_reject_newline_injection(self):
        self.assertIsNone(TMUX_NAME_RE.match('qn-abcdef01\n'))

    def test_reject_space_injection(self):
        self.assertIsNone(TMUX_NAME_RE.match('qn-abcd ef01'))

    def test_reject_path_traversal(self):
        self.assertIsNone(TMUX_NAME_RE.match('qn-../../etc'))


# ===================================================================
# 6. _generate_tmux_name() tests
# ===================================================================
class TestGenerateTmuxName(unittest.TestCase):
    """Verify tmux name generation follows the expected pattern."""

    def test_standard_uuid(self):
        name = _generate_tmux_name('a1b2c3d4-e5f6-7890-abcd-ef1234567890')
        self.assertEqual(name, 'qn-a1b2c3d4')

    def test_output_matches_regex(self):
        name = _generate_tmux_name('deadbeef-1234-5678-9abc-def012345678')
        self.assertRegex(name, TMUX_NAME_RE)

    def test_short_input_preserved(self):
        name = _generate_tmux_name('abcd1234')
        self.assertEqual(name, 'qn-abcd1234')

    def test_very_short_input(self):
        name = _generate_tmux_name('ab')
        self.assertEqual(name, 'qn-ab')


# ===================================================================
# 7. _tmux_list_sessions() / _tmux_session_exists() (mocked subprocess)
# ===================================================================
class TestTmuxListSessions(unittest.TestCase):
    """Test _tmux_list_sessions parsing with mocked subprocess output."""

    def _make_result(self, stdout, returncode=0):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=''
        )

    @patch('app.subprocess.run')
    def test_parses_valid_output(self, mock_run):
        mock_run.return_value = self._make_result(
            'qn-abcdef01|1707840000|0|12345\nqn-12345678|1707850000|1|67890\n'
        )
        sessions = _tmux_list_sessions()
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]['name'], 'qn-abcdef01')
        self.assertEqual(sessions[0]['created'], 1707840000)
        self.assertEqual(sessions[0]['attached'], 0)
        self.assertEqual(sessions[0]['pane_pid'], 12345)
        self.assertEqual(sessions[1]['attached'], 1)

    @patch('app.subprocess.run')
    def test_filters_non_qn_sessions(self, mock_run):
        mock_run.return_value = self._make_result(
            'qn-abcdef01|1707840000|0|111\nother-session|1707840000|0|222\n'
        )
        sessions = _tmux_list_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]['name'], 'qn-abcdef01')

    @patch('app.subprocess.run')
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = self._make_result('', returncode=1)
        sessions = _tmux_list_sessions()
        self.assertEqual(sessions, [])

    @patch('app.subprocess.run')
    def test_handles_empty_stdout(self, mock_run):
        mock_run.return_value = self._make_result('')
        sessions = _tmux_list_sessions()
        self.assertEqual(sessions, [])

    @patch('app.subprocess.run')
    def test_handles_missing_pane_pid(self, mock_run):
        mock_run.return_value = self._make_result(
            'qn-abcdef01|1707840000|0\n'
        )
        sessions = _tmux_list_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertIsNone(sessions[0]['pane_pid'])


class TestTmuxSessionExists(unittest.TestCase):
    """Test _tmux_session_exists with mocked subprocess."""

    @patch('app.subprocess.run')
    def test_returns_true_when_exists(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='', stderr=''
        )
        self.assertTrue(_tmux_session_exists('qn-abcdef01'))

    @patch('app.subprocess.run')
    def test_returns_false_when_missing(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout='', stderr=''
        )
        self.assertFalse(_tmux_session_exists('qn-abcdef01'))


# ===================================================================
# 8. _pid_alive() tests
# ===================================================================
class TestPidAlive(unittest.TestCase):
    """Test process liveness check."""

    def test_current_process_is_alive(self):
        self.assertTrue(_pid_alive(os.getpid()))

    def test_bogus_pid_is_dead(self):
        self.assertFalse(_pid_alive(999999999))


# ===================================================================
# 9. _reap_tmux_sessions() tests
# ===================================================================
class TestReapTmuxSessions(unittest.TestCase):
    """Test tmux session reaping with mocked dependencies."""

    @patch('app._tmux_kill_session')
    @patch('app._pid_alive', return_value=False)
    @patch('app._tmux_list_sessions')
    def test_reaps_dead_pane(self, mock_list, mock_alive, mock_kill):
        """Sessions with dead pane PIDs are killed."""
        mock_list.return_value = [
            {'name': 'qn-deadbeef', 'created': 0, 'attached': 0, 'pane_pid': 99999},
        ]
        _reap_tmux_sessions()
        mock_kill.assert_called_once_with('qn-deadbeef')

    @patch('app._tmux_kill_session')
    @patch('app._pid_alive', return_value=True)
    @patch('app._tmux_list_sessions')
    def test_skips_alive_pane(self, mock_list, mock_alive, mock_kill):
        """Sessions with alive pane PIDs are not killed."""
        mock_list.return_value = [
            {'name': 'qn-livebeef', 'created': int(time.time()), 'attached': 0, 'pane_pid': 1},
        ]
        _reap_tmux_sessions()
        mock_kill.assert_not_called()

    @patch('app._tmux_kill_session')
    @patch('app._pid_alive', return_value=True)
    @patch('app._tmux_list_sessions')
    def test_reaps_old_detached(self, mock_list, mock_alive, mock_kill):
        """Detached sessions older than timeout are killed."""
        old_timestamp = int(time.time()) - (25 * 3600)  # 25 hours ago
        mock_list.return_value = [
            {'name': 'qn-oldbeef0', 'created': old_timestamp, 'attached': 0, 'pane_pid': 1},
        ]
        _reap_tmux_sessions()
        mock_kill.assert_called_once_with('qn-oldbeef0')

    @patch('app._tmux_kill_session')
    @patch('app._tmux_list_sessions')
    def test_skips_attached_sessions(self, mock_list, mock_kill):
        """Sessions attached to active terminals are never reaped."""
        mock_list.return_value = [
            {'name': 'qn-attached', 'created': 0, 'attached': 0, 'pane_pid': 99999},
        ]
        # Simulate an active terminal attached to this session
        with app_module.active_terminals_lock:
            app_module.active_terminals['fake-tid'] = {
                'tmux_session': 'qn-attached', 'pid': 1
            }
        try:
            _reap_tmux_sessions()
            mock_kill.assert_not_called()
        finally:
            with app_module.active_terminals_lock:
                app_module.active_terminals.pop('fake-tid', None)

    @patch('app._tmux_kill_session')
    @patch('app._tmux_list_sessions')
    def test_disabled_when_zero(self, mock_list, mock_kill):
        """Reaping disabled when tmux_reap_hours is 0."""
        original = CONFIG.get('tmux_reap_hours')
        CONFIG['tmux_reap_hours'] = 0
        try:
            _reap_tmux_sessions()
            mock_list.assert_not_called()
            mock_kill.assert_not_called()
        finally:
            if original is None:
                CONFIG.pop('tmux_reap_hours', None)
            else:
                CONFIG['tmux_reap_hours'] = original


# ===================================================================
# 10. _tmux_set_owner() / _tmux_get_owner() tests
# ===================================================================
class TestTmuxOwnership(unittest.TestCase):
    """Test tmux session ownership helpers with mocked subprocess."""

    @patch('app.subprocess.run')
    def test_set_owner_calls_tmux(self, mock_run):
        _tmux_set_owner('qn-abcdef01', 'alice')
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn('set-environment', args)
        self.assertIn('QN_OWNER', args)
        self.assertIn('alice', args)

    @patch('app.subprocess.run')
    def test_set_owner_skips_empty_username(self, mock_run):
        _tmux_set_owner('qn-abcdef01', '')
        mock_run.assert_not_called()

    @patch('app.subprocess.run')
    def test_get_owner_parses_output(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='QN_OWNER=bob\n', stderr=''
        )
        self.assertEqual(_tmux_get_owner('qn-abcdef01'), 'bob')

    @patch('app.subprocess.run')
    def test_get_owner_returns_none_when_unset(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout='', stderr=''
        )
        self.assertIsNone(_tmux_get_owner('qn-abcdef01'))

    @patch('app.subprocess.run')
    def test_get_owner_handles_dash_prefix(self, mock_run):
        """tmux outputs '-QN_OWNER' when the variable has been removed."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='-QN_OWNER\n', stderr=''
        )
        self.assertIsNone(_tmux_get_owner('qn-abcdef01'))

    @patch('app.subprocess.run')
    def test_get_owner_handles_equals_in_username(self, mock_run):
        """Edge case: username containing '=' should be preserved."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='QN_OWNER=user=name\n', stderr=''
        )
        self.assertEqual(_tmux_get_owner('qn-abcdef01'), 'user=name')


# ===================================================================
# SSH Credential Safety
# ===================================================================
class TestSshCredentialSafety(unittest.TestCase):
    """Verify SSH credentials are never exposed via process arguments."""

    def test_no_sshpass_dash_p_in_source(self):
        """sshpass -p <password> exposes credentials in /proc/cmdline.
        The app must use sshpass -e (env var) instead."""
        import re
        app_path = os.path.join(_project_root, 'app.py')
        with open(app_path) as f:
            source = f.read()
        # Find any sshpass with -p flag (but not -p for ssh port)
        matches = re.findall(r"'sshpass',\s*'-p'", source)
        self.assertEqual(len(matches), 0,
                         "Found sshpass -p in app.py — use sshpass -e with SSHPASS env var instead")

    def test_sshpass_uses_env_flag(self):
        """Verify sshpass is invoked with -e flag."""
        import re
        app_path = os.path.join(_project_root, 'app.py')
        with open(app_path) as f:
            source = f.read()
        matches = re.findall(r"'sshpass',\s*'-e'", source)
        self.assertGreater(len(matches), 0,
                           "sshpass should use -e flag (reads password from SSHPASS env var)")


# ===================================================================
# CORS Origin Validation
# ===================================================================
class TestCorsOrigins(unittest.TestCase):
    """Verify CORS origins are explicit, never wildcard."""

    def test_cors_origins_not_wildcard(self):
        """_get_cors_origins must never return None or '*'."""
        from app import _get_cors_origins
        origins = _get_cors_origins()
        self.assertIsNotNone(origins)
        self.assertNotEqual(origins, '*')
        self.assertIsInstance(origins, list)

    def test_cors_origins_returns_list(self):
        """Origins must be a list of URL strings."""
        from app import _get_cors_origins
        origins = _get_cors_origins()
        for origin in origins:
            self.assertTrue(origin.startswith('http'), f"Bad origin: {origin}")

    def test_cors_custom_origins_from_config(self):
        """When cors_origins is set in CONFIG, those are returned."""
        from app import _get_cors_origins, CONFIG
        original = CONFIG.get('cors_origins')
        try:
            CONFIG['cors_origins'] = ['https://example.com:5001']
            origins = _get_cors_origins()
            self.assertEqual(origins, ['https://example.com:5001'])
        finally:
            if original is None:
                CONFIG.pop('cors_origins', None)
            else:
                CONFIG['cors_origins'] = original


# ===================================================================
# Runner
# ===================================================================
if __name__ == '__main__':
    unittest.main()
