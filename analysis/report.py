"""
analysis/report.py — Privacy-preserving session report builder.

A SessionReport bundles extracted features and scoring results into a
canonical JSON document whose SHA-256 hash can be anchored to the blockchain.

Privacy guarantees
------------------
- No raw events, source code, or typed text is included.
- All features come from the privacy-filtered PoEEvent schema.
- Only the report_hash (a hex digest) needs to leave this machine.

Public API
----------
    SessionReport          dataclass
    build_report(events, merkle_root, config) -> SessionReport
    load_report(path)      -> dict   (raw JSON dict, not a SessionReport)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from collector.schema import PoEEvent
from .features import SessionFeatures, extract
from .scorer import ScoringConfig, ScoringResult, score_session
from .ml import MLResult, predict_session, MODEL_VERSION
from collector.interfaces import CollectorMetadata

_SCHEMA_VERSION = "2.0"


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class SessionReport:
    """
    A complete, privacy-preserving analysis report for one session.

    Fields
    ------
    schema_version : str
        Format version — bump when the JSON layout changes.
    generated_at : str
        ISO-8601 UTC timestamp of report creation.
    session_id : str
        UUID of the analysed session.
    features : SessionFeatures
        Extracted behavioral metrics (no raw events).
    scoring : ScoringResult
        Heuristic score, grade, per-rule breakdown, limitations.
    merkle_root : str
        Merkle root of the event batch (hex).  Included for cross-referencing
        with the blockchain record.
    report_hash : str
        "sha256:" + SHA-256 of the canonical JSON.  Only this field needs to
        be sent to the blockchain — it commits the full report without exposing
        its contents.
    """

    schema_version: str
    generated_at:   str
    session_id:     str
    features:       SessionFeatures
    scoring:        ScoringResult
    ml:             MLResult
    merkle_root:    str
    collector:      CollectorMetadata = field(
        default_factory=lambda: CollectorMetadata(name="unknown")
    )
    lifecycle_status: str = "completed"
    warnings:         list[str] = field(default_factory=list)
    feature_version:  str = ""
    model_version:    str = MODEL_VERSION
    report_hash:     str = field(default="", init=False)

    def __post_init__(self) -> None:
        if not self.report_hash:
            self.report_hash = self._compute_hash()

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a plain dict suitable for JSON serialization."""
        from dataclasses import asdict as _asdict

        def _clean(obj):
            """Recursively convert dataclass fields, handle None gracefully."""
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _clean(v) for k, v in _asdict(obj).items()
                        if not k.startswith("_")}
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_clean(i) for i in obj]
            return obj

        d = _clean(self)
        # Remove private fields from SessionFeatures serialisation
        d["features"] = {k: v for k, v in d["features"].items()
                         if not k.startswith("_")}
        return d

    def to_json(self, indent: int = 2) -> str:
        """Return pretty-printed JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path: str | Path) -> Path:
        """Write the report as JSON to *path*.  Returns the resolved path."""
        out = Path(path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.to_json(), encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    def _compute_hash(self) -> str:
        """
        SHA-256 of the canonical JSON (keys sorted, no whitespace, report_hash and
        generated_at excluded).  Deterministic: same features + score + merkle_root
        produce the same hash, regardless of when the report was generated.
        """
        d = self.to_dict()
        d.pop("report_hash", None)
        d.pop("generated_at", None)
        canonical = json.dumps(
            d, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        return f"sha256:{digest}"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_report(
    events: list[PoEEvent],
    merkle_root: str = "",
    config: Optional[ScoringConfig] = None,
    collector: Optional[CollectorMetadata] = None,
    lifecycle_status: str = "completed",
) -> SessionReport:
    """
    Run the full analysis pipeline and return a SessionReport.

    Parameters
    ----------
    events : list[PoEEvent]
        All events for one session.
    merkle_root : str
        Merkle root computed by collector.merkle.merkle_root().
        Can be empty string if not yet computed.
    config : ScoringConfig, optional
        Custom scoring thresholds/weights.

    Returns
    -------
    SessionReport
        Fully populated report with report_hash set.
    """
    feats   = extract(events)
    scoring = score_session(feats, config)
    ml      = predict_session(feats)
    metadata = collector or CollectorMetadata(
        name="synthetic" if feats.synthetic else "unknown",
        synthetic=feats.synthetic,
        authorized=not feats.synthetic,
    )

    report = SessionReport(
        schema_version = _SCHEMA_VERSION,
        generated_at   = datetime.now(timezone.utc).isoformat(),
        session_id     = feats.session_id,
        features       = feats,
        scoring        = scoring,
        ml             = ml,
        merkle_root    = merkle_root,
        collector      = metadata,
        lifecycle_status = lifecycle_status,
        warnings       = list(feats.data_quality_warnings),
        feature_version = feats.feature_schema_version,
        model_version   = ml.model_version,
    )
    return report


# ---------------------------------------------------------------------------
# Loader (plain dict — no schema validation needed for downstream use)
# ---------------------------------------------------------------------------

def load_report(path: str | Path) -> dict:
    """Read a previously saved JSON report and return it as a plain dict."""
    p = Path(path).expanduser().resolve()
    return json.loads(p.read_text(encoding="utf-8"))
