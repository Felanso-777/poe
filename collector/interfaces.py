"""Collector contracts and metadata shared by platform implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .schema import PoEEvent


@dataclass(frozen=True)
class CollectorMetadata:
    """Describes how a session was collected without exposing raw activity."""

    name: str
    version: str = "1.0"
    platform: str = "unknown"
    synthetic: bool = False
    authorized: bool = True


class Collector(Protocol):
    """Common lifecycle contract for Windows, Linux, macOS, and mock collectors."""

    metadata: CollectorMetadata

    def start(self, interval_seconds: float = 0.5) -> None:
        ...

    def stop(self) -> list[PoEEvent]:
        ...
