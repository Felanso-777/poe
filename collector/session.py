"""
collector/session.py — Session lifecycle management.

A session represents one continuous recording window.  Each session:
  • is assigned a UUID on creation
  • persists its events in a dedicated JSONL file
  • emits SESSION_START / SESSION_END bookend events automatically
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from typing import Optional

from .schema import EventType, PoEEvent
from .storage import JSONLStorage


class SessionError(RuntimeError):
    """Raised on invalid session state transitions or unknown session IDs."""


class SessionStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    ABORTED = "aborted"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


@dataclass
class Session:
    """Represents a single recording session's lifecycle and file path."""

    session_id:   str
    storage_path: Optional[Path] = None
    created_at:   float = field(default_factory=time.time)
    started_at:   Optional[float] = None
    stopped_at:   Optional[float] = None
    status:       SessionStatus = SessionStatus.CREATED
    synthetic:    bool = False
    collector_name: str = "unknown"

    @property
    def is_running(self) -> bool:
        return self.status == SessionStatus.RUNNING

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.stopped_at if self.stopped_at is not None else time.time()
        return end - self.started_at


class SessionManager:
    """
    Creates, starts, stops, and queries PoE recording sessions.

    Each session stores its events in:
        <storage_dir>/<session_id>.jsonl

    Parameters
    ----------
    storage_dir : str | Path
        Root directory for per-session JSONL files.
        Created automatically if it does not exist.
    """

    def __init__(self, storage_dir: str | Path = "~/.poe/sessions") -> None:
        self._dir     = Path(storage_dir).expanduser().resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, Session] = {}
        self._storage = JSONLStorage()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_session(
        self,
        *,
        synthetic: bool = False,
        collector_name: str = "unknown",
    ) -> str:
        """
        Allocate a new session and return its UUID string.

        Does NOT start the session — call start_session() when ready to
        begin recording.
        """
        sid  = str(uuid.uuid4())
        path = self._dir / f"{sid}.jsonl"
        self._sessions[sid] = Session(
            session_id=sid,
            storage_path=path,
            synthetic=synthetic,
            collector_name=collector_name,
        )
        return sid

    def start_session(self, session_id: str) -> Session:
        """
        Begin recording for *session_id*.

        Emits a SESSION_START event and starts the session clock.
        Raises SessionError if the session is already running or finished.
        """
        session = self._get(session_id)
        if session.is_running:
            raise SessionError(f"Session {session_id!r} is already running.")
        if session.stopped_at is not None:
            raise SessionError(f"Session {session_id!r} has already been stopped.")

        session.started_at = time.time()
        session.status = SessionStatus.RUNNING
        self._storage.append(
            PoEEvent(event_type=EventType.SESSION_START, session_id=session_id),
            session.storage_path,
        )
        return session

    def stop_session(self, session_id: str) -> Session:
        """
        Finish recording for *session_id*.

        Emits a SESSION_END event with duration and returns the completed Session.
        Raises SessionError if the session is not running.
        """
        session = self._get(session_id)
        if not session.is_running:
            raise SessionError(
                f"Session {session_id!r} is not running "
                f"(started={session.started_at}, stopped={session.stopped_at})."
            )

        session.stopped_at = time.time()
        session.status = SessionStatus.COMPLETED
        self._storage.append(
            PoEEvent(
                event_type=EventType.SESSION_END,
                session_id=session_id,
                metadata={"duration_seconds": round(session.duration_seconds, 3)},
            ),
            session.storage_path,
        )
        return session

    def finish_session(self, session_id: str, status: SessionStatus) -> Session:
        """Close a session with an explicit non-success lifecycle outcome."""
        if status not in {
            SessionStatus.INTERRUPTED, SessionStatus.ABORTED,
            SessionStatus.INCOMPLETE, SessionStatus.FAILED,
        }:
            raise SessionError(f"Invalid non-completed status: {status.value}")
        session = self._get(session_id)
        if not session.is_running:
            raise SessionError(f"Session {session_id!r} is not running.")
        session.stopped_at = time.time()
        session.status = status
        return session

    def append_event(self, event: PoEEvent) -> None:
        """
        Persist an externally-constructed event to its session's JSONL file.

        The session must be running.  Raises SessionError otherwise.
        """
        session = self._get(event.session_id)
        if not session.is_running:
            raise SessionError(
                f"Cannot append event: session {event.session_id!r} is not running."
            )
        self._storage.append(event, session.storage_path)

    def get_session(self, session_id: str) -> Session:
        """Return the Session for *session_id*.  Raises SessionError if unknown."""
        return self._get(session_id)

    def list_sessions(self) -> list[Session]:
        """Return all sessions managed by this instance."""
        return list(self._sessions.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionError(f"Unknown session ID: {session_id!r}")
