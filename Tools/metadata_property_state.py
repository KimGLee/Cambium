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

import kblib
import metadata_execution_contract
import project_page_state


SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
PROPERTY_RECORD_KEYS = frozenset((
    "value", "evidence_receipt", "content_fingerprint",
))
LAST_CONTENT_MODIFIED = "last_content_modified"
LAST_REVIEWED = "last_reviewed"
SEMANTIC_CONTENT_EVENT = "semantic-content-change"
PAGE_REVIEW_CHECK = "page_review_acceptance"
PAGE_WRITER_CAPABILITY = "project-page-state-v2"
PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION = \
    "profile-extension-enum-owner-projection-v1"
PROPERTY_ADAPTER = "coverage-property-state-v1"
PROPERTY_RECONCILE_POLICY = "upsert-exact-or-remove-v1"
PROPERTY_INVALIDATION_RULE = \
    "remove-owner-and-page-copy-on-semantic-content-change-v1"
LEGACY_PROPERTY_STATE = "legacy_property_state"
LEGACY_PROPERTY_STATUS = "legacy-unverified"
LEGACY_PROPERTY_RECORD_KEYS = frozenset(("status", "value"))
LEGACY_MIGRATION_RECORD_KEYS = frozenset((
    "path", "before_page_sha256", "after_page_sha256",
    "legacy_property_state",
))
SEMANTIC_BASELINE_RECORD_KEYS = frozenset((
    "path", "page_sha256", "semantic_content_sha256",
))


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


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
    if not _nonempty(receipt_id):
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
        field, allowed_values)


def profile_gate_projection_rules(root, extension_gates,
                                  metadata_contract=None, *,
                                  authorized_profile_contract=None):
    """Compose Core page rules with every typed Profile Gate enum.

    All Profile-managed page copies participate in the semantic fingerprint,
    even when a transaction updates only one Gate.  Multiple transitions may
    legitimately grant different completion values for the same owner field;
    their enums are unioned into one deterministic projection rule while each
    transition still validates its own narrower Gate enum at consumption.
    """
    profile_contract = authorized_profile_contract
    if (profile_contract is None or
            not getattr(profile_contract, "authorized", False)):
        raise ValueError(
            "Profile Gate projection requires one authorized typed Profile "
            "contract")
    authorized_gates = tuple(getattr(
        profile_contract, "extension_gates", ()))
    if tuple(extension_gates) != authorized_gates:
        raise ValueError(
            "Profile Gate rules differ from the authorized typed contract")
    contract = metadata_contract or \
        metadata_execution_contract.load_metadata_execution_contract(root)
    return metadata_execution_contract.compose_profile_projection_rules(
        contract, profile_contract)


def authorized_profile_projection_rules(root, profile_view):
    """Return the one metadata contract and rule set for an authorized view.

    Runtime writers receive the already-authorized Profile view from
    ``check_queue``.  Keeping this adapter here means migration, current
    projection, and validation all compose Core rules with the *same* typed
    ``extension_gates`` contract instead of growing parallel Profile parsers.
    """
    contract = profile_view.get("_contract") if isinstance(
        profile_view, dict) else None
    extension_gates = getattr(contract, "extension_gates", None)
    if extension_gates is None:
        raise ValueError(
            "the authorized Profile has no typed extension-gate contract")
    metadata_contract = \
        metadata_execution_contract.load_metadata_execution_contract(root)
    return metadata_contract, profile_gate_projection_rules(
        root, extension_gates, metadata_contract=metadata_contract,
        authorized_profile_contract=contract)


def _legacy_property_records(legacy, property_rules, path):
    if not isinstance(legacy, dict):
        raise ValueError(
            "legacy_property_state for %s must be a mapping" % path)
    extra = sorted(set(legacy) - set(property_rules))
    if extra:
        raise ValueError(
            "legacy_property_state for %s has undeclared field(s): %s" %
            (path, ", ".join(extra)))
    checked = {}
    for field in sorted(legacy):
        record = legacy[field]
        if (not isinstance(record, dict) or
                set(record) != LEGACY_PROPERTY_RECORD_KEYS):
            raise ValueError(
                "legacy_property_state.%s for %s is not the closed "
                "status/value observation" % (field, path))
        if record.get("status") != LEGACY_PROPERTY_STATUS:
            raise ValueError(
                "legacy_property_state.%s for %s must have status %s" %
                (field, path, LEGACY_PROPERTY_STATUS))
        value = project_page_state._typed_owner_value(
            record.get("value"), property_rules[field], path)
        checked[field] = {
            "status": LEGACY_PROPERTY_STATUS,
            "value": value,
        }
    return checked


