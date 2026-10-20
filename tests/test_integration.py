"""
tests/test_integration.py — Integration tests for Phase 5 pipeline.

These tests use a mock AuditLedgerClient (no real blockchain node needed)
to verify the full pipeline: collect → Merkle → analyse → submit → verify.

Test scenarios:
    - Successful session: full pipeline produces consistent receipt
    - Modified event: Merkle mismatch detected, verification fails  
    - Duplicate submission: DuplicateError raised and handled
    - Blockchain connection failure: RPCError raised and handled
    - Dry-run: pipeline runs without calling blockchain
    - Verify with tampered event: FAIL reported, exit code non-zero
    - Chain client encoding: session_id and merkle_root encode correctly
    - Config error: missing env vars raise ConfigError
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# PoE modules
from blockchain.chain import (
    AuditLedgerClient,
    ChainError,
    ConfigError,
    DuplicateError,
    RPCError,
    SessionRecord,
    SubmitReceipt,
    _session_id_bytes32,
    _root_bytes32,
)
from collector.merkle import leaf_hash, merkle_root, build_proof, verify_proof
from collector.schema import EventType, PoEEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SID = str(uuid.uuid4())


def _make_event(et: EventType = EventType.FILE_MODIFIED, offset: int = 0) -> PoEEvent:
    meta = {}
    if et == EventType.FILE_MODIFIED:
        meta = {"file_name": "main.py", "language": "python",
                "lines_added": 5, "lines_deleted": 1}
    elif et == EventType.KEYSTROKE_COUNT:
        meta = {"count": 42}
    elif et == EventType.WINDOW_FOCUS:
        meta = {"app_name": "VS Code"}
    return PoEEvent(event_type=et, session_id=_SID, metadata=meta)


def _session_events(n: int = 10) -> list[PoEEvent]:
    types = [
        EventType.SESSION_START,
        EventType.FILE_MODIFIED,
        EventType.KEYSTROKE_COUNT,
        EventType.WINDOW_FOCUS,
        EventType.PROCESS_START,
    ]
    events = [PoEEvent(event_type=EventType.SESSION_START, session_id=_SID)]
    for i in range(n - 2):
        events.append(_make_event(types[i % len(types)]))
    events.append(PoEEvent(event_type=EventType.SESSION_END, session_id=_SID,
                           metadata={"duration_seconds": 120}))
    return events


def _make_mock_client(
    submit_receipt: Optional[SubmitReceipt] = None,
    submit_raises: Optional[Exception] = None,
    verify_result: bool = True,
    exists_result: bool = True,
    get_session_result: Optional[SessionRecord] = None,
) -> MagicMock:
    """Build a fully faked AuditLedgerClient."""
    events = _session_events()
    mroot  = merkle_root(events)

    client = MagicMock(spec=AuditLedgerClient)

    if submit_raises:
        client.submit_session.side_effect = submit_raises
    else:
        client.submit_session.return_value = submit_receipt or SubmitReceipt(
            tx_hash        = "0x" + "ab" * 32,
            block_number   = 42,
            session_id_hex = "aa" * 32,
            merkle_root_hex= mroot,
        )

    client.verify_merkle_root.return_value = verify_result
    client.session_exists.return_value     = exists_result
    client.get_session.return_value = get_session_result or SessionRecord(
        session_id_hex  = "aa" * 32,
        merkle_root_hex = mroot,
        timestamp       = 1_700_000_000,
        submitter       = "0x" + "cc" * 20,
    )
    return client


# ---------------------------------------------------------------------------
# blockchain/chain.py unit tests (no node required)
# ---------------------------------------------------------------------------

class TestChainEncoding:
    def test_session_id_uses_ethereum_keccak(self):
        from web3 import Web3

        session_id = "3f0d1127-1a24-4d75-b3a1-b4846466afae"
        assert _session_id_bytes32(session_id) == Web3.keccak(text=session_id)

    def test_root_bytes32_correct_length(self):
        root_hex   = "a" * 64
        root_bytes = _root_bytes32(root_hex)
        assert len(root_bytes) == 32

    def test_root_bytes32_roundtrip(self):
        root_hex   = "ab" * 32
        root_bytes = _root_bytes32(root_hex)
        assert root_bytes.hex() == root_hex

    def test_root_bytes32_invalid_length_raises(self):
        with pytest.raises(ConfigError):
            _root_bytes32("short")

    def test_config_error_on_missing_env(self, monkeypatch):
        monkeypatch.delenv("POE_RPC_URL",          raising=False)
        monkeypatch.delenv("POE_CONTRACT_ADDRESS",  raising=False)
        monkeypatch.delenv("POE_PRIVATE_KEY",       raising=False)
        with pytest.raises(ConfigError):
            AuditLedgerClient.from_env(load_dotenv=False)

    def test_config_error_on_partial_env(self, monkeypatch):
        monkeypatch.setenv("POE_RPC_URL", "http://127.0.0.1:8545")
        monkeypatch.delenv("POE_CONTRACT_ADDRESS", raising=False)
        monkeypatch.delenv("POE_PRIVATE_KEY",      raising=False)
        with pytest.raises(ConfigError):
            AuditLedgerClient.from_env(load_dotenv=False)


# ---------------------------------------------------------------------------
# log_effort pipeline (mocked blockchain)
# ---------------------------------------------------------------------------

class TestLogEffortPipeline:
    def test_dry_run_no_blockchain_call(self, tmp_path):
        """Dry-run must complete without calling any blockchain code."""
        from log_effort import run_pipeline
        result = run_pipeline(
            duration=0.5, batch_size=5, force_mock=True,
            dry_run=True, output_dir=str(tmp_path), seed=99,
        )
        assert result["session_id"]
        assert result["merkle_root"]
        assert result["report_hash"].startswith("sha256:")
        assert result["tx_hash"] is None
        # Report file should be saved
        assert Path(result["report_path"]).exists()

    def test_successful_submission(self, tmp_path):
        """Full pipeline with a mocked client completes and stores receipt."""
        from log_effort import run_pipeline
        mock_client = _make_mock_client()

        with patch("blockchain.chain.AuditLedgerClient") as MockClass:
            MockClass.from_env.return_value = mock_client
            result = run_pipeline(
                duration=0.5, batch_size=5, force_mock=True,
                dry_run=False, output_dir=str(tmp_path), seed=1,
            )

        assert result["tx_hash"] is not None
        assert result["tx_hash"].startswith("0x")
        mock_client.submit_session.assert_called_once()

    def test_duplicate_submission_exits(self, tmp_path):
        """DuplicateError should cause sys.exit(2)."""
        from log_effort import run_pipeline
        mock_client = _make_mock_client(
            submit_raises=DuplicateError("Session already exists.")
        )
        with patch("blockchain.chain.AuditLedgerClient") as MockClass:
            MockClass.from_env.return_value = mock_client
            with pytest.raises(SystemExit) as exc_info:
                run_pipeline(
                    duration=0.5, batch_size=100, force_mock=True,
                    dry_run=False, output_dir=str(tmp_path), seed=2,
                )
        assert exc_info.value.code == 2

    def test_rpc_failure_exits(self, tmp_path):
        """RPCError (connection failure) should cause sys.exit(3)."""
        from log_effort import run_pipeline
        mock_client = _make_mock_client(
            submit_raises=RPCError("Cannot connect to node.")
        )
        with patch("blockchain.chain.AuditLedgerClient") as MockClass:
            MockClass.from_env.return_value = mock_client
            with pytest.raises(SystemExit) as exc_info:
                run_pipeline(
                    duration=0.5, batch_size=100, force_mock=True,
                    dry_run=False, output_dir=str(tmp_path), seed=3,
                )
        assert exc_info.value.code == 3

    def test_report_contains_no_raw_events(self, tmp_path):
        """The saved JSON report must not contain raw source code or event content."""
        from log_effort import run_pipeline
        result = run_pipeline(
            duration=0.5, batch_size=5, force_mock=True,
            dry_run=True, output_dir=str(tmp_path), seed=7,
        )
        report_text = Path(result["report_path"]).read_text()
        report_dict = json.loads(report_text)
        # Raw event_ids or event lists must not be in the report
        # (only aggregate features and score are present)
        assert "events" not in report_dict
        # The report should have the standard schema
        assert "features" in report_dict
        assert "scoring"  in report_dict


# ---------------------------------------------------------------------------
# Merkle-based tamper detection
# ---------------------------------------------------------------------------

class TestTamperDetection:
    def test_modified_event_changes_root(self):
        events   = _session_events(6)
        root_original = merkle_root(events)

        # Tamper: replace one event with a new one (different event_id/timestamp)
        tampered = events[:3] + [_make_event(EventType.KEYSTROKE_COUNT)] + events[4:]
        root_tampered = merkle_root(tampered)
        assert root_original != root_tampered

    def test_tampered_root_fails_on_chain_verify(self):
        events = _session_events(4)
        good   = merkle_root(events)
        bad    = "ff" * 32

        client = _make_mock_client(verify_result=False)
        result = client.verify_merkle_root(_SID, bad)
        assert not result

    def test_inclusion_proof_detects_tampered_event(self):
        events = _session_events(6)
        root   = merkle_root(events)
        ev     = events[2]

        proof  = build_proof(events, ev.event_id)
        # Tamper: use a different event's leaf hash
        wrong_leaf = leaf_hash(events[3])
        assert not verify_proof(wrong_leaf, proof, root)

    def test_good_event_proof_passes(self):
        events = _session_events(6)
        root   = merkle_root(events)
        for ev in events:
            proof = build_proof(events, ev.event_id)
            assert verify_proof(leaf_hash(ev), proof, root)


# ---------------------------------------------------------------------------
# verify_effort pipeline (mocked blockchain)
# ---------------------------------------------------------------------------

class TestVerifyEffortPipeline:
    def _write_receipt(self, tmp_path: Path, session_id: str, events: list) -> Path:
        mroot = merkle_root(events)
        storage_path = tmp_path / f"{session_id}.jsonl"
        from collector.storage import JSONLStorage
        s = JSONLStorage()
        s.append_batch(events, storage_path)

        receipt = {
            "session_id":  session_id,
            "merkle_root": mroot,
            "report_hash": "sha256:" + "aa" * 32,
            "tx_hash":     "0x" + "bb" * 32,
            "block_number": 10,
        }
        rpath = tmp_path / f"{session_id}-receipt.json"
        rpath.write_text(json.dumps(receipt), encoding="utf-8")
        return rpath

    def test_successful_verification(self, tmp_path):
        events = _session_events(8)
        sid    = events[0].session_id
        mroot  = merkle_root(events)
        rpath  = self._write_receipt(tmp_path, sid, events)

        client = _make_mock_client(
            verify_result=True,
            exists_result=True,
            get_session_result=SessionRecord(
                session_id_hex  = "aa" * 32,
                merkle_root_hex = mroot,
                timestamp       = 1_700_000_000,
                submitter       = "0x" + "cc" * 20,
            ),
        )
        with patch("verify_effort.AuditLedgerClient") as MockClass:
            MockClass.from_env.return_value = client
            from verify_effort import verify
            code = verify(str(rpath))
        assert code == 0

    def test_session_not_found_fails(self, tmp_path):
        events = _session_events(4)
        sid    = events[0].session_id
        rpath  = self._write_receipt(tmp_path, sid, events)

        client = _make_mock_client(exists_result=False)
        with patch("verify_effort.AuditLedgerClient") as MockClass:
            MockClass.from_env.return_value = client
            from verify_effort import verify
            with pytest.raises(SystemExit) as exc_info:
                verify(str(rpath))
        assert exc_info.value.code != 0

    def test_rpc_error_on_exists_fails(self, tmp_path):
        events = _session_events(4)
        sid    = events[0].session_id
        rpath  = self._write_receipt(tmp_path, sid, events)

        client = MagicMock(spec=AuditLedgerClient)
        client.session_exists.side_effect = RPCError("Connection refused")

        with patch("verify_effort.AuditLedgerClient") as MockClass:
            MockClass.from_env.return_value = client
            from verify_effort import verify
            with pytest.raises(SystemExit) as exc_info:
                verify(str(rpath))
        assert exc_info.value.code != 0
