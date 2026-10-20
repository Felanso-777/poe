"""
collector/merkle.py — SHA-256 Merkle tree for PoE event batches.

Algorithm
---------
Leaf hash
    SHA-256( b"PoE|leaf|" + canonical_bytes(event) )

    canonical_bytes is the UTF-8 encoding of the pipe-delimited string:
        "<event_id>|<timestamp>|<event_type>|<session_id>"
    Fields are always in this fixed order so the hash is deterministic.

Parent hash
    SHA-256( b"PoE|node|" + left_hash_bytes + right_hash_bytes )
    where *_hash_bytes is the 32-byte binary digest (not hex).

Domain prefixes ("leaf" / "node") prevent second-preimage attacks where an
attacker submits a node hash as if it were a leaf hash.

Odd leaves
    When a level has an odd number of nodes the last node is duplicated
    before pairing (standard Bitcoin Merkle behavior).

Empty tree
    merkle_root([]) returns EMPTY_ROOT = SHA-256( b"PoE|empty" )
    This is a documented, non-zero sentinel rather than the all-zero hash,
    which could be confused with an uninitialized state.

Inclusion proof
    A proof for leaf L is a list of {"hash": hex, "side": "left"|"right"}
    dicts from bottom to top of the tree.  The verifier recomputes the
    parent hashes step by step and checks that the result equals the root.

Public API
----------
    EMPTY_ROOT : str                            # constant hex string
    leaf_hash(event) -> str                     # hex
    merkle_root(events) -> str                  # hex
    build_proof(events, event_id) -> list[dict]
    verify_proof(leaf_hex, proof, root_hex) -> bool
    MerkleAggregator                            # batcher-integrated helper
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import PoEEvent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LEAF_PREFIX  = b"PoE|leaf|"
_NODE_PREFIX  = b"PoE|node|"
_EMPTY_PREFIX = b"PoE|empty"

EMPTY_ROOT: str = hashlib.sha256(_EMPTY_PREFIX).hexdigest()


# ---------------------------------------------------------------------------
# Core hashing helpers
# ---------------------------------------------------------------------------

def _canonical_bytes(event: "PoEEvent") -> bytes:
    """Return the deterministic byte representation of *event* for hashing.

    Uses only the four identity fields that are guaranteed present on every
    PoEEvent.  Metadata is intentionally excluded — it is privacy-filtered
    by schema.py and its inclusion would add no meaningful security here.
    The field order and separator are fixed by the algorithm specification.
    """
    et = event.event_type
    et_str = getattr(et, "value", et)
    canonical = f"{event.event_id}|{event.timestamp}|{et_str}|{event.session_id}"
    return canonical.encode("utf-8")


def leaf_hash(event: "PoEEvent") -> str:
    """Return the SHA-256 hex digest of the canonical leaf for *event*."""
    return hashlib.sha256(_LEAF_PREFIX + _canonical_bytes(event)).hexdigest()


def _node_hash(left_hex: str, right_hex: str) -> str:
    """Return the SHA-256 hex digest for an internal Merkle node."""
    left_bytes  = bytes.fromhex(left_hex)
    right_bytes = bytes.fromhex(right_hex)
    return hashlib.sha256(_NODE_PREFIX + left_bytes + right_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Tree construction
# ---------------------------------------------------------------------------

def _build_levels(leaves: list[str]) -> list[list[str]]:
    """
    Build all levels of the Merkle tree bottom-up.

    Returns a list of levels, where levels[0] is the leaf level and
    levels[-1] is the root level (a single element).
    """
    levels: list[list[str]] = [leaves]
    current = leaves
    while len(current) > 1:
        # Duplicate the last node if the count is odd
        if len(current) % 2 == 1:
            current = current + [current[-1]]
        next_level = [
            _node_hash(current[i], current[i + 1])
            for i in range(0, len(current), 2)
        ]
        levels.append(next_level)
        current = next_level
    return levels


def merkle_root(events: list["PoEEvent"]) -> str:
    """
    Compute the Merkle root for a list of PoEEvents.

    Returns EMPTY_ROOT if *events* is empty.
    Returns the single leaf hash if *events* has one element.
    """
    if not events:
        return EMPTY_ROOT
    leaves = [leaf_hash(e) for e in events]
    levels = _build_levels(leaves)
    return levels[-1][0]


# ---------------------------------------------------------------------------
# Inclusion proofs
# ---------------------------------------------------------------------------

def build_proof(events: list["PoEEvent"], event_id: str) -> list[dict]:
    """
    Build an inclusion proof for the event whose event_id == *event_id*.

    Returns a list of dicts, each with keys:
        "hash" : str  — sibling hash (hex)
        "side" : str  — "left" or "right"

    Apply the proof from the first element (leaf sibling) to the last
    (root sibling) to reconstruct the root.

    Raises KeyError if *event_id* is not found in *events*.
    """
    if not events:
        raise KeyError(f"event_id {event_id!r} not found (empty event list)")

    # Find the target index
    id_to_index = {e.event_id: i for i, e in enumerate(events)}
    if event_id not in id_to_index:
        raise KeyError(f"event_id {event_id!r} not found in events")

    leaves = [leaf_hash(e) for e in events]
    levels = _build_levels(leaves)

    proof: list[dict] = []
    index = id_to_index[event_id]

    for level in levels[:-1]:  # all levels except the root
        # Extend with duplicate if odd
        padded = level if len(level) % 2 == 0 else level + [level[-1]]
        if index % 2 == 0:
            # current node is left; sibling is to the right
            sibling_index = index + 1
            proof.append({"hash": padded[sibling_index], "side": "right"})
        else:
            # current node is right; sibling is to the left
            sibling_index = index - 1
            proof.append({"hash": padded[sibling_index], "side": "left"})
        index //= 2

    return proof


def verify_proof(leaf_hex: str, proof: list[dict], root_hex: str) -> bool:
    """
    Verify an inclusion proof.

    Parameters
    ----------
    leaf_hex : str
        Hex leaf hash (from leaf_hash()).
    proof : list[dict]
        Proof path returned by build_proof().
    root_hex : str
        Expected Merkle root hex.

    Returns True if the proof is valid.
    """
    current = leaf_hex
    for step in proof:
        sibling = step["hash"]
        side    = step["side"]
        if side == "right":
            current = _node_hash(current, sibling)
        elif side == "left":
            current = _node_hash(sibling, current)
        else:
            return False  # malformed proof step
    return current == root_hex


# ---------------------------------------------------------------------------
# MerkleAggregator — batcher integration
# ---------------------------------------------------------------------------

class MerkleAggregator:
    """
    Wraps an EventBatcher flush callback to compute a Merkle root per batch.

    Usage
    -----
    aggregator = MerkleAggregator()
    batcher = EventBatcher(
        max_size=50,
        on_flush=aggregator.on_flush,
    )
    # ... add events ...
    batcher.force_flush()
    for batch, root in aggregator.completed_batches:
        print(f"Batch of {len(batch)} events, Merkle root: {root}")

    The Merkle root (a hex string) represents the batch but contains no
    raw event data.  Only the root should be forwarded to the blockchain.
    """

    def __init__(self) -> None:
        self.completed_batches: list[tuple[list, str]] = []

    def on_flush(self, batch: list) -> None:
        """Called by EventBatcher on each flush.  Stores (batch, root) pair."""
        root = merkle_root(batch)
        self.completed_batches.append((batch, root))

    def latest_root(self) -> str | None:
        """Return the Merkle root of the most recently flushed batch, or None."""
        if not self.completed_batches:
            return None
        return self.completed_batches[-1][1]
