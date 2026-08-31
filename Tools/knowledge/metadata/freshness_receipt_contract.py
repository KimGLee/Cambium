"""Closed machine contract for current freshness scan Receipts.

The freshness engine owns page classification.  ``check_freshness`` owns the
scan boundary and publication sequence.  This module is the one machine owner
of the two Receipt payloads that publication admits to current hot,
historical, and cold catalogs.  It validates those payloads without selecting
a scan scope, reading pages, or creating maintenance work.
"""

import re

import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
from Tools.execution.task_runtime import runtime_paths
from Tools.knowledge.content import maintenance_candidates
from Tools.knowledge.metadata import freshness_engine
from Tools.knowledge.metadata import vocabulary_contract
from Tools.platform.common import primitives
from Tools.platform.repository import path_contract as repository_path_contract


TOOL = "check_freshness"
TOOL_VERSION = "2.1.0"
RECEIPT_TYPE_ID = "freshness-scan-receipt-v1"
CANDIDATE_CHECK = "freshness"
SUMMARY_CHECK = "freshness-check-summary"
SCHEMA_VERSION = 1
CANDIDATE_SET_BASIS = "sorted-candidate-records-v1"

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SCAN_ID_RE = re.compile(r"freshness-scan-sha256:[0-9a-f]{64}\Z")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")

_BASE_FIELDS = frozenset((
    "receipt_id", "receipt_type_id", "check", "target", "result",
    "details", "checked_at", "tool", "tool_version", "invalidated_by",
))
_RUNTIME_IDENTITY_FIELDS = frozenset(kblib.RECEIPT_IDENTITY_FIELDS)
_PROFILE_EVIDENCE_FIELDS = frozenset((
    "selected_profile_manifest", "profile_snapshot_sha256",
    "profile_contract_fingerprint", "profile_load_inputs_sha256",
    "compiled_vocab_sha256",
))
_PROFILE_EVIDENCE_TRIGGER_FIELDS = _PROFILE_EVIDENCE_FIELDS - {
    "selected_profile_manifest"
}
_CANDIDATE_FIELDS = frozenset((
    "freshness_schema_version", "scan_id", "candidate_id",
    "candidate_kind", "reason_codes", "reasons", "as_of", "priority",
    "volatility", "volatility_source", "baseline_field", "baseline",
    "review_by", "overdue_days",
))
_SUMMARY_FIELDS = frozenset((
    "freshness_schema_version", "scan_id", "as_of", "scan_complete",
    "discovered_count", "files_count", "candidate_count",
    "page_candidate_count", "scan_finding_codes", "candidate_ids",
    "candidate_records", "candidate_set_basis", "candidate_set_sha256",
    "classification_counts", "scope", "exclude_components",
    "defaults_source_kind", "defaults_source", "defaults_fingerprint",
    "input_snapshot_sha256",
))
_CANDIDATE_RECORD_FIELDS = frozenset((
    "candidate_id", "object_path", "candidate_kind", "priority",
))
_REASON_FIELDS = frozenset((
    "code", "field", "raw_value", "date_value",
))

_REASON_CODES_BY_KIND = {
    freshness_engine.UNPARSEABLE_FRONTMATTER:
        frozenset(("unparseable_frontmatter",)),
    freshness_engine.INVALID_BASELINE:
        frozenset(("invalid_completed_event_date",
                   "future_completed_event_date")),
    freshness_engine.FUTURE_BASELINE:
        frozenset(("future_completed_event_date",)),
    freshness_engine.MODIFIED_SINCE_REVIEW:
        frozenset(("content_modified_since_review",)),
    freshness_engine.INVALID_VOLATILITY:
        frozenset(("invalid_volatility",)),
    freshness_engine.UNRESOLVED_VOLATILITY:
        frozenset(("unresolved_volatility",)),
    freshness_engine.PENDING_FIRST_VERIFICATION:
        frozenset(("pending_first_verification",)),
    freshness_engine.OVERDUE:
        frozenset(("overdue",)),
}
_REQUIRED_REASON_BY_KIND = {
    kind: next(iter(codes))
    for kind, codes in _REASON_CODES_BY_KIND.items()
    if kind != freshness_engine.INVALID_BASELINE
}
_REQUIRED_REASON_BY_KIND[freshness_engine.INVALID_BASELINE] = \
    "invalid_completed_event_date"


