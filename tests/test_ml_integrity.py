"""Tests for versioned ML output and explicit artifact verification failures."""

from datetime import datetime, timedelta, timezone

from analysis import build_report, predict_session
from collector.schema import EventType, PoEEvent
from integrity import verify_report_artifact


def _events(synthetic: bool = False):
    start = datetime(2026, 10, 16, tzinfo=timezone.utc)
    events = [
        PoEEvent(EventType.SESSION_START, "ml-test", timestamp=start.isoformat(), synthetic=synthetic)
    ]
    for index in range(12):
        events.append(
            PoEEvent(
                EventType.KEYSTROKE_COUNT,
                "ml-test",
                {"count": 4},
                timestamp=(start + timedelta(seconds=index + 1)).isoformat(),
                synthetic=synthetic,
            )
        )
    events.append(
        PoEEvent(
            EventType.SESSION_END,
            "ml-test",
            timestamp=(start + timedelta(seconds=20)).isoformat(),
            synthetic=synthetic,
        )
    )
    return events


def test_prediction_has_versioned_probabilities():
    result = predict_session(build_report(_events()).features)
    assert result.model_version
    assert result.feature_version == "2.0"
    assert set(result.probabilities) == {
        "likely_human_driven_activity", "possible_automation", "inconclusive"
    }
    assert abs(sum(result.probabilities.values()) - 1.0) < 0.001


def test_synthetic_session_is_inconclusive():
    report = build_report(_events(synthetic=True))
    assert report.ml.inconclusive
    assert report.ml.classification == "inconclusive"
    assert report.collector.synthetic
    assert report.warnings


def test_modified_report_is_rejected():
    report = build_report(_events(), merkle_root="registered-root")
    data = report.to_dict()
    data["features"]["event_count"] = 999
    result = verify_report_artifact(
        data,
        registered_report_hash=report.report_hash,
        registered_merkle_root="registered-root",
    )
    assert not result.ok
    assert result.status == "MODIFIED_AFTER_REGISTRATION"
