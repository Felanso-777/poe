"""
tests/test_schema.py — Unit tests for collector.schema.

Covers:
  - Valid PoEEvent construction with auto-generated fields
  - to_dict() / from_dict() round-trip
  - Unknown metadata keys silently dropped
  - Disallowed event_type raises EventValidationError
  - Empty session_id raises EventValidationError
  - Missing required fields in from_dict raises EventValidationError
  - String metadata values truncated to 512 characters
"""

import uuid

import pytest

from collector.schema import EventType, EventValidationError, PoEEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_event(**kwargs) -> PoEEvent:
    defaults = dict(event_type=EventType.FILE_MODIFIED, session_id=str(uuid.uuid4()))
    defaults.update(kwargs)
    return PoEEvent(**defaults)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestPoEEventConstruction:
    def test_auto_generates_event_id(self):
        e = make_event()
        assert e.event_id  # non-empty
        uuid.UUID(e.event_id)  # valid UUID4

    def test_auto_generates_timestamp(self):
        e = make_event()
        assert "T" in e.timestamp  # ISO 8601 format contains 'T'

    def test_valid_event_type_string(self):
        e = make_event(event_type="FILE_MODIFIED")
        assert e.event_type == "FILE_MODIFIED"

    def test_valid_event_type_enum(self):
        e = make_event(event_type=EventType.KEYSTROKE_COUNT,
                       metadata={"count": 42})
        assert e.event_type == EventType.KEYSTROKE_COUNT

    def test_valid_metadata_kept(self):
        e = make_event(
            event_type=EventType.FILE_MODIFIED,
            metadata={"file_name": "main.py", "language": "python",
                      "lines_added": 5, "lines_deleted": 1},
        )
        assert e.metadata["file_name"] == "main.py"
        assert e.metadata["lines_added"] == 5

    def test_unknown_metadata_keys_dropped(self):
        e = make_event(
            event_type=EventType.WINDOW_FOCUS,
            metadata={"app_name": "VS Code", "window_title": "SECRET_TOKEN"},
        )
        assert "window_title" not in e.metadata
        assert e.metadata.get("app_name") == "VS Code"

    def test_no_metadata_allowed_for_session_start(self):
        e = make_event(
            event_type=EventType.SESSION_START,
            metadata={"secret": "password123"},
        )
        assert e.metadata == {}

    def test_metadata_string_truncated(self):
        long_val = "x" * 600
        e = make_event(
            event_type=EventType.FILE_MODIFIED,
            metadata={"file_name": long_val},
        )
        assert len(e.metadata["file_name"]) == 512

    def test_invalid_event_type_raises(self):
        with pytest.raises(EventValidationError):
            make_event(event_type="INVALID_TYPE")

    def test_empty_session_id_raises(self):
        with pytest.raises(EventValidationError):
            PoEEvent(event_type=EventType.FILE_MODIFIED, session_id="")

    def test_non_string_session_id_raises(self):
        with pytest.raises(EventValidationError):
            PoEEvent(event_type=EventType.FILE_MODIFIED, session_id=None)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

class TestPoEEventSerialisation:
    def test_to_dict_keys(self):
        e = make_event()
        d = e.to_dict()
        assert set(d.keys()) == {"event_id", "timestamp", "event_type",
                                  "session_id", "metadata"}

    def test_to_dict_values_match(self):
        sid = str(uuid.uuid4())
        e = make_event(session_id=sid, event_type=EventType.WINDOW_FOCUS,
                       metadata={"app_name": "Terminal"})
        d = e.to_dict()
        assert d["session_id"] == sid
        assert d["event_type"] == EventType.WINDOW_FOCUS
        assert d["metadata"]["app_name"] == "Terminal"

    def test_from_dict_roundtrip(self):
        original = make_event(
            event_type=EventType.FILE_MODIFIED,
            metadata={"file_name": "schema.py", "language": "python",
                      "lines_added": 3, "lines_deleted": 0},
        )
        reconstructed = PoEEvent.from_dict(original.to_dict())
        assert reconstructed.event_id   == original.event_id
        assert reconstructed.timestamp  == original.timestamp
        assert reconstructed.event_type == original.event_type
        assert reconstructed.session_id == original.session_id
        assert reconstructed.metadata   == original.metadata

    def test_from_dict_missing_event_type_raises(self):
        with pytest.raises(EventValidationError):
            PoEEvent.from_dict({"session_id": str(uuid.uuid4())})

    def test_from_dict_missing_session_id_raises(self):
        with pytest.raises(EventValidationError):
            PoEEvent.from_dict({"event_type": "FILE_MODIFIED"})

    def test_from_dict_auto_fills_event_id(self):
        """from_dict with no event_id should auto-generate one."""
        d = {"event_type": "WINDOW_FOCUS", "session_id": str(uuid.uuid4()),
             "metadata": {"app_name": "VS Code"}}
        e = PoEEvent.from_dict(d)
        assert e.event_id  # not None/empty
        uuid.UUID(e.event_id)  # valid UUID

    def test_from_dict_invalid_event_type_raises(self):
        with pytest.raises(EventValidationError):
            PoEEvent.from_dict({"event_type": "NOT_REAL",
                                "session_id": str(uuid.uuid4())})


# ---------------------------------------------------------------------------
# EventType enum
# ---------------------------------------------------------------------------

class TestEventType:
    def test_all_expected_types_exist(self):
        expected = {
            "FILE_MODIFIED", "FILE_CREATED", "FILE_DELETED",
            "WINDOW_FOCUS", "PROCESS_START", "PROCESS_END",
            "SESSION_START", "SESSION_END", "KEYSTROKE_COUNT",
        }
        actual = {e.value for e in EventType}
        assert expected == actual