def validate_legacy_property_migration_records(records, *, expected_paths=None):
    """Validate the closed page before/after evidence carried by migration.

    The records are deliberately receipt-neutral.  Producers bind them to a
    receipt and Profile/metadata identities; consumers first validate this
    closed byte-level shape and then judge the producer era separately.
    """
    if not isinstance(records, (list, tuple)):
        raise ValueError(
            "legacy property migration records must be an explicit list")
    result = {}
    paths = []
    for index, record in enumerate(records):
        label = "legacy property migration records[%d]" % index
        if (not isinstance(record, dict) or
                set(record) != LEGACY_MIGRATION_RECORD_KEYS):
            raise ValueError("%s is not the closed migration shape" % label)
        path = record.get("path")
        if not _nonempty(path):
            raise ValueError("%s has no path" % label)
        if path in result:
            raise ValueError(
                "legacy property migration repeats path %s" % path)
        for field in ("before_page_sha256", "after_page_sha256"):
            value = record.get(field)
            if value is not None and (
                    not isinstance(value, str) or
                    SHA256_RE.fullmatch(value) is None):
                raise ValueError(
                    "%s %s must be canonical sha256 or null" %
                    (label, field))
        if ((record.get("before_page_sha256") is None) !=
                (record.get("after_page_sha256") is None)):
            raise ValueError(
                "%s may not materialize or delete a page" % label)
        legacy = record.get("legacy_property_state")
        if not isinstance(legacy, dict):
            raise ValueError(
                "%s legacy_property_state must be a mapping" % label)
        for property_name, observation in legacy.items():
            if not _nonempty(property_name):
                raise ValueError(
                    "%s legacy property name must be non-empty" % label)
            if (not isinstance(observation, dict) or
                    set(observation) != LEGACY_PROPERTY_RECORD_KEYS or
                    observation.get("status") != LEGACY_PROPERTY_STATUS):
                raise ValueError(
                    "%s legacy_property_state.%s is not a closed %s "
                    "observation" %
                    (label, property_name, LEGACY_PROPERTY_STATUS))
        paths.append(path)
        result[path] = copy.deepcopy(record)
    if paths != sorted(paths):
        raise ValueError(
            "legacy property migration records must be path-sorted")
    if expected_paths is not None:
        expected = list(expected_paths)
        if (expected != sorted(expected) or
                len(expected) != len(set(expected))):
            raise ValueError(
                "expected legacy migration paths are not canonical")
        if paths != expected:
            raise ValueError(
                "legacy property migration paths do not equal the expected "
                "page set")
    return result


def legacy_property_migration_set_sha256(records):
    """Hash one validated, canonical migration record set."""
    validate_legacy_property_migration_records(records)
    return kblib.sha256_bytes(kblib.canonical_json_bytes(list(records)))


