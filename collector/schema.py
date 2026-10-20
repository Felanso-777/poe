"""
collector/schema.py — Normalized PoE event schema.

Every event flowing through the Proof of Effort pipeline is represented as a
PoEEvent.  The schema stores only privacy-preserving metadata:
  - file names (not full paths)
  - aggregate keystroke counts (never content)
  - process names (never arguments – args may contain passwords/tokens)
  - app names (not full window titles – titles may contain typed text)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventType(str, Enum):
    FILE_MODIFIED   = "FILE_MODIFIED"
    FILE_CREATED    = "FILE_CREATED"
    FILE_DELETED    = "FILE_DELETED"
    WINDOW_FOCUS    = "WINDOW_FOCUS"
    PROCESS_START   = "PROCESS_START"
    PROCESS_END     = "PROCESS_END"
    SESSION_START   = "SESSION_START"
    SESSION_END     = "SESSION_END"
    KEYSTROKE_COUNT = "KEYSTROKE_COUNT"


EVENT_SCHEMA_VERSION = "1.1"


# Permitted metadata keys per event type.
# Keys not in this mapping are SILENTLY DROPPED during event construction.
_ALLOWED_META: dict[str, frozenset[str]] = {
    EventType.FILE_MODIFIED:   frozenset({"file_name", "file_extension", "language", "relative_path", "file_size_bytes", "lines_added", "lines_deleted"}),
    EventType.FILE_CREATED:    frozenset({"file_name", "file_extension", "language", "relative_path", "file_size_bytes"}),
    EventType.FILE_DELETED:    frozenset({"file_name", "file_extension", "language", "relative_path"}),
    EventType.WINDOW_FOCUS:    frozenset({"app_name"}),
    EventType.PROCESS_START:   frozenset({"process_name"}),      # no args
    EventType.PROCESS_END:     frozenset({"process_name", "exit_code"}),
    EventType.SESSION_START:   frozenset(),
    EventType.SESSION_END:     frozenset({"duration_seconds"}),
    EventType.KEYSTROKE_COUNT: frozenset({"count"}),
}

_MAX_STRING_LEN = 512


class EventValidationError(ValueError):
    """Raised when a PoEEvent cannot be constructed from the given arguments."""


def _sanitize_metadata(event_type: EventType, raw_meta: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *raw_meta* with disallowed keys removed and strings truncated."""
    allowed = _ALLOWED_META[event_type]
    clean: dict[str, Any] = {}
    for key, value in raw_meta.items():
        if key not in allowed:
            continue  # silently drop unknown / sensitive key
        if isinstance(value, str):
            value = value[:_MAX_STRING_LEN]
        clean[key] = value
    return clean


@dataclass(frozen=True)
class PoEEvent:
    """
    An immutable, normalized Proof-of-Effort activity event.

    Parameters
    ----------
    event_type : str
        One of the EventType enum values.
    session_id : str
        UUID string identifying the recording session.
    metadata : dict, optional
        Permitted metadata for this event_type.  Unknown keys are silently
        dropped; string values are truncated to 512 characters.
    event_id : str, optional
        Auto-generated UUID4 if omitted.
    timestamp : str, optional
        ISO 8601 UTC string.  Auto-generated at construction time if omitted.
    """

    event_type: str
    session_id: str
    metadata:   dict = field(default_factory=dict)
    event_id:   str  = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:  str  = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: str = EVENT_SCHEMA_VERSION
    synthetic: bool = False

    def __post_init__(self) -> None:
        # Validate event_type
        try:
            et = EventType(self.event_type)
        except ValueError:
            raise EventValidationError(
                f"Unknown event_type {self.event_type!r}. "
                f"Valid types: {[e.value for e in EventType]}"
            )
        # Validate session_id
        if not self.session_id or not isinstance(self.session_id, str):
            raise EventValidationError("session_id must be a non-empty string.")
        # Sanitize metadata in-place (frozen dataclass requires object.__setattr__)
        clean = _sanitize_metadata(et, self.metadata if self.metadata else {})
        object.__setattr__(self, "metadata", clean)

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON encoding."""
        data = {
            "event_id":   self.event_id,
            "timestamp":  self.timestamp,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "metadata":   self.metadata,
        }
        # Keep the original serialized shape for production callers while
        # persisting an explicit marker whenever synthetic data is emitted.
        if self.synthetic:
            data["schema_version"] = self.schema_version
            data["synthetic"] = True
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "PoEEvent":
        """
        Reconstruct a PoEEvent from a dict (e.g. a parsed JSONL line).

        Raises EventValidationError on missing required fields or invalid values.
        """
        required = {"event_type", "session_id"}
        missing = required - data.keys()
        if missing:
            raise EventValidationError(f"Missing required fields: {missing}")
        return cls(
            event_type=data["event_type"],
            session_id=data["session_id"],
            metadata=data.get("metadata", {}),
            event_id=data.get("event_id", str(uuid.uuid4())),
            timestamp=data.get(
                "timestamp", datetime.now(timezone.utc).isoformat()
            ),
            schema_version=data.get("schema_version", EVENT_SCHEMA_VERSION),
            synthetic=bool(data.get("synthetic", False)),
        )
