"""
tests/test_session.py — Unit tests for collector.session.SessionManager.

Covers:
  - create_session() returns a UUID string
  - start_session() sets is_running=True; writes SESSION_START event
  - stop_session() sets is_running=False; writes SESSION_END with duration_seconds
  - Starting an already-running session raises SessionError
  - Stopping a non-running session raises SessionError
  - append_event() on a running session persists the event to JSONL
  - append_event() on a stopped session raises SessionError
  - get_session() raises SessionError for unknown ID
  - list_sessions() returns all created sessions
"""

import uuid

import pytest

from collector.schema import EventType, PoEEvent
from collector.session import SessionError, SessionManager
from collector.storage import JSONLStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_manager(tmp_path) -> SessionManager:
    return SessionManager(storage_dir=tmp_path / "sessions")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSessionManagerCreate:
    def test_create_returns_uuid_string(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        uuid.UUID(sid)  # raises if not valid UUID

    def test_create_adds_to_list(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        sessions = mgr.list_sessions()
        assert any(s.session_id == sid for s in sessions)

    def test_create_does_not_start_session(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        s   = mgr.get_session(sid)
        assert not s.is_running


class TestSessionManagerStart:
    def test_start_sets_is_running(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        mgr.start_session(sid)
        assert mgr.get_session(sid).is_running

    def test_start_writes_session_start_event(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        mgr.start_session(sid)
        session = mgr.get_session(sid)
        events = JSONLStorage().read_all(session.storage_path)
        types  = [e.event_type for e in events]
        assert EventType.SESSION_START in types

    def test_start_already_running_raises(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        mgr.start_session(sid)
        with pytest.raises(SessionError):
            mgr.start_session(sid)

    def test_start_unknown_id_raises(self, tmp_path):
        mgr = make_manager(tmp_path)
        with pytest.raises(SessionError):
            mgr.start_session(str(uuid.uuid4()))


class TestSessionManagerStop:
    def test_stop_clears_is_running(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        mgr.start_session(sid)
        mgr.stop_session(sid)
        assert not mgr.get_session(sid).is_running

    def test_stop_writes_session_end_event(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        mgr.start_session(sid)
        mgr.stop_session(sid)
        session = mgr.get_session(sid)
        events  = JSONLStorage().read_all(session.storage_path)
        types   = [e.event_type for e in events]
        assert EventType.SESSION_END in types

    def test_stop_records_duration(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        mgr.start_session(sid)
        mgr.stop_session(sid)
        session = mgr.get_session(sid)
        events  = JSONLStorage().read_all(session.storage_path)
        end_ev  = next(e for e in events if e.event_type == EventType.SESSION_END)
        assert "duration_seconds" in end_ev.metadata
        assert end_ev.metadata["duration_seconds"] >= 0

    def test_stop_not_running_raises(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        with pytest.raises(SessionError):
            mgr.stop_session(sid)

    def test_stop_already_stopped_raises(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        mgr.start_session(sid)
        mgr.stop_session(sid)
        with pytest.raises(SessionError):
            mgr.stop_session(sid)


class TestSessionManagerAppendEvent:
    def test_append_persists_event(self, tmp_path):
        mgr  = make_manager(tmp_path)
        sid  = mgr.create_session()
        mgr.start_session(sid)
        ev = PoEEvent(event_type=EventType.KEYSTROKE_COUNT,
                      session_id=sid,
                      metadata={"count": 99})
        mgr.append_event(ev)
        session = mgr.get_session(sid)
        events  = JSONLStorage().read_all(session.storage_path)
        ks_events = [e for e in events if e.event_type == EventType.KEYSTROKE_COUNT]
        assert len(ks_events) == 1
        assert ks_events[0].metadata["count"] == 99

    def test_append_to_stopped_session_raises(self, tmp_path):
        mgr = make_manager(tmp_path)
        sid = mgr.create_session()
        mgr.start_session(sid)
        mgr.stop_session(sid)
        ev = PoEEvent(event_type=EventType.WINDOW_FOCUS,
                      session_id=sid,
                      metadata={"app_name": "Test"})
        with pytest.raises(SessionError):
            mgr.append_event(ev)


class TestSessionManagerListAndGet:
    def test_list_sessions_returns_all(self, tmp_path):
        mgr  = make_manager(tmp_path)
        sids = [mgr.create_session() for _ in range(3)]
        listed_ids = {s.session_id for s in mgr.list_sessions()}
        assert set(sids) == listed_ids

    def test_get_unknown_raises(self, tmp_path):
        mgr = make_manager(tmp_path)
        with pytest.raises(SessionError):
            mgr.get_session("does-not-exist")
