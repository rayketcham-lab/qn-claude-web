#!/usr/bin/env python3
"""
Tests validating WebUI button/handler consistency between index.html and app.js.

Every interactive element in the HTML must have a corresponding event handler in JS.
Every JS getElementById/querySelector must reference an ID that exists in HTML.

Run with:
    python3 -m pytest tests/test_webui_elements.py -v
"""

import os
import re
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_JS = os.path.join(_project_root, 'static', 'js', 'app.js')
_INDEX_HTML = os.path.join(_project_root, 'templates', 'index.html')


def _read(path):
    with open(path) as f:
        return f.read()


class TestTouchShortcutButtons(unittest.TestCase):
    """Touch shortcut buttons must have event handlers."""

    @classmethod
    def setUpClass(cls):
        cls.js = _read(_APP_JS)
        cls.html = _read(_INDEX_HTML)

    def test_touch_controls_exist_in_html(self):
        """HTML must have touch-controls toolbar."""
        self.assertIn('touch-controls', self.html)

    def test_touch_key_handler_exists(self):
        """app.js must handle touch-key button clicks."""
        self.assertRegex(self.js, r'touch-key|touch-controls|data-key',
                         'No event handler for touch shortcut buttons')

    def test_touch_keys_send_to_terminal(self):
        """Touch key handler must send data to terminal (terminal_input)."""
        touch_section = re.search(r'touch.*(ctrl-c|data-key).*terminal', self.js,
                                  re.DOTALL | re.IGNORECASE)
        self.assertIsNotNone(touch_section,
                             'Touch key handler must interact with terminal')


class TestMobileSidebarButtons(unittest.TestCase):
    """Mobile sidebar open/close buttons must have handlers."""

    @classmethod
    def setUpClass(cls):
        cls.js = _read(_APP_JS)

    def test_sidebar_open_handler(self):
        """btn-open-sidebar must have a click handler."""
        self.assertRegex(self.js, r'btn-open-sidebar',
                         'No handler for btn-open-sidebar')

    def test_sidebar_close_handler(self):
        """btn-hamburger must have a click handler to close sidebar."""
        self.assertRegex(self.js, r'btn-hamburger',
                         'No handler for btn-hamburger (close sidebar)')

    def test_sidebar_overlay_handler(self):
        """sidebar-overlay must have a click handler to close sidebar."""
        self.assertRegex(self.js, r'sidebar-overlay',
                         'No handler for sidebar-overlay')


class TestElementIdConsistency(unittest.TestCase):
    """JS element references must match HTML IDs."""

    @classmethod
    def setUpClass(cls):
        cls.js = _read(_APP_JS)
        cls.html = _read(_INDEX_HTML)

    def test_file_tree_id_matches(self):
        """JS must reference the correct file tree ID from HTML."""
        html_id = re.search(r'id="(files?-tree)"', self.html)
        self.assertIsNotNone(html_id, 'files-tree element not found in HTML')
        actual_id = html_id.group(1)
        self.assertIn(f"'{actual_id}'", self.js,
                      f'app.js must reference "{actual_id}" (HTML ID), not a different variant')

    def test_search_results_id_matches(self):
        """JS must reference the correct search results ID from HTML."""
        html_id = re.search(r'id="((?:chat-)?search-results)"', self.html)
        self.assertIsNotNone(html_id, 'search-results element not found in HTML')
        actual_id = html_id.group(1)
        self.assertRegex(self.js, rf"getElementById\(\s*'{re.escape(actual_id)}'",
                         f'app.js must use getElementById("{actual_id}")')


class TestIssueReporterIntegration(unittest.TestCase):
    """Issue reporter widget must be integrated."""

    @classmethod
    def setUpClass(cls):
        cls.html = _read(_INDEX_HTML)
        cls.js_path = os.path.join(_project_root, 'static', 'js', 'issue-reporter.js')

    def test_issue_reporter_script_exists(self):
        """issue-reporter.js must exist in static/js/."""
        self.assertTrue(os.path.exists(self.js_path),
                        'static/js/issue-reporter.js not found')

    def test_issue_reporter_loaded_in_html(self):
        """index.html must load issue-reporter.js."""
        self.assertRegex(self.html, r'issue-reporter\.js',
                         'issue-reporter.js not loaded in index.html')

    def test_issue_reporter_initialized(self):
        """IssueReporter.init() must be called with config."""
        self.assertRegex(self.html, r'IssueReporter\.init',
                         'IssueReporter.init() not called in index.html')


if __name__ == '__main__':
    unittest.main()