def _fingerprint(value):
    return kblib.sha256_bytes(kblib.canonical_json_bytes(value))


def _date(value):
    return (isinstance(value, str) and _DATE_RE.fullmatch(value) is not None
            and freshness_engine.parse_iso_date(value) is not None)


def _nullable_date(value):
    return value is None or _date(value)


def _nullable_text(value):
    return value is None or isinstance(value, str)


def _closed_fields(record, required, errors):
    allowed = (required | _RUNTIME_IDENTITY_FIELDS |
               _PROFILE_EVIDENCE_TRIGGER_FIELDS)
    missing = sorted(required - set(record))
    extra = sorted(set(record) - allowed)
    if missing or extra:
        errors.append(
            "freshness Receipt fields are not closed: missing=%s extra=%s" %
            (missing, extra))


def _base_errors(record):
    check = record.get("check") if isinstance(record, dict) else None
    checks = ((check,) if check in (CANDIDATE_CHECK, SUMMARY_CHECK) else ())
    errors = receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID, tool=TOOL,
        tool_version=TOOL_VERSION, checks=checks)
    if not isinstance(record, dict):
        return errors
    for field in ("receipt_id", "target", "details"):
        if not primitives.nonempty_string(record.get(field)):
            errors.append("freshness Receipt has invalid %s" % field)
    if not primitives.valid_timestamp(record.get("checked_at")):
        errors.append("freshness Receipt has invalid checked_at")
    for field in _RUNTIME_IDENTITY_FIELDS & set(record):
        if not primitives.nonempty_string(record.get(field)):
            errors.append("freshness Receipt has invalid %s" % field)
    if (record.get("invalidated_by") is not None and
            not primitives.nonempty_string(record.get("invalidated_by"))):
        errors.append("freshness Receipt has invalid invalidated_by")
    if record.get("freshness_schema_version") != SCHEMA_VERSION:
        errors.append("freshness_schema_version must be 1")
    if not isinstance(record.get("scan_id"), str) or \
            _SCAN_ID_RE.fullmatch(record["scan_id"]) is None:
        errors.append("freshness Receipt has invalid scan_id")
    if not _date(record.get("as_of")):
        errors.append("freshness Receipt has invalid as_of")
    return errors


def _profile_evidence_errors(record, *, required):
    errors = []
    present = _PROFILE_EVIDENCE_TRIGGER_FIELDS & set(record)
    if required or present:
        missing = sorted(_PROFILE_EVIDENCE_FIELDS - set(record))
        if missing:
            errors.append(
                "canonical freshness evidence misses Profile binding: %s" %
                ", ".join(missing))
        for field in _PROFILE_EVIDENCE_FIELDS:
            if field in record and not primitives.nonempty_string(
                    record.get(field)):
                errors.append(
                    "canonical freshness evidence has invalid %s" % field)
        for field in _PROFILE_EVIDENCE_TRIGGER_FIELDS:
            if field in record and (not isinstance(record[field], str) or
                                    _SHA256_RE.fullmatch(record[field]) is None):
                errors.append(
                    "canonical freshness evidence has invalid %s" % field)
    return errors


