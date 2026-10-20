"""
analysis/__init__.py — Proof of Effort analysis package.

Public interface
----------------
    extract(events)                -> SessionFeatures   (features)
    score_session(features, cfg)   -> ScoringResult     (scorer)
    build_report(events, root, cfg)-> SessionReport     (report)
    load_report(path)              -> dict              (report)
    SessionFeatures, ScoringConfig, ScoringResult, SessionReport

This package is independent of the blockchain and ML layers.
It imports only from collector.schema and the Python standard library.
"""

from .features import FEATURE_SCHEMA_VERSION, SessionFeatures, extract, feature_vector
from .ml import MLResult, predict_session
from .scorer   import RuleResult, ScoringConfig, ScoringResult, score_session
from .report   import SessionReport, build_report, load_report

__all__ = [
    "SessionFeatures",
    "extract",
    "feature_vector",
    "FEATURE_SCHEMA_VERSION",
    "MLResult",
    "predict_session",
    "RuleResult",
    "ScoringConfig",
    "ScoringResult",
    "score_session",
    "SessionReport",
    "build_report",
    "load_report",
]
