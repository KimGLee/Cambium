#!/usr/bin/env python3
"""Pure, closed-world freshness classification.

This module owns no filesystem traversal, Profile admission, CLI, receipt
publication, or human rendering.  Callers provide immutable page snapshots and
one already-admitted volatility-default mapping.  Every discovered page then
receives exactly one outcome; an active in-scope page can never disappear into
an implicit ``continue`` that is later mistaken for evidence of freshness.
"""

from dataclasses import dataclass
import datetime
import re
from typing import Any, Mapping, Optional, Tuple

import vocabulary_contract


# Compatibility names are immutable aliases of the K08-owned projections.
# Keeping identity here preserves the pure classifier API without creating a
# second semantic copy inside the engine.
INTERVAL_DAYS = vocabulary_contract.REVIEW_INTERVALS_DAYS
PRIORITY_ORDER = vocabulary_contract.PRIORITY_ORDER

EXCLUDED = "excluded"
INACTIVE = "inactive"
UNPARSEABLE_FRONTMATTER = "unparseable_frontmatter"
INVALID_BASELINE = "invalid_baseline"
FUTURE_BASELINE = "future_baseline"
MODIFIED_SINCE_REVIEW = "modified_since_review"
INVALID_VOLATILITY = "invalid_volatility"
UNRESOLVED_VOLATILITY = "unresolved_volatility"
STABLE = "stable"
PENDING_FIRST_VERIFICATION = "pending_first_verification"
OVERDUE = "overdue"
FRESH = "fresh"

OUTCOME_KINDS = (
    EXCLUDED,
    INACTIVE,
    UNPARSEABLE_FRONTMATTER,
    INVALID_BASELINE,
    FUTURE_BASELINE,
    MODIFIED_SINCE_REVIEW,
    INVALID_VOLATILITY,
    UNRESOLVED_VOLATILITY,
    STABLE,
    PENDING_FIRST_VERIFICATION,
    OVERDUE,
    FRESH,
)

CANDIDATE_KINDS = frozenset((
    UNPARSEABLE_FRONTMATTER,
    INVALID_BASELINE,
    FUTURE_BASELINE,
    MODIFIED_SINCE_REVIEW,
    INVALID_VOLATILITY,
    UNRESOLVED_VOLATILITY,
    PENDING_FIRST_VERIFICATION,
    OVERDUE,
))

ABSENT = "absent"
VALID = "valid"
INVALID = "invalid"
FUTURE = "future"

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_EVENT_FIELDS = (
    "last_content_modified", "last_verified", "last_reviewed",
)
_CANDIDATE_CATEGORY_ORDER = {
    OVERDUE: 0,
    FUTURE_BASELINE: 1,
    INVALID_BASELINE: 2,
    MODIFIED_SINCE_REVIEW: 3,
    PENDING_FIRST_VERIFICATION: 4,
    INVALID_VOLATILITY: 5,
    UNRESOLVED_VOLATILITY: 6,
    UNPARSEABLE_FRONTMATTER: 7,
}


