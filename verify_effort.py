"""
verify_effort.py — Verify a locally recorded session against the blockchain.

Workflow
--------
1. Read the saved receipt JSON (produced by log_effort.py)
2. Re-read the JSONL event file
3. Recompute the Merkle root from the local events
4. Call verifyMerkleRoot() on-chain → must return True
5. Call getSession() → confirm timestamp and submitter
6. Optionally verify a single event's inclusion proof

Verification failures are ALWAYS reported clearly and explicitly.
This script NEVER silently replaces a failed result with success.

Usage
-----
    python verify_effort.py <receipt-json-or-session-jsonl> [--event-id UUID]

    # Verify using a receipt file (preferred):
    python verify_effort.py ~/.poe/sessions/<sid>-receipt.json

    # Verify using raw JSONL (recomputes session_id from events):
    python verify_effort.py ~/.poe/sessions/<sid>.jsonl

    # Also verify inclusion proof for a specific event:
    python verify_effort.py <receipt> --event-id <event-uuid>

Environment
-----------
    POE_RPC_URL, POE_CONTRACT_ADDRESS, POE_PRIVATE_KEY  (see .env.example)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

from collector import JSONLStorage, build_proof, leaf_hash, merkle_root as compute_merkle_root, verify_proof
from blockchain.chain import AuditLedgerClient, ChainError, ConfigError, RPCError

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt = "%H:%M:%S",
)
logger = logging.getLogger("poe.verify_effort")

# Exit codes
EXIT_OK              = 0
EXIT_VERIFICATION_FAIL = 1
EXIT_NOT_FOUND       = 2
EXIT_CONFIG_ERROR    = 3
EXIT_RPC_ERROR       = 4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _separator(char: str = "-", width: int = 60) -> None:
    print(char * width)


def _fail(msg: str, code: int = EXIT_VERIFICATION_FAIL) -> None:
    """Print a clear FAIL message and exit.  NEVER silently succeed."""
    print(f"\n  [FAIL] {msg}", file=sys.stderr)
    sys.exit(code)


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def _load_receipt(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_jsonl_for_receipt(receipt_path: Path) -> Path | None:
    """Guess the JSONL file path from the receipt path."""
    sid = receipt_path.stem.replace("-receipt", "")
    jsonl = receipt_path.parent / f"{sid}.jsonl"
    return jsonl if jsonl.exists() else None


# ---------------------------------------------------------------------------
# Verification pipeline
# ---------------------------------------------------------------------------

def verify(
    input_path: str,
    event_id:   str | None = None,
) -> int:
    """
    Full verification pipeline.

    Returns an exit code (0 = all checks passed).
    """
    path = Path(input_path).expanduser().resolve()

    if not path.exists():
        _fail(f"File not found: {path}", EXIT_CONFIG_ERROR)

    _separator("=")
    print("  Proof of Effort - Session Verifier  (Phase 5)")
    _separator("=")

    # -- Load receipt or JSONL -----------------------------------------------
    session_id  : str | None = None
    merkle_hex  : str | None = None
    report_hash : str | None = None
    events = []

    if path.suffix == ".json":
        receipt = _load_receipt(path)
        session_id  = receipt.get("session_id")
        merkle_hex  = receipt.get("merkle_root")
        report_hash = receipt.get("report_hash")
        logger.info("Loaded receipt for session %s", session_id)

        jsonl_path = _find_jsonl_for_receipt(path)
        if jsonl_path:
            events = JSONLStorage().read_all(jsonl_path)
            logger.info("Loaded %d events from %s", len(events), jsonl_path)
        else:
            logger.warning("No JSONL file found alongside receipt — skipping local Merkle recompute.")

    elif path.suffix == ".jsonl":
        events = JSONLStorage().read_all(path)
        if not events:
            _fail("No events found in JSONL file.", EXIT_VERIFICATION_FAIL)
        session_id = events[0].session_id
        logger.info("Loaded %d events for session %s", len(events), session_id)
    else:
        _fail(f"Unsupported file type: {path.suffix}. Use .json (receipt) or .jsonl.", EXIT_CONFIG_ERROR)

    if not session_id:
        _fail("Could not determine session_id from input file.", EXIT_CONFIG_ERROR)

    # -- Step 1: Recompute Merkle root locally --------------------------------
    if events:
        local_merkle = compute_merkle_root(events)
        print(f"\n  Session ID   : {session_id}")
        print(f"  Events loaded: {len(events)}")
        print(f"  Local Merkle : {local_merkle}")

        if merkle_hex and local_merkle != merkle_hex:
            _fail(
                f"LOCAL MERKLE MISMATCH!\n"
                f"    Stored in receipt : {merkle_hex}\n"
                f"    Recomputed locally: {local_merkle}\n"
                f"  This means event data has been modified since submission.",
                EXIT_VERIFICATION_FAIL,
            )
        elif merkle_hex:
            _ok("Local Merkle root matches receipt.")
        merkle_hex = local_merkle
    else:
        print(f"\n  Session ID   : {session_id}")
        print(f"  Merkle root  : {merkle_hex} (from receipt, no events to verify)")

    # -- Step 2: Connect to blockchain ----------------------------------------
    try:
        client = AuditLedgerClient.from_env()
    except ChainError as exc:
        _fail(str(exc), EXIT_CONFIG_ERROR)

    # -- Step 3: Check session exists on-chain --------------------------------
    try:
        exists = client.session_exists(session_id)
    except RPCError as exc:
        _fail(f"RPC error: {exc}", EXIT_RPC_ERROR)

    if not exists:
        _fail(
            f"Session {session_id!r} NOT FOUND on-chain.\n"
            "  It may not have been submitted yet, or the wrong network is configured.",
            EXIT_NOT_FOUND,
        )
    _ok("Session found on-chain.")

    # -- Step 4: Fetch stored record ------------------------------------------
    try:
        record = client.get_session(session_id)
    except ChainError as exc:
        _fail(str(exc), EXIT_VERIFICATION_FAIL)

    print(f"\n  On-chain record:")
    print(f"    Merkle root : {record.merkle_root_hex}")
    print(f"    Timestamp   : {record.timestamp} (block time)")
    print(f"    Submitter   : {record.submitter}")

    # -- Step 5: Verify Merkle root on-chain ----------------------------------
    if merkle_hex:
        try:
            root_ok = client.verify_merkle_root(session_id, merkle_hex)
        except RPCError as exc:
            _fail(f"RPC error during verifyMerkleRoot: {exc}", EXIT_RPC_ERROR)

        if not root_ok:
            _fail(
                f"ON-CHAIN MERKLE ROOT MISMATCH!\n"
                f"    Submitted to contract: {record.merkle_root_hex}\n"
                f"    Local recomputed:      {merkle_hex}\n"
                f"  The events or the root stored locally do NOT match the blockchain record.",
                EXIT_VERIFICATION_FAIL,
            )
        _ok("On-chain Merkle root matches local computation.")

    # -- Step 5b: Verify report hash on-chain ---------------------------------
    if report_hash:
        # Recompute SHA-256 of the local report file
        receipt_parent = path.parent if path.suffix == ".json" else None
        report_path_candidates = [
            receipt_parent / f"{session_id}-report.json" if receipt_parent else None,
            Path(session_id + "-report.json"),
        ]
        report_file = None
        for candidate in report_path_candidates:
            if candidate and candidate.exists():
                report_file = candidate
                break

        if report_file:
            try:
                report_data = json.loads(report_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                _fail(f"Unable to read report JSON {report_file}: {exc}", EXIT_VERIFICATION_FAIL)

            report_data.pop("report_hash", None)
            report_data.pop("generated_at", None)
            canonical_report = json.dumps(
                report_data,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                default=str,
            ).encode("utf-8")
            local_report_hash = "sha256:" + hashlib.sha256(canonical_report).hexdigest()

            try:
                report_ok = client.verify_report_hash(session_id, local_report_hash)
            except (RPCError, ConfigError) as exc:
                _fail(f"RPC error during report hash verification: {exc}", EXIT_RPC_ERROR)

            if not report_ok:
                _fail(
                    f"ON-CHAIN REPORT HASH MISMATCH!\n"
                    f"    Stored on-chain : {record.report_hash_hex}\n"
                    f"    Local report file: {report_file}\n"
                    f"    Local recomputed : {local_report_hash}\n"
                    f"  The summary report has been modified since submission.",
                    EXIT_VERIFICATION_FAIL,
                )
            _ok("On-chain report hash matches local report file.")
        else:
            print(
                f"\n  [WARN] Report file not found alongside receipt — skipping "
                f"report hash verification."
            )

    # -- Step 6 (optional): Inclusion proof for a specific event --------------
    if event_id and events:
        print(f"\n  Inclusion proof for event: {event_id}")
        try:
            proof   = build_proof(events, event_id)
            lhash   = leaf_hash(next(e for e in events if e.event_id == event_id))
            proof_ok = verify_proof(lhash, proof, merkle_hex)
        except KeyError:
            _fail(f"Event {event_id!r} not found in local events.", EXIT_VERIFICATION_FAIL)
        except StopIteration:
            _fail(f"Event {event_id!r} not found.", EXIT_VERIFICATION_FAIL)

        if not proof_ok:
            _fail(
                f"INCLUSION PROOF FAILED for event {event_id}.\n"
                f"    The event data may have been tampered with.",
                EXIT_VERIFICATION_FAIL,
            )
        _ok(f"Inclusion proof verified for event {event_id}.")

    # -- All checks passed ----------------------------------------------------
    _separator()
    print(f"\n  All verification checks PASSED for session {session_id}")
    if report_hash:
        print(f"  Report hash  : {report_hash}")
    print(f"  (Only the hash was stored on-chain — no raw events were submitted)\n")

    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python verify_effort.py",
        description="PoE Phase 5 — verify a session against the blockchain ledger.",
    )
    p.add_argument(
        "input_path",
        metavar="PATH",
        help="Path to a -receipt.json or .jsonl session file.",
    )
    p.add_argument(
        "--event-id",
        metavar="UUID",
        default=None,
        help="Optionally verify the inclusion proof for a specific event UUID.",
    )
    return p


if __name__ == "__main__":
    args   = _build_parser().parse_args()
    code   = verify(args.input_path, event_id=args.event_id)
    sys.exit(code)
