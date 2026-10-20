"""
collector — Proof of Effort local activity collection package.

Public interface
----------------
    EventType, PoEEvent, EventValidationError  (schema)
    Session, SessionError, SessionManager       (session)
    JSONLStorage                                (storage)
    EventBatcher                                (batcher)
    MockCollector                               (mock_collector)
    eBPFCollector, EBPF_AVAILABLE              (ebpf_collector)  [Linux only]
    merkle_root, leaf_hash, build_proof,
    verify_proof, EMPTY_ROOT, MerkleAggregator (merkle)

Blockchain and ML layers are NOT imported here.  This package is intentionally
self-contained and depends only on the Python standard library.
"""

from .schema         import EventType, EventValidationError, PoEEvent
from .session        import Session, SessionError, SessionManager
from .storage        import JSONLStorage
from .batcher        import EventBatcher
from .mock_collector import MockCollector
from .windows_collector import WindowsCollector, normalize_authorized_folders
from .interfaces import Collector, CollectorMetadata
from .session import SessionStatus
from .ebpf_collector import EBPF_AVAILABLE, eBPFCollector
from .merkle         import (
    EMPTY_ROOT,
    MerkleAggregator,
    build_proof,
    leaf_hash,
    merkle_root,
    verify_proof,
)

__all__ = [
    # schema
    "EventType",
    "EventValidationError",
    "PoEEvent",
    # session
    "Session",
    "SessionError",
    "SessionManager",
    # storage
    "JSONLStorage",
    # batcher
    "EventBatcher",
    # collectors
    "MockCollector",
    "WindowsCollector",
    "normalize_authorized_folders",
    "Collector",
    "CollectorMetadata",
    "SessionStatus",
    "eBPFCollector",
    "EBPF_AVAILABLE",
    # merkle
    "EMPTY_ROOT",
    "MerkleAggregator",
    "build_proof",
    "leaf_hash",
    "merkle_root",
    "verify_proof",
]
