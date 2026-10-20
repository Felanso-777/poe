"""
tests/test_storage.py — Unit tests for collector.storage.JSONLStorage.

Covers:
  - Single append writes one valid JSONL line
  - append_batch writes N lines atomically
  - read_all reconstructs events correctly
  - Malformed JSON line is skipped; rest of file is still readable
  - Invalid-schema line is skipped; rest of file is still readable
  - read_all on a non-existent file returns []
  - read_raw returns plain dicts without schema validation
"""

import json
import uuid


from collector.schema import EventType, PoEEvent
from collector.storage import JSONLStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(et=EventType.FILE_MODIFIED, meta=None) -> PoEEvent:
    m = meta or {"file_name": "test.py", "language": "python"}
    return PoEEvent(event_type=et, session_id=str(uuid.uuid4()), metadata=m)


# ---------------------------------------------------------------------------
# Write tests
# ---------------------------------------------------------------------------

class TestJSONLStorageWrite:
    def test_append_creates_file(self, tmp_path):
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"
        ev      = _event()
        storage.append(ev, path)
        assert path.exists()

    def test_append_writes_one_line(self, tmp_path):
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"
        ev      = _event()
        storage.append(ev, path)
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_append_line_is_valid_json(self, tmp_path):
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"
        ev      = _event()
        storage.append(ev, path)
        line = path.read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["event_id"] == ev.event_id

    def test_append_batch_writes_n_lines(self, tmp_path):
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"
        events  = [_event() for _ in range(5)]
        storage.append_batch(events, path)
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 5

    def test_append_batch_empty_is_noop(self, tmp_path):
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"
        storage.append_batch([], path)  # should not create file or raise
        assert not path.exists()

    def test_multiple_appends_accumulate(self, tmp_path):
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"
        for _ in range(3):
            storage.append(_event(), path)
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3


# ---------------------------------------------------------------------------
# Read tests
# ---------------------------------------------------------------------------

class TestJSONLStorageRead:
    def test_read_all_returns_empty_for_missing_file(self, tmp_path):
        storage = JSONLStorage()
        result  = storage.read_all(tmp_path / "nonexistent.jsonl")
        assert result == []

    def test_read_all_reconstructs_events(self, tmp_path):
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"
        events  = [_event() for _ in range(3)]
        storage.append_batch(events, path)

        loaded = storage.read_all(path)
        assert len(loaded) == 3
        loaded_ids = {e.event_id for e in loaded}
        assert loaded_ids == {e.event_id for e in events}

    def test_read_all_skips_malformed_json(self, tmp_path, caplog):
        """A corrupt line must not prevent reading subsequent valid lines."""
        import logging
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"

        ev = _event()
        storage.append(ev, path)
        # Inject a malformed line
        with path.open("a", encoding="utf-8") as fh:
            fh.write("NOT_VALID_JSON\n")
        # Append another good event
        ev2 = _event()
        storage.append(ev2, path)

        with caplog.at_level(logging.WARNING):
            loaded = storage.read_all(path)

        assert len(loaded) == 2
        assert any("malformed" in r.message.lower() for r in caplog.records)

    def test_read_all_skips_invalid_schema_line(self, tmp_path, caplog):
        """A line missing session_id must be skipped gracefully."""
        import logging
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"

        ev = _event()
        storage.append(ev, path)
        # Inject line with missing required field
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event_type": "FILE_MODIFIED"}) + "\n")
        ev2 = _event()
        storage.append(ev2, path)

        with caplog.at_level(logging.WARNING):
            loaded = storage.read_all(path)

        assert len(loaded) == 2

    def test_read_raw_returns_dicts(self, tmp_path):
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"
        events  = [_event() for _ in range(2)]
        storage.append_batch(events, path)

        raw = storage.read_raw(path)
        assert len(raw) == 2
        assert all(isinstance(r, dict) for r in raw)

    def test_read_raw_skips_malformed(self, tmp_path):
        storage = JSONLStorage()
        path    = tmp_path / "session.jsonl"
        storage.append(_event(), path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write("GARBAGE\n")
        storage.append(_event(), path)

        raw = storage.read_raw(path)
        assert len(raw) == 2  # malformed line skipped
