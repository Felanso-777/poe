"""
analysis/features.py — Behavioral feature extraction from PoE event lists.

Extracts only defensible, observable metrics from the existing PoEEvent schema.
No inferences about code authorship, typing speed, or human vs. AI origin are made.

All fields are computed from data already collected; nothing new is captured here.
Missing or incomplete data is represented as None or 0, never raises.

Public API
----------
    SessionFeatures   (dataclass)
    extract(events)   -> SessionFeatures
    feature_vector(features) -> tuple[float, ...]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from collector.schema import EventType, PoEEvent

FEATURE_SCHEMA_VERSION = "2.0"


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class SessionFeatures:
    """
    Behavioral metrics extracted from a list of PoEEvents.

    All numeric fields that cannot be computed from available data are
    set to None (optional) or 0 (counts), never raise.

    Fields
    ------
    session_id : str
        Session identifier taken from the first event.  Empty string if no events.
    event_count : int
        Total number of events in the session (including bookend events).
    duration_seconds : float or None
        Wall-clock duration.  Computed from SESSION_START / SESSION_END timestamps
        if present; falls back to max_ts - min_ts across all events.
        None for empty sessions.
    events_per_minute : float or None
        event_count / (duration_seconds / 60).  None if duration is 0 or None.
    unique_event_types : int
        Number of distinct EventType values observed.
    type_diversity_ratio : float
        unique_event_types / total possible types (9).  Range [0, 1].
    inter_event_gaps_seconds : list[float]
        Time differences (seconds) between consecutive events, sorted by timestamp.
        Empty if fewer than 2 events.
    mean_gap_seconds : float or None
        Arithmetic mean of inter_event_gaps_seconds.  None if no gaps.
    max_gap_seconds : float or None
        Maximum gap.  None if no gaps.
    total_keystrokes : int
        Sum of all KEYSTROKE_COUNT metadata 'count' values.
    total_lines_added : int
        Sum of all FILE_MODIFIED metadata 'lines_added' values.
    total_lines_deleted : int
        Sum of all FILE_MODIFIED metadata 'lines_deleted' values.
    file_types_seen : list[str]
        Unique programming languages from FILE_MODIFIED / FILE_CREATED metadata.
    process_names_seen : list[str]
        Unique process names from PROCESS_START metadata.
    has_session_bookends : bool
        True if both SESSION_START and SESSION_END events are present.
    """

    session_id:                  str            = ""
    event_count:                 int            = 0
    duration_seconds:            Optional[float] = None
    events_per_minute:           Optional[float] = None
    unique_event_types:          int            = 0
    type_diversity_ratio:        float          = 0.0
    inter_event_gaps_seconds:    list           = field(default_factory=list)
    mean_gap_seconds:            Optional[float] = None
    max_gap_seconds:             Optional[float] = None
    total_keystrokes:            int            = 0
    total_lines_added:           int            = 0
    total_lines_deleted:         int            = 0
    file_types_seen:             list           = field(default_factory=list)
    process_names_seen:          list           = field(default_factory=list)
    has_session_bookends:        bool           = False
    feature_schema_version:      str             = FEATURE_SCHEMA_VERSION
    file_event_count:            int             = 0
    window_focus_count:          int             = 0
    process_start_count:         int             = 0
    process_end_count:           int             = 0
    workflow_transition_count:   int             = 0
    interaction_event_count:     int             = 0
    automation_indicator_count:  int             = 0
    median_gap_seconds:          Optional[float] = None
    gap_stddev_seconds:          Optional[float] = None
    data_quality_score:           float           = 0.0
    data_quality_warnings:        list            = field(default_factory=list)
    synthetic:                    bool            = False

    # Total possible event types (used for diversity ratio denominator)
    _TOTAL_EVENT_TYPES: int = field(default=len(EventType), init=False, repr=False, compare=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ISO_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
)


def _parse_ts(ts_str: str) -> Optional[datetime]:
    """Try several ISO-8601 variants.  Return None on failure."""
    for fmt in _ISO_FORMATS:
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    # Python 3.11+ fromisoformat handles all modern ISO 8601
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _safe_mean(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _safe_median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _safe_stddev(values: list[float], mean: Optional[float]) -> Optional[float]:
    if not values or mean is None:
        return None
    return (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract(events: list[PoEEvent]) -> SessionFeatures:
    """
    Extract behavioral features from a list of PoEEvents.

    Parameters
    ----------
    events : list[PoEEvent]
        All events for a single session (order is not assumed; sorted internally).

    Returns
    -------
    SessionFeatures
        All available metrics.  Missing / uncomputable fields are None or 0.
    """
    if not events:
        return SessionFeatures(
            data_quality_score=0.0,
            data_quality_warnings=[
                "No events were collected; classification is inconclusive."
            ],
        )

    # --- Parse timestamps --------------------------------------------------
    timed: list[tuple[datetime, PoEEvent]] = []
    for ev in events:
        dt = _parse_ts(ev.timestamp)
        if dt is not None:
            timed.append((dt, ev))

    timed.sort(key=lambda x: x[0])
    sorted_events = [ev for _, ev in timed]

    # --- Basic fields -------------------------------------------------------
    session_id       = sorted_events[0].session_id if sorted_events else (events[0].session_id if events else "")
    event_count      = len(events)
    type_set         = {ev.event_type for ev in events}
    unique_types     = len(type_set)
    diversity_ratio  = unique_types / len(EventType)

    has_start        = any(ev.event_type == EventType.SESSION_START for ev in events)
    has_end          = any(ev.event_type == EventType.SESSION_END   for ev in events)

    # --- Duration -----------------------------------------------------------
    duration: Optional[float] = None
    if timed:
        # Prefer SESSION_START / SESSION_END events for duration
        start_times = [dt for dt, ev in timed if ev.event_type == EventType.SESSION_START]
        end_times   = [dt for dt, ev in timed if ev.event_type == EventType.SESSION_END]

        if start_times and end_times:
            duration = (max(end_times) - min(start_times)).total_seconds()
        else:
            # Fallback: span of all timestamps
            duration = (timed[-1][0] - timed[0][0]).total_seconds()

    # --- Events per minute -------------------------------------------------
    epm: Optional[float] = None
    if duration is not None and duration > 0:
        epm = event_count / (duration / 60.0)

    # --- Inter-event gaps --------------------------------------------------
    gaps: list[float] = []
    if len(timed) >= 2:
        for i in range(1, len(timed)):
            gap = (timed[i][0] - timed[i - 1][0]).total_seconds()
            if gap >= 0:
                gaps.append(gap)

    # --- Aggregate metadata stats ------------------------------------------
    total_keystrokes  = 0
    total_lines_added = 0
    total_lines_del   = 0
    file_types: set[str] = set()
    procs:      set[str] = set()
    file_event_count = 0
    window_focus_count = 0
    process_start_count = 0
    process_end_count = 0
    interaction_event_count = 0
    automation_indicator_count = 0

    for ev in events:
        et = EventType(ev.event_type)

        if et == EventType.KEYSTROKE_COUNT:
            total_keystrokes += int(ev.metadata.get("count", 0))
            interaction_event_count += 1

        elif et in (EventType.FILE_MODIFIED, EventType.FILE_CREATED):
            file_event_count += 1
            interaction_event_count += 1
            lang = ev.metadata.get("language", "")
            if lang:
                file_types.add(lang)
            if et == EventType.FILE_MODIFIED:
                total_lines_added += int(ev.metadata.get("lines_added",   0))
                total_lines_del   += int(ev.metadata.get("lines_deleted", 0))

        elif et == EventType.PROCESS_START:
            process_start_count += 1
            pname = ev.metadata.get("process_name", "")
            if pname:
                procs.add(pname)
            if pname.lower() in {"bot", "selenium", "playwright", "autohotkey", "robot"}:
                automation_indicator_count += 1
        elif et == EventType.PROCESS_END:
            process_end_count += 1
        elif et == EventType.WINDOW_FOCUS:
            window_focus_count += 1
            interaction_event_count += 1

    mean_gap = _safe_mean(gaps)
    warnings: list[str] = []
    if len(events) < 10:
        warnings.append("Session is too short for reliable behavioral classification.")
    if not has_start or not has_end:
        warnings.append("Session bookends are incomplete; duration may be approximate.")
    if not timed:
        warnings.append("Event timestamps could not be parsed.")
    if any(ev.synthetic for ev in events):
        warnings.append("Synthetic collector data is for testing only and is not real evidence.")
    quality = 1.0
    if len(events) < 10:
        quality -= 0.45
    if not has_start or not has_end:
        quality -= 0.2
    if not timed:
        quality -= 0.25
    if any(ev.synthetic for ev in events):
        quality = 0.0

    workflow_transition_count = sum(
        1 for previous, current in zip(sorted_events, sorted_events[1:])
        if previous.event_type != current.event_type
    )

    return SessionFeatures(
        session_id               = session_id,
        event_count              = event_count,
        duration_seconds         = duration,
        events_per_minute        = epm,
        unique_event_types       = unique_types,
        type_diversity_ratio     = diversity_ratio,
        inter_event_gaps_seconds = gaps,
        mean_gap_seconds         = mean_gap,
        max_gap_seconds          = max(gaps) if gaps else None,
        median_gap_seconds       = _safe_median(gaps),
        gap_stddev_seconds       = _safe_stddev(gaps, mean_gap),
        total_keystrokes         = total_keystrokes,
        total_lines_added        = total_lines_added,
        total_lines_deleted      = total_lines_del,
        file_types_seen          = sorted(file_types),
        process_names_seen       = sorted(procs),
        has_session_bookends     = has_start and has_end,
        file_event_count         = file_event_count,
        window_focus_count       = window_focus_count,
        process_start_count      = process_start_count,
        process_end_count        = process_end_count,
        workflow_transition_count= workflow_transition_count,
        interaction_event_count  = interaction_event_count,
        automation_indicator_count = automation_indicator_count,
        data_quality_score       = round(max(0.0, quality), 3),
        data_quality_warnings    = warnings,
        synthetic                = any(ev.synthetic for ev in events),
    )


def feature_vector(features: SessionFeatures) -> tuple[float, ...]:
    """Return the versioned, deterministic numeric vector used by ML inference."""
    return (
        float(features.event_count),
        float(features.duration_seconds or 0.0),
        float(features.events_per_minute or 0.0),
        float(features.unique_event_types),
        float(features.type_diversity_ratio),
        float(features.mean_gap_seconds or 0.0),
        float(features.median_gap_seconds or 0.0),
        float(features.gap_stddev_seconds or 0.0),
        float(features.total_keystrokes),
        float(features.total_lines_added + features.total_lines_deleted),
        float(features.file_event_count),
        float(features.window_focus_count),
        float(features.process_start_count),
        float(features.process_end_count),
        float(features.workflow_transition_count),
        float(features.interaction_event_count),
        float(features.automation_indicator_count),
        float(features.data_quality_score),
        float(features.has_session_bookends),
    )