def build_legacy_property_removal_plan(
        root, paths, *, rules, declared_legacy=None):
    """Plan removal of every unowned machine copy from exact page snapshots.

    ``declared_legacy=None`` is the initial-adoption mode: observations are
    derived from the immutable page snapshot.  Amendment mode supplies an
    exact path->marker mapping and this function proves it equals *all*
    machine-managed values currently present on each selected page.  The
    returned projection uses ``project_page_state``'s existing transaction;
    this module remains a pure planner and never becomes a second page or
    Coverage writer.
    """
    selected = list(paths)
    if (selected != sorted(selected) or
            len(selected) != len(set(selected)) or
            not all(_nonempty(path) for path in selected)):
        raise ValueError(
            "legacy property migration paths must be sorted, unique, and "
            "non-empty")
    active_rules = tuple(rules)
    property_rules = {
        rule.get("field"): rule for rule in active_rules
        if isinstance(rule, dict) and
        rule.get("source_adapter") in
        project_page_state.PROPERTY_VALUE_ADAPTERS
    }
    if not property_rules:
        raise ValueError(
            "legacy property migration has no authorized property rules")
    if declared_legacy is not None:
        if not isinstance(declared_legacy, dict) or \
                sorted(declared_legacy) != selected:
            raise ValueError(
                "declared legacy observations must exactly cover the "
                "migration page set")

    projections = []
    records = []
    after_text_by_path = {}
    for path in selected:
        snapshot = kblib.repository_target_snapshot(
            root, path, suffixes=(".md", ".MD"), singly_linked=True)
        text = snapshot.read_text() if snapshot.exists else None
        fields = {}
        match = None
        if text is not None:
            match = project_page_state.FRONTMATTER.match(text)
            if match is not None:
                fields = project_page_state._frontmatter_mapping(text, path)

        observed = {}
        for field, rule in sorted(property_rules.items()):
            if field not in fields:
                continue
            value = project_page_state._typed_owner_value(
                fields[field], rule, path)
            observed[field] = {
                "status": LEGACY_PROPERTY_STATUS,
                "value": value,
            }
        legacy = (observed if declared_legacy is None else
                  _legacy_property_records(
                      declared_legacy[path], property_rules, path))
        if legacy != observed:
            missing = sorted(set(observed) - set(legacy))
            invented = sorted(set(legacy) - set(observed))
            mismatched = sorted(
                field for field in set(observed).intersection(legacy)
                if observed[field] != legacy[field])
            details = []
            if missing:
                details.append("unmarked page fields %s" % ", ".join(missing))
            if invented:
                details.append("invented fields %s" % ", ".join(invented))
            if mismatched:
                details.append("different values for %s" %
                               ", ".join(mismatched))
            raise ValueError(
                "legacy_property_state for %s does not equal the exact "
                "page-side machine values (%s)" %
                (path, "; ".join(details) or "different observation"))

        new_text = text
        changes = []
        if legacy:
            if match is None:
                raise ValueError(
                    "legacy observations for %s have no frontmatter source" %
                    path)
            frontmatter = match.group(2)
            for field in sorted(legacy):
                pattern = project_page_state._field_pattern(field)
                matches = list(pattern.finditer(frontmatter))
                if len(matches) != 1:
                    raise ValueError(
                        "%s declares top-level %s but its unique source line "
                        "cannot be located" % (path, field))
                before = legacy[field]["value"]
                frontmatter = re.sub(
                    r"^%s:.*\n?" % re.escape(field), "", frontmatter,
                    count=1, flags=re.M)
                changes.append((field, before, None))
            new_text = (match.group(1) + frontmatter + match.group(3) +
                        text[match.end():])
            project_page_state._frontmatter_mapping(new_text, path)

        after_data = new_text.encode("utf-8") if new_text is not None else None
        after_sha = (kblib.sha256_bytes(after_data)
                     if after_data is not None else None)
        records.append({
            "path": path,
            "before_page_sha256": snapshot.sha256 if snapshot.exists else None,
            "after_page_sha256": after_sha,
            "legacy_property_state": copy.deepcopy(legacy),
        })
        if new_text is not None:
            after_text_by_path[path] = new_text
        projections.append(project_page_state.PageProjection(
            path, snapshot, after_data, changes))

    ledger = project_page_state._ledger_snapshot(root)
    plan = project_page_state.ProjectionPlan(
        ledger, projections, active_rules, revalidate_contract=False)
    validate_legacy_property_migration_records(
        records, expected_paths=selected)
    return {
        "plan": plan,
        "records": records,
        "count": len(records),
        "set_sha256": legacy_property_migration_set_sha256(records),
        "after_text_by_path": after_text_by_path,
    }


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
        if not _nonempty(path):
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


def _retire_legacy_property(row, path, field):
    """Remove one unverified observation when current evidence takes over.

    The migration marker is audit context, never a second owner.  Every pure
    transition helper calls this in the same proposed-Coverage mutation that
    installs the current record, so the eventual outer transaction cannot
    publish two authority classes for one field.
    """
    legacy = row.get(LEGACY_PROPERTY_STATE)
    if legacy is None:
        return False
    if not isinstance(legacy, dict):
        raise ValueError(
            "Coverage legacy_property_state for %s must be a mapping" % path)
    existed = field in legacy
    legacy.pop(field, None)
    if not legacy:
        row.pop(LEGACY_PROPERTY_STATE, None)
    return existed


