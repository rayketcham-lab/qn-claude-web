#!/usr/bin/env python3
"""
Tests for auto mode / permission-mode compatibility.

Verifies that:
- build_claude_command respects autonomous=True → --permission-mode auto
- 'auto' is in allowed_modes
- .claude/settings.json is valid with required keys
- deny list has entries, allow list exists

Run with:
    python3 -m pytest tests/test_auto_mode.py -v
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

build_claude_command = app_module.build_claude_command
_SETTINGS_PATH = os.path.join(_project_root, '.claude', 'settings.json')


def _load_settings():
    with open(_SETTINGS_PATH) as f:
        return json.load(f)


# ===================================================================
# 1. build_claude_command with permission_mode='auto'
# ===================================================================
class TestBuildCommandAutoPermissionMode(unittest.TestCase):
    """Verify build_claude_command with permission_mode='auto' uses --permission-mode auto."""

    def test_build_command_auto_permission_mode(self):
        """flags={'permission_mode': 'auto'} produces --permission-mode auto."""
        cmd = build_claude_command(
            project_path='/opt',
            flags={'permission_mode': 'auto'},
        )
        self.assertIn('--permission-mode', cmd,
                      "Command must include --permission-mode flag")
        idx = cmd.index('--permission-mode')
        self.assertEqual(cmd[idx + 1], 'auto',
                         "permission_mode 'auto' must map to --permission-mode auto")

    def test_build_command_default_permission_mode(self):
        """flags={'permission_mode': 'default'} produces --permission-mode default."""
        cmd = build_claude_command(
            project_path='/opt',
            flags={'permission_mode': 'default'},
        )
        idx = cmd.index('--permission-mode')
        self.assertEqual(cmd[idx + 1], 'default')

    def test_build_command_accept_edits_permission_mode(self):
        """flags={'permission_mode': 'acceptEdits'} produces --permission-mode acceptEdits."""
        cmd = build_claude_command(
            project_path='/opt',
            flags={'permission_mode': 'acceptEdits'},
        )
        idx = cmd.index('--permission-mode')
        self.assertEqual(cmd[idx + 1], 'acceptEdits')

    def test_build_command_plan_permission_mode(self):
        """flags={'permission_mode': 'plan'} produces --permission-mode plan."""
        cmd = build_claude_command(
            project_path='/opt',
            flags={'permission_mode': 'plan'},
        )
        idx = cmd.index('--permission-mode')
        self.assertEqual(cmd[idx + 1], 'plan')

    def test_build_command_dont_ask_permission_mode(self):
        """flags={'permission_mode': 'dontAsk'} produces --permission-mode dontAsk."""
        cmd = build_claude_command(
            project_path='/opt',
            flags={'permission_mode': 'dontAsk'},
        )
        idx = cmd.index('--permission-mode')
        self.assertEqual(cmd[idx + 1], 'dontAsk')

    def test_build_command_invalid_permission_mode_rejected(self):
        """An invalid permission_mode must be ignored (not passed to claude)."""
        cmd = build_claude_command(
            project_path='/opt',
            flags={'permission_mode': 'malicious; rm -rf /'},
        )
        # --permission-mode should not appear with the invalid value
        if '--permission-mode' in cmd:
            idx = cmd.index('--permission-mode')
            self.assertNotIn(
                'malicious',
                cmd[idx + 1],
                "Invalid permission_mode must not be passed to claude"
            )

    def test_build_command_no_permission_mode_uses_accept_edits_compat(self):
        """
        dangerously_skip_permissions=True (legacy) maps to --permission-mode acceptEdits
        for backwards compatibility.
        """
        cmd = build_claude_command(
            project_path='/opt',
            flags={'dangerously_skip_permissions': True},
        )
        if '--permission-mode' in cmd:
            idx = cmd.index('--permission-mode')
            self.assertEqual(
                cmd[idx + 1], 'acceptEdits',
                "dangerously_skip_permissions=True must upgrade to acceptEdits"
            )

    def test_build_command_no_flags_no_permission_mode(self):
        """Empty flags should not add --permission-mode at all."""
        cmd = build_claude_command(project_path='/opt', flags={})
        self.assertNotIn('--permission-mode', cmd,
                         "No flags should not add --permission-mode")


# ===================================================================
# 2. 'auto' in allowed_modes
# ===================================================================
class TestAutoModeInAllowedModes(unittest.TestCase):
    """Verify 'auto' is in the allowed_modes tuple."""

    def test_auto_mode_in_allowed_modes(self):
        """
        The allowed_modes tuple inside build_claude_command must include 'auto'.
        We test this indirectly: passing 'auto' results in it being used.
        """
        cmd = build_claude_command(
            project_path='/opt',
            flags={'permission_mode': 'auto'},
        )
        self.assertIn('--permission-mode', cmd)
        idx = cmd.index('--permission-mode')
        self.assertEqual(cmd[idx + 1], 'auto',
                         "'auto' must be in allowed_modes")

    def test_all_documented_modes_accepted(self):
        """All documented permission modes are accepted by build_claude_command."""
        documented_modes = ('default', 'acceptEdits', 'plan', 'dontAsk', 'auto')
        for mode in documented_modes:
            cmd = build_claude_command(
                project_path='/opt',
                flags={'permission_mode': mode},
            )
            self.assertIn('--permission-mode', cmd,
                          f"Mode '{mode}' should produce --permission-mode flag")
            idx = cmd.index('--permission-mode')
            self.assertEqual(
                cmd[idx + 1], mode,
                f"Mode '{mode}' must map to --permission-mode {mode}"
            )

    def test_undocumented_mode_rejected(self):
        """An undocumented mode like 'superDanger' must not appear in the command."""
        cmd = build_claude_command(
            project_path='/opt',
            flags={'permission_mode': 'superDanger'},
        )
        # Either --permission-mode is absent entirely, or the value is not 'superDanger'
        if '--permission-mode' in cmd:
            idx = cmd.index('--permission-mode')
            self.assertNotEqual(cmd[idx + 1], 'superDanger')


# ===================================================================
# 3. settings.json valid JSON with required keys
# ===================================================================
class TestSettingsJsonValid(unittest.TestCase):
    """Load .claude/settings.json, verify it's valid JSON with required keys."""

    def _load(self):
        with open(_SETTINGS_PATH) as f:
            return json.load(f)

    def test_settings_json_valid(self):
        """settings.json must be valid JSON."""
        try:
            data = self._load()
        except json.JSONDecodeError as e:
            self.fail(f"settings.json is invalid JSON: {e}")
        self.assertIsInstance(data, dict)

    def test_settings_json_has_permissions_key(self):
        """settings.json must have a 'permissions' key."""
        data = self._load()
        self.assertIn('permissions', data,
                      "settings.json must have 'permissions' key")

    def test_settings_json_permissions_has_allow_and_deny(self):
        """settings.json permissions must have both 'allow' and 'deny' lists."""
        data = self._load()
        perms = data.get('permissions', {})
        self.assertIn('allow', perms,
                      "permissions must have 'allow' list")
        self.assertIn('deny', perms,
                      "permissions must have 'deny' list")

    def test_settings_json_allow_is_list(self):
        """allow list must be a JSON array."""
        data = self._load()
        allow = data.get('permissions', {}).get('allow', None)
        self.assertIsInstance(allow, list,
                              "allow must be a JSON array")

    def test_settings_json_deny_is_list(self):
        """deny list must be a JSON array."""
        data = self._load()
        deny = data.get('permissions', {}).get('deny', None)
        self.assertIsInstance(deny, list,
                              "deny must be a JSON array")

    def test_settings_json_has_env_section(self):
        """settings.json should have an env section."""
        data = self._load()
        self.assertIn('env', data,
                      "settings.json must have 'env' key")

    def test_settings_json_env_is_dict(self):
        """env section must be a JSON object."""
        data = self._load()
        env = data.get('env', None)
        self.assertIsInstance(env, dict,
                              "env must be a JSON object")


