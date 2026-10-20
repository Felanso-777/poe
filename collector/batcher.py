"""
collector/batcher.py — Configurable two-trigger event batcher.

A flush is triggered when EITHER:
  • the buffer reaches *max_size* events  (count trigger), or
  • the oldest event in the buffer is older than *max_age_seconds* (age trigger).

All public methods are thread-safe.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .schema import PoEEvent

FlushCallback = Callable[[list[PoEEvent]], None]


class EventBatcher:
    """
    Accumulates PoEEvents and flushes them when a trigger condition fires.

    Parameters
    ----------
    max_size : int
        Flush when the buffer holds this many events (default 50).
    max_age_seconds : float
        Flush when the oldest buffered event is this many seconds old (default 30).
    on_flush : callable, optional
        Called with the flushed batch list whenever a flush occurs.
        Invoked synchronously inside the lock; keep it fast.

    Usage — manual flush
    --------------------
    batcher = EventBatcher(max_size=50, max_age_seconds=30.0)
    batcher.add(event)          # returns flushed batch or []
    batch = batcher.force_flush()

    Usage — callback-based
    ----------------------
    batcher = EventBatcher(on_flush=lambda b: storage.append_batch(b, path))
    batcher.add(event)          # callback fires automatically on trigger
    batcher.force_flush()       # drain at session end
    """

    def __init__(
        self,
        max_size: int = 50,
        max_age_seconds: float = 30.0,
        on_flush: Optional[FlushCallback] = None,
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be > 0")

        self.max_size        = max_size
        self.max_age_seconds = max_age_seconds
        self._on_flush       = on_flush

        self._buffer:     list[PoEEvent]  = []
        self._oldest_ts:  Optional[float] = None   # monotonic clock of first buffered event
        self._lock        = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, event: PoEEvent) -> list[PoEEvent]:
        """
        Add *event* to the buffer.

        Returns the flushed batch if a trigger fired, otherwise [].
        If *on_flush* is configured it is also called on trigger.
        """
        with self._lock:
            self._buffer.append(event)
            if self._oldest_ts is None:
                self._oldest_ts = time.monotonic()
            if self._should_flush():
                return self._do_flush()
        return []

    def flush(self) -> list[PoEEvent]:
        """
        Flush if a trigger condition is currently met.

        Returns the flushed batch or [] if no trigger fired.
        """
        with self._lock:
            if self._buffer and self._should_flush():
                return self._do_flush()
        return []

    def force_flush(self) -> list[PoEEvent]:
        """Unconditionally drain the entire buffer regardless of triggers."""
        with self._lock:
            if not self._buffer:
                return []
            return self._do_flush()

    @property
    def pending_count(self) -> int:
        """Number of events currently in the buffer."""
        with self._lock:
            return len(self._buffer)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _should_flush(self) -> bool:
        """Evaluate trigger conditions.  Called with the lock held."""
        if len(self._buffer) >= self.max_size:
            return True
        if self._oldest_ts is not None:
            if time.monotonic() - self._oldest_ts >= self.max_age_seconds:
                return True
        return False

    def _do_flush(self) -> list[PoEEvent]:
        """
        Drain the buffer and invoke the callback.  Called with the lock held.
        """
        batch = list(self._buffer)
        self._buffer.clear()
        self._oldest_ts = None
        if self._on_flush and batch:
            self._on_flush(batch)
        return batch
