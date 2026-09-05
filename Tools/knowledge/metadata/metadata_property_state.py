#!/usr/bin/env python3
"""Pure owner-state transitions for evidence-backed page properties.

This module does not take locks or write files.  An Integrator supplies an
already-created evidence receipt, receives a proposed complete Coverage
mapping, and commits that mapping together with the page projections through
``project_page_state``'s outer-transaction API.  Keeping receipt validation,
owner-state mutation, and page rendering separate makes the transaction
boundary explicit without creating another Coverage writer.
"""

import copy
import datetime
import re

import Tools.platform.common.kblib as kblib
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.knowledge.metadata.metadata_page_state_contract as metadata_page_state_contract
import Tools.knowledge.metadata.project_page_state as project_page_state
from Tools.platform.common.primitives import nonempty_string


SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
LAST_CONTENT_MODIFIED = "last_content_modified"
LAST_REVIEWED = "last_reviewed"
SEMANTIC_CONTENT_EVENT = "semantic-content-change"
PAGE_REVIEW_CHECK = "page_review_acceptance"
PAGE_WRITER_CAPABILITY = project_page_state.WRITER_CAPABILITY
PROPERTY_ADAPTER = metadata_page_state_contract.PROPERTY_STATE_ADAPTER
PROPERTY_INVALIDATION_RULE = \
    project_page_state.CONTENT_CHANGE_REMOVE_OWNER_RULE
PROPERTY_RECORD_KEYS = \
    metadata_execution_contract.source_adapter_owner_record_keys(
        PROPERTY_ADAPTER)
SEMANTIC_BASELINE_RECORD_KEYS = frozenset((
    "path", "page_sha256", "semantic_content_sha256",
))


def _date(value, label):
    if not isinstance(value, str) or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("%s must be YYYY-MM-DD" % label)
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("%s is not a calendar date" % label) from exc


def receipt_utc_date(receipt):
    """Return the UTC calendar date already frozen by ``make_receipt``."""
    checked_at = receipt.get("checked_at") if isinstance(receipt, dict) else None
    if not isinstance(checked_at, str) or not checked_at.endswith("Z"):
        raise ValueError("evidence receipt checked_at must be canonical UTC")
    try:
        instant = datetime.datetime.strptime(
            checked_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc)
    except ValueError as exc:
        raise ValueError(
            "evidence receipt checked_at must be YYYY-MM-DDTHH:MM:SSZ") from exc
    return instant.date().isoformat()


def _receipt_identity(receipt, *, check=None):
    if not isinstance(receipt, dict):
        raise ValueError("evidence receipt must be a mapping")
    receipt_id = receipt.get("receipt_id")
    if not nonempty_string(receipt_id):
        raise ValueError("evidence receipt has no receipt_id")
    if receipt.get("result") != "pass" or receipt.get("invalidated_by") is not None:
        raise ValueError("evidence receipt must be a current pass")
    if check is not None and receipt.get("check") != check:
        raise ValueError(
            "evidence receipt check=%r, expected %r" %
            (receipt.get("check"), check))
    return receipt_id


def _rules(root):
    contract = metadata_execution_contract.load_metadata_execution_contract(
        root)
    rules = metadata_execution_contract.rules_for_capability(
        contract, project_page_state.WRITER_CAPABILITY)
    return contract, tuple(rules)


def gate_projection_rule(field, allowed_values):
    """Return the fixed Core projection protocol for one Profile enum."""
    return metadata_execution_contract.profile_extension_enum_projection_rule(
        field, allowed_values,
        writer_capability=project_page_state.WRITER_CAPABILITY)


