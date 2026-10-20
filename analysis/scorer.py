"""
analysis/scorer.py — Transparent, configurable heuristic scoring engine.

Scoring formula
---------------
    score = sum( rule.weight * (1.0 if rule.satisfied(features) else 0.0) )
                for rule in active_rules

    where sum(rule.weight for rule in active_rules) == 100.0

Each rule produces a RuleResult with its name, weight, whether it was satisfied,
and a plain-English rationale.  The resulting score is not a ground-truth
measurement; it is a configurable heuristic indicator of observed development
activity.

Important limitations (always included in output)
--------------------------------------------------
1. Score reflects observable activity patterns — NOT code quality or authorship.
2. Event frequency does not prove whether code was typed by a human or generated
   by an AI assistant.
3. AI-assisted coding is not penalized.
4. A high score means observable activity was recorded; it does not verify
   that the activity produced value.
5. A low score may reflect a short or fragmented recording session, not low effort.

Public API
----------
    ScoringConfig     dataclass of weights + thresholds (override to customize)
    RuleResult        single-rule outcome
    ScoringResult     overall scoring output
    score_session(features, config) -> ScoringResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .features import SessionFeatures

# ---------------------------------------------------------------------------
# Limitations — always present in every ScoringResult
# ---------------------------------------------------------------------------

_HARD_LIMITATIONS: list[str] = [
    "Score reflects observable activity patterns, not code quality or authorship.",
    "Event frequency does not prove whether code was written by a human or an AI assistant.",
    "AI-assisted coding is not penalized by any rule in this scorer.",
    "A high score confirms recorded activity; it does not verify the value of that activity.",
    "A low score may reflect a short or interrupted recording session, not low effort.",
    "All thresholds are heuristic defaults and should be calibrated per team/project.",
]

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    """Outcome of a single scoring rule."""
    name:        str
    weight:      float
    satisfied:   bool
    points:      float               # weight if satisfied, else 0
    rationale:   str                 # why this rule exists
    detail:      str                 # what was observed for this session


@dataclass
class ScoringResult:
    """
    Full scoring output for one session.

    Fields
    ------
    score : float
        0–100.  Sum of points from satisfied rules.
    grade : str
        "A" (≥ 80), "B" (≥ 65), "C" (≥ 50), "D" (≥ 35), "F" (< 35).
    confidence : str
        "low" (< 10 events), "medium" (10–49 events), "high" (≥ 50 events).
    rule_results : list[RuleResult]
        Per-rule breakdown — the full explanation of the score.
    limitations : list[str]
        Hard-coded honesty statements always present in every result.
    notes : list[str]
        Dynamic notes generated from the session's features.
    """
    score:        float
    grade:        str
    confidence:   str
    rule_results: list[RuleResult]
    limitations:  list[str]
    notes:        list[str]

    # Explicitly NO isHuman field — see limitations above.


@dataclass
class ScoringConfig:
    """
    Configurable weights and thresholds for the heuristic scorer.

    All weights should sum to 100.  If they do not, the scorer normalizes them.
    Thresholds can be tuned per team or project without touching the scoring logic.
    """
    # Weights (default sum = 100)
    weight_min_event_count:  float = 15.0
    weight_min_duration:     float = 15.0
    weight_type_diversity:   float = 20.0
    weight_has_file_edits:   float = 20.0
    weight_has_keystrokes:   float = 15.0
    weight_reasonable_gap:   float = 15.0

    # Thresholds
    min_event_count:         int   = 10      # events
    min_duration_seconds:    float = 60.0    # seconds
    min_unique_types:        int   = 3       # distinct event types
    min_lines_modified:      int   = 1       # lines added or deleted
    min_keystrokes:          int   = 1       # total keystroke count
    max_mean_gap_seconds:    float = 300.0   # 5 minutes


# ---------------------------------------------------------------------------
# Grade bands
# ---------------------------------------------------------------------------

def _grade(score: float) -> str:
    if score >= 80: return "A"
    if score >= 65: return "B"
    if score >= 50: return "C"
    if score >= 35: return "D"
    return "F"


def _confidence(event_count: int) -> str:
    if event_count >= 50: return "high"
    if event_count >= 10: return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

@dataclass
class _Rule:
    name:      str
    rationale: str
    weight_attr: str     # attribute name on ScoringConfig for this rule's weight
    check:     Callable[[SessionFeatures, ScoringConfig], tuple[bool, str]]
    # check returns (satisfied, detail_string)


_RULES: list[_Rule] = [
    _Rule(
        name="MinEventCount",
        rationale=(
            "Very short sessions have too little signal to draw any conclusions. "
            "A minimum event count ensures the session contains measurable activity."
        ),
        weight_attr="weight_min_event_count",
        check=lambda f, c: (
            f.event_count >= c.min_event_count,
            f"Observed {f.event_count} events (threshold: {c.min_event_count})",
        ),
    ),
    _Rule(
        name="MinDuration",
        rationale=(
            "Sessions under a minute are likely accidental starts or test runs. "
            "A minimum duration threshold filters these out."
        ),
        weight_attr="weight_min_duration",
        check=lambda f, c: (
            f.duration_seconds is not None and f.duration_seconds >= c.min_duration_seconds,
            (f"Duration {round(f.duration_seconds or 0, 1)} s "
             f"(threshold: {c.min_duration_seconds} s)"),
        ),
    ),
    _Rule(
        name="TypeDiversity",
        rationale=(
            "Real development work typically involves a mix of activity types: "
            "file edits, window switches, process runs, keystrokes. "
            "A session with only one event type has limited signal."
        ),
        weight_attr="weight_type_diversity",
        check=lambda f, c: (
            f.unique_event_types >= c.min_unique_types,
            f"Observed {f.unique_event_types} distinct event types (threshold: {c.min_unique_types})",
        ),
    ),
    _Rule(
        name="HasFileEdits",
        rationale=(
            "Observable file modification events provide direct evidence of "
            "editor activity.  This rule does NOT distinguish typed from "
            "AI-generated code — it only checks that edit events occurred."
        ),
        weight_attr="weight_has_file_edits",
        check=lambda f, c: (
            (f.total_lines_added + f.total_lines_deleted) >= c.min_lines_modified,
            (f"{f.total_lines_added} lines added, {f.total_lines_deleted} lines deleted "
             f"(threshold: {c.min_lines_modified} total changes)"),
        ),
    ),
    _Rule(
        name="HasKeystrokes",
        rationale=(
            "Keystroke count events (aggregate counts, never content) confirm "
            "that input was received during the session.  A zero count may "
            "indicate a misconfigured collector, not necessarily no activity."
        ),
        weight_attr="weight_has_keystrokes",
        check=lambda f, c: (
            f.total_keystrokes >= c.min_keystrokes,
            f"Total keystrokes observed: {f.total_keystrokes} (threshold: {c.min_keystrokes})",
        ),
    ),
    _Rule(
        name="ReasonableGap",
        rationale=(
            "A very large mean gap between events suggests the session was "
            "left running idle.  This rule checks for continuous engagement, "
            "not work speed.  Rule is skipped (passes) when gap data is absent."
        ),
        weight_attr="weight_reasonable_gap",
        check=lambda f, c: (
            f.mean_gap_seconds is None or f.mean_gap_seconds <= c.max_mean_gap_seconds,
            (f"Mean gap {round(f.mean_gap_seconds or 0, 1)} s "
             f"(threshold: <= {c.max_mean_gap_seconds} s)"
             if f.mean_gap_seconds is not None
             else "No gap data available — rule passed by default"),
        ),
    ),
]


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

def score_session(
    features: SessionFeatures,
    config: Optional[ScoringConfig] = None,
) -> ScoringResult:
    """
    Apply heuristic rules to *features* and return a ScoringResult.

    Parameters
    ----------
    features : SessionFeatures
        Extracted from analysis.features.extract().
    config : ScoringConfig, optional
        Supply a custom config to override weights and thresholds.
        Defaults to ScoringConfig() (all default values).

    Returns
    -------
    ScoringResult
        score (0–100), grade, confidence, per-rule breakdown, limitations, notes.
    """
    cfg = config or ScoringConfig()

    # Collect weights; normalize so they sum to 100
    raw_weights = [getattr(cfg, r.weight_attr) for r in _RULES]
    total_weight = sum(raw_weights) or 100.0
    scale = 100.0 / total_weight

    rule_results: list[RuleResult] = []
    total_score = 0.0

    for rule, raw_w in zip(_RULES, raw_weights):
        w = raw_w * scale
        satisfied, detail = rule.check(features, cfg)
        pts = w if satisfied else 0.0
        total_score += pts
        rule_results.append(RuleResult(
            name=rule.name,
            weight=round(w, 2),
            satisfied=satisfied,
            points=round(pts, 2),
            rationale=rule.rationale,
            detail=detail,
        ))

    score = round(min(max(total_score, 0.0), 100.0), 2)

    # Generate dynamic notes
    notes: list[str] = []
    if features.event_count == 0:
        notes.append("No events found in this session.")
    if not features.has_session_bookends:
        notes.append("Session bookend events (SESSION_START/END) are missing; duration may be approximate.")
    if features.file_types_seen:
        notes.append(f"Languages observed: {', '.join(features.file_types_seen)}.")
    if features.process_names_seen:
        notes.append(f"Processes observed: {', '.join(features.process_names_seen)}.")
    if features.total_keystrokes > 0:
        notes.append(f"Total aggregate keystrokes recorded: {features.total_keystrokes}.")

    return ScoringResult(
        score=score,
        grade=_grade(score),
        confidence=_confidence(features.event_count),
        rule_results=rule_results,
        limitations=list(_HARD_LIMITATIONS),
        notes=notes,
    )