def _reason_errors(record):
    errors = []
    kind = record.get("candidate_kind")
    codes = record.get("reason_codes")
    reasons = record.get("reasons")
    if (not isinstance(codes, list) or not codes or
            any(not isinstance(code, str) or not code for code in codes)):
        return ["freshness candidate reason_codes must be non-empty text"]
    if not isinstance(reasons, list) or len(reasons) != len(codes):
        return ["freshness candidate reasons must match reason_codes"]
    projected_codes = []
    for index, reason in enumerate(reasons):
        label = "freshness candidate reason[%d]" % index
        if not isinstance(reason, dict) or set(reason) != _REASON_FIELDS:
            errors.append("%s fields are not closed" % label)
            continue
        code = reason.get("code")
        projected_codes.append(code)
        if not isinstance(code, str) or not code:
            errors.append("%s code is invalid" % label)
        for field in ("field", "raw_value"):
            if not _nullable_text(reason.get(field)):
                errors.append("%s %s is invalid" % (label, field))
        if not _nullable_date(reason.get("date_value")):
            errors.append("%s date_value is invalid" % label)
    if projected_codes != codes:
        errors.append("freshness candidate reason_codes differ from reasons")
    allowed = _REASON_CODES_BY_KIND.get(kind, frozenset())
    if any(code not in allowed for code in codes):
        errors.append("freshness candidate reason code is not owned by its kind")
    required = _REQUIRED_REASON_BY_KIND.get(kind)
    if required is not None and required not in codes:
        errors.append("freshness candidate omits its required reason code")
    return errors


def _candidate_errors(record):
    errors = _base_errors(record)
    _closed_fields(record, _BASE_FIELDS | _CANDIDATE_FIELDS, errors)
    if record.get("check") != CANDIDATE_CHECK or \
            record.get("result") != "candidate":
        errors.append("freshness candidate must use check=freshness and result=candidate")
    target = record.get("target")
    try:
        repository_path_contract.canonical_repository_relative_path(
            target, "freshness candidate target")
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    else:
        if record.get("candidate_id") != \
                maintenance_candidates.candidate_id_for_path(target):
            errors.append("freshness candidate_id does not bind target")
    kind = record.get("candidate_kind")
    if kind not in freshness_engine.CANDIDATE_KINDS:
        errors.append("freshness candidate_kind is not current")
    errors.extend(_reason_errors(record))
    priority = record.get("priority")
    if priority is not None and not isinstance(priority, str):
        errors.append("freshness candidate priority must be text or null")
    volatility = record.get("volatility")
    if (volatility is not None and
            volatility not in vocabulary_contract.REVIEW_INTERVALS_DAYS):
        errors.append("freshness candidate volatility is invalid")
    source = record.get("volatility_source")
    if source not in (None, "frontmatter", "defaults"):
        errors.append("freshness candidate volatility_source is invalid")
    if not _nullable_text(record.get("baseline_field")):
        errors.append("freshness candidate baseline_field is invalid")
    for field in ("baseline", "review_by"):
        if not _nullable_date(record.get(field)):
            errors.append("freshness candidate %s is invalid" % field)
    overdue_days = record.get("overdue_days")
    if overdue_days is not None and (
            type(overdue_days) is not int or overdue_days < 0):
        errors.append("freshness candidate overdue_days is invalid")
    if kind == freshness_engine.OVERDUE:
        if (volatility is None or source is None or
                record.get("baseline_field") not in
                ("last_verified", "last_reviewed") or
                not _date(record.get("baseline")) or
                not _date(record.get("review_by")) or
                type(overdue_days) is not int):
            errors.append("overdue freshness candidate lacks due-date binding")
    elif kind == freshness_engine.PENDING_FIRST_VERIFICATION:
        if (volatility is None or source is None or
                record.get("baseline_field") != "file-modified" or
                not _date(record.get("baseline")) or
                overdue_days is not None):
            errors.append("pending freshness candidate lacks diagnostic binding")
    elif kind == freshness_engine.MODIFIED_SINCE_REVIEW:
        if (record.get("baseline_field") != "last_content_modified" or
                not _date(record.get("baseline")) or
                any(record.get(field) is not None for field in (
                    "volatility", "volatility_source", "review_by",
                    "overdue_days"))):
            errors.append("modified freshness candidate has invalid binding")
    elif any(record.get(field) is not None for field in (
            "volatility", "volatility_source", "baseline_field", "baseline",
            "review_by", "overdue_days")):
        errors.append("freshness candidate carries fields outside its kind")
    errors.extend(_profile_evidence_errors(record, required=False))
    return errors


