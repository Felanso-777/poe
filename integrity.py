"""Canonical artifact hashing and explicit local/on-chain verification results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from collector.merkle import merkle_root
from collector.schema import PoEEvent


MERKLE_ARTIFACTS = (
    "normalized_event_identity_records",
    "feature_snapshot",
    "heuristic_snapshot",
    "ml_snapshot",
    "report_hash",
)


def canonical_json(value: Any) -> bytes:
    """Serialize JSON deterministically for all integrity commitments."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    ).encode("utf-8")


def sha256_artifact(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def artifact_manifest(events: list[PoEEvent], report: Any) -> dict[str, Any]:
    """Build the exact privacy-safe artifact set covered by a report."""
    data = report.to_dict() if hasattr(report, "to_dict") else report
    return {
        "normalized_event_identity_records": [
            {
                "event_id": event.event_id,
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "session_id": event.session_id,
            }
            for event in events
        ],
        "feature_snapshot": data.get("features", {}),
        "heuristic_snapshot": data.get("scoring", {}),
        "ml_snapshot": data.get("ml", {}),
        "report_hash": data.get("report_hash", ""),
    }


def artifact_merkle_root(events: list[PoEEvent], report: Any) -> str:
    """Return a Merkle root over the documented report artifact manifest."""
    manifest = artifact_manifest(events, report)
    leaves = [
        hashlib.sha256(b"PoE|artifact|" + canonical_json(manifest[name])).hexdigest()
        for name in MERKLE_ARTIFACTS
    ]
    # Reuse event Merkle semantics by hashing the deterministic leaf sequence.
    if not leaves:
        return merkle_root([])
    while len(leaves) > 1:
        if len(leaves) % 2:
            leaves.append(leaves[-1])
        leaves = [
            hashlib.sha256(
                b"PoE|artifact-node|" + bytes.fromhex(leaves[index]) + bytes.fromhex(leaves[index + 1])
            ).hexdigest()
            for index in range(0, len(leaves), 2)
        ]
    return leaves[0]


@dataclass(frozen=True)
class VerificationResult:
    status: str
    ok: bool
    message: str
    computed_report_hash: str | None = None
    registered_report_hash: str | None = None
    computed_merkle_root: str | None = None
    registered_merkle_root: str | None = None


def verify_report_artifact(
    report: dict[str, Any],
    *,
    registered_report_hash: str,
    registered_merkle_root: str,
    computed_merkle_root: str | None = None,
) -> VerificationResult:
    """Reject altered reports with a machine-readable failure status."""
    candidate = dict(report)
    candidate.pop("report_hash", None)
    candidate.pop("generated_at", None)
    computed_hash = sha256_artifact(candidate)
    actual_root = computed_merkle_root or report.get("merkle_root")
    if computed_hash != registered_report_hash:
        return VerificationResult(
            "MODIFIED_AFTER_REGISTRATION", False,
            "Report hash does not match the immutable registered hash.",
            computed_hash, registered_report_hash, actual_root, registered_merkle_root,
        )
    if actual_root != registered_merkle_root:
        return VerificationResult(
            "MODIFIED_AFTER_REGISTRATION", False,
            "Merkle root does not match the immutable registered root.",
            computed_hash, registered_report_hash, actual_root, registered_merkle_root,
        )
    return VerificationResult(
        "VERIFIED", True, "Artifact matches its immutable registration.",
        computed_hash, registered_report_hash, actual_root, registered_merkle_root,
    )
