"""
tests/test_batcher.py — Unit tests for collector.batcher.EventBatcher.

Covers:
  - Adding fewer than max_size events does not flush
  - Adding exactly max_size events triggers size flush and returns batch
  - force_flush() drains buffer regardless of count
  - on_flush callback is invoked on size-trigger
  - Age trigger: sleep past max_age_seconds then flush() returns batch
  - pending_count reflects buffer size
  - Invalid max_size raises ValueError
  - Invalid max_age_seconds raises ValueError
"""

import time
import uuid

import pytest

from collector.batcher import EventBatcher
from collector.schema import EventType, PoEEvent


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _event() -> PoEEvent:
    return PoEEvent(
        event_type=EventType.KEYSTROKE_COUNT,
        session_id=str(uuid.uuid4()),
        metadata={"count": 10},
    )


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

class TestEventBatcherConfig:
    def test_max_size_zero_raises(self):
        with pytest.raises(ValueError):
            EventBatcher(max_size=0)

    def test_max_size_negative_raises(self):
        with pytest.raises(ValueError):
            EventBatcher(max_size=-5)

    def test_max_age_zero_raises(self):
        with pytest.raises(ValueError):
            EventBatcher(max_age_seconds=0)

    def test_max_age_negative_raises(self):
        with pytest.raises(ValueError):
            EventBatcher(max_age_seconds=-1.0)

    def test_valid_config_creates_batcher(self):
        b = EventBatcher(max_size=10, max_age_seconds=5.0)
        assert b.max_size == 10
        assert b.max_age_seconds == 5.0


# ---------------------------------------------------------------------------
# Buffer / size trigger
# ---------------------------------------------------------------------------

class TestEventBatcherSizeTrigger:
    def test_add_below_max_no_flush(self):
        b = EventBatcher(max_size=5)
        for _ in range(4):
            result = b.add(_event())
        assert result == []
        assert b.pending_count == 4

    def test_add_at_max_triggers_flush(self):
        b = EventBatcher(max_size=5)
        batch = []
        for _ in range(5):
            batch = b.add(_event())
        assert len(batch) == 5
        assert b.pending_count == 0

    def test_pending_count_decrements_after_flush(self):
        b = EventBatcher(max_size=3)
        for _ in range(3):
            b.add(_event())
        assert b.pending_count == 0

    def test_force_flush_drains_partial_buffer(self):
        b = EventBatcher(max_size=10)
        for _ in range(4):
            b.add(_event())
        batch = b.force_flush()
        assert len(batch) == 4
        assert b.pending_count == 0

    def test_force_flush_empty_returns_empty(self):
        b = EventBatcher(max_size=5)
        assert b.force_flush() == []

    def test_add_after_flush_restarts_buffer(self):
        b = EventBatcher(max_size=2)
        for _ in range(2):
            b.add(_event())
        assert b.pending_count == 0
        b.add(_event())
        assert b.pending_count == 1


# ---------------------------------------------------------------------------
# on_flush callback
# ---------------------------------------------------------------------------

class TestEventBatcherCallback:
    def test_callback_invoked_on_size_trigger(self):
        received: list = []
        b = EventBatcher(max_size=3, on_flush=lambda batch: received.extend(batch))
        for _ in range(3):
            b.add(_event())
        assert len(received) == 3

    def test_callback_invoked_on_force_flush(self):
        received: list = []
        b = EventBatcher(max_size=10, on_flush=lambda batch: received.extend(batch))
        for _ in range(4):
            b.add(_event())
        b.force_flush()
        assert len(received) == 4

    def test_callback_not_invoked_if_no_flush(self):
        called = []
        b = EventBatcher(max_size=10, on_flush=lambda batch: called.append(batch))
        for _ in range(5):
            b.add(_event())
        assert called == []


# ---------------------------------------------------------------------------
# Age trigger
# ---------------------------------------------------------------------------

class TestEventBatcherAgeTrigger:
    def test_age_trigger_fires_after_delay(self):
        b = EventBatcher(max_size=100, max_age_seconds=0.1)
        b.add(_event())
        time.sleep(0.15)
        batch = b.flush()
        assert len(batch) == 1
        assert b.pending_count == 0

    def test_age_trigger_does_not_fire_immediately(self):
        b = EventBatcher(max_size=100, max_age_seconds=5.0)
        b.add(_event())
        batch = b.flush()  # called immediately — should not flush
        assert batch == []
        assert b.pending_count == 1
