"""
collector/storage.py — Thread-safe JSONL persistence layer.

Each line in the file is an independent JSON object representing one PoEEvent.
Malformed or invalid lines are skipped with a warning rather than raising, so
a single corrupt line never prevents reading an entire session file.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Iterator

from .schema import EventValidationError, PoEEvent

logger = logging.getLogger(__name__)


class JSONLStorage:
    """
    Append-only, thread-safe JSONL (JSON Lines) writer/reader.

    The instance is stateless with respect to which file it targets; callers
    supply the path on every call.  A single instance can safely serve
    multiple concurrent sessions.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(self, event: PoEEvent, path: Path) -> None:
        """Serialise *event* and append it as one line to *path*."""
        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)

    def append_batch(self, events: list[PoEEvent], path: Path) -> None:
        """Write multiple events in a single lock acquisition (atomic write)."""
        if not events:
            return
        lines = (
            "\n".join(json.dumps(e.to_dict(), ensure_ascii=False) for e in events)
            + "\n"
        )
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(lines)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_all(self, path: Path) -> list[PoEEvent]:
        """
        Read and validate all events from *path*.

        Malformed JSON lines and events that fail schema validation are
        silently skipped with a WARNING log entry.
        """
        events: list[PoEEvent] = []
        for lineno, raw in enumerate(self._iter_lines(path), start=1):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSON on line %d: %s", lineno, exc)
                continue
            try:
                events.append(PoEEvent.from_dict(data))
            except EventValidationError as exc:
                logger.warning("Skipping invalid event on line %d: %s", lineno, exc)
        return events

    def read_raw(self, path: Path) -> list[dict]:
        """
        Return raw dicts without schema validation.

        Useful for debugging or migrating older formats.
        """
        out: list[dict] = []
        for lineno, raw in enumerate(self._iter_lines(path), start=1):
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSON on line %d: %s", lineno, exc)
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _iter_lines(path: Path) -> Iterator[str]:
        """Yield non-empty stripped lines from *path*, or nothing if absent."""
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    yield stripped