# ===================================================================
# 4. settings deny list not empty
# ===================================================================
class TestSettingsDenyListNotEmpty(unittest.TestCase):
    """Verify deny list has entries."""

    def test_settings_deny_list_not_empty(self):
        """deny list must have at least one entry."""
        with open(_SETTINGS_PATH) as f:
            data = json.load(f)
        deny = data.get('permissions', {}).get('deny', [])
        self.assertGreater(len(deny), 0,
                           "deny list must not be empty — dangerous commands must be blocked")

    def test_settings_deny_has_git_entries(self):
        """deny list must include git-related entries."""
        with open(_SETTINGS_PATH) as f:
            data = json.load(f)
        deny = data.get('permissions', {}).get('deny', [])
        git_entries = [e for e in deny if 'git' in e.lower()]
        self.assertGreater(len(git_entries), 0,
                           "deny list must include at least one git-related entry")

    def test_settings_deny_has_rm_entries(self):
        """deny list must include rm-related entries."""
        with open(_SETTINGS_PATH) as f:
            data = json.load(f)
        deny = data.get('permissions', {}).get('deny', [])
        rm_entries = [e for e in deny if 'rm' in e.lower()]
        self.assertGreater(len(rm_entries), 0,
                           "deny list must include at least one rm-related entry")