def _candidate_record_errors(record, index):
    label = "freshness summary candidate_records[%d]" % index
    errors = []
    if not isinstance(record, dict) or set(record) != _CANDIDATE_RECORD_FIELDS:
        return ["%s fields are not closed" % label]
    path = record.get("object_path")
    try:
        repository_path_contract.canonical_repository_relative_path(
            path, label + ".object_path")
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    else:
        if record.get("candidate_id") != \
                maintenance_candidates.candidate_id_for_path(path):
            errors.append("%s candidate_id does not bind object_path" % label)
    if record.get("candidate_kind") not in freshness_engine.CANDIDATE_KINDS:
        errors.append("%s candidate_kind is not current" % label)
    if record.get("priority") is not None and not isinstance(
            record.get("priority"), str):
        errors.append("%s priority must be text or null" % label)
    return errors


def _summary_errors(record):
    errors = _base_errors(record)
    _closed_fields(record, _BASE_FIELDS | _SUMMARY_FIELDS, errors)
    if record.get("check") != SUMMARY_CHECK:
        errors.append("freshness summary check is invalid")
    if record.get("scan_complete") is not True:
        errors.append("freshness summary must bind a complete scan")
    counts = record.get("classification_counts")
    if (not isinstance(counts, dict) or
            set(counts) != set(freshness_engine.OUTCOME_KINDS) or
            any(type(value) is not int or value < 0
                for value in counts.values())):
        errors.append("freshness summary classification_counts are not closed")
        counts = None
    for field in ("discovered_count", "files_count", "candidate_count",
                  "page_candidate_count"):
        if type(record.get(field)) is not int or record[field] < 0:
            errors.append("freshness summary %s is invalid" % field)
    candidate_records = record.get("candidate_records")
    if not isinstance(candidate_records, list):
        errors.append("freshness summary candidate_records must be a list")
        candidate_records = []
    for index, candidate in enumerate(candidate_records):
        errors.extend(_candidate_record_errors(candidate, index))
    paths = [candidate.get("object_path") for candidate in candidate_records
             if isinstance(candidate, dict)]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        errors.append("freshness summary candidate_records are not ordered and unique")
    candidate_ids = record.get("candidate_ids")
    expected_ids = sorted(
        candidate.get("candidate_id") for candidate in candidate_records
        if isinstance(candidate, dict) and
        isinstance(candidate.get("candidate_id"), str))
    if candidate_ids != expected_ids or len(expected_ids) != len(candidate_records):
        errors.append("freshness summary candidate_ids differ from candidate_records")
    if record.get("candidate_set_basis") != CANDIDATE_SET_BASIS:
        errors.append("freshness summary candidate_set_basis is invalid")
    expected_set_sha = _fingerprint({
        "schema_version": SCHEMA_VERSION,
        "basis": CANDIDATE_SET_BASIS,
        "candidate_records": candidate_records,
    })
    if record.get("candidate_set_sha256") != expected_set_sha:
        errors.append("freshness summary candidate_set_sha256 is invalid")
    findings = record.get("scan_finding_codes")
    if not isinstance(findings, list) or any(
            not isinstance(value, str) for value in findings):
        errors.append("freshness summary scan_finding_codes are invalid")
        findings = []
    if counts is not None:
        discovered = sum(counts.values())
        page_candidates = sum(
            counts[kind] for kind in freshness_engine.CANDIDATE_KINDS)
        expected_findings = ["nothing_checked"] if discovered == 0 else []
        candidate_kind_counts = {
            kind: sum(1 for candidate in candidate_records
                      if isinstance(candidate, dict) and
                      candidate.get("candidate_kind") == kind)
            for kind in freshness_engine.CANDIDATE_KINDS
        }
        if record.get("discovered_count") != discovered:
            errors.append("freshness summary discovered_count disagrees with classifications")
        if record.get("files_count") != discovered - counts[
                freshness_engine.EXCLUDED]:
            errors.append("freshness summary files_count disagrees with classifications")
        if record.get("page_candidate_count") != page_candidates:
            errors.append("freshness summary page_candidate_count disagrees with classifications")
        if any(candidate_kind_counts[kind] != counts[kind]
               for kind in freshness_engine.CANDIDATE_KINDS):
            errors.append("freshness summary candidate records disagree with classifications")
        if findings != expected_findings:
            errors.append("freshness summary scan findings disagree with discovered scope")
        if record.get("candidate_count") != page_candidates + len(findings):
            errors.append("freshness summary candidate_count is invalid")
        expected_result = "candidate" if page_candidates or findings else "pass"
        if record.get("result") != expected_result:
            errors.append("freshness summary result disagrees with candidate closure")
    scope = record.get("scope")
    if scope != ".":
        try:
            repository_path_contract.canonical_repository_relative_path(
                scope, "freshness summary scope")
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
    if record.get("target") != scope:
        errors.append("freshness summary target must equal scope")
    excludes = record.get("exclude_components")
    if (not isinstance(excludes, list) or excludes != sorted(set(excludes)) or
            any(not isinstance(value, str) or not value or "/" in value or
                "\\" in value or value in (".", "..") for value in excludes)):
        errors.append("freshness summary exclude_components are invalid")
    for field in ("defaults_fingerprint", "input_snapshot_sha256",
                  "candidate_set_sha256"):
        if not isinstance(record.get(field), str) or \
                _SHA256_RE.fullmatch(record[field]) is None:
            errors.append("freshness summary %s is invalid" % field)
    kind = record.get("defaults_source_kind")
    source = record.get("defaults_source")
    if kind == "none":
        if source is not None or record.get("defaults_fingerprint") != \
                _fingerprint({"schema_version": 1,
                              "volatility_defaults": None}):
            errors.append("freshness summary none defaults binding is invalid")
    elif kind == "canonical":
        if source != runtime_paths.VOCAB_ARTIFACT_PATH:
            errors.append("freshness summary canonical defaults source is invalid")
        if record.get("compiled_vocab_sha256") != record.get(
                "defaults_fingerprint"):
            errors.append("freshness summary compiled vocabulary binding is invalid")
    elif kind == "standalone":
        if source != "standalone":
            errors.append("freshness summary standalone defaults source is invalid")
    else:
        errors.append("freshness summary defaults_source_kind is invalid")
    errors.extend(_profile_evidence_errors(
        record, required=kind == "canonical"))
    expected_scan_id = "freshness-scan-" + _fingerprint({
        "schema_version": 1,
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "as_of": record.get("as_of"),
        "scope": scope,
        "exclude_components": excludes,
        "defaults_source_kind": kind,
        "defaults_source": source,
        "defaults_fingerprint": record.get("defaults_fingerprint"),
        "input_snapshot_sha256": record.get("input_snapshot_sha256"),
        "candidate_set_sha256": record.get("candidate_set_sha256"),
    })
    if record.get("scan_id") != expected_scan_id:
        errors.append("freshness summary scan_id does not bind its scan inputs")
    return errors


def current_receipt_errors(record, *, root=None):
    """Return all current hard-cut freshness Receipt contract errors."""
    if not isinstance(record, dict):
        return _base_errors(record)
    check = record.get("check")
    if check == CANDIDATE_CHECK:
        return _candidate_errors(record)
    if check == SUMMARY_CHECK:
        return _summary_errors(record)
    errors = _base_errors(record)
    errors.append("freshness Receipt check is not current")
    return errors


__all__ = ("current_receipt_errors",)