def profile_gate_projection_rules(root, extension_gates,
                                  metadata_contract=None, *,
                                  typed_profile_contract=None):
    """Compose Core page rules with every typed Profile Gate enum.

    All Profile-managed page copies participate in the semantic fingerprint,
    even when a transaction updates only one Gate.  Multiple transitions may
    legitimately grant different completion values for the same owner field;
    their enums are unioned into one deterministic projection rule while each
    transition still validates its own narrower Gate enum at consumption.
    """
    profile_contract = typed_profile_contract
    if (profile_contract is None or
            not getattr(profile_contract, "valid", False)):
        raise ValueError(
            "Profile Gate projection requires one valid typed Profile "
            "contract")
    authorized_gates = tuple(getattr(
        profile_contract, "extension_gates", ()))
    if tuple(extension_gates) != authorized_gates:
        raise ValueError(
            "Profile Gate rules differ from the authorized typed contract")
    contract = metadata_contract
    if not isinstance(contract, metadata_execution_contract.CompiledMetadataExecutionContract):
        raise ValueError("pure Profile projection requires its explicit compiled metadata input")
    return metadata_execution_contract.compose_profile_projection_rules(
        contract, profile_contract)


def authorized_profile_projection_rules(root, profile_view):
    """Return the one metadata contract and rule set for an authorized view.

    Runtime writers receive the already-authorized Profile view from
    ``check_queue``.  Keeping this adapter here means current projection and
    validation compose Core rules with the *same* typed
    ``extension_gates`` contract instead of growing parallel Profile parsers.
    """
    from Tools.governance.profile.profile_admission import contract_from_admitted_view
    contract = contract_from_admitted_view(root, profile_view)
    extension_gates = getattr(contract, "extension_gates", None)
    if extension_gates is None:
        raise ValueError(
            "the authorized Profile has no typed extension-gate contract")
    metadata_contract = profile_view.get("_metadata_execution_contract") \
        if isinstance(profile_view, dict) else None
    if not isinstance(
            metadata_contract,
            metadata_execution_contract.CompiledMetadataExecutionContract):
        raise ValueError(
            "the authorized Profile has no admitted metadata execution "
            "contract")
    if profile_view.get("metadata_execution_contract_fingerprint") != \
            metadata_contract.contract_fingerprint:
        raise ValueError(
            "the authorized Profile metadata contract fingerprint differs "
            "from its admitted object")
    return metadata_contract, profile_gate_projection_rules(
        root, extension_gates, metadata_contract=metadata_contract,
        typed_profile_contract=contract)


def _page_rows(coverage):
    if not isinstance(coverage, dict):
        raise ValueError("Coverage must be a mapping")
    pages = coverage.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Coverage pages must be an explicit list")
    indexed = {}
    for index, row in enumerate(pages):
        if not isinstance(row, dict):
            raise ValueError("Coverage pages[%d] must be a mapping" % index)
        path = row.get("path")
        if not nonempty_string(path):
            raise ValueError("Coverage pages[%d].path must be non-empty" % index)
        if path in indexed:
            raise ValueError("Coverage repeats page path %s" % path)
        indexed[path] = row
    return indexed


def _property_state(row, path):
    state = row.get("property_state")
    if state is None:
        state = {}
        row["property_state"] = state
    if not isinstance(state, dict):
        raise ValueError("Coverage property_state for %s must be a mapping" % path)
    return state


def _record(value, receipt_id, fingerprint):
    if not nonempty_string(receipt_id):
        raise ValueError("property evidence receipt ID must be non-empty")
    if not isinstance(fingerprint, str) or SHA256_RE.fullmatch(fingerprint) is None:
        raise ValueError("property content fingerprint must be canonical sha256")
    return {
        "value": value,
        "evidence_receipt": receipt_id,
        "content_fingerprint": fingerprint,
    }


def _validated_existing_record(state, field, path):
    record = state.get(field)
    if record is None:
        return None
    if not isinstance(record, dict) or set(record) != PROPERTY_RECORD_KEYS:
        raise ValueError(
            "Coverage property_state.%s for %s is not a closed current record" %
            (field, path))
    value = record.get("value")
    if value is not None:
        _date(value, "Coverage property_state.%s.value" % field)
    if not nonempty_string(record.get("evidence_receipt")):
        raise ValueError(
            "Coverage property_state.%s for %s has no evidence receipt" %
            (field, path))
    fingerprint = record.get("content_fingerprint")
    if not isinstance(fingerprint, str) or SHA256_RE.fullmatch(fingerprint) is None:
        raise ValueError(
            "Coverage property_state.%s for %s has invalid content fingerprint" %
            (field, path))
    return record


