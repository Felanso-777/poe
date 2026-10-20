"""Deterministic, explainable baseline classifier for structured session data.

This is intentionally a small dependency-free logistic model. Its weights and
feature order are versioned metadata so a later trained model can replace it
without changing the report contract.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .features import FEATURE_SCHEMA_VERSION, SessionFeatures, feature_vector

MODEL_VERSION = "logistic-baseline-1.0"
MODEL_METADATA_VERSION = "1.0"
TRAINING_DATA_SCHEMA_VERSION = "1.0"
LABELS = ("likely_human_driven_activity", "possible_automation", "inconclusive")

# Coefficients are conservative indicators, not authorship evidence.
_WEIGHTS = (
    (0.04, 0.001, 0.0), (0.001, 0.0002, 0.0), (0.02, 0.0, 0.0),
    (0.3, -0.1, 0.0), (1.0, -0.3, 0.0), (-0.01, 0.0, 0.0),
    (-0.01, 0.0, 0.0), (-0.01, 0.0, 0.0), (0.0001, 0.0, 0.0),
    (0.001, 0.0, 0.0), (0.05, -0.01, 0.0), (0.02, 0.02, 0.0),
    (0.02, 0.08, 0.0), (0.01, 0.03, 0.0), (0.1, 0.0, 0.0),
    (0.05, 0.03, 0.0), (-0.1, 0.4, 0.0), (1.8, -1.0, 0.0),
    (0.4, -0.1, 0.0),
)
_BIAS = (0.0, -0.2, 0.0)


@dataclass(frozen=True)
class MLResult:
    classification: str
    confidence: float
    probabilities: dict[str, float]
    model_version: str
    feature_version: str
    explanation: dict[str, Any]
    inconclusive: bool


def model_metadata() -> dict[str, Any]:
    return {
        "metadata_version": MODEL_METADATA_VERSION,
        "model_version": MODEL_VERSION,
        "algorithm": "multiclass logistic regression",
        "feature_version": FEATURE_SCHEMA_VERSION,
        "labels": list(LABELS),
        "training_data_schema_version": TRAINING_DATA_SCHEMA_VERSION,
        "weights": [list(row) for row in _WEIGHTS],
        "bias": list(_BIAS),
        "limitations": [
            "This model predicts patterns in recorded activity only.",
            "It does not prove human identity, human authorship, or absence of AI assistance.",
        ],
    }


def save_model_metadata(path: str | Path) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model_metadata(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _softmax(scores: list[float]) -> list[float]:
    largest = max(scores)
    values = [math.exp(score - largest) for score in scores]
    total = sum(values)
    return [value / total for value in values]


def predict_session(features: SessionFeatures) -> MLResult:
    vector = feature_vector(features)
    scores = [
        bias + sum(value * row[index] for index, value in enumerate(vector))
        for bias, row in zip(_BIAS, zip(*_WEIGHTS))
    ]
    probabilities = _softmax(scores)
    ordered = dict(zip(LABELS, (round(value, 6) for value in probabilities)))
    best_index = max(range(len(probabilities)), key=probabilities.__getitem__)
    confidence = probabilities[best_index]
    inconclusive = (
        features.synthetic
        or features.data_quality_score < 0.6
        or features.event_count < 10
        or confidence < 0.55
    )
    classification = "inconclusive" if inconclusive else LABELS[best_index]
    strongest = sorted(
        zip(vector, range(len(vector))), key=lambda item: abs(item[0]), reverse=True
    )[:3]
    return MLResult(
        classification=classification,
        confidence=round(0.0 if inconclusive and features.synthetic else confidence, 6),
        probabilities=ordered,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_SCHEMA_VERSION,
        explanation={
            "method": "weighted feature contributions with softmax probabilities",
            "top_observed_feature_indices": [index for _, index in strongest],
            "warnings": list(features.data_quality_warnings),
        },
        inconclusive=inconclusive,
    )
