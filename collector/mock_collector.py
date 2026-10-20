"""
collector/mock_collector.py — Synthetic event generator for testing.

Produces realistic-looking PoEEvents using only stdlib random + time.
Does NOT read the filesystem, keyboard, network, or any kernel interface.
Safe to run without elevated permissions.

Typical use
-----------
    mc = MockCollector(session_id="...", batcher=batcher)
    mc.start(interval_seconds=0.5)
    time.sleep(5)
    mc.stop()           # returns any remaining flushed events
"""

from __future__ import annotations

import random
import threading
import time
from typing import Optional

from .batcher import EventBatcher
from .schema import EventType, PoEEvent
from .interfaces import CollectorMetadata

# ---------------------------------------------------------------------------
# Fake but realistic sample values — no real paths, no real user data
# ---------------------------------------------------------------------------

_FAKE_FILES = [
    ("main.py",       "python"),
    ("utils.py",      "python"),
    ("index.ts",      "typescript"),
    ("App.tsx",       "typescript"),
    ("api_router.go", "go"),
    ("schema.sql",    "sql"),
    ("README.md",     "markdown"),
    ("Makefile",      "makefile"),
    ("config.yaml",   "yaml"),
]

_FAKE_APPS  = ["VS Code", "Terminal", "Browser", "Slack", "Postgres", "Docker Desktop"]
_FAKE_PROCS = ["node", "python", "cargo", "tsc", "pytest", "eslint", "git", "go"]

# Weighted distribution mimicking a typical coding session
_EVENT_TYPES, _WEIGHTS = zip(*[
    (EventType.FILE_MODIFIED,   40),
    (EventType.FILE_CREATED,     5),
    (EventType.FILE_DELETED,     3),
    (EventType.WINDOW_FOCUS,    15),
    (EventType.PROCESS_START,   10),
    (EventType.PROCESS_END,     10),
    (EventType.KEYSTROKE_COUNT, 17),
])


class MockCollector:
    """
    Emits synthetic PoEEvents at a configurable rate via a background thread.

    Parameters
    ----------
    session_id : str
        Session UUID to embed in every emitted event.
    batcher : EventBatcher
        Receives each emitted event via batcher.add().
    seed : int, optional
        RNG seed for reproducible test output.
    """

    def __init__(
        self,
        session_id: str,
        batcher: EventBatcher,
        seed: Optional[int] = None,
    ) -> None:
        self._session_id = session_id
        self._batcher    = batcher
        self._rng        = random.Random(seed)
        self._running    = False
        self._thread: Optional[threading.Thread] = None
        self.metadata = CollectorMetadata(
            name="MockCollector", platform="any", synthetic=True, authorized=False
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, interval_seconds: float = 0.5) -> None:
        """Start emitting events on a background daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._run,
            args=(interval_seconds,),
            daemon=True,
            name="MockCollector",
        )
        self._thread.start()

    def stop(self) -> list[PoEEvent]:
        """
        Stop emission and drain any remaining buffered events.

        Returns the final flushed batch (may be empty if batcher was empty).
        """
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        return self._batcher.force_flush()

    def emit_one(self, event_type: Optional[EventType] = None) -> PoEEvent:
        """
        Emit a single synthetic event immediately (useful in unit tests).

        The event is passed through the batcher (may trigger a flush).
        """
        et    = event_type or self._rng.choices(_EVENT_TYPES, weights=_WEIGHTS, k=1)[0]
        event = self._build(et)
        self._batcher.add(event)
        return event

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self, interval: float) -> None:
        while self._running:
            et    = self._rng.choices(_EVENT_TYPES, weights=_WEIGHTS, k=1)[0]
            event = self._build(et)
            self._batcher.add(event)
            time.sleep(interval)

    def _build(self, et: EventType) -> PoEEvent:
        """Construct a synthetic event with realistic metadata."""
        meta: dict = {}

        if et == EventType.FILE_MODIFIED:
            fname, lang = self._rng.choice(_FAKE_FILES)
            meta = {
                "file_name":     fname,
                "language":      lang,
                "lines_added":   self._rng.randint(0, 30),
                "lines_deleted": self._rng.randint(0, 10),
            }
        elif et == EventType.FILE_CREATED:
            fname, lang = self._rng.choice(_FAKE_FILES)
            meta = {"file_name": fname, "language": lang}
        elif et == EventType.FILE_DELETED:
            fname, _ = self._rng.choice(_FAKE_FILES)
            meta = {"file_name": fname}
        elif et == EventType.WINDOW_FOCUS:
            meta = {"app_name": self._rng.choice(_FAKE_APPS)}
        elif et == EventType.PROCESS_START:
            meta = {"process_name": self._rng.choice(_FAKE_PROCS)}
        elif et == EventType.PROCESS_END:
            meta = {
                "process_name": self._rng.choice(_FAKE_PROCS),
                "exit_code":    self._rng.choice([0, 0, 0, 1]),
            }
        elif et == EventType.KEYSTROKE_COUNT:
            meta = {"count": self._rng.randint(1, 150)}

        return PoEEvent(
            event_type=et.value,
            session_id=self._session_id,
            metadata=meta,
            synthetic=True,
        )
