"""Privacy-aware Windows folder collector.

This collector watches only explicitly authorized folders. It stores metadata
and aggregate counts, never file contents, process arguments, or window text.
"""

from __future__ import annotations

import logging
import os
import platform
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

from .batcher import EventBatcher
from .interfaces import CollectorMetadata
from .schema import EventType, PoEEvent

logger = logging.getLogger(__name__)

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover - dependency availability is environment-specific
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment]

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


_LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cs": "csharp",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".sql": "sql", ".md": "markdown", ".json": "json",
    ".yaml": "yaml", ".yml": "yaml",
}


def normalize_authorized_folders(folders: Iterable[str | Path]) -> tuple[Path, ...]:
    """Resolve and deduplicate user-selected folders."""
    normalized: list[Path] = []
    for folder in folders:
        path = Path(folder).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise ValueError(f"Authorized folder does not exist or is not a directory: {path}")
        if path not in normalized:
            normalized.append(path)
    if not normalized:
        raise ValueError("At least one authorized folder is required.")
    return tuple(normalized)


class _FolderEventHandler(FileSystemEventHandler):
    def __init__(self, collector: "WindowsCollector") -> None:
        self._collector = collector

    def on_created(self, event) -> None:  # type: ignore[no-untyped-def]
        if not event.is_directory:
            self._collector._file_event(EventType.FILE_CREATED, event.src_path)

    def on_modified(self, event) -> None:  # type: ignore[no-untyped-def]
        if not event.is_directory:
            self._collector._file_event(EventType.FILE_MODIFIED, event.src_path)

    def on_deleted(self, event) -> None:  # type: ignore[no-untyped-def]
        if not event.is_directory:
            self._collector._file_event(EventType.FILE_DELETED, event.src_path)

    def on_moved(self, event) -> None:  # type: ignore[no-untyped-def]
        if not event.is_directory:
            self._collector._file_event(EventType.FILE_DELETED, event.src_path)
            self._collector._file_event(EventType.FILE_CREATED, event.dest_path)


class WindowsCollector:
    """Collect authorized-folder activity and safe process metadata on Windows."""

    def __init__(
        self,
        session_id: str,
        batcher: EventBatcher,
        authorized_folders: Iterable[str | Path],
        *,
        include_processes: bool = True,
        debounce_seconds: float = 0.25,
        process_poll_seconds: float = 1.0,
    ) -> None:
        if platform.system() != "Windows":
            raise OSError("WindowsCollector is supported only on Windows.")
        if Observer is None:
            raise RuntimeError("watchdog is required for WindowsCollector.")
        self._session_id = session_id
        self._batcher = batcher
        self._folders = normalize_authorized_folders(authorized_folders)
        self._include_processes = include_processes
        self._debounce_seconds = debounce_seconds
        self._process_poll_seconds = process_poll_seconds
        self._observer = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._seen_processes: dict[int, str] = {}
        self._last_events: dict[tuple[str, str], float] = {}
        self.errors: list[str] = []
        self.metadata = CollectorMetadata(
            name="WindowsCollector",
            platform="Windows",
            synthetic=False,
            authorized=True,
        )

    @property
    def authorized_folders(self) -> tuple[Path, ...]:
        return self._folders

    def start(self, interval_seconds: float = 0.5) -> None:
        if self._running:
            return
        self._observer = Observer()
        handler = _FolderEventHandler(self)
        for folder in self._folders:
            self._observer.schedule(handler, str(folder), recursive=True)
        self._observer.start()
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_processes,
            args=(max(interval_seconds, self._process_poll_seconds),),
            daemon=True,
            name="WindowsCollectorProcessPoller",
        )
        self._thread.start()

    def stop(self) -> list[PoEEvent]:
        self._running = False
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        return self._batcher.force_flush()

    def _is_authorized(self, raw_path: str | Path) -> bool:
        try:
            candidate = Path(raw_path).resolve()
            return any(
                candidate == folder or folder in candidate.parents
                for folder in self._folders
            )
        except OSError as exc:
            self.errors.append(f"Could not resolve event path: {exc}")
            return False

    def _file_event(self, event_type: EventType, raw_path: str) -> None:
        if not self._running or not self._is_authorized(raw_path):
            return
        now = time.monotonic()
        key = (event_type.value, str(Path(raw_path).resolve()))
        if now - self._last_events.get(key, 0.0) < self._debounce_seconds:
            return
        self._last_events[key] = now
        path = Path(raw_path)
        extension = path.suffix.lower()
        metadata = {
            "file_name": path.name[:128],
            "file_extension": extension[:32],
            "language": _LANGUAGES.get(extension, ""),
            "relative_path": self._relative_path(path),
        }
        if event_type != EventType.FILE_DELETED:
            try:
                metadata["file_size_bytes"] = path.stat().st_size
            except OSError as exc:
                self.errors.append(f"Could not read file metadata for {path.name}: {exc}")
        self._emit(event_type, metadata)

    def _relative_path(self, path: Path) -> str:
        for folder in self._folders:
            try:
                return str(path.resolve().relative_to(folder)).replace("\\", "/")[:512]
            except ValueError:
                continue
        return path.name[:128]

    def _poll_processes(self, interval: float) -> None:
        if not self._include_processes or psutil is None:
            return
        while self._running:
            try:
                current: dict[int, str] = {}
                for process in psutil.process_iter(["pid", "name"]):
                    info = process.info
                    pid = info.get("pid")
                    name = info.get("name")
                    if isinstance(pid, int) and isinstance(name, str):
                        current[pid] = name[:128]
                        if pid not in self._seen_processes:
                            self._emit(EventType.PROCESS_START, {"process_name": name[:128]})
                for pid, name in self._seen_processes.items():
                    if pid not in current:
                        self._emit(EventType.PROCESS_END, {"process_name": name})
                self._seen_processes = current
            except (psutil.Error, OSError) as exc:
                self.errors.append(f"Process monitoring error: {exc}")
            time.sleep(interval)

    def _emit(self, event_type: EventType, metadata: dict) -> None:
        self._batcher.add(PoEEvent(
            event_type=event_type.value,
            session_id=self._session_id,
            metadata=metadata,
            synthetic=False,
        ))
