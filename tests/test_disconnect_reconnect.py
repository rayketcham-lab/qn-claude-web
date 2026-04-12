#!/usr/bin/env python3
"""
Tests for WebSocket disconnect/reconnect terminal session continuity.

Reproduces and prevents regression of: "POOF I lost both sessions" — when a
WebSocket transiently drops, the disconnect grace period works server-side,
but the *client* has no way to know which of its local terminal tabs are
still alive. The server-side fix is a `terminal_sync` event emitted on every
(re)connect listing the terminals owned by the new SID. The client uses this
to reconcile its local tab list and remove zombies.

These tests are intentionally verbose — when something fails in CI, the
output should be enough to diagnose without re-running locally. Every test
logs:
  [PHASE] what it's doing
  [STATE] full snapshot of relevant globals
  [EVENT] every WS event observed, with payload
  [CHECK] every assertion, with the actual vs expected values

Run:
    python3 -m pytest tests/test_disconnect_reconnect.py -v -s
    # -s lets the diagnostic prints reach the terminal

Set TEST_DEBUG=1 in env for even more verbose dumps.

Test classes
------------
TestGracePeriodCancel       — reconnect cancels pending detach timer
TestGraceExpiry             — timer firing detaches PTY, leaves tmux alive
TestTerminalSync            — the new event (RED until app.py fix lands)
TestBrowserMappingHygiene   — browser_to_sid cleanup safety
TestEndToEndReconnect       — full disconnect → expire → reconnect flow
TestConfigDefaults          — disconnect_grace_secs default sanity check
"""

import json
import os
import sys
import threading
import time
import unittest
from contextlib import contextmanager

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_vendor_dir = os.path.join(_project_root, 'vendor')
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import app as app_module

flask_app = app_module.app
flask_app.config['TESTING'] = True
flask_app.config['SECRET_KEY'] = 'test-secret-disconnect-reconnect'
flask_app.config['WTF_CSRF_ENABLED'] = False


# ---------------------------------------------------------------------------
# Diagnostic helpers — verbose state dumps & structured logging
# ---------------------------------------------------------------------------

DEBUG = os.environ.get('TEST_DEBUG', '0') == '1'


def _log(tag, msg, **kwargs):
    """Structured log line that survives pytest -s."""
    extras = ' '.join(f'{k}={v!r}' for k, v in kwargs.items())
    line = f'  [{tag}] {msg}'
    if extras:
        line += f'  ({extras})'
    print(line, flush=True)


def _dump_state(label='state'):
    """Snapshot of every global involved in disconnect/reconnect flow."""
    with app_module.pending_disconnect_lock:
        b2s = dict(app_module.browser_to_sid)
        pending = {sid: f'<Timer alive={t.is_alive()}>'
                   for sid, t in app_module.pending_disconnects.items()}
    with app_module.active_terminals_lock:
        terms = {
            tid: {
                'ws_sid': t.get('ws_sid'),
                'tmux_session': t.get('tmux_session'),
                'project': t.get('project'),
                'pid': t.get('pid'),
            }
            for tid, t in app_module.active_terminals.items()
        }
    snap = {
        'browser_to_sid': b2s,
        'pending_disconnects': pending,
        'active_terminals': terms,
        'disconnect_grace_secs': app_module.CONFIG.get('disconnect_grace_secs'),
    }
    _log('STATE', label, **{'json': json.dumps(snap, default=str, indent=2)})
    return snap


@contextmanager
def _phase(name):
    """Mark a test phase so failures show which step blew up."""
    _log('PHASE', f'>>> {name}')
    t0 = time.time()
    try:
        yield
    finally:
        _log('PHASE', f'<<< {name}', took_ms=int((time.time() - t0) * 1000))


def _events_received(sc):
    """Drain pending events and return the full list, also logging each."""
    received = sc.get_received()
    for ev in received:
        _log('EVENT', ev.get('name', '?'), args=ev.get('args'))
    return received


def _events_named(sc, name):
    return [e for e in _events_received(sc) if e.get('name') == name]


def _reset_globals():
    """Clean every global this suite touches. Run in setUp AND tearDown."""
    with app_module.pending_disconnect_lock:
        for sid, timer in list(app_module.pending_disconnects.items()):
            try:
                timer.cancel()
            except Exception:
                pass
        app_module.pending_disconnects.clear()
        app_module.browser_to_sid.clear()
    with app_module.active_terminals_lock:
        app_module.active_terminals.clear()


def _snapshot_config():
    return dict(app_module.CONFIG)


def _restore_config(snap):
    app_module.CONFIG.clear()
    app_module.CONFIG.update(snap)


def _disable_auth():
    app_module.AUTH['auth'] = {'enabled': False, 'username': '', 'password_hash': ''}
    app_module.AUTH['users'] = []


