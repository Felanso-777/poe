"""
tests/test_mock_collector.py — Unit tests for collector.mock_collector.MockCollector.

Covers:
  - emit_one() returns a PoEEvent with the correct session_id
  - emit_one() with explicit event_type produces that type
  - Two collectors with the same seed produce identical event sequences
  - start() + stop() collects events without raising
  - stop() before start() is safe (idempotent)
  - Events emitted for all expected event types over enough samples
"""

import time
import uuid


from collector.batcher import EventBatcher
from collector.mock_collector import MockCollector
from collector.schema import EventType, PoEEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_collector(seed=0, max_size=200) -> tuple[MockCollector, EventBatcher, list]:
    """Return (collector, batcher, received_list)."""
    sid      = str(uuid.uuid4())
    received: list[PoEEvent] = []
    batcher  = EventBatcher(
        max_size=max_size,
        max_age_seconds=60.0,
        on_flush=lambda batch: received.extend(batch),
    )
    mc = MockCollector(session_id=sid, batcher=batcher, seed=seed)
    return mc, batcher, received


# ---------------------------------------------------------------------------
# emit_one
# ---------------------------------------------------------------------------

class TestMockCollectorEmitOne:
    def test_returns_poe_event(self):
        mc, _, _ = _make_collector()
        ev = mc.emit_one()
        assert isinstance(ev, PoEEvent)

    def test_correct_session_id(self):
        sid     = str(uuid.uuid4())
        batcher = EventBatcher(max_size=100, max_age_seconds=60)
        mc      = MockCollector(session_id=sid, batcher=batcher, seed=1)
        ev      = mc.emit_one()
        assert ev.session_id == sid

    def test_explicit_event_type_respected(self):
        mc, _, _ = _make_collector()
        ev = mc.emit_one(event_type=EventType.WINDOW_FOCUS)
        assert ev.event_type == EventType.WINDOW_FOCUS

    def test_emit_one_file_modified_has_metadata(self):
        mc, _, _ = _make_collector()
        ev = mc.emit_one(event_type=EventType.FILE_MODIFIED)
        assert "file_name" in ev.metadata

    def test_emit_one_keystroke_has_count(self):
        mc, _, _ = _make_collector()
        ev = mc.emit_one(event_type=EventType.KEYSTROKE_COUNT)
        assert "count" in ev.metadata
        assert ev.metadata["count"] >= 1

    def test_emit_one_process_start_no_args(self):
        """process_name only — no command-line arguments captured."""
        mc, _, _ = _make_collector()
        ev = mc.emit_one(event_type=EventType.PROCESS_START)
        assert "process_name" in ev.metadata
        assert "args" not in ev.metadata


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

class TestMockCollectorReproducibility:
    def test_same_seed_same_sequence(self):
        mc1, bat1, _ = _make_collector(seed=42)
        mc2, bat2, _ = _make_collector(seed=42)
        events1 = [mc1.emit_one() for _ in range(20)]
        events2 = [mc2.emit_one() for _ in range(20)]
        types1  = [e.event_type for e in events1]
        types2  = [e.event_type for e in events2]
        assert types1 == types2

    def test_different_seeds_different_sequences(self):
        mc1, _, _ = _make_collector(seed=1)
        mc2, _, _ = _make_collector(seed=2)
        types1 = [mc1.emit_one().event_type for _ in range(30)]
        types2 = [mc2.emit_one().event_type for _ in range(30)]
        # Very unlikely to be identical across 30 events
        assert types1 != types2


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------

class TestMockCollectorLifecycle:
    def test_start_and_stop_no_exception(self):
        mc, batcher, _ = _make_collector(seed=0)
        mc.start(interval_seconds=0.05)
        time.sleep(0.3)
        remaining = mc.stop()
        assert isinstance(remaining, list)

    def test_stop_before_start_is_safe(self):
        mc, batcher, _ = _make_collector()
        # stop without start should not raise
        result = mc.stop()
        assert result == []

    def test_start_twice_is_safe(self):
        """Calling start() a second time while running should be a no-op."""
        mc, batcher, _ = _make_collector()
        mc.start(interval_seconds=0.1)
        mc.start(interval_seconds=0.1)  # second call — should not raise
        mc.stop()

    def test_events_accumulate_during_run(self):
        """After a brief run, at least some events should be buffered or received."""
        sid      = str(uuid.uuid4())
        received: list[PoEEvent] = []
        batcher  = EventBatcher(
            max_size=5,
            max_age_seconds=60.0,
            on_flush=lambda batch: received.extend(batch),
        )
        mc = MockCollector(session_id=sid, batcher=batcher, seed=7)
        mc.start(interval_seconds=0.05)
        time.sleep(0.5)
        remaining = mc.stop()
        total = len(received) + len(remaining)
        assert total >= 1


# ---------------------------------------------------------------------------
# Coverage of emitted event types
# ---------------------------------------------------------------------------

class TestMockCollectorEventTypeCoverage:
    def test_all_non_session_types_can_be_emitted(self):
        """Over 200 random emissions, every non-session event type should appear."""
        mc, _, _ = _make_collector(seed=99)
        types_seen = set()
        for _ in range(200):
            ev = mc.emit_one()
            types_seen.add(ev.event_type)

        expected = {
            EventType.FILE_MODIFIED, EventType.FILE_CREATED, EventType.FILE_DELETED,
            EventType.WINDOW_FOCUS, EventType.PROCESS_START, EventType.PROCESS_END,
            EventType.KEYSTROKE_COUNT,
        }
        assert expected == types_seen