def _record(value, receipt_id, fingerprint):
    if not _nonempty(receipt_id):
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
    if not _nonempty(record.get("evidence_receipt")):
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
            not all(_nonempty(path) for path in selected)):
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
        if not _nonempty(path):
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

    An absent ``property_state`` is the explicit legacy boundary.  Once the
    key is present it must be a mapping; an empty mapping is valid and needs
    no page read.
    """
    if not isinstance(row, dict):
        raise ValueError("Coverage page row for %s must be a mapping" % path)
    if "property_state" not in row:
        return None, None, {}
    state = row.get("property_state")
    if not isinstance(state, dict):
        raise ValueError(
            "Coverage property_state for %s must be a mapping" % path)
    active_rules = tuple(rules)
    property_rules = {
        rule.get("field"): rule for rule in active_rules
        if isinstance(rule, dict) and
        rule.get("source_adapter") in
        project_page_state.PROPERTY_VALUE_ADAPTERS
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
        # ``_owner_value`` is the projector's one value-shape, closed-record,
        # tombstone, and semantic-binding implementation.  This public
        # wrapper intentionally delegates to it instead of reimplementing
        # those rules in each runtime consumer.
        record = state.get(field)
        record_fingerprint = (record.get("content_fingerprint")
                              if isinstance(record, dict) else None)
        expected_fingerprint = (
            accepted_stale_fingerprint
            if (accepted_stale_fingerprint is not None and
                record_fingerprint == accepted_stale_fingerprint)
            else fingerprint)
        project_page_state._owner_value(
            row, property_rules[field], path, expected_fingerprint, state)
    return snapshot, fingerprint, copy.deepcopy(state)


def _current_binding(state, path):
    modified = _validated_existing_record(
        state, LAST_CONTENT_MODIFIED, path)
    reviewed = _validated_existing_record(state, LAST_REVIEWED, path)
    for record in (modified, reviewed):
        if record is not None and record.get("value") is not None:
            return record.get("content_fingerprint")
    return None


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
        project_page_state.PROPERTY_VALUE_ADAPTERS
    }
    proposed = copy.deepcopy(coverage)
    rows = _page_rows(proposed)
    selected = sorted(set(paths))
    if any(not _nonempty(path) for path in selected):
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
        # Read existing owner state without materialising the migration
        # boundary.  A projection-only rewrite is not a semantic event and
        # therefore must not add an empty ``property_state`` mapping.
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
        _retire_legacy_property(row, path, LAST_CONTENT_MODIFIED)
        prior_review = _validated_existing_record(
            state, LAST_REVIEWED, path)
        review_invalidated = False
        legacy_state = row.get(LEGACY_PROPERTY_STATE)
        legacy_review_observation = (
            copy.deepcopy(legacy_state.get(LAST_REVIEWED))
            if isinstance(legacy_state, dict) else None)
        legacy_review = _retire_legacy_property(
            row, path, LAST_REVIEWED)
        invalidated_fields = []
        invalidated_records = []
        if (prior_review is not None and
                prior_review.get("content_fingerprint") != current):
            state[LAST_REVIEWED] = _record(None, receipt_id, current)
            review_invalidated = True
        elif legacy_review:
            # The current content-change receipt does not validate the old
            # date, but it does authoritatively invalidate that old page copy.
            state[LAST_REVIEWED] = _record(None, receipt_id, current)
            review_invalidated = True
        if review_invalidated:
            invalidated_fields.append(LAST_REVIEWED)
            invalidated_records.append({
                "field": LAST_REVIEWED,
                "action": "tombstone-current-owner",
                "before_owner_record": copy.deepcopy(prior_review),
                "before_legacy_observation": legacy_review_observation,
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
            project_page_state._owner_value(
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
                "before_legacy_observation": None,
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
                _nonempty(record["before_owner_record"].get(
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
        if not _nonempty(path) or path in seen:
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
        modified = _validated_existing_record(
            state, LAST_CONTENT_MODIFIED, path)
        if (modified is not None and modified.get("value") is not None and
                _date(reviewed_on, "page-review reviewed_on") <
                _date(modified["value"], "last_content_modified")):
            raise ValueError(
                "page-review %s predates current content change" % receipt_id)
        state[LAST_REVIEWED] = _record(reviewed_on, receipt_id, current)
        _retire_legacy_property(row, path, LAST_REVIEWED)
        changed.append(path)
    return proposed, tuple(sorted(changed))


def apply_gate_transition(coverage, page_path, field, value, receipt_id,
                          semantic_fingerprint, allowed_values):
    """Apply one already-authorized Profile Gate value to Coverage state."""
    if not _nonempty(field):
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
        if not _nonempty(existing.get("evidence_receipt")):
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
    _retire_legacy_property(row, page_path, field)
    return proposed


def build_projection_plan(root, coverage, paths, *, rules=None,
                          authorized_owner_removals=None):
    """Build page after-images from one proposed owner-state mapping."""
    return project_page_state.build_projection_plan(
        root, selected_pages=sorted(set(paths)), ledger_override=coverage,
        rules=rules,
        authorized_owner_removals=authorized_owner_removals)
