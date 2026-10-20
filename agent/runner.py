"""Production session orchestration using the shared PoE pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Optional

from analysis import build_report
from blockchain.chain import AuditLedgerClient, ChainError
from collector import (
    EventBatcher,
    JSONLStorage,
    SessionManager,
    SessionStatus,
    WindowsCollector,
    merkle_root,
)

from .config import AgentConfig

logger = logging.getLogger(__name__)


class ProductionSessionRunner:
    """Start, stop, analyze, and optionally anchor a real Windows session."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        config.validate()
        self.config = config
        self._on_status = on_status or (lambda message: logger.info(message))
        self.manager = SessionManager(config.output_dir)
        self.session_id: Optional[str] = None
        self.session = None
        self.collector: Optional[WindowsCollector] = None
        self._batcher: Optional[EventBatcher] = None
        self._started = False

    def start(self) -> str:
        if self._started:
            raise RuntimeError("A production session is already running.")
        self.session_id = self.manager.create_session(
            synthetic=False,
            collector_name="WindowsCollector",
        )
        self.session = self.manager.start_session(self.session_id)
        self._batcher = EventBatcher(
            max_size=50,
            max_age_seconds=5.0,
            on_flush=lambda batch: self.manager._storage.append_batch(
                batch, self.session.storage_path
            ),
        )
        self.collector = WindowsCollector(
            self.session_id,
            self._batcher,
            self.config.authorized_folders,
            include_processes=self.config.include_processes,
        )
        self.collector.start()
        self._started = True
        self._on_status(f"Monitoring started: {self.session_id}")
        return self.session_id

    def stop(self) -> dict:
        if not self._started or self.session is None or self.collector is None:
            raise RuntimeError("No production session is running.")
        remaining = self.collector.stop()
        if remaining:
            self.manager._storage.append_batch(remaining, self.session.storage_path)
        self.manager.stop_session(self.session.session_id)
        events = JSONLStorage().read_all(self.session.storage_path)
        root = merkle_root(events)
        report = build_report(
            events,
            merkle_root=root,
            collector=self.collector.metadata,
            lifecycle_status=self.session.status.value,
        )
        report_path = report.save(
            Path(self.config.output_dir).expanduser()
            / f"{self.session.session_id}-report.json"
        )
        result = {
            "session_id": self.session.session_id,
            "event_count": len(events),
            "merkle_root": root,
            "report_hash": report.report_hash,
            "report_path": str(report_path),
            "blockchain_status": "NOT_ATTEMPTED",
            "collector_errors": list(self.collector.errors),
        }
        try:
            client = AuditLedgerClient.from_env()
            receipt = client.submit_session(
                self.session.session_id,
                root,
                report_hash_hex=report.report_hash,
                model_version=report.model_version,
                feature_version=report.feature_version,
                heuristic_score_bps=int(round(report.scoring.score * 100)),
                ml_classification=report.ml.classification,
                ml_confidence_bps=int(round(report.ml.confidence * 10000)),
                synthetic=report.collector.synthetic,
            )
            result.update(
                blockchain_status="ANCHORED",
                tx_hash=receipt.tx_hash,
                block_number=receipt.block_number,
            )
        except ChainError as exc:
            result.update(blockchain_status="PENDING", blockchain_error=str(exc))
            self._save_pending(result)
            self._on_status(f"Session saved locally; blockchain submission pending: {exc}")
        self._started = False
        self._on_status(
            f"Monitoring stopped. Events: {len(events)}; ML: {report.ml.classification}"
        )
        return result

    def abort(self) -> None:
        if not self._started or self.session is None or self.collector is None:
            return
        self.collector.stop()
        self.manager.finish_session(
            self.session.session_id,
            status=SessionStatus.ABORTED,
        )
        self._started = False
        self._on_status("Monitoring aborted; partial data was retained locally.")

    def _save_pending(self, result: dict) -> None:
        output = Path(self.config.output_dir).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        queue = output / "pending-submissions.jsonl"
        with queue.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, sort_keys=True) + "\n")