def semantic_page_snapshot(root, path, rules=None):
    """Return one exact page snapshot and its projection-neutral fingerprint."""
    active_rules = tuple(rules) if rules is not None else _rules(root)[1]
    snapshot = kblib.repository_target_snapshot(
        root, path, suffixes=(".md", ".MD"), singly_linked=True)
    if not snapshot.exists:
        raise ValueError("metadata transition target is not materialized: %s" % path)
    text = snapshot.read_text()
    fingerprint = project_page_state.semantic_content_fingerprint(
        path, text, active_rules)
    return snapshot, fingerprint


def semantic_baseline_records(root, paths, *, rules):
    """Freeze one batch manifest's raw and projection-neutral page identity.

    This is the content-change *before* image.  It is captured when a batch
    opens, before a worker may edit its manifest, and later consumed by the
    serial Integrator.  A first observation at apply time is not a change
    event: without this earlier binding the system cannot distinguish a
    substantive edit from a projector-only rewrite or an unchanged page.
    """
    selected = list(paths)
    if (selected != sorted(selected) or len(selected) != len(set(selected)) or
            not all(nonempty_string(path) for path in selected)):
        raise ValueError(
            "semantic baseline paths must be sorted, unique, non-empty "
            "repository-relative strings")
    records = []
    for path in selected:
        snapshot, fingerprint = semantic_page_snapshot(
            root, path, rules=rules)
        records.append({
            "path": path,
            "page_sha256": snapshot.sha256,
            "semantic_content_sha256": fingerprint,
        })
    return tuple(records)


def validate_semantic_baseline_records(records, *, expected_paths=None):
    """Return the canonical path->semantic mapping for one frozen manifest."""
    if not isinstance(records, (list, tuple)):
        raise ValueError("semantic baseline records must be an explicit list")
    paths = []
    result = {}
    for index, record in enumerate(records):
        label = "semantic baseline records[%d]" % index
        if not isinstance(record, dict) or \
                set(record) != SEMANTIC_BASELINE_RECORD_KEYS:
            raise ValueError("%s is not the closed baseline shape" % label)
        path = record.get("path")
        if not nonempty_string(path):
            raise ValueError("%s has no path" % label)
        for field in ("page_sha256", "semantic_content_sha256"):
            value = record.get(field)
            if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
                raise ValueError("%s %s is not canonical sha256" %
                                 (label, field))
        if path in result:
            raise ValueError("semantic baseline repeats path %s" % path)
        paths.append(path)
        result[path] = record["semantic_content_sha256"]
    if paths != sorted(paths):
        raise ValueError("semantic baseline records must be path-sorted")
    if expected_paths is not None:
        expected = list(expected_paths)
        if expected != sorted(expected) or len(expected) != len(set(expected)):
            raise ValueError("expected semantic baseline paths are not canonical")
        if paths != expected:
            raise ValueError(
                "semantic baseline path set does not equal the batch manifest")
    return result


def semantic_baseline_set_sha256(records):
    """Hash the closed, already-canonical baseline record set."""
    validate_semantic_baseline_records(records)
    return kblib.sha256_bytes(kblib.canonical_json_bytes(list(records)))