def _make_fake_terminal(ws_sid, tmux_session='qn-fake0001', project='/tmp', pid=99999):
    """Insert a synthetic active_terminals entry without spawning a real PTY.

    For tests that exercise ws_sid bookkeeping only, a real PTY is overkill
    and brittle. We bypass terminal_create and inject the dict directly.
    """
    tid = f'term-{tmux_session}'
    with app_module.active_terminals_lock:
        app_module.active_terminals[tid] = {
            'ws_sid': ws_sid,
            'tmux_session': tmux_session,
            'project': project,
            'pid': pid,
            # Fields other code paths may read; keep present but inert.
            'fd': -1,
            'log_file': '/dev/null',
            'created_at': time.time(),
        }
    _log('SETUP', f'injected fake terminal', tid=tid, ws_sid=ws_sid, tmux=tmux_session)
    return tid


def _make_test_client(query_string=''):
    """Return (http_client, sc, sid) — sid extracted after connect."""
    from flask_socketio import SocketIOTestClient
    http_client = flask_app.test_client()
    sc = SocketIOTestClient(
        flask_app, app_module.socketio,
        flask_test_client=http_client,
        query_string=query_string,
    )
    # The SocketIO test client exposes its sid via .eio_sid after connect.
    sid = getattr(sc, 'sid', None) or getattr(sc, 'eio_sid', None)
    _log('CONNECT', 'client established', sid=sid, query=query_string)
    return http_client, sc, sid


def _current_sid_for_browser(browser_id):
    with app_module.pending_disconnect_lock:
        return app_module.browser_to_sid.get(browser_id)


# ---------------------------------------------------------------------------
# Base class — handles per-test global cleanup + auth disable
# ---------------------------------------------------------------------------

class _DisconnectTestBase(unittest.TestCase):
    def setUp(self):
        self._cfg_snap = _snapshot_config()
        _disable_auth()
        _reset_globals()
        # Use a short grace so expiry tests don't take forever.
        app_module.CONFIG['disconnect_grace_secs'] = 1
        _log('TEST', f'--- {self.id()} ---')
        if DEBUG:
            _dump_state('setUp')

    def tearDown(self):
        if DEBUG:
            _dump_state('tearDown')
        _reset_globals()
        _restore_config(self._cfg_snap)


# ===================================================================
# 1. Grace period cancellation on reconnect
# ===================================================================
class TestGracePeriodCancel(_DisconnectTestBase):
    """Reconnecting the same browser_id must cancel the pending detach."""

    def test_reconnect_cancels_pending_disconnect_timer(self):
        browser_id = 'cancel-grace-001'

        with _phase('initial connect + inject terminal'):
            _, sc1, _ = _make_test_client(f'browser_id={browser_id}')
            _events_received(sc1)
            sid1 = _current_sid_for_browser(browser_id)
            self.assertIsNotNone(sid1, msg='browser_to_sid mapping missing after connect')
            _make_fake_terminal(sid1)

        with _phase('disconnect — grace timer should start'):
            sc1.disconnect()
            with app_module.pending_disconnect_lock:
                pending_count = len(app_module.pending_disconnects)
                has_sid1 = sid1 in app_module.pending_disconnects
            _log('CHECK', 'pending disconnects', count=pending_count, has_sid1=has_sid1)
            self.assertTrue(
                has_sid1,
                msg=f'expected sid {sid1!r} in pending_disconnects; got {list(app_module.pending_disconnects)}'
            )

        with _phase('reconnect with same browser_id'):
            _, sc2, _ = _make_test_client(f'browser_id={browser_id}')
            _events_received(sc2)
            with app_module.pending_disconnect_lock:
                still_pending = sid1 in app_module.pending_disconnects
            _log('CHECK', 'old sid still pending after reconnect?', still_pending=still_pending)
            self.assertFalse(
                still_pending,
                msg=f'old sid {sid1!r} grace timer was NOT cancelled after reconnect; '
                    f'pending now: {list(app_module.pending_disconnects)}'
            )

        with _phase('terminal must be re-associated to new sid'):
            sid2 = _current_sid_for_browser(browser_id)
            self.assertNotEqual(sid1, sid2, msg='reconnect should produce a new ws_sid')
            with app_module.active_terminals_lock:
                associations = [
                    (tid, t.get('ws_sid'))
                    for tid, t in app_module.active_terminals.items()
                ]
            _log('CHECK', 'terminal associations after reconnect',
                 associations=associations, sid1=sid1, sid2=sid2)
            self.assertTrue(
                all(ws == sid2 for _, ws in associations),
                msg=f'expected all terminals to point at new sid {sid2!r}, got {associations}'
            )
            sc2.disconnect()

    def test_reconnect_with_different_browser_id_does_not_cancel(self):
        """Sanity: a *different* browser reconnecting must NOT cancel the grace
        timer of an unrelated previous client."""
        bid_a = 'browser-A'
        bid_b = 'browser-B'

        _, sc_a, _ = _make_test_client(f'browser_id={bid_a}')
        _events_received(sc_a)
        sid_a = _current_sid_for_browser(bid_a)
        _make_fake_terminal(sid_a, tmux_session='qn-aaaa0001')
        sc_a.disconnect()

        with app_module.pending_disconnect_lock:
            self.assertIn(sid_a, app_module.pending_disconnects,
                          msg='A grace timer should be pending')

        _, sc_b, _ = _make_test_client(f'browser_id={bid_b}')
        _events_received(sc_b)

        with app_module.pending_disconnect_lock:
            still = sid_a in app_module.pending_disconnects
        _log('CHECK', 'A still pending after B connect', still=still)
        self.assertTrue(
            still,
            msg=f'B connecting must not affect A; pending={list(app_module.pending_disconnects)}'
        )
        sc_b.disconnect()


