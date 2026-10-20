"""
tests/test_merkle.py — Unit tests for collector.merkle.

Covers:
  - leaf_hash is deterministic for the same event
  - leaf_hash is unique for different events
  - Any field change in an event changes its hash (integrity)
  - Leaf ordering matters for the root
  - Empty list returns EMPTY_ROOT
  - Single event: root == leaf_hash
  - Odd-sized batches (3, 5 events)
  - Even-sized batches (4 events — 2-level tree)
  - Inclusion proof is valid for every leaf in a batch
  - Tampered root fails verify_proof
  - Tampered leaf hash fails verify_proof
  - Unknown event_id raises KeyError in build_proof
  - MerkleAggregator stores (batch, root) per flush
"""

import uuid

import pytest

from collector.merkle import (
    EMPTY_ROOT,
    MerkleAggregator,
    build_proof,
    leaf_hash,
    merkle_root,
    verify_proof,
)
from collector.schema import EventType, PoEEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ev(et: EventType = EventType.FILE_MODIFIED) -> PoEEvent:
    """Create a fresh PoEEvent with a unique event_id."""
    meta = {}
    if et == EventType.FILE_MODIFIED:
        meta = {"file_name": "test.py", "language": "python"}
    elif et == EventType.KEYSTROKE_COUNT:
        meta = {"count": 10}
    elif et == EventType.WINDOW_FOCUS:
        meta = {"app_name": "VS Code"}
    return PoEEvent(event_type=et, session_id=str(uuid.uuid4()), metadata=meta)


def _batch(n: int) -> list[PoEEvent]:
    return [_ev() for _ in range(n)]


# ---------------------------------------------------------------------------
# leaf_hash
# ---------------------------------------------------------------------------

class TestLeafHash:
    def test_deterministic(self):
        ev = _ev()
        assert leaf_hash(ev) == leaf_hash(ev)

    def test_unique_per_event(self):
        ev1, ev2 = _ev(), _ev()
        assert leaf_hash(ev1) != leaf_hash(ev2)

    def test_is_64_char_hex(self):
        h = leaf_hash(_ev())
        assert len(h) == 64
        int(h, 16)  # raises if not hex

    def test_event_id_change_changes_hash(self):
        ev = _ev()
        # Frozen dataclass — construct a new one with a different event_id
        ev2 = PoEEvent(
            event_type=ev.event_type,
            session_id=ev.session_id,
            metadata=dict(ev.metadata),
            event_id=str(uuid.uuid4()),   # different ID
            timestamp=ev.timestamp,
        )
        assert leaf_hash(ev) != leaf_hash(ev2)

    def test_timestamp_change_changes_hash(self):
        ev = _ev()
        ev2 = PoEEvent(
            event_type=ev.event_type,
            session_id=ev.session_id,
            metadata=dict(ev.metadata),
            event_id=ev.event_id,
            timestamp="1970-01-01T00:00:00+00:00",  # different
        )
        assert leaf_hash(ev) != leaf_hash(ev2)

    def test_event_type_change_changes_hash(self):
        ev = _ev(EventType.WINDOW_FOCUS)
        ev2 = PoEEvent(
            event_type=EventType.PROCESS_START,
            session_id=ev.session_id,
            metadata={"process_name": "python"},
            event_id=ev.event_id,
            timestamp=ev.timestamp,
        )
        assert leaf_hash(ev) != leaf_hash(ev2)

    def test_session_id_change_changes_hash(self):
        ev = _ev()
        ev2 = PoEEvent(
            event_type=ev.event_type,
            session_id=str(uuid.uuid4()),   # different session
            metadata=dict(ev.metadata),
            event_id=ev.event_id,
            timestamp=ev.timestamp,
        )
        assert leaf_hash(ev) != leaf_hash(ev2)


# ---------------------------------------------------------------------------
# merkle_root
# ---------------------------------------------------------------------------

class TestMerkleRoot:
    def test_empty_returns_empty_root_constant(self):
        assert merkle_root([]) == EMPTY_ROOT

    def test_empty_root_is_hex_string(self):
        assert len(EMPTY_ROOT) == 64
        int(EMPTY_ROOT, 16)

    def test_single_event_root_equals_leaf_hash(self):
        ev   = _ev()
        root = merkle_root([ev])
        assert root == leaf_hash(ev)

    def test_root_is_deterministic(self):
        events = _batch(4)
        assert merkle_root(events) == merkle_root(events)

    def test_ordering_matters(self):
        events = _batch(4)
        reversed_events = events[::-1]
        assert merkle_root(events) != merkle_root(reversed_events)

    def test_odd_batch_3_is_stable(self):
        events = _batch(3)
        assert merkle_root(events) == merkle_root(events)

    def test_odd_batch_5_is_stable(self):
        events = _batch(5)
        assert merkle_root(events) == merkle_root(events)

    def test_even_batch_4(self):
        events = _batch(4)
        root   = merkle_root(events)
        assert len(root) == 64
        int(root, 16)  # valid hex

    def test_different_batches_different_roots(self):
        assert merkle_root(_batch(4)) != merkle_root(_batch(4))

    def test_adding_one_event_changes_root(self):
        events = _batch(4)
        root4  = merkle_root(events)
        root5  = merkle_root(events + [_ev()])
        assert root4 != root5

    def test_modifying_one_event_changes_root(self):
        events = _batch(4)
        root_original = merkle_root(events)

        # Replace the third event with a new one
        new_events    = events[:2] + [_ev()] + events[3:]
        root_modified = merkle_root(new_events)
        assert root_original != root_modified