def validate_owner_property_records(root, row, path, *, rules,
                                    page_text=None,
                                    accepted_stale_fingerprint=None):
    """Validate one current ``property_state`` against one compiled rule set.

    This is deliberately narrower than a runtime validator: it reads no
    receipt catalog and assigns no producer meaning to an evidence ID.  It
    only proves that the owner mapping is closed, every field/value/tombstone
    is authorized by the supplied projection rules, and every record binds
    one exact projection-neutral semantic fingerprint.  By default that is
    the current page.  A transaction planner may instead supply its already
    staged exact ``page_text`` after-image; the repository target is still
    snapshotted for path safety, while proposed-state validation and the
    eventual publisher consume the same bytes.  Callers may therefore compose
    Core rules with the *same* authorized Profile contract before resolving
    evidence without growing a second value-shape parser.

    Planning-only rows are skipped before this function is called.  A current
    runtime row must carry ``property_state`` as a mapping; an empty mapping
    is valid and needs no page read.
    """
    if not isinstance(row, dict):
        raise ValueError("Coverage page row for %s must be a mapping" % path)
    if "property_state" not in row:
        raise ValueError(
            "current Coverage row for %s has no property_state" % path)
    state = row.get("property_state")
    if not isinstance(state, dict):
        raise ValueError(
            "Coverage property_state for %s must be a mapping" % path)
    active_rules = tuple(rules)
    property_rules = {
        rule.get("field"): rule for rule in active_rules
        if isinstance(rule, dict) and
        rule.get("source_adapter") in
        metadata_page_state_contract.PROPERTY_VALUE_ADAPTERS
    }
    extra = sorted(set(state) - set(property_rules))
    if extra:
        raise ValueError(
            "Coverage property_state for %s has undeclared field(s): %s" %
            (path, ", ".join(extra)))
    if not state:
        return None, None, {}
    if page_text is not None and not isinstance(page_text, str):
        raise TypeError("projected page after-image must be text")
    snapshot = kblib.repository_target_snapshot(
        root, path, suffixes=(".md", ".MD"), singly_linked=True)
    if not snapshot.exists:
        raise ValueError(
            "metadata transition target is not materialized: %s" % path)
    exact_text = snapshot.read_text() if page_text is None else page_text
    fingerprint = project_page_state.semantic_content_fingerprint(
        path, exact_text, active_rules)
    if accepted_stale_fingerprint is not None and (
            not isinstance(accepted_stale_fingerprint, str) or
            SHA256_RE.fullmatch(accepted_stale_fingerprint) is None):
        raise ValueError(
            "accepted stale fingerprint must be canonical sha256")
    for field in sorted(state):
        # The page-state contract is the single value-shape, closed-record,
        # tombstone, and semantic-binding implementation.  This wrapper
        # delegates to it instead of reimplementing those rules in each
        # runtime consumer.
        record = state.get(field)
        record_fingerprint = (record.get("content_fingerprint")
                              if isinstance(record, dict) else None)
        expected_fingerprint = (
            accepted_stale_fingerprint
            if (accepted_stale_fingerprint is not None and
                record_fingerprint == accepted_stale_fingerprint)
            else fingerprint)
        metadata_page_state_contract.owner_value(
            row, property_rules[field], path, expected_fingerprint, state)
    return snapshot, fingerprint, copy.deepcopy(state)