# ===================================================================
# 2. Grace expiry detaches the PTY
# ===================================================================
class TestGraceExpiry(_DisconnectTestBase):
    """When grace expires with no reconnect, the terminal is removed from
    active_terminals (tmux session itself survives — covered elsewhere)."""

    def test_grace_expiry_removes_terminal_from_active_set(self):
        browser_id = 'expiry-001'

        with _phase('connect + inject terminal'):
            _, sc, _ = _make_test_client(f'browser_id={browser_id}')
            _events_received(sc)
            sid = _current_sid_for_browser(browser_id)
            tid = _make_fake_terminal(sid, tmux_session='qn-expir001')

        with _phase('disconnect; wait > grace period'):
            sc.disconnect()
            grace = app_module.CONFIG['disconnect_grace_secs']
            time.sleep(grace + 0.5)

        with _phase('verify active_terminals scrubbed'):
            with app_module.active_terminals_lock:
                still_present = tid in app_module.active_terminals
                remaining = list(app_module.active_terminals)
            _log('CHECK', 'terminal removed?', still_present=still_present, remaining=remaining)
            self.assertFalse(
                still_present,
                msg=f'expected terminal {tid!r} to be removed after grace expiry; '
                    f'active_terminals still has: {remaining}'
            )
            with app_module.pending_disconnect_lock:
                self.assertNotIn(
                    sid, app_module.pending_disconnects,
                    msg='expired timer should self-remove from pending_disconnects'
                )


# ===================================================================
# 3. terminal_sync — the new event (these are the RED tests)
# ===================================================================
class TestTerminalSync(_DisconnectTestBase):
    """The server emits `terminal_sync` on every connect listing the terminals
    owned by the (possibly newly re-associated) ws_sid. The client uses this
    to drop zombie tabs and continue normally.

    These tests will FAIL until the emit is added to handle_connect in app.py.
    That failure IS the spec — the diagnostic output names the missing event.
    """

    def _assert_sync_event(self, sc, expected_terminals):
        events = _events_received(sc)
        sync = [e for e in events if e.get('name') == 'terminal_sync']
        self.assertTrue(
            sync,
            msg=(
                'expected a "terminal_sync" event on connect, got none. '
                f'events received: {[e.get("name") for e in events]}. '
                'FIX: add `emit("terminal_sync", {"active_terminals": [...]})` '
                'at end of handle_connect() in app.py near line 2716.'
            )
        )
        payload = sync[-1]['args'][0] if sync[-1].get('args') else {}
        actual = sorted(t.get('id') for t in payload.get('active_terminals', []))
        expected = sorted(expected_terminals)
        _log('CHECK', 'sync payload', actual=actual, expected=expected, raw=payload)
        self.assertEqual(
            actual, expected,
            msg=f'terminal_sync payload mismatch — server reports {actual}, '
                f'test expected {expected}. Full payload: {payload}'
        )
        return payload

    def test_sync_emitted_on_fresh_connect_with_no_terminals(self):
        browser_id = 'sync-fresh-001'
        _, sc, _ = _make_test_client(f'browser_id={browser_id}')
        self._assert_sync_event(sc, expected_terminals=[])
        sc.disconnect()

    def test_sync_lists_terminals_after_reconnect(self):
        browser_id = 'sync-reconnect-002'

        with _phase('first connect + 2 terminals'):
            _, sc1, _ = _make_test_client(f'browser_id={browser_id}')
            _events_received(sc1)  # drain initial events
            sid1 = _current_sid_for_browser(browser_id)
            tid_a = _make_fake_terminal(sid1, tmux_session='qn-syncA001')
            tid_b = _make_fake_terminal(sid1, tmux_session='qn-syncB001')

        with _phase('disconnect (within grace) + reconnect'):
            sc1.disconnect()
            _, sc2, _ = _make_test_client(f'browser_id={browser_id}')

        with _phase('reconnect must emit terminal_sync listing both terminals'):
            self._assert_sync_event(sc2, expected_terminals=[tid_a, tid_b])
            sc2.disconnect()

    def test_sync_excludes_terminals_owned_by_other_sids(self):
        """A connect from browser X must not see browser Y's terminals."""
        bid_x = 'sync-isolate-X'
        bid_y = 'sync-isolate-Y'

        _, sc_y, _ = _make_test_client(f'browser_id={bid_y}')
        _events_received(sc_y)
        sid_y = _current_sid_for_browser(bid_y)
        _make_fake_terminal(sid_y, tmux_session='qn-otherY01')

        _, sc_x, _ = _make_test_client(f'browser_id={bid_x}')
        # X has no terminals — sync payload must be empty even though Y has one.
        self._assert_sync_event(sc_x, expected_terminals=[])

        sc_x.disconnect()
        sc_y.disconnect()