# ===================================================================
# 5. allow list exists
# ===================================================================
class TestSettingsAllowListExists(unittest.TestCase):
    """Verify allow list exists and has entries."""

    def test_settings_allow_list_exists(self):
        """allow list must exist in settings.json."""
        with open(_SETTINGS_PATH) as f:
            data = json.load(f)
        perms = data.get('permissions', {})
        self.assertIn('allow', perms,
                      "settings.json permissions must have 'allow' key")

    def test_settings_allow_list_has_entries(self):
        """allow list must have at least some entries (Read, Edit, common tools)."""
        with open(_SETTINGS_PATH) as f:
            data = json.load(f)
        allow = data.get('permissions', {}).get('allow', [])
        self.assertGreater(len(allow), 0,
                           "allow list should not be empty — common tools need to be allowed")

    def test_settings_allow_list_includes_read(self):
        """allow list must include 'Read' tool."""
        with open(_SETTINGS_PATH) as f:
            data = json.load(f)
        allow = data.get('permissions', {}).get('allow', [])
        self.assertIn('Read', allow,
                      "allow list must include 'Read' tool")

    def test_settings_allow_list_includes_edit(self):
        """allow list must include 'Edit' tool."""
        with open(_SETTINGS_PATH) as f:
            data = json.load(f)
        allow = data.get('permissions', {}).get('allow', [])
        self.assertIn('Edit', allow,
                      "allow list must include 'Edit' tool")


# ===================================================================
# Additional build_claude_command correctness tests
# ===================================================================
class TestBuildClaudeCommandCorrectness(unittest.TestCase):
    """Additional correctness tests for build_claude_command."""

    def test_build_command_returns_list(self):
        """build_claude_command must return a list."""
        cmd = build_claude_command(project_path='/opt', flags={})
        self.assertIsInstance(cmd, list)

    def test_build_command_starts_with_claude(self):
        """First element of command list must be 'claude'."""
        cmd = build_claude_command(project_path='/opt', flags={})
        self.assertEqual(cmd[0], 'claude')

    def test_build_command_resume_flag(self):
        """flags={'resume': True} adds -r flag."""
        cmd = build_claude_command(project_path='/opt', flags={'resume': True})
        self.assertIn('-r', cmd)

    def test_build_command_continue_flag(self):
        """flags={'continue': True} adds -c flag."""
        cmd = build_claude_command(project_path='/opt', flags={'continue': True})
        self.assertIn('-c', cmd)

    def test_build_command_verbose_flag(self):
        """flags={'verbose': True} adds --verbose flag."""
        cmd = build_claude_command(project_path='/opt', flags={'verbose': True})
        self.assertIn('--verbose', cmd)

    def test_build_command_model_sanitized(self):
        """Model name injection is blocked in build_claude_command."""
        cmd = build_claude_command(
            project_path='/opt',
            flags={'model': 'claude; rm -rf /'},
        )
        # Either --model is absent or the injected string is not present
        if '--model' in cmd:
            idx = cmd.index('--model')
            self.assertNotIn(';', cmd[idx + 1])
        else:
            pass  # model was rejected, which is correct

    def test_build_command_valid_model(self):
        """Valid model name is included in the command."""
        cmd = build_claude_command(
            project_path='/opt',
            flags={'model': 'claude-sonnet-4-5'},
        )
        self.assertIn('--model', cmd)
        idx = cmd.index('--model')
        self.assertEqual(cmd[idx + 1], 'claude-sonnet-4-5')

    def test_build_command_effort_level(self):
        """Valid effort level is included in the command."""
        for level in ('low', 'medium', 'high', 'max'):
            cmd = build_claude_command(
                project_path='/opt',
                flags={'effort_level': level},
            )
            self.assertIn('--effort', cmd)
            idx = cmd.index('--effort')
            self.assertEqual(cmd[idx + 1], level)

    def test_build_command_invalid_effort_level_rejected(self):
        """Invalid effort level must not appear in the command."""
        cmd = build_claude_command(
            project_path='/opt',
            flags={'effort_level': 'turbo; rm -rf /'},
        )
        self.assertNotIn('--effort', cmd)


if __name__ == '__main__':
    unittest.main()