def apply_content_change(coverage, root, paths, receipt, *,
                         before_semantic_fingerprints, rules=None):
    """Project semantic-content events into owner state.

    A path changes only when its current semantic fingerprint differs from the
    exact manifest baseline frozen when the batch opened.  Apply-time first
    observation is deliberately forbidden: it cannot prove that any content
    changed and would let projector-only rewrites fabricate a modification
    date.
    """
    receipt_id = _receipt_identity(receipt, check="delta_apply")
    occurred_on = receipt_utc_date(receipt)
    active_rules = tuple(rules) if rules is not None else _rules(root)[1]
    property_rules = {
        rule.get("field"): rule for rule in active_rules
        if isinstance(rule, dict) and
        rule.get("source_adapter") in
        metadata_page_state_contract.PROPERTY_VALUE_ADAPTERS
    }
    proposed = copy.deepcopy(coverage)
    rows = _page_rows(proposed)
    selected = sorted(set(paths))
    if any(not nonempty_string(path) for path in selected):
        raise ValueError("content-change paths must be non-empty strings")
    if (not isinstance(before_semantic_fingerprints, dict) or
            sorted(before_semantic_fingerprints) != selected or
            any(not isinstance(value, str) or
                SHA256_RE.fullmatch(value) is None
                for value in before_semantic_fingerprints.values())):
        raise ValueError(
            "content-change before fingerprints must exactly bind the "
            "manifest path set")
    events = []
    changed = []
    for path in selected:
        row = rows.get(path)
        if row is None:
            raise ValueError("content-change page is absent from Coverage: %s" % path)
        _snapshot, current = semantic_page_snapshot(
            root, path, rules=active_rules)
        # Read existing owner state without materialising runtime state.  A
        # projection-only rewrite is not a semantic event and therefore must
        # not add an empty ``property_state`` mapping.
        state = row.get("property_state")
        if state is None:
            state = {}
        elif not isinstance(state, dict):
            raise ValueError(
                "Coverage property_state for %s must be a mapping" % path)
        before = before_semantic_fingerprints[path]
        stale_owner_fields = sorted(
            field for field, record in state.items()
            if (isinstance(record, dict) and
                record.get("content_fingerprint") != before))
        if stale_owner_fields:
            raise ValueError(
                "content-change page %s owner evidence for %s does not "
                "match the batch-opening semantic baseline" %
                (path, ", ".join(stale_owner_fields)))
        if before == current:
            continue
        state = _property_state(row, path)
        prior_modified = _validated_existing_record(
            state, LAST_CONTENT_MODIFIED, path)
        if (prior_modified is not None and
                prior_modified.get("value") is not None and
                _date(prior_modified["value"], "last_content_modified") >
                _date(occurred_on, "content-change date")):
            raise ValueError(
                "content-change event for %s predates current owner state" % path)
        state[LAST_CONTENT_MODIFIED] = _record(
            occurred_on, receipt_id, current)
        prior_review = _validated_existing_record(
            state, LAST_REVIEWED, path)
        review_invalidated = False
        invalidated_fields = []
        invalidated_records = []
        if (prior_review is not None and
                prior_review.get("content_fingerprint") != current):
            state[LAST_REVIEWED] = _record(None, receipt_id, current)
            review_invalidated = True
        if review_invalidated:
            invalidated_fields.append(LAST_REVIEWED)
            invalidated_records.append({
                "field": LAST_REVIEWED,
                "action": "tombstone-current-owner",
                "before_owner_record": copy.deepcopy(prior_review),
            })
        for field, rule in sorted(property_rules.items()):
            if field in (LAST_CONTENT_MODIFIED, LAST_REVIEWED):
                continue
            existing = state.get(field)
            if existing is None:
                continue
            if not isinstance(existing, dict):
                raise ValueError(
                    "Coverage property_state.%s for %s must be a mapping" %
                    (field, path))
            existing_fingerprint = existing.get("content_fingerprint")
            metadata_page_state_contract.owner_value(
                row, rule, path, existing_fingerprint, state)
            if existing_fingerprint == current:
                continue
            if rule.get("invalidation_rule") != \
                    PROPERTY_INVALIDATION_RULE:
                raise ValueError(
                    "Coverage property_state.%s for %s is stale but its "
                    "compiled rule does not authorize semantic-content "
                    "owner removal" % (field, path))
            del state[field]
            invalidated_fields.append(field)
            invalidated_records.append({
                "field": field,
                "action": "remove-owner-and-page-copy",
                "before_owner_record": copy.deepcopy(existing),
            })
        events.append({
            "event": SEMANTIC_CONTENT_EVENT,
            "path": path,
            "accepted_on": occurred_on,
            "before_semantic_content_sha256": before,
            "after_semantic_content_sha256": current,
            "last_reviewed_invalidated": review_invalidated,
            "invalidated_property_fields": sorted(invalidated_fields),
            "invalidated_property_records": sorted(
                invalidated_records, key=lambda record: record["field"]),
            "invalidated_property_receipt_ids": sorted({
                record["before_owner_record"]["evidence_receipt"]
                for record in invalidated_records
                if isinstance(record.get("before_owner_record"), dict) and
                nonempty_string(record["before_owner_record"].get(
                    "evidence_receipt"))
            }),
        })
        changed.append(path)
    return proposed, tuple(changed), tuple(events)


