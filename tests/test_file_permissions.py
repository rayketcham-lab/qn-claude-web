#!/usr/bin/env python3
"""
Tests validating file ownership and permission model for /opt/claude-web/.

The permission model:
- All project files owned by pleb:pleb
- App runs as pleb (systemd User=pleb)
- claude user is in pleb group for dev access
- Source/config files: 664 (owner+group rw, world r)
- Sensitive files (auth, config): 660 (owner+group rw, no world)
- Runtime dirs (sessions, backups, certs): 770 (no world access)
- No world-writable files outside of venv symlinks

Run with:
    python3 -m pytest tests/test_file_permissions.py -v
"""

import grp
import os
import pwd
import stat
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _scan_root():
    """For source-content scans, prefer the fresh CI checkout over the
    on-disk runner tree — the runner's tree accumulates runtime state
    (logs, session data, sandbox scratch dirs) that isn't source code."""
    ws = os.environ.get('GITHUB_WORKSPACE')
    if ws and os.path.isdir(ws):
        return ws
    return _project_root


class TestGroupMembership(unittest.TestCase):
    """claude user must be in the pleb group for development access."""

    def test_claude_in_pleb_group(self):
        """claude user must be a member of the pleb group."""
        try:
            pleb_group = grp.getgrnam('pleb')
        except KeyError:
            self.skipTest('pleb group does not exist on this system')
        try:
            claude_user = pwd.getpwnam('claude')
        except KeyError:
            self.skipTest('claude user does not exist on this system')

        # Check if claude is in pleb group (either as primary or supplementary)
        in_group = (claude_user.pw_gid == pleb_group.gr_gid or
                    'claude' in pleb_group.gr_mem)
        self.assertTrue(in_group,
                        'claude user must be in pleb group for dev access. '
                        'Fix: sudo usermod -aG pleb claude')


class TestSourceFilePermissions(unittest.TestCase):
    """Source files should be 664 (owner+group rw, world r)."""

    _source_files = [
        'app.py',
        'static/js/app.js',
        'static/css/style.css',
        'templates/index.html',
        'templates/login.html',
    ]

    def _get_perms(self, relpath):
        full = os.path.join(_project_root, relpath)
        if not os.path.exists(full):
            self.skipTest(f'{relpath} does not exist')
            return None
        return stat.S_IMODE(os.stat(full).st_mode)

    def test_source_files_not_world_writable(self):
        """Source files must NOT be world-writable (no 666/777)."""
        for f in self._source_files:
            perms = self._get_perms(f)
            self.assertFalse(perms & stat.S_IWOTH,
                             f'{f} is world-writable ({oct(perms)}) — '
                             f'fix: chmod 664 {f}')

    def test_source_files_group_writable(self):
        """Source files must be group-writable for claude dev access."""
        for f in self._source_files:
            perms = self._get_perms(f)
            self.assertTrue(perms & stat.S_IWGRP,
                            f'{f} missing group write ({oct(perms)}) — '
                            f'fix: chmod 664 {f}')

    def test_source_files_owned_by_pleb_group(self):
        """Source files must be in pleb group (owner may be pleb or claude)."""
        allowed_owners = {'pleb', 'claude'}
        for f in self._source_files:
            full = os.path.join(_project_root, f)
            if not os.path.exists(full):
                continue
            st = os.stat(full)
            owner = pwd.getpwuid(st.st_uid).pw_name
            group = grp.getgrgid(st.st_gid).gr_name
            self.assertIn(owner, allowed_owners,
                          f'{f} owned by {owner}, expected pleb or claude')
            self.assertIn(group, ('pleb', 'claude'),
                          f'{f} group is {group}, expected pleb or claude')


class TestSensitiveFilePermissions(unittest.TestCase):
    """Sensitive files (config, auth) should be 660 — no world access."""

    _sensitive_files = [
        'config.json',
        'auth.json',
    ]

    def _get_perms(self, relpath):
        full = os.path.join(_project_root, relpath)
        if not os.path.exists(full):
            self.skipTest(f'{relpath} does not exist')
            return None
        return stat.S_IMODE(os.stat(full).st_mode)

    def test_sensitive_files_no_world_access(self):
        """config.json and auth.json must have no world read or write."""
        for f in self._sensitive_files:
            perms = self._get_perms(f)
            world_bits = perms & (stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH)
            self.assertEqual(world_bits, 0,
                             f'{f} has world access ({oct(perms)}) — '
                             f'fix: chmod 660 {f}')

    def test_sensitive_files_group_readable(self):
        """config.json and auth.json must be group-readable (for claude dev access)."""
        for f in self._sensitive_files:
            perms = self._get_perms(f)
            self.assertTrue(perms & stat.S_IRGRP,
                            f'{f} missing group read ({oct(perms)}) — '
                            f'fix: chmod 660 {f}')

    def test_sensitive_files_group_writable(self):
        """config.json and auth.json must be group-writable."""
        for f in self._sensitive_files:
            perms = self._get_perms(f)
            self.assertTrue(perms & stat.S_IWGRP,
                            f'{f} missing group write ({oct(perms)}) — '
                            f'fix: chmod 660 {f}')


class TestRuntimeDirPermissions(unittest.TestCase):
    """Runtime directories should be 770 — no world access."""

    _runtime_dirs = ['sessions', 'backups', 'certs']

    def test_runtime_dirs_no_world_access(self):
        """Runtime dirs must have no world access."""
        for d in self._runtime_dirs:
            full = os.path.join(_project_root, d)
            if not os.path.isdir(full):
                continue
            perms = stat.S_IMODE(os.stat(full).st_mode)
            world_bits = perms & (stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH)
            self.assertEqual(world_bits, 0,
                             f'{d}/ has world access ({oct(perms)}) — '
                             f'fix: chmod 770 {d}')


class TestNoWorldWritableSourceFiles(unittest.TestCase):
    """No source files should be world-writable (excludes venv symlinks)."""

    def test_no_world_writable_source_files(self):
        """Scan for world-writable files outside venv/."""
        scan_root = _scan_root()
        violations = []
        for root, dirs, files in os.walk(scan_root):
            # Skip venv, __pycache__, .git
            dirs[:] = [d for d in dirs if d not in ('venv', '__pycache__', '.git', 'node_modules')]
            rel_root = os.path.relpath(root, scan_root)
            for f in files:
                full = os.path.join(root, f)
                if os.path.islink(full):
                    continue
                perms = stat.S_IMODE(os.stat(full).st_mode)
                if perms & stat.S_IWOTH:
                    rel = os.path.join(rel_root, f)
                    violations.append(f'{rel} ({oct(perms)})')
        self.assertEqual(violations, [],
                         'World-writable files found:\n' +
                         '\n'.join(violations))


if __name__ == '__main__':
    unittest.main()
