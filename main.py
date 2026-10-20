"""
main.py — Proof of Effort CLI entry point (Phase 2).

Provides three sub-commands that exercise the `collector` package without
touching the blockchain or ML model.

Usage
-----
    python main.py demo
    python main.py run  [--duration N] [--interval F] [--batch-size N] [--output-dir DIR]
    python main.py read <path-to-session.jsonl>

All events are written as JSONL to the output directory (default: ~/.poe/sessions/).
No kernel permissions are required — the mock collector generates synthetic events.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# collector is a sibling package — no blockchain imports
# ---------------------------------------------------------------------------
from collector import (
    EventBatcher,
    JSONLStorage,
    MockCollector,
    SessionManager,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("poe.main")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_separator(char: str = "-", width: int = 60) -> None:
    print(char * width)


def _summarise_session(session_path: Path) -> None:
    """Read *session_path* and print a summary table."""
    storage = JSONLStorage()
    events  = storage.read_all(session_path)

    if not events:
        print(f"  No events found in {session_path}")
        return

    from collections import Counter
    counts = Counter(e.event_type for e in events)

    print(f"\n  Session file : {session_path}")
    print(f"  Total events : {len(events)}")
    _print_separator()
    print(f"  {'Event Type':<25}  {'Count':>6}")
    _print_separator()
    for et, n in sorted(counts.items()):
        print(f"  {et:<25}  {n:>6}")
    _print_separator()
    # Show first and last timestamp
    timestamps = [e.timestamp for e in events]
    print(f"  First event  : {min(timestamps)}")
    print(f"  Last event   : {max(timestamps)}")
    print()


# ---------------------------------------------------------------------------
# Sub-command implementations
# ---------------------------------------------------------------------------

def cmd_demo(_args: argparse.Namespace) -> None:
    """Run a 5-second mock session and print a summary."""
    print(f"\n  Proof of Effort - Mock Demo  (Phase 2)")
    _print_separator()
    print("  Collector  : MockCollector (synthetic events, no kernel access)")
    print("  Duration   : 5 seconds")
    print("  Batch size : 10 events")
    _print_separator()

    output_dir = Path("~/.poe/sessions").expanduser()
    manager    = SessionManager(storage_dir=output_dir)
    sid        = manager.create_session()
    session    = manager.start_session(sid)

    batcher = EventBatcher(
        max_size=10,
        max_age_seconds=30.0,
        on_flush=lambda batch: manager._storage.append_batch(
            batch, session.storage_path
        ),
    )

    collector = MockCollector(session_id=sid, batcher=batcher, seed=42)
    collector.start(interval_seconds=0.25)

    logger.info("Session %s started - collecting for 5 s ...", sid)
    time.sleep(5)

    remaining = collector.stop()
    if remaining:
        manager._storage.append_batch(remaining, session.storage_path)

    manager.stop_session(sid)
    logger.info("Session stopped.")

    _summarise_session(session.storage_path)
    print(f"  JSONL file  : {session.storage_path}\n")


def cmd_run(args: argparse.Namespace) -> None:
    """Configurable mock session runner."""
    output_dir = Path(args.output_dir).expanduser().resolve()
    duration   = args.duration
    interval   = args.interval
    batch_size = args.batch_size

    print(f"\n  Proof of Effort - Collector Run  (Phase 2)")
    _print_separator()
    print(f"  Output dir : {output_dir}")
    print(f"  Duration   : {duration} seconds")
    print(f"  Interval   : {interval} seconds/event")
    print(f"  Batch size : {batch_size}")
    _print_separator()

    manager = SessionManager(storage_dir=output_dir)
    sid     = manager.create_session()
    session = manager.start_session(sid)

    batcher = EventBatcher(
        max_size=batch_size,
        max_age_seconds=max(duration / 3, 1.0),
        on_flush=lambda batch: manager._storage.append_batch(
            batch, session.storage_path
        ),
    )

    collector = MockCollector(session_id=sid, batcher=batcher)
    collector.start(interval_seconds=interval)

    logger.info("Session %s started - collecting for %s s ...", sid, duration)
    time.sleep(duration)

    remaining = collector.stop()
    if remaining:
        manager._storage.append_batch(remaining, session.storage_path)

    manager.stop_session(sid)
    logger.info("Session stopped.")

    _summarise_session(session.storage_path)
    print(f"  JSONL file  : {session.storage_path}\n")


def cmd_read(args: argparse.Namespace) -> None:
    """Read an existing JSONL session file."""
    path = Path(args.path).expanduser().resolve()
    if not path.exists():
        print(f"  ERROR: File not found - {path}", file=sys.stderr)
        sys.exit(1)
    _summarise_session(path)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Proof of Effort - local activity collector (Phase 2)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- demo ----------------------------------------------------------------
    sub.add_parser(
        "demo",
        help="Run a 5-second demo session with the mock collector.",
    )

    # -- run -----------------------------------------------------------------
    run_p = sub.add_parser(
        "run",
        help="Run a configurable mock collector session.",
    )
    run_p.add_argument(
        "--duration", type=float, default=10.0,
        metavar="SECONDS", help="How long to collect (default: 10 s).",
    )
    run_p.add_argument(
        "--interval", type=float, default=0.5,
        metavar="SECONDS", help="Time between emitted events (default: 0.5 s).",
    )
    run_p.add_argument(
        "--batch-size", type=int, default=20,
        metavar="N", help="Flush batch after N events (default: 20).",
    )
    run_p.add_argument(
        "--output-dir", type=str, default="~/.poe/sessions",
        metavar="DIR", help="Directory to store JSONL files (default: ~/.poe/sessions).",
    )

    # -- read ----------------------------------------------------------------
    read_p = sub.add_parser(
        "read",
        help="Read and summarise a JSONL session file.",
    )
    read_p.add_argument(
        "path",
        metavar="PATH",
        help="Path to the .jsonl session file.",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    dispatch = {
        "demo": cmd_demo,
        "run":  cmd_run,
        "read": cmd_read,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