def parse_iso_date(value):
    """Return one strict ``YYYY-MM-DD`` date, or ``None``.

    The frontmatter contract admits dates, not timestamps or date prefixes.
    Strict parsing also keeps an explicitly malformed event distinct from an
    absent event, which is required before baseline fallback is safe.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not _DATE_RE.fullmatch(value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def _is_absent(value):
    return value is None or (isinstance(value, str) and not value.strip())


@dataclass(frozen=True)
class EventDate:
    field: str
    state: str
    raw: Any = None
    value: Optional[datetime.date] = None

    def as_reason(self):
        if self.state == INVALID:
            code = "invalid_completed_event_date"
        elif self.state == FUTURE:
            code = "future_completed_event_date"
        else:
            raise ValueError("only invalid/future events are candidate reasons")
        return FreshnessReason(
            code=code,
            field=self.field,
            raw_value=None if self.raw is None else str(self.raw),
            date_value=self.value,
        )


@dataclass(frozen=True)
class FreshnessReason:
    code: str
    field: Optional[str] = None
    raw_value: Optional[str] = None
    date_value: Optional[datetime.date] = None

    def as_dict(self):
        return {
            "code": self.code,
            "field": self.field,
            "raw_value": self.raw_value,
            "date_value": (
                self.date_value.isoformat()
                if self.date_value is not None else None
            ),
        }


@dataclass(frozen=True)
class PageSnapshot:
    path: str
    frontmatter: Optional[Mapping[str, Any]]
    modified_on: datetime.date
    frontmatter_error: bool = False
    excluded: bool = False


@dataclass(frozen=True)
class FreshnessPolicy:
    as_of: datetime.date
    volatility_defaults: Optional[Mapping[str, str]] = None


@dataclass(frozen=True)
class PageOutcome:
    path: str
    kind: str
    priority: str = ""
    volatility: Optional[str] = None
    volatility_source: Optional[str] = None
    baseline_field: Optional[str] = None
    baseline: Optional[datetime.date] = None
    review_by: Optional[datetime.date] = None
    overdue_days: Optional[int] = None
    reasons: Tuple[FreshnessReason, ...] = ()

    @property
    def is_candidate(self):
        return self.kind in CANDIDATE_KINDS

    @property
    def priority_rank(self):
        return PRIORITY_ORDER.get(self.priority, len(PRIORITY_ORDER))


@dataclass(frozen=True)
class FreshnessRun:
    as_of: datetime.date
    outcomes: Tuple[PageOutcome, ...]
    candidates: Tuple[PageOutcome, ...]

    @property
    def counts(self):
        counts = {kind: 0 for kind in OUTCOME_KINDS}
        for outcome in self.outcomes:
            counts[outcome.kind] += 1
        return counts

    @property
    def discovered_count(self):
        return len(self.outcomes)

    @property
    def files_count(self):
        return sum(1 for item in self.outcomes if item.kind != EXCLUDED)

    @property
    def candidate_count(self):
        return self.page_candidate_count + len(self.scan_finding_codes)

    @property
    def page_candidate_count(self):
        return len(self.candidates)

    @property
    def scan_finding_codes(self):
        return ("nothing_checked",) if self.nothing_checked else ()

    @property
    def nothing_checked(self):
        return not self.outcomes

    @property
    def complete(self):
        return (
            sum(self.counts.values()) == self.discovered_count and
            all(item.kind in OUTCOME_KINDS for item in self.outcomes)
        )

    @property
    def result(self):
        # Positive freshness evidence is a closed-world statement: the run
        # must be complete as well as candidate-free.  ``evaluate_freshness``
        # always returns a complete run, but keeping the rule here prevents a
        # future caller from turning a partial typed result into a pass.
        return "pass" if self.complete and not self.candidate_count else "candidate"


def _event_date(frontmatter, field, as_of):
    raw = frontmatter.get(field)
    if _is_absent(raw):
        return EventDate(field=field, state=ABSENT, raw=raw)
    value = parse_iso_date(raw)
    if value is None:
        return EventDate(field=field, state=INVALID, raw=raw)
    if value > as_of:
        return EventDate(field=field, state=FUTURE, raw=raw, value=value)
    return EventDate(field=field, state=VALID, raw=raw, value=value)


def _base_outcome(snapshot, kind, *, frontmatter=None, reasons=(),
                  volatility=None, volatility_source=None,
                  baseline_field=None, baseline=None, review_by=None,
                  overdue_days=None):
    frontmatter = frontmatter or {}
    return PageOutcome(
        path=snapshot.path,
        kind=kind,
        priority=str(frontmatter.get("priority") or ""),
        volatility=volatility,
        volatility_source=volatility_source,
        baseline_field=baseline_field,
        baseline=baseline,
        review_by=review_by,
        overdue_days=overdue_days,
        reasons=tuple(reasons),
    )


def classify_page(snapshot, policy):
    """Classify one snapshot into exactly one closed-world outcome."""
    if snapshot.excluded:
        return _base_outcome(snapshot, EXCLUDED)

    if snapshot.frontmatter_error or snapshot.frontmatter is None:
        return _base_outcome(
            snapshot,
            UNPARSEABLE_FRONTMATTER,
            reasons=(FreshnessReason(code="unparseable_frontmatter"),),
        )

    frontmatter = snapshot.frontmatter
    lifecycle = str(frontmatter.get("lifecycle") or "active")
    if lifecycle in ("retired", "merged"):
        return _base_outcome(snapshot, INACTIVE, frontmatter=frontmatter)

    # Validate every explicit completed-event field before selecting a
    # baseline or deciding whether volatility makes a due date applicable.
    # Otherwise an unselected field, stable policy, or unresolved volatility
    # can hide temporally impossible evidence.
    events = tuple(
        _event_date(frontmatter, field, policy.as_of)
        for field in _EVENT_FIELDS
    )
    invalid_events = tuple(event for event in events
                           if event.state == INVALID)
    future_events = tuple(event for event in events
                          if event.state == FUTURE)
    temporal_reasons = tuple(
        event.as_reason() for event in invalid_events + future_events
    )
    if invalid_events:
        return _base_outcome(
            snapshot, INVALID_BASELINE, frontmatter=frontmatter,
            reasons=temporal_reasons)
    if future_events:
        return _base_outcome(
            snapshot, FUTURE_BASELINE, frontmatter=frontmatter,
            reasons=temporal_reasons)

    last_modified, last_verified, last_reviewed = events
    if (last_modified.state == VALID and
            (last_reviewed.state == ABSENT or
             last_reviewed.value < last_modified.value)):
        return _base_outcome(
            snapshot, MODIFIED_SINCE_REVIEW, frontmatter=frontmatter,
            baseline_field="last_content_modified",
            baseline=last_modified.value,
            reasons=(FreshnessReason(
                code="content_modified_since_review",
                field="last_content_modified",
                date_value=last_modified.value,
            ),),
        )

    raw_volatility = frontmatter.get("volatility")
    volatility = None
    volatility_source = None
    if not _is_absent(raw_volatility):
        if (not isinstance(raw_volatility, str) or
                raw_volatility not in INTERVAL_DAYS):
            return _base_outcome(
                snapshot, INVALID_VOLATILITY, frontmatter=frontmatter,
                reasons=(FreshnessReason(
                    code="invalid_volatility",
                    field="volatility",
                    raw_value=str(raw_volatility),
                ),),
            )
        volatility = raw_volatility
        volatility_source = "frontmatter"
    elif policy.volatility_defaults is not None:
        domain = str(frontmatter.get("domain") or "")
        volatility = policy.volatility_defaults.get(domain)
        if volatility in INTERVAL_DAYS:
            volatility_source = "defaults"

    if volatility not in INTERVAL_DAYS:
        return _base_outcome(
            snapshot, UNRESOLVED_VOLATILITY, frontmatter=frontmatter,
            reasons=(FreshnessReason(
                code="unresolved_volatility",
                field="volatility",
            ),),
        )

    baseline_event = (
        last_verified if last_verified.state == VALID else last_reviewed
    )
    interval = INTERVAL_DAYS[volatility]
    if baseline_event.state == ABSENT:
        # ``stable`` removes the recurring deadline only.  It cannot turn the
        # absence of every completed verification/review event into positive
        # freshness evidence.  The filesystem date remains diagnostic input,
        # not a synthetic completed event.
        try:
            review_by = (
                snapshot.modified_on + datetime.timedelta(days=interval)
                if interval is not None else None
            )
        except OverflowError:
            # A valid date near datetime.date.max may have a conceptual due
            # date outside Python's representable calendar.  The candidate
            # remains explicit; ``None`` means unrepresentable/no recurring
            # deadline rather than absent classification.
            review_by = None
        return _base_outcome(
            snapshot, PENDING_FIRST_VERIFICATION,
            frontmatter=frontmatter,
            volatility=volatility,
            volatility_source=volatility_source,
            baseline_field="file-modified",
            baseline=snapshot.modified_on,
            review_by=review_by,
            reasons=(FreshnessReason(code="pending_first_verification"),),
        )

    if interval is None:
        return _base_outcome(
            snapshot, STABLE, frontmatter=frontmatter,
            volatility=volatility, volatility_source=volatility_source,
            baseline_field=baseline_event.field,
            baseline=baseline_event.value)

    baseline = baseline_event.value
    # Compare elapsed days first.  Adding an interval to a valid date such as
    # 9999-12-31 can overflow even though the page is plainly not overdue.
    # When the due date lies beyond the representable calendar, keep it typed
    # as ``None`` instead of crashing or inventing a truncated date.
    elapsed_days = (policy.as_of - baseline).days
    if elapsed_days >= interval:
        review_by = baseline + datetime.timedelta(days=interval)
        return _base_outcome(
            snapshot, OVERDUE, frontmatter=frontmatter,
            volatility=volatility, volatility_source=volatility_source,
            baseline_field=baseline_event.field, baseline=baseline,
            review_by=review_by,
            overdue_days=(policy.as_of - review_by).days,
            reasons=(FreshnessReason(code="overdue"),),
        )
    try:
        review_by = baseline + datetime.timedelta(days=interval)
    except OverflowError:
        review_by = None
    return _base_outcome(
        snapshot, FRESH, frontmatter=frontmatter,
        volatility=volatility, volatility_source=volatility_source,
        baseline_field=baseline_event.field, baseline=baseline,
        review_by=review_by)


def _candidate_sort_key(outcome):
    category_rank = _CANDIDATE_CATEGORY_ORDER[outcome.kind]
    severity_rank = (
        -outcome.overdue_days
        if outcome.kind == OVERDUE and outcome.overdue_days is not None
        else 0
    )
    return (outcome.priority_rank, category_rank, severity_rank, outcome.path)


def evaluate_freshness(snapshots, policy):
    """Evaluate snapshots deterministically and return a typed run result."""
    ordered = sorted(tuple(snapshots), key=lambda item: item.path)
    outcomes = tuple(classify_page(item, policy) for item in ordered)
    candidates = tuple(sorted(
        (item for item in outcomes if item.is_candidate),
        key=_candidate_sort_key,
    ))
    return FreshnessRun(
        as_of=policy.as_of,
        outcomes=outcomes,
        candidates=candidates,
    )
