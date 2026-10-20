"""
log_effort.py — End-to-end PoE pipeline: collect → analyse → submit to blockchain.

Workflow
--------
1. Start a session (SessionManager)
2. Collect events (MockCollector or eBPFCollector)
3. Flush batches through MerkleAggregator
4. Extract behavioral features and generate a SessionReport
5. Submit (session_id_keccak, merkle_root) to AuditLedger on-chain
6. Save the receipt + report locally

Usage
-----
    python log_effort.py [--duration 10] [--batch-size 20] [--mock] [--dry-run]

Options
-------
    --duration N     Collection time in seconds (default: 10)
    --batch-size N   Flush batch after N events (default: 20)
    --mock           Force mock collector even on Linux (default: auto-detect)
    --dry-run        Run the full pipeline but skip blockchain submission
    --output-dir D   Where to store JSONL and report files (default: ~/.poe/sessions)
    --seed N         RNG seed for MockCollector reproducibility

Environment
-----------
    POE_RPC_URL, POE_CONTRACT_ADDRESS, POE_PRIVATE_KEY  (see .env.example)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from collector import (
    EBPF_AVAILABLE,
    EventBatcher,
    JSONLStorage,
    MerkleAggregator,
    MockCollector,
    SessionManager,
    eBPFCollector,
    merkle_root as compute_merkle_root,
)
from analysis import build_report

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt = "%H:%M:%S",
)
logger = logging.getLogger("poe.log_effort")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _separator(char: str = "-", width: int = 60) -> None:
    print(char * width)


def _save_receipt(receipt_data: dict, out_dir: Path, session_id: str) -> Path:
    """Write the submission receipt JSON to disk."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{session_id}-receipt.json"
    path.write_text(json.dumps(receipt_data, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    duration:     float = 10.0,
    batch_size:   int   = 20,
    force_mock:   bool  = False,
    dry_run:      bool  = False,
    output_dir:   str   = "~/.poe/sessions",
    seed:         int | None = None,
) -> dict:
    """
    Execute the full PoE pipeline.

    Returns a summary dict with keys:
        session_id, merkle_root, report_hash,
        tx_hash (None if dry_run), receipt_path, report_path
    """
    out = Path(output_dir).expanduser().resolve()

    _separator("=")
    print("  Proof of Effort - Session Logger  (Phase 5)")
    _separator("=")
    print(f"  Duration   : {duration} s")
    print(f"  Batch size : {batch_size}")
    print(f"  Output     : {out}")
    print(f"  Dry-run    : {dry_run}")
    print(f"  eBPF ready : {EBPF_AVAILABLE and not force_mock}")
    _separator()

    # -- Session setup -------------------------------------------------------
    manager = SessionManager(storage_dir=out)
    sid     = manager.create_session()
    session = manager.start_session(sid)
    logger.info("Session created: %s", sid)

    # -- Batcher + Merkle aggregator ----------------------------------------
    aggregator = MerkleAggregator()

    all_events: list = []

    def _on_flush(batch: list) -> None:
        manager._storage.append_batch(batch, session.storage_path)
        all_events.extend(batch)
        aggregator.on_flush(batch)

    batcher = EventBatcher(
        max_size       = batch_size,
        max_age_seconds= max(duration / 3, 1.0),
        on_flush       = _on_flush,
    )

    # -- Collector -----------------------------------------------------------
    use_ebpf = EBPF_AVAILABLE and not force_mock
    if use_ebpf:
        collector = eBPFCollector(session_id=sid, batcher=batcher, fallback_to_mock=True)
        logger.info("Using eBPFCollector")
    else:
        collector = MockCollector(session_id=sid, batcher=batcher, seed=seed)
        logger.info("Using MockCollector (synthetic events)")

    collector.start()
    logger.info("Collecting for %.1f seconds ...", duration)
    time.sleep(duration)

    remaining = collector.stop()
    if remaining:
        _on_flush(remaining)

    manager.stop_session(sid)
    # Read all events back from JSONL so the Merkle root includes session
    # bookend events (SESSION_START / SESSION_END) that SessionManager writes
    # directly to disk and bypasses the batcher/all_events list.
    all_events = JSONLStorage().read_all(session.storage_path)
    logger.info("Collection complete. %d events on disk.", len(all_events))

    # -- Merkle root ---------------------------------------------------------
    merkle = compute_merkle_root(all_events)
    logger.info("Merkle root: %s", merkle)

    # -- Analysis report -----------------------------------------------------
    report      = build_report(
        all_events,
        merkle_root=merkle,
        collector=collector.metadata,
        lifecycle_status=session.status.value,
    )
    report_path = report.save(out / f"{sid}-report.json")
    logger.info("Analysis report saved: %s", report_path)
    logger.info(
        "Score: %.1f (%s) | Confidence: %s",
        report.scoring.score,
        report.scoring.grade,
        report.scoring.confidence,
    )

    # -- Blockchain submission -----------------------------------------------
    tx_hash = None
    receipt_path = None

    if dry_run:
        logger.info("[DRY RUN] Skipping blockchain submission.")
        print("\n  [DRY RUN] Would submit:")
        print(f"    session_id  : {sid}")
        print(f"    merkle_root : {merkle}")
        print(f"    report_hash : {report.report_hash}")
    else:
        try:
            from blockchain.chain import AuditLedgerClient, ChainError, DuplicateError

            client  = AuditLedgerClient.from_env()
            receipt_obj = client.submit_session(
                sid,
                merkle,
                report_hash_hex=report.report_hash,
                model_version=report.model_version,
                feature_version=report.feature_version,
                heuristic_score_bps=int(round(report.scoring.score * 100)),
                ml_classification=report.ml.classification,
                ml_confidence_bps=int(round(report.ml.confidence * 10000)),
                synthetic=report.collector.synthetic,
            )
            tx_hash = receipt_obj.tx_hash

            receipt_data = {
                "session_id":      sid,
                "merkle_root":     merkle,
                "report_hash":     report.report_hash,
                "tx_hash":         tx_hash,
                "block_number":    receipt_obj.block_number,
                "session_id_hex":  receipt_obj.session_id_hex,
                "merkle_root_hex": receipt_obj.merkle_root_hex,
                "model_version":    report.model_version,
                "feature_version":  report.feature_version,
                "collector":        report.collector.name,
                "synthetic":         report.collector.synthetic,
            }
            receipt_path = _save_receipt(receipt_data, out, sid)

            logger.info("Submitted! tx=%s block=%d", tx_hash, receipt_obj.block_number)
            print(f"\n  Blockchain receipt saved: {receipt_path}")

        except DuplicateError as exc:
            logger.error("DUPLICATE: %s", exc)
            print(f"\n  ERROR: Duplicate session — {exc}", file=sys.stderr)
            sys.exit(2)
        except ChainError as exc:
            logger.error("Blockchain error: %s", exc)
            print(f"\n  ERROR: {exc}", file=sys.stderr)
            sys.exit(3)

    _separator()
    print(f"\n  Session ID   : {sid}")
    print(f"  Merkle root  : {merkle}")
    print(f"  Report hash  : {report.report_hash}")
    print(f"  Score        : {report.scoring.score} ({report.scoring.grade})")
    print(f"  Report file  : {report_path}")
    if tx_hash:
        print(f"  Tx hash      : {tx_hash}")
    print()

    return {
        "session_id":    sid,
        "merkle_root":   merkle,
        "report_hash":   report.report_hash,
        "tx_hash":       tx_hash,
        "receipt_path":  str(receipt_path) if receipt_path else None,
        "report_path":   str(report_path),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python log_effort.py",
        description="PoE Phase 5 — collect events, analyse, submit to blockchain.",
    )
    p.add_argument("--duration",   type=float, default=10.0, metavar="S",
                   help="Collection duration in seconds (default: 10).")
    p.add_argument("--batch-size", type=int,   default=20,  metavar="N",
                   help="Events per batch (default: 20).")
    p.add_argument("--mock",       action="store_true",
                   help="Force MockCollector even when eBPF is available.")
    p.add_argument("--dry-run",    action="store_true",
                   help="Skip blockchain submission (useful for testing).")
    p.add_argument("--output-dir", type=str, default="~/.poe/sessions", metavar="DIR",
                   help="Output directory for JSONL and report files.")
    p.add_argument("--seed",       type=int, default=None, metavar="N",
                   help="RNG seed for MockCollector reproducibility.")
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    run_pipeline(
        duration   = args.duration,
        batch_size = args.batch_size,
        force_mock = args.mock,
        dry_run    = args.dry_run,
        output_dir = args.output_dir,
        seed       = args.seed,
    )