# ---------------------------------------------------------------------------
# Inclusion proofs
# ---------------------------------------------------------------------------

class TestInclusionProof:
    def test_proof_valid_for_all_leaves_even_batch(self):
        events = _batch(4)
        root   = merkle_root(events)
        for ev in events:
            proof = build_proof(events, ev.event_id)
            assert verify_proof(leaf_hash(ev), proof, root), \
                f"Proof failed for event_id={ev.event_id}"

    def test_proof_valid_for_all_leaves_odd_batch(self):
        events = _batch(3)
        root   = merkle_root(events)
        for ev in events:
            proof = build_proof(events, ev.event_id)
            assert verify_proof(leaf_hash(ev), proof, root)

    def test_proof_valid_single_event(self):
        ev    = _ev()
        root  = merkle_root([ev])
        proof = build_proof([ev], ev.event_id)
        assert verify_proof(leaf_hash(ev), proof, root)

    def test_tampered_root_fails(self):
        events = _batch(4)
        ev     = events[0]
        proof  = build_proof(events, ev.event_id)
        bad_root = "ff" * 32          # obviously wrong root
        assert not verify_proof(leaf_hash(ev), proof, bad_root)

    def test_tampered_leaf_fails(self):
        events = _batch(4)
        ev     = events[0]
        root   = merkle_root(events)
        proof  = build_proof(events, ev.event_id)
        bad_leaf = "aa" * 32          # hash of a different event
        assert not verify_proof(bad_leaf, proof, root)

    def test_tampered_proof_step_fails(self):
        events = _batch(4)
        ev     = events[0]
        root   = merkle_root(events)
        proof  = build_proof(events, ev.event_id)
        # Corrupt the first sibling hash
        corrupted = [{"hash": "bb" * 32, "side": proof[0]["side"]}] + proof[1:]
        assert not verify_proof(leaf_hash(ev), corrupted, root)

    def test_unknown_event_id_raises(self):
        events = _batch(3)
        with pytest.raises(KeyError):
            build_proof(events, str(uuid.uuid4()))

    def test_empty_events_raises(self):
        with pytest.raises(KeyError):
            build_proof([], str(uuid.uuid4()))

    def test_proof_for_5_events(self):
        """Odd tree (5 leaves) — every leaf should verify."""
        events = _batch(5)
        root   = merkle_root(events)
        for ev in events:
            proof = build_proof(events, ev.event_id)
            assert verify_proof(leaf_hash(ev), proof, root)

    def test_proof_length_for_power_of_two(self):
        """For 8 leaves the proof path length should be exactly 3 (log2(8))."""
        events = _batch(8)
        ev     = events[0]
        proof  = build_proof(events, ev.event_id)
        assert len(proof) == 3


# ---------------------------------------------------------------------------
# MerkleAggregator
# ---------------------------------------------------------------------------

class TestMerkleAggregator:
    def test_no_batches_initially(self):
        agg = MerkleAggregator()
        assert agg.completed_batches == []
        assert agg.latest_root() is None

    def test_stores_batch_and_root_on_flush(self):
        from collector.batcher import EventBatcher
        agg     = MerkleAggregator()
        batcher = EventBatcher(max_size=3, on_flush=agg.on_flush)
        events  = [_ev() for _ in range(3)]
        for ev in events:
            batcher.add(ev)
        assert len(agg.completed_batches) == 1
        stored_batch, stored_root = agg.completed_batches[0]
        assert len(stored_batch) == 3
        assert stored_root == merkle_root(stored_batch)

    def test_latest_root_matches_last_batch(self):
        from collector.batcher import EventBatcher
        agg     = MerkleAggregator()
        batcher = EventBatcher(max_size=2, on_flush=agg.on_flush)
        for _ in range(4):   # two flushes
            batcher.add(_ev())
        assert len(agg.completed_batches) == 2
        assert agg.latest_root() == agg.completed_batches[-1][1]

    def test_root_from_aggregator_verifiable(self):
        """build_proof + verify_proof should work on aggregator-produced roots."""
        from collector.batcher import EventBatcher
        agg     = MerkleAggregator()
        batcher = EventBatcher(max_size=4, on_flush=agg.on_flush)
        events  = [_ev() for _ in range(4)]
        for ev in events:
            batcher.add(ev)

        batch, root = agg.completed_batches[0]
        for ev in batch:
            proof = build_proof(batch, ev.event_id)
            assert verify_proof(leaf_hash(ev), proof, root)

    def test_force_flush_triggers_aggregator(self):
        from collector.batcher import EventBatcher
        agg     = MerkleAggregator()
        batcher = EventBatcher(max_size=100, on_flush=agg.on_flush)
        for _ in range(5):
            batcher.add(_ev())
        batcher.force_flush()
        assert len(agg.completed_batches) == 1