# ===================================================================
# 4. browser_to_sid cleanup safety
# ===================================================================
class TestBrowserMappingHygiene(_DisconnectTestBase):
    """Cleanup paths must not leave stale browser_id → sid pointers."""

    def test_grace_expiry_removes_browser_mapping(self):
        browser_id = 'hygiene-001'
        _, sc, _ = _make_test_client(f'browser_id={browser_id}')
        _events_received(sc)
        sid = _current_sid_for_browser(browser_id)
        _make_fake_terminal(sid)
        sc.disconnect()
        time.sleep(app_module.CONFIG['disconnect_grace_secs'] + 0.5)

        with app_module.pending_disconnect_lock:
            remaining_for_browser = app_module.browser_to_sid.get(browser_id)
        _log('CHECK', 'browser mapping after expiry',
             browser_id=browser_id, remaining_sid=remaining_for_browser)
        self.assertIsNone(
            remaining_for_browser,
            msg=f'browser_to_sid[{browser_id!r}] should be cleaned up after grace expiry; '
                f'still points to {remaining_for_browser!r}'
        )


# ===================================================================
# 5. End-to-end: disconnect → expire → fresh reconnect → see detached list
# ===================================================================
class TestEndToEndReconnect(_DisconnectTestBase):
    """Full happy-path coverage: even after grace expires, the client should
    be able to reconnect cleanly and learn (via terminal_sync) that it owns
    no live terminals on the new SID."""

    def test_full_disconnect_expire_reconnect_flow(self):
        browser_id = 'e2e-001'

        with _phase('1. connect + start work'):
            _, sc1, _ = _make_test_client(f'browser_id={browser_id}')
            _events_received(sc1)
            sid1 = _current_sid_for_browser(browser_id)
            _make_fake_terminal(sid1, tmux_session='qn-e2e00001')

        with _phase('2. disconnect, allow grace to expire'):
            sc1.disconnect()
            time.sleep(app_module.CONFIG['disconnect_grace_secs'] + 0.5)
            with app_module.active_terminals_lock:
                self.assertEqual(
                    len(app_module.active_terminals), 0,
                    msg='all terminals should be reaped by now'
                )

        with _phase('3. fresh reconnect — sync should report empty'):
            _, sc2, _ = _make_test_client(f'browser_id={browser_id}')
            events = _events_received(sc2)
            sync = [e for e in events if e.get('name') == 'terminal_sync']
            self.assertTrue(
                sync,
                msg=f'no terminal_sync on reconnect; events={[e.get("name") for e in events]}'
            )
            payload = sync[-1]['args'][0] if sync[-1].get('args') else {}
            self.assertEqual(
                payload.get('active_terminals', []), [],
                msg=f'fresh reconnect should report empty terminal list, got {payload!r}'
            )
            sc2.disconnect()


# ===================================================================
# 6. Config defaults
# ===================================================================
class TestConfigDefaults(unittest.TestCase):
    """The grace period must be set to something sane by default."""

    def test_disconnect_grace_secs_present_and_sane(self):
        # Reload the canonical defaults rather than the test-tweaked CONFIG.
        defaults = app_module.DEFAULT_CONFIG if hasattr(app_module, 'DEFAULT_CONFIG') else {}
        # Fall back to live CONFIG if defaults dict isn't exposed.
        grace = defaults.get('disconnect_grace_secs', app_module.CONFIG.get('disconnect_grace_secs'))
        _log('CHECK', 'disconnect_grace_secs default', value=grace)
        self.assertIsNotNone(grace, msg='disconnect_grace_secs must be defined')
        self.assertIsInstance(grace, (int, float), msg=f'must be numeric, got {type(grace).__name__}')
        self.assertGreaterEqual(grace, 5, msg='grace too short — flaky transient drops will detach')
        self.assertLessEqual(grace, 600, msg='grace too long — orphans pile up')


if __name__ == '__main__':
    unittest.main(verbosity=2)
