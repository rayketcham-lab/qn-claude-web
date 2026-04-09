#!/usr/bin/env python3
"""
Tests validating terminal mouse tracking reset behavior in app.js.

When TUI apps (like Claude Code CLI) enable mouse tracking and exit uncleanly,
xterm.js stays in mouse-capture mode. This breaks normal text selection (requiring
Shift) and clipboard paste. The fix: reset mouse tracking escape sequences on
every terminal connect and reconnect.

Run with:
    python3 -m pytest tests/test_terminal_mouse.py -v
"""

import os
import re
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_JS = os.path.join(_project_root, 'static', 'js', 'app.js')


def _read_app_js():
    with open(_APP_JS) as f:
        return f.read()


class TestTerminalMouseReset(unittest.TestCase):
    """Verify xterm.js mouse tracking is reset on connect/reconnect."""

    @classmethod
    def setUpClass(cls):
        cls.js = _read_app_js()

    def test_mouse_reset_sequences_exist(self):
        """app.js must contain all four mouse tracking disable sequences."""
        for seq in ['?1000l', '?1002l', '?1003l', '?1006l']:
            self.assertIn(seq, self.js,
                          f'Missing mouse tracking reset sequence: {seq}')

    def test_mouse_reset_in_create_terminal(self):
        """_createTerminalInstance must reset mouse tracking after open()."""
        create_match = re.search(
            r'_createTerminalInstance\s*\(.*?\)\s*\{(.*?)^\s{4}\}',
            self.js, re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(create_match,
                             '_createTerminalInstance method not found')
        body = create_match.group(1)

        open_pos = body.find('terminal.open(')
        self.assertGreater(open_pos, -1, 'terminal.open() not found in method')

        after_open = body[open_pos:]
        self.assertRegex(after_open, r'\?1003l',
                         'Mouse tracking reset not found after terminal.open()')

    def test_mouse_reset_in_add_terminal_tab(self):
        """_addTerminalTab must reset mouse tracking on connect."""
        # Find the method definition (not a call site)
        match = re.search(r'_addTerminalTab\s*\([^)]*\)\s*\{', self.js)
        self.assertIsNotNone(match, '_addTerminalTab method not found')
        body = self.js[match.start():match.start() + 1000]
        self.assertRegex(body, r'\?1003l',
                         'Mouse tracking reset not found in _addTerminalTab')

    def test_mouse_reset_on_reconnect(self):
        """terminal_created handler must call _addTerminalTab (which resets mouse)."""
        created_match = re.search(
            r"socket\.on\(\s*['\"]terminal_created['\"].*?\}\s*\)",
            self.js, re.DOTALL)
        self.assertIsNotNone(created_match,
                             'terminal_created handler not found')
        self.assertIn('_addTerminalTab', created_match.group(0),
                      'terminal_created must call _addTerminalTab')


class TestTerminalClipboardHandling(unittest.TestCase):
    """Verify clipboard operations don't require Shift modifier."""

    @classmethod
    def setUpClass(cls):
        cls.js = _read_app_js()

    def test_custom_key_handler_passes_ctrl_v(self):
        """Ctrl+V must be passed to browser (return false) for paste."""
        self.assertRegex(
            self.js,
            r"e\.key\s*===\s*['\"]v['\"]\)?\s*return\s+false",
            'Ctrl+V must return false to let browser handle paste')

    def test_custom_key_handler_passes_ctrl_c_with_selection(self):
        """Ctrl+C with selection must be passed to browser for copy."""
        self.assertRegex(
            self.js,
            r"e\.key\s*===\s*['\"]c['\"].*hasSelection\(\).*return\s+false",
            'Ctrl+C with selection must return false for browser copy')

    def test_right_click_paste_not_blocked(self):
        """Terminal must not have a contextmenu handler that blocks paste."""
        context_match = re.search(
            r"terminal.*addEventListener\(\s*['\"]contextmenu['\"].*?preventDefault",
            self.js, re.DOTALL)
        self.assertIsNone(context_match,
                          'contextmenu handler should not preventDefault (blocks paste)')


if __name__ == '__main__':
    unittest.main()