def apply_review_acceptance(coverage, root, receipts, *, rules=None,
                            metadata_contract_fingerprint=None):
    """Consume exact per-page review receipts into proposed owner state."""
    active_rules = tuple(rules) if rules is not None else _rules(root)[1]
    proposed = copy.deepcopy(coverage)
    rows = _page_rows(proposed)
    changed = []
    seen = set()
    for receipt in receipts:
        receipt_id = _receipt_identity(receipt, check=PAGE_REVIEW_CHECK)
        path = receipt.get("target")
        if not nonempty_string(path) or path in seen:
            raise ValueError("page-review receipts must target unique page paths")
        seen.add(path)
        row = rows.get(path)
        if row is None:
            raise ValueError("reviewed page is absent from Coverage: %s" % path)
        reviewed_on = receipt.get("reviewed_on")
        if reviewed_on != receipt_utc_date(receipt):
            raise ValueError(
                "page-review %s reviewed_on does not equal checked_at UTC date" %
                receipt_id)
        _date(reviewed_on, "page-review reviewed_on")
        _snapshot, current = semantic_page_snapshot(
            root, path, rules=active_rules)
        if receipt.get("semantic_content_sha256") != current:
            raise ValueError(
                "page-review %s does not bind current semantic content" %
                receipt_id)
        if (metadata_contract_fingerprint is not None and
                receipt.get("metadata_execution_contract_fingerprint") !=
                metadata_contract_fingerprint):
            raise ValueError(
                "page-review %s metadata contract binding is stale" % receipt_id)
        state = _property_state(row, path)
        gate_receipts = row.get("gate_receipts")
        if (not isinstance(gate_receipts, list) or
                not all(nonempty_string(value) for value in gate_receipts) or
                len(gate_receipts) != len(set(gate_receipts))):
            raise ValueError(
                "reviewed page %s must carry a unique current gate_receipts "
                "list" % path)
        modified = _validated_existing_record(
            state, LAST_CONTENT_MODIFIED, path)
        if (modified is not None and modified.get("value") is not None and
                _date(reviewed_on, "page-review reviewed_on") <
                _date(modified["value"], "last_content_modified")):
            raise ValueError(
                "page-review %s predates current content change" % receipt_id)
        if receipt_id not in gate_receipts:
            gate_receipts.append(receipt_id)
        row["authoring_status"] = "reviewed"
        state[LAST_REVIEWED] = _record(reviewed_on, receipt_id, current)
        changed.append(path)
    return proposed, tuple(sorted(changed))


def apply_gate_transition(coverage, page_path, field, value, receipt_id,
                          semantic_fingerprint, allowed_values):
    """Apply one already-authorized Profile Gate value to Coverage state."""
    if not nonempty_string(field):
        raise ValueError("Gate field must be a non-empty identifier")
    allowed = tuple(allowed_values)
    if value not in allowed:
        raise ValueError(
            "Gate value %r is not one of %r" % (value, allowed))
    proposed = copy.deepcopy(coverage)
    row = _page_rows(proposed).get(page_path)
    if row is None:
        raise ValueError("Gate target is absent from Coverage: %s" % page_path)
    state = _property_state(row, page_path)
    existing = state.get(field)
    if existing is not None:
        if (not isinstance(existing, dict) or
                set(existing) != PROPERTY_RECORD_KEYS):
            raise ValueError(
                "Coverage property_state.%s for %s is not a closed current "
                "record" % (field, page_path))
        if existing.get("value") not in allowed:
            raise ValueError(
                "Coverage property_state.%s for %s has an undeclared enum "
                "value" % (field, page_path))
        if not nonempty_string(existing.get("evidence_receipt")):
            raise ValueError(
                "Coverage property_state.%s for %s has no evidence receipt" %
                (field, page_path))
        existing_fingerprint = existing.get("content_fingerprint")
        if (not isinstance(existing_fingerprint, str) or
                SHA256_RE.fullmatch(existing_fingerprint) is None):
            raise ValueError(
                "Coverage property_state.%s for %s has an invalid content "
                "fingerprint" % (field, page_path))
    state[field] = _record(value, receipt_id, semantic_fingerprint)
    return proposed


def build_projection_plan(root, coverage, paths, *, rules=None,
                          authorized_owner_removals=None):
    """Build page after-images from one proposed owner-state mapping."""
    return project_page_state.build_projection_plan(
        root, selected_pages=sorted(set(paths)), ledger_override=coverage,
        rules=rules,
        authorized_owner_removals=authorized_owner_removals)
