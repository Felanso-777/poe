"""
blockchain/chain.py — Python client for the AuditLedger Solidity contract.

Provides a clean, typed interface that exactly matches the contract ABI:
    submitSession(bytes32 sessionId, bytes32 merkleRoot)
    getSession(bytes32 sessionId)   -> SessionRecord
    verifyMerkleRoot(bytes32, bytes32) -> bool
    sessionExists(bytes32) -> bool

ABI encoding rules (matching Solidity)
---------------------------------------
- sessionId on-chain  : keccak256( utf-8 bytes of the UUID string )
- merkleRoot on-chain : the 32-byte binary digest of the hex Merkle root string

Both conversions are handled by `_session_id_bytes32` and `_root_bytes32`
helpers so callers always pass plain Python strings.

Configuration (via environment variables or .env file)
------------------------------------------------------
    POE_RPC_URL          = http://127.0.0.1:8545    (Hardhat localhost)
    POE_CONTRACT_ADDRESS = 0x...
    POE_PRIVATE_KEY      = 0x...  (Hardhat test account — never a real key)
    POE_CHAIN_ID         = 31337  (Hardhat default)

Never hardcode secrets.  Use a .env file (git-ignored) or set env vars directly.

Error handling
--------------
ChainError      — base class
ConfigError     — missing env vars or ABI artifact
RPCError        — cannot reach the node
ContractError   — transaction reverted (includes revert reason)
DuplicateError  — ZeroSessionId / ZeroMerkleRoot / DuplicateSession
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ChainError(RuntimeError):
    """Base class for all blockchain-layer errors."""

class ConfigError(ChainError):
    """Missing or invalid configuration (env vars, ABI file, etc.)."""

class RPCError(ChainError):
    """Cannot connect to the Ethereum node."""

class ContractError(ChainError):
    """Transaction reverted or call failed."""

class DuplicateError(ContractError):
    """Session already exists on-chain (DuplicateSession revert)."""

# ---------------------------------------------------------------------------
# ABI path (relative to this file's location inside blockchain/)
# ---------------------------------------------------------------------------

_ABI_PATH = (
    Path(__file__).parent
    / "artifacts" / "contracts" / "AuditLedger.sol" / "AuditLedger.json"
)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SessionRecord:
    """Mirrors the Solidity Session struct returned by getSession()."""
    session_id_hex:  str    # hex string (bytes32)
    merkle_root_hex: str    # hex string (bytes32)
    timestamp:       int    # block.timestamp (unix seconds)
    submitter:       str    # checksummed address string
    report_hash_hex: str = ""
    model_version: str = ""
    feature_version: str = ""
    heuristic_score_bps: int = 0
    ml_classification: str = ""
    ml_confidence_bps: int = 0
    synthetic: bool = False

@dataclass
class SubmitReceipt:
    """Result of a successful submitSession() call."""
    tx_hash:         str    # 0x-prefixed hex
    block_number:    int
    session_id_hex:  str    # the bytes32 that was stored
    merkle_root_hex: str

# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def _session_id_bytes32(uuid_str: str) -> bytes:
    """keccak256 of the UTF-8 UUID string → 32 bytes (matches Solidity spec)."""
    # NIST SHA-3 and Ethereum Keccak-256 have different padding. Use web3's
    # consensus-compatible implementation rather than hashlib.sha3_256.
    from web3 import Web3

    return Web3.keccak(text=uuid_str)


def _root_bytes32(merkle_root_hex: str) -> bytes:
    """Convert a 64-char hex Merkle root string to raw 32 bytes."""
    if len(merkle_root_hex) != 64:
        raise ConfigError(
            f"merkle_root must be a 64-char hex string, got {len(merkle_root_hex)} chars"
        )
    return bytes.fromhex(merkle_root_hex)

# ---------------------------------------------------------------------------
# AuditLedgerClient
# ---------------------------------------------------------------------------

class AuditLedgerClient:
    """
    High-level Python interface to the deployed AuditLedger contract.

    Instantiate once:
        client = AuditLedgerClient.from_env()

    Then use:
        receipt = client.submit_session(session_uuid, merkle_root_hex)
        record  = client.get_session(session_uuid)
        ok      = client.verify_merkle_root(session_uuid, merkle_root_hex)
        exists  = client.session_exists(session_uuid)
    """

    def __init__(self, w3, contract) -> None:
        self._w3       = w3
        self._contract = contract

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, *, load_dotenv: bool = True) -> "AuditLedgerClient":
        """
        Build a client from environment variables.

        Required env vars:
            POE_RPC_URL, POE_CONTRACT_ADDRESS, POE_PRIVATE_KEY

        Optional:
            POE_CHAIN_ID  (default 31337 for Hardhat)
        """
        # Load .env if present (ignore if python-dotenv not installed)
        if load_dotenv:
            _try_load_dotenv()

        rpc_url  = os.environ.get("POE_RPC_URL", "")
        address  = os.environ.get("POE_CONTRACT_ADDRESS", "")
        priv_key = os.environ.get("POE_PRIVATE_KEY", "")

        missing = [k for k, v in {
            "POE_RPC_URL":          rpc_url,
            "POE_CONTRACT_ADDRESS": address,
            "POE_PRIVATE_KEY":      priv_key,
        }.items() if not v]

        if missing:
            raise ConfigError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Copy .env.example to .env and fill in the values."
            )

        # Lazy import web3 so dry-run collection does not require blockchain
        # dependencies. Web3 v8 renamed the PoA middleware.
        try:
            from web3 import Web3
        except ImportError as exc:
            raise ConfigError(
                "web3 is not installed.  Run: pip install web3"
            ) from exc
        try:
            from web3.middleware import ExtraDataToPOAMiddleware
            poa_middleware = ExtraDataToPOAMiddleware
        except ImportError:
            try:
                from web3.middleware import geth_poa_middleware
                poa_middleware = geth_poa_middleware
            except ImportError as exc:
                raise ConfigError(
                    "The installed web3 package does not provide PoA middleware. "
                    "Upgrade web3 with: python -m pip install --upgrade web3"
                ) from exc

        # Connect
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
            # Inject PoA middleware (needed for Hardhat/Ganache)
            w3.middleware_onion.inject(poa_middleware, layer=0)
        except Exception as exc:
            raise RPCError(f"Failed to create Web3 provider for {rpc_url}: {exc}") from exc

        if not w3.is_connected():
            raise RPCError(
                f"Cannot connect to Ethereum node at {rpc_url}.\n"
                "Make sure the Hardhat node is running: npx hardhat node"
            )

        # Load ABI
        try:
            abi = _load_abi()
        except FileNotFoundError as exc:
            raise ConfigError(
                f"ABI artifact not found at {_ABI_PATH}.\n"
                "Compile the contract first: cd blockchain && npx hardhat compile"
            ) from exc

        # Build contract instance
        checksum_addr = Web3.to_checksum_address(address)
        if not w3.eth.get_code(checksum_addr):
            raise ConfigError(
                f"No contract code is deployed at {checksum_addr} on {rpc_url}. "
                "Deploy AuditLedger to this network and update POE_CONTRACT_ADDRESS."
            )
        contract      = w3.eth.contract(address=checksum_addr, abi=abi)

        # Set default account from private key
        account = w3.eth.account.from_key(priv_key)
        w3.eth.default_account = account.address

        client = cls(w3, contract)
        client._account  = account
        client._chain_id = int(os.environ.get("POE_CHAIN_ID", "31337"))
        return client

    # ------------------------------------------------------------------
    # Write: submitSession
    # ------------------------------------------------------------------

    def submit_session(
        self,
        session_uuid: str,
        merkle_root_hex: str,
        report_hash_hex: str = "",
        model_version: str = "",
        feature_version: str = "",
        heuristic_score_bps: int = 0,
        ml_classification: str = "",
        ml_confidence_bps: int = 0,
        synthetic: bool = False,
    ) -> SubmitReceipt:
        """
        Call submitSession(bytes32, bytes32) on the contract.

        Parameters
        ----------
        session_uuid : str
            UUID string of the session (not sent on-chain; keccak256d first).
        merkle_root_hex : str
            64-char hex string of the Merkle root.

        Returns
        -------
        SubmitReceipt
            Transaction hash, block number, encoded IDs.

        Raises
        ------
        DuplicateError   — contract revert: DuplicateSession
        ContractError    — other revert (NotAuthorized, ZeroSessionId, etc.)
        RPCError         — node unreachable
        """
        from web3 import Web3

        sid_bytes  = _session_id_bytes32(session_uuid)
        root_bytes = _root_bytes32(merkle_root_hex)

        # Validate non-zero (catch it here before wasting gas)
        if sid_bytes == b"\x00" * 32:
            raise ContractError("session_id hashed to zero — this should never happen.")
        if root_bytes == b"\x00" * 32:
            raise ContractError("merkle_root must not be zero bytes.")

        try:
            if ml_classification or heuristic_score_bps or ml_confidence_bps or synthetic:
                if report_hash_hex.startswith("sha256:"):
                    report_hash_hex = report_hash_hex.split(":", 1)[1]
                if len(report_hash_hex) != 64:
                    raise ConfigError("report_hash must be a 64-character SHA-256 hex digest.")
                function = self._contract.functions.submitSessionWithAnalysis(
                    sid_bytes, root_bytes, bytes.fromhex(report_hash_hex),
                    model_version, feature_version, heuristic_score_bps,
                    ml_classification, ml_confidence_bps, synthetic
                )
            elif report_hash_hex or model_version or feature_version:
                if report_hash_hex.startswith("sha256:"):
                    report_hash_hex = report_hash_hex.split(":", 1)[1]
                if len(report_hash_hex) != 64:
                    raise ConfigError("report_hash must be a 64-character SHA-256 hex digest.")
                report_bytes = bytes.fromhex(report_hash_hex)
                function = self._contract.functions.submitSessionWithMetadata(
                    sid_bytes, root_bytes, report_bytes, model_version, feature_version
                )
            else:
                function = self._contract.functions.submitSession(sid_bytes, root_bytes)
            tx_params = {
                "from":     self._account.address,
                "chainId":  self._chain_id,
                "nonce":    self._w3.eth.get_transaction_count(self._account.address),
                "gasPrice": self._w3.eth.gas_price,
            }
            # Metadata submissions store dynamic strings and cost more than
            # legacy submissions. Estimate the selected call rather than
            # relying on a fixed limit that can fail after contract changes.
            estimated_gas = function.estimate_gas(tx_params)
            tx_params["gas"] = max(200_000, int(estimated_gas * 1.25))
            tx = function.build_transaction(tx_params)
            signed  = self._account.sign_transaction(tx)
            raw_transaction = getattr(signed, "raw_transaction", None)
            if raw_transaction is None:
                raw_transaction = signed.rawTransaction
            tx_hash = self._w3.eth.send_raw_transaction(raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        except Exception as exc:
            self._raise_contract_error(exc, session_uuid)

        if receipt.status != 1:
            raise ContractError(
                f"Transaction {receipt.transactionHash.hex()} reverted "
                f"(status=0).  Check contract revert reason."
            )

        recorded_topic = Web3.keccak(
            text="SessionRecorded(bytes32,bytes32,address,uint256)"
        )
        recorded = any(
            log["address"].lower() == self._contract.address.lower()
            and log["topics"]
            and log["topics"][0] == recorded_topic
            for log in receipt["logs"]
        )
        if not recorded:
            raise ContractError(
                "Transaction succeeded but AuditLedger emitted no SessionRecorded "
                "event. The configured address may not be the deployed contract."
            )

        logger.info(
            "Session submitted: tx=%s block=%d",
            receipt.transactionHash.hex(),
            receipt.blockNumber,
        )

        return SubmitReceipt(
            tx_hash        = receipt.transactionHash.hex(),
            block_number   = receipt.blockNumber,
            session_id_hex = sid_bytes.hex(),
            merkle_root_hex= root_bytes.hex(),
        )

    # ------------------------------------------------------------------
    # Read: getSession
    # ------------------------------------------------------------------

    def get_session(self, session_uuid: str) -> SessionRecord:
        """
        Retrieve the stored Session struct for *session_uuid*.

        Raises ContractError (SessionNotFound) if not on-chain.
        """
        from web3 import Web3
        sid_bytes = _session_id_bytes32(session_uuid)
        try:
            result = self._contract.functions.getSession(sid_bytes).call()
        except Exception as exc:
            self._raise_contract_error(exc, session_uuid)

        session_id, merkle_root, *remaining = result
        # The first four fields are stable; metadata fields are present on
        # upgraded contracts and absent on legacy deployments.
        timestamp, submitter = remaining[-2], remaining[-1]
        metadata = remaining[:-2]
        return SessionRecord(
            session_id_hex  = session_id.hex(),
            merkle_root_hex = merkle_root.hex(),
            timestamp       = int(timestamp),
            submitter       = submitter,
            report_hash_hex = metadata[0].hex() if metadata and metadata[0] != b"\x00" * 32 else "",
            model_version   = metadata[1] if len(metadata) > 1 else "",
            feature_version = metadata[2] if len(metadata) > 2 else "",
            heuristic_score_bps = int(metadata[3]) if len(metadata) > 3 else 0,
            ml_classification = metadata[4] if len(metadata) > 4 else "",
            ml_confidence_bps = int(metadata[5]) if len(metadata) > 5 else 0,
            synthetic = bool(metadata[6]) if len(metadata) > 6 else False,
        )

    # ------------------------------------------------------------------
    # Read: verifyMerkleRoot
    # ------------------------------------------------------------------

    def verify_merkle_root(
        self,
        session_uuid: str,
        merkle_root_hex: str,
    ) -> bool:
        """
        Call verifyMerkleRoot(bytes32, bytes32) → bool.

        Returns False (does not raise) when session not found or root mismatch.
        """
        from web3 import Web3
        sid_bytes  = _session_id_bytes32(session_uuid)
        root_bytes = _root_bytes32(merkle_root_hex)
        try:
            return bool(
                self._contract.functions.verifyMerkleRoot(sid_bytes, root_bytes).call()
            )
        except Exception as exc:
            raise RPCError(f"verifyMerkleRoot call failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Read: verifyReportHash
    # ------------------------------------------------------------------

    def verify_report_hash(
        self,
        session_uuid: str,
        report_hash_hex: str,
    ) -> bool:
        """
        Check whether *report_hash_hex* matches the reportHash stored on-chain
        for *session_uuid*.  Returns False (does not raise) when the session
        does not exist or has no report hash recorded.

        Parameters
        ----------
        session_uuid : str
            UUID string of the session.
        report_hash_hex : str
            64-character hex SHA-256 digest (with or without "sha256:" prefix).
        """
        from web3 import Web3
        sid_bytes = _session_id_bytes32(session_uuid)

        # Normalise: strip "sha256:" prefix if present
        if report_hash_hex.startswith("sha256:"):
            report_hash_hex = report_hash_hex.split(":", 1)[1]
        if len(report_hash_hex) != 64:
            raise ConfigError(
                f"report_hash must be a 64-character hex digest, got "
                f"{len(report_hash_hex)} chars."
            )
        root_bytes = bytes.fromhex(report_hash_hex)

        try:
            record = self.get_session(session_uuid)
        except ContractError:
            return False

        stored = record.report_hash_hex
        if not stored:
            return False
        return stored.lower() == root_bytes.hex().lower()

    # ------------------------------------------------------------------
    # Read: sessionExists
    # ------------------------------------------------------------------

    def session_exists(self, session_uuid: str) -> bool:
        """Return True if *session_uuid* is already recorded on-chain."""
        from web3 import Web3
        sid_bytes = _session_id_bytes32(session_uuid)
        try:
            return bool(
                self._contract.functions.sessionExists(sid_bytes).call()
            )
        except Exception as exc:
            raise RPCError(f"sessionExists call failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _raise_contract_error(self, exc: Exception, session_uuid: str = "") -> None:
        """Translate web3 exceptions into typed ChainError subclasses."""
        msg = str(exc)
        if "DuplicateSession" in msg:
            raise DuplicateError(
                f"Session {session_uuid!r} is already recorded on-chain. "
                "Duplicate submissions are rejected by the contract."
            ) from exc
        if "SessionNotFound" in msg:
            raise ContractError(
                f"Session {session_uuid!r} not found on-chain."
            ) from exc
        if "NotAuthorized" in msg:
            raise ContractError(
                "The signing account is not authorized to submit sessions. "
                "Call authorize(address) from the contract owner first."
            ) from exc
        if "ZeroSessionId" in msg:
            raise ContractError("Contract rejected zero sessionId.") from exc
        if "ZeroMerkleRoot" in msg:
            raise ContractError("Contract rejected zero merkleRoot.") from exc
        if "connect" in msg.lower() or "timeout" in msg.lower():
            raise RPCError(f"RPC connection error: {msg}") from exc
        raise ContractError(f"Contract call failed: {msg}") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_abi() -> list:
    """Load the AuditLedger ABI from the Hardhat artifact JSON."""
    with _ABI_PATH.open("r", encoding="utf-8") as fh:
        artifact = json.load(fh)
    return artifact["abi"]


def _try_load_dotenv() -> None:
    """Load the repository .env so tracker and dashboard use one configuration."""
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)
    except ImportError:
        pass
