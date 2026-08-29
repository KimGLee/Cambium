"""Durable evidence for every write that changes the Ledgers outside a batch.

Cross-Ledger commits, contract-amendment rows, operational registrations, the
registration-to-execution bridge, same-scope Queue replans, and the initial
materialization receipt.  These are one subject because they are the complete
set of ways the Ledgers legitimately change without a batch, and the register
is only append-only if all of them are covered.
"""

import os

import kblib
import metadata_property_state
import runtime_paths
import runtime_state_contract

from queue_runtime.canon import (
    ANY_PRODUCER_ERA_VERSION,
    APPLY_AMENDMENT_TOOL_VERSION,
    BATCH_ID_RE,
    CONTRACT_AMENDMENT_TOOL_VERSION,
    LEGACY_PROPERTY_ADOPTION_OPERATION,
    QUEUE_PATH,
    REGISTER_AMENDMENT_TOOL,
    REGISTER_AMENDMENT_TOOL_VERSION,
    SHA256_RE,
    SUPPORTED_APPLY_AMENDMENT_TOOL_VERSIONS,
)
from queue_runtime.primitives import (
    closed_mapping_errors,
    nonempty_string,
    timestamp_value,
    valid_timestamp,
)
from queue_runtime.producer_era import (
    producer_era_errors,
    accounted_standards_versions,
)
from queue_runtime.receipts import require_receipt
from queue_runtime.task_contract import (
    contract_anchor_chain,
    contract_sha256,
)


# These exact legacy protocols remain replayable.  1.0.0 is the first
# registration shape; 1.1.0 adds withdrawal.  Neither may claim the
# delegated-authority fields introduced by 1.2.0.  The current 1.3.0 era adds
# the Coverage-only ``property-state-migration`` operation; older rows remain
# producer-era history and are never asked to satisfy that new operation.
# 1.4.0 widens the legacy observation domain for Profile Gate vocabulary
# fields from the completion enum to the field's registered vocabulary and
# admits explicit null observations of present-but-blank claims; current
# owner state and Gate transitions keep the narrower completion enum.
SUPPORTED_REGISTER_AMENDMENT_TOOL_VERSIONS = frozenset((
    "1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0",
))
# 1.3.0 produced the original registered queue-replan commit shape.  Its
# bindings are still validated field by field; unknown protocols fail closed.
SUPPORTED_COMPILE_QUEUE_TOOL_VERSIONS = frozenset((
    "1.3.0", "1.4.0", "1.5.0",
))
OPERATIONAL_AMENDMENT_OPERATIONS = \
    runtime_state_contract.OPERATIONAL_AMENDMENT_OPERATIONS


PROPERTY_STATE_MIGRATION_BINDING_FIELDS = (
    "property_state_migration_records",
    "property_state_migration_count",
    "property_state_migration_set_sha256",
    "metadata_execution_contract_fingerprint",
    "metadata_execution_rule_fingerprint",
    "operation_capability",
    "selected_profile_manifest",
    "profile_snapshot_sha256",
    "profile_contract_fingerprint",
    "profile_load_inputs_sha256",
)


def operational_amendment_registration_errors(
        progress, amendment, label, current_catalog, historical_catalog,
        queue, coverage_sha, queue_sha, progress_sha):
    """Validate the registration which authorized one operational Amendment.

    A pending Amendment is a current authorization and therefore resolves only
    through the Standards-adoption-filtered catalog.  Once the transaction is
    verified, the same registration is immutable historical evidence; later
    Standards adoption may invalidate it for new work without erasing the fact
    that it authorized the completed transaction.
    """
    errors = []
    operation = amendment.get("operation")
    if operation is None:
        # An ordinary Guidance log row carries no operation and owes no
        # registration binding.
        return errors
    if operation == "contract-amendment":
        # Written only by its dedicated K13/06 transaction writer, which has
        # no pending phase; the row lands committed with its verification
        # receipt, and _contract_amendment_row_errors owns its binding.
        return errors
    if operation not in OPERATIONAL_AMENDMENT_OPERATIONS:
        # Fail closed: a row *claiming* an operation this validator does not
        # know would otherwise skip every registration binding below, making
        # an unknown operation name a way to hold authorization with no
        # registered evidence at all.
        errors.append(
            "%s declares unknown operation %r; operational Amendments are "
            "limited to %s, and an unrecognized operation cannot be exempt "
            "from registration binding" %
            (label, operation,
             ", ".join(sorted(OPERATIONAL_AMENDMENT_OPERATIONS) +
                       ["contract-amendment"])))
        return errors
    status = amendment.get("status")
    writeback = amendment.get("writeback_done")
    pending = status == "approved" and writeback is False
    verified = status == "verified" and writeback is True
    catalog = current_catalog if pending else historical_catalog
    receipt_id = amendment.get("registration_receipt")
    approval_reference = amendment.get("approval_reference")
    if not nonempty_string(approval_reference):
        errors.append("%s approval_reference must be a non-empty string" % label)

    state_prefix = ("queue_state_revision" if operation == "queue-replan"
                    else "state_revision")
    expected = {
        "tool": REGISTER_AMENDMENT_TOOL,
        # K12/10 producer-era identity: a registration sealed under an
        # accounted Standards era is never re-judged against the current
        # writer constant — the payload contract below stays exact, and a
        # protocol the current runtime cannot execute fails at execution or
        # is withdrawn, never by version drift here.
        "tool_version": ANY_PRODUCER_ERA_VERSION,
        "check": "amendment_registration",
        "target": amendment.get("id"),
        "task_id": queue.get("task_id"),
        "actor_role": "integrator",
        "amendment_id": amendment.get("id"),
        "operation": operation,
        "approval_reference": approval_reference,
        "summary": amendment.get("summary"),
        "affected_pages": amendment.get("affected_pages"),
        "affected_batches": amendment.get("affected_batches"),
        "scope_version_before": amendment.get("scope_version_before"),
        "scope_version_after": amendment.get("scope_version_after"),
        "queue_revision_before": amendment.get("queue_revision_before"),
        "queue_revision_after": amendment.get("queue_revision_after"),
        "state_revision_before": amendment.get(state_prefix + "_before"),
        "state_revision_after": amendment.get(state_prefix + "_after"),
        "coverage_proposal_path": amendment.get("coverage_proposal_path"),
        "coverage_proposal_sha256": amendment.get(
            "coverage_proposal_sha256"),
    }
    if operation == "queue-replan":
        expected["replan_diff_sha256"] = amendment.get("replan_diff_sha256")
    else:
        expected.update({
            "plan_path": amendment.get("plan_path"),
            "plan_sha256": amendment.get("plan_sha256"),
            "cancel_batch_id": amendment.get("cancel_batch_id"),
        })
    if operation == "property-state-migration":
        expected.update({
            field: amendment.get(field)
            for field in PROPERTY_STATE_MIGRATION_BINDING_FIELDS
        })
    receipt = require_receipt(
        catalog, receipt_id, "%s registration" % label, errors,
        expected=expected,
    )
    if receipt is None:
        return errors
    receipt_version = receipt.get("tool_version")
    if receipt_version not in SUPPORTED_REGISTER_AMENDMENT_TOOL_VERSIONS:
        errors.append(
            "%s registration receipt has unsupported register_amendment "
            "producer version %r" % (label, receipt_version))
    if (operation == "property-state-migration" and
            receipt_version != REGISTER_AMENDMENT_TOOL_VERSION):
        errors.append(
            "%s property-state-migration requires register_amendment %s" %
            (label, REGISTER_AMENDMENT_TOOL_VERSION))
    if operation == "property-state-migration":
        try:
            migration_records = \
                metadata_property_state.validate_legacy_property_migration_records(
                    amendment.get("property_state_migration_records"),
                    expected_paths=amendment.get("affected_pages"))
            migration_set_sha = \
                metadata_property_state.legacy_property_migration_set_sha256(
                    amendment.get("property_state_migration_records"))
        except (TypeError, ValueError) as exc:
            errors.append(
                "%s property-state-migration records are invalid: %s" %
                (label, exc))
            migration_records = {}
            migration_set_sha = None
        if amendment.get("property_state_migration_count") != len(
                migration_records):
            errors.append(
                "%s property-state-migration count does not equal its exact "
                "record set" % label)
        if amendment.get(
                "property_state_migration_set_sha256") != migration_set_sha:
            errors.append(
                "%s property-state-migration record-set digest is stale" %
                label)
        if amendment.get("operation_capability") != \
                LEGACY_PROPERTY_ADOPTION_OPERATION:
            errors.append(
                "%s property-state-migration does not bind the %s typed "
                "operation" % (label, LEGACY_PROPERTY_ADOPTION_OPERATION))
        for field in (
                "property_state_migration_set_sha256",
                "metadata_execution_contract_fingerprint",
                "metadata_execution_rule_fingerprint",
                "profile_snapshot_sha256", "profile_contract_fingerprint",
                "profile_load_inputs_sha256"):
            if not SHA256_RE.fullmatch(str(amendment.get(field) or "")):
                errors.append(
                    "%s property-state-migration has invalid %s" %
                    (label, field))
        if not nonempty_string(amendment.get("selected_profile_manifest")):
            errors.append(
                "%s property-state-migration has no selected Profile "
                "manifest" % label)
    authority_fields = (
        "decision_mode", "authority_id", "authority_sha256",
        "change_classes", "amendment_impact_sha256",
    )
    if receipt_version in ("1.2.0", REGISTER_AMENDMENT_TOOL_VERSION):
        for field in authority_fields:
            if receipt.get(field) != amendment.get(field):
                errors.append(
                    "%s registration receipt %s=%r, expected %r" %
                    (label, field, receipt.get(field), amendment.get(field)))
        if amendment.get("decision_mode") not in (
                "contract-delegated", "explicit-user"):
            errors.append(
                "%s current registration decision_mode is invalid" % label)
        classes = amendment.get("change_classes")
        if (not isinstance(classes, list) or not classes or
                classes != sorted(set(classes))):
            errors.append(
                "%s current registration change_classes must be a non-empty "
                "sorted unique list" % label)
        for field in ("amendment_impact_sha256",):
            if not SHA256_RE.fullmatch(str(amendment.get(field) or "")):
                errors.append("%s current registration has invalid %s" %
                              (label, field))
        if amendment.get("decision_mode") == "contract-delegated":
            if (not nonempty_string(amendment.get("authority_id")) or
                    not SHA256_RE.fullmatch(str(
                        amendment.get("authority_sha256") or ""))):
                errors.append(
                    "%s delegated registration must bind authority id/hash" %
                    label)
        elif (amendment.get("authority_id") is not None or
              amendment.get("authority_sha256") is not None):
            errors.append(
                "%s explicit-user registration must not claim contract "
                "authority" % label)
    elif any(field in amendment or field in receipt
             for field in authority_fields):
        errors.append(
            "%s legacy registration era must not claim delegated-authority "
            "fields" % label)
    if not valid_timestamp(receipt.get("checked_at")):
        errors.append("%s registration receipt has invalid checked_at" % label)
    elif amendment.get("date") != receipt.get("checked_at")[:10]:
        errors.append("%s date must equal the registration receipt date" % label)
    for field in (
            "contract_sha256", "before_coverage_sha256",
            "after_coverage_sha256", "before_required_queue_sha256",
            "after_required_queue_sha256", "before_progress_sha256",
            "after_progress_sha256"):
        if not SHA256_RE.fullmatch(str(receipt.get(field, ""))):
            errors.append("%s registration receipt has invalid %s" %
                          (label, field))
    if pending:
        pending_bindings = {
            "contract_sha256": contract_sha256(progress),
            "before_coverage_sha256": coverage_sha,
            "after_coverage_sha256": coverage_sha,
            "before_required_queue_sha256": queue_sha,
            "after_required_queue_sha256": queue_sha,
            "after_progress_sha256": progress_sha,
        }
        for field, value in pending_bindings.items():
            if receipt.get(field) != value:
                errors.append(
                    "%s current registration receipt has %s=%r, expected %r" %
                    (label, field, receipt.get(field), value)
                )
    elif status == "withdrawn" and writeback is False:
        # K13/06 withdrawal: a pending registration whose execution can no
        # longer validate is retired through the registering writer, never by
        # editing the row.  The withdrawal receipt is immutable history; the
        # bound plan/proposal bytes above stay verified forever.
        if not nonempty_string(amendment.get("withdrawal_reason")):
            errors.append("%s withdrawn row must record a nonempty "
                          "withdrawal_reason" % label)
        require_receipt(
            historical_catalog, amendment.get("withdrawal_receipt"),
            "%s withdrawal" % label, errors,
            expected={
                "tool": REGISTER_AMENDMENT_TOOL,
                "tool_version": ANY_PRODUCER_ERA_VERSION,
                "check": "amendment_withdrawal",
                "target": amendment.get("id"),
                "amendment_id": amendment.get("id"),
                "registration_receipt": receipt_id,
            },
        )
        return errors
    elif not verified:
        # The operation-specific validators report the illegal lifecycle pair;
        # registration is meaningful only at either end of that pair.
        return errors
    return errors


def _registration_execution_bridge_errors(
        amendment, label, historical_catalog, commit_receipt,
        commit_queue_before_field):
    """Bind one completed operation to the exact state its registration froze."""
    errors = []
    if not isinstance(commit_receipt, dict):
        return errors
    registration_id = amendment.get("registration_receipt")
    registration_entry = historical_catalog.get(registration_id) if \
        nonempty_string(registration_id) else None
    registration = registration_entry[1] if registration_entry is not None \
        else None
    if not isinstance(registration, dict):
        return errors
    for registration_field, commit_field in (
            ("after_coverage_sha256", "before_coverage_sha256"),
            ("after_required_queue_sha256", commit_queue_before_field),
            ("after_progress_sha256", "before_progress_sha256")):
        registered_sha = registration.get(registration_field)
        execution_sha = commit_receipt.get(commit_field)
        if (SHA256_RE.fullmatch(str(registered_sha or "")) and
                SHA256_RE.fullmatch(str(execution_sha or "")) and
                registered_sha != execution_sha):
            errors.append(
                "%s registration %s=%r does not bridge to execution %s=%r" %
                (label, registration_field, registered_sha,
                 commit_field, execution_sha)
            )
    registration_time = timestamp_value(registration.get("checked_at"))
    commit_time = timestamp_value(commit_receipt.get("checked_at"))
    if commit_time is None:
        errors.append("%s execution receipt has invalid checked_at" % label)
    elif registration_time is not None and commit_time < registration_time:
        errors.append(
            "%s execution receipt predates its registration receipt" % label
        )
    return errors


CONTRACT_AMENDMENT_ROW_FIELDS = frozenset((
    "id", "date", "summary", "status", "writeback_done", "operation",
    "approval_reference",
    "scope_version_before", "scope_version_after",
    "queue_revision_before", "queue_revision_after",
    "state_revision_before", "state_revision_after",
    "contract_version_before", "contract_version_after",
    "plan_path", "plan_sha256", "verification_receipt",
    # The state edge this transaction claims, recorded in the row so the
    # commit receipt can be cross-bound to a durable record exactly as the
    # K13/15 adoption record binds its receipt.  ``after_progress_sha256``
    # is absent by construction: the row lives inside the progress document.
    "coverage_sha256_before", "required_queue_sha256_before",
    "progress_sha256_before", "after_coverage_sha256",
    "after_required_queue_sha256", "policy_fingerprint",
    "changed_contract_fields",
))
CONTRACT_AMENDMENT_ROW_OPTIONAL_FIELDS = frozenset((
    "changed_contract_fields",
))
CONTRACT_AMENDMENT_PLAN_PREFIX = \
    runtime_paths.CONTRACT_AMENDMENT_DELTA_ROOT
CONTRACT_AMENDMENT_TOOL_VERSIONS = frozenset(("1.0.0", "1.1.0"))


def _contract_amendment_row_errors(root, amendment, label, historical_catalog,
                                   task_id, accounted, live_contract):
    """Validate one committed contract-amendment row, K13/06.

    The dedicated writer has no pending phase: it either commits the whole
    transaction -- contract bytes, Queue revision, this row, and the receipt
    the row names -- or writes nothing.  A row in any other state is
    therefore not an in-progress amendment but evidence of a bypassed
    writer, and fails closed.  Anchor continuity (the before/after contract
    fingerprints actually chaining) belongs to contract_anchor_chain; this
    validator owns the row's own shape and its binding to plan and receipt.
    """
    errors = []
    errors.extend(closed_mapping_errors(
        amendment, label, CONTRACT_AMENDMENT_ROW_FIELDS,
        CONTRACT_AMENDMENT_ROW_OPTIONAL_FIELDS))
    required_fields = (CONTRACT_AMENDMENT_ROW_FIELDS -
                       CONTRACT_AMENDMENT_ROW_OPTIONAL_FIELDS)
    if set(amendment) - CONTRACT_AMENDMENT_ROW_FIELDS or \
            required_fields - set(amendment):
        return errors
    if (amendment.get("status") != "verified" or
            amendment.get("writeback_done") is not True):
        errors.append(
            "%s contract-amendment must be verified/written-back; its writer "
            "has no pending phase, so any other state is a bypassed "
            "transaction rather than an in-progress one" % label)
    for field in ("id", "date", "summary", "approval_reference",
                  "contract_version_before", "contract_version_after"):
        if not nonempty_string(amendment.get(field)):
            errors.append("%s %s must be a non-empty string" % (label, field))
    if amendment.get("contract_version_before") == amendment.get(
            "contract_version_after"):
        errors.append("%s must advance contract_version" % label)
    scope_before = amendment.get("scope_version_before")
    scope_after = amendment.get("scope_version_after")
    if not nonempty_string(scope_before) or scope_before != scope_after:
        errors.append("%s must record one unchanged scope_version; scope "
                      "belongs to the replan machinery" % label)
    queue_before = amendment.get("queue_revision_before")
    queue_after = amendment.get("queue_revision_after")
    if (not isinstance(queue_before, int) or isinstance(queue_before, bool) or
            queue_before < 1 or queue_after != queue_before + 1):
        errors.append("%s queue revision edge must increment by one" % label)
    state_before = amendment.get("state_revision_before")
    state_after = amendment.get("state_revision_after")
    if (not isinstance(state_before, int) or isinstance(state_before, bool) or
            state_before < 0 or state_after != state_before):
        errors.append("%s must preserve state_revision; it changes no batch "
                      "lifecycle" % label)
    plan_path = amendment.get("plan_path")
    plan_sha = amendment.get("plan_sha256")
    if not nonempty_string(plan_path) or not (
            isinstance(plan_sha, str) and SHA256_RE.fullmatch(plan_sha)):
        errors.append("%s must bind plan_path and plan_sha256" % label)
    else:
        try:
            plan_file = kblib.managed_repository_path(
                root, plan_path, CONTRACT_AMENDMENT_PLAN_PREFIX,
                suffixes=(".yaml", ".yml"), must_exist=True)
            if kblib.sha256_file(plan_file) != plan_sha:
                errors.append("%s plan bytes differ from persisted SHA" %
                              label)
        except (OSError, ValueError) as exc:
            errors.append("%s plan is not resolvable: %s" % (label, exc))
    # The row's own state-edge and policy identity fields must be well
    # formed before anything binds to them.
    for field in ("coverage_sha256_before", "required_queue_sha256_before",
                  "progress_sha256_before", "after_coverage_sha256",
                  "after_required_queue_sha256", "policy_fingerprint"):
        value = amendment.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            errors.append(
                "%s %s must be spelled sha256:<64 hex digits>" %
                (label, field))
    receipt_id = amendment.get("verification_receipt")
    entry = historical_catalog.get(receipt_id) if nonempty_string(
        receipt_id) else None
    if entry is None:
        errors.append("%s verification_receipt is not in the receipt "
                      "catalog" % label)
        return errors
    receipt = entry[1]
    bindings = {
        "tool": "apply_contract_amendment",
        "check": "contract_amendment",
        "result": "pass",
        "actor_role": "integrator",
        "transaction_phase": "commit",
        "plan_path": plan_path,
        "plan_sha256": plan_sha,
        "before_contract_version": amendment.get("contract_version_before"),
        "after_contract_version": amendment.get("contract_version_after"),
        "queue_revision_before": queue_before,
        "queue_revision_after": queue_after,
        # The receipt's claimed state edge must equal the durable row's,
        # so tampering either alone is visible.  The receipt spells the
        # queue fields with the longer Required Queue writer names.
        "before_coverage_sha256": amendment.get("coverage_sha256_before"),
        "before_required_queue_sha256":
            amendment.get("required_queue_sha256_before"),
        "before_progress_sha256": amendment.get("progress_sha256_before"),
        "after_coverage_sha256": amendment.get("after_coverage_sha256"),
        "after_required_queue_sha256":
            amendment.get("after_required_queue_sha256"),
        "policy_fingerprint": amendment.get("policy_fingerprint"),
    }
    for field, value in bindings.items():
        if receipt.get(field) != value:
            errors.append("%s commit receipt has %s=%r, expected %r" %
                          (label, field, receipt.get(field), value))
    after_progress = receipt.get("after_progress_sha256")
    if not SHA256_RE.fullmatch(str(after_progress or "")):
        errors.append("%s commit receipt has invalid after_progress_sha256" %
                      label)
    receipt_version = receipt.get("tool_version")
    if receipt_version not in \
            CONTRACT_AMENDMENT_TOOL_VERSIONS:
        errors.append(
            "%s commit receipt has unsupported producer tool_version %r; "
            "known contract-amendment eras: %s" %
            (label, receipt.get("tool_version"),
             ", ".join(sorted(CONTRACT_AMENDMENT_TOOL_VERSIONS))))
    if receipt_version == CONTRACT_AMENDMENT_TOOL_VERSION:
        changed = amendment.get("changed_contract_fields")
        if (not isinstance(changed, list) or not changed or
                changed != sorted(set(changed)) or
                set(changed) - {"policy_exceptions", "amendment_authority"}):
            errors.append(
                "%s current-era changed_contract_fields must be a non-empty "
                "sorted subset of policy_exceptions/amendment_authority" %
                label)
        elif receipt.get("changed_contract_fields") != changed:
            errors.append(
                "%s commit receipt does not bind changed_contract_fields" %
                label)
    elif "changed_contract_fields" in amendment or \
            "changed_contract_fields" in receipt:
        errors.append(
            "%s legacy contract-amendment era must not claim "
            "changed_contract_fields" % label)
    if receipt.get("task_id") != task_id:
        errors.append(
            "%s commit receipt has task_id=%r, expected %r" %
            (label, receipt.get("task_id"), task_id))
    for field in runtime_state_contract.RUNTIME_STANDARDS_IDENTITY_FIELDS:
        if not nonempty_string(receipt.get(field)):
            errors.append(
                "%s commit receipt carries no %s identity; a receipt whose "
                "Standards era cannot be told is not replayable evidence" %
                (label, field))
    # Nonemptiness is not identity: the claimed era must be one this
    # instance accounts for, and the manifest must be the task's own.  A
    # receipt claiming `never-adopted` or a foreign profile is one this
    # runtime never produced.
    errors.extend(producer_era_errors(
        receipt, receipt_id, "%s commit" % label, accounted))
    live_manifest = (live_contract or {}).get("selected_profile_manifest")
    claimed_manifest = receipt.get("selected_profile_manifest")
    if (nonempty_string(claimed_manifest) and
            nonempty_string(live_manifest) and
            claimed_manifest != live_manifest):
        errors.append(
            "%s commit receipt claims selected_profile_manifest=%r, but "
            "this task's contract selects %r; a grant judged against a "
            "foreign profile is not this task's evidence" %
            (label, claimed_manifest, live_manifest))
    return errors


def cross_ledger_amendment_errors(
        root, progress, current_catalog, historical_catalog, queue,
        coverage_sha, queue_sha, progress_sha):
    """Validate append-only commit evidence for cross-Ledger Amendments."""
    errors = []
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        return errors
    expected_sequence = 1
    previous_commit = None
    seen_transactions = set()
    seen_commits = set()
    pending_count = 0
    pending_seen = False
    accounted = accounted_standards_versions(progress, queue)
    live_contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    for index, amendment in enumerate(amendments):
        if (isinstance(amendment, dict) and
                amendment.get("operation") == "contract-amendment"):
            errors.extend(_contract_amendment_row_errors(
                root, amendment, "Progress amendments[%d]" % index,
                historical_catalog, progress.get("task_id"),
                accounted, live_contract))
            continue
        if (isinstance(amendment, dict) and
                amendment.get("operation") is not None and
                amendment.get("operation") not in
                OPERATIONAL_AMENDMENT_OPERATIONS):
            # Fail closed here, at the walk itself: a row claiming an
            # operation no validator owns would otherwise be skipped by
            # every specialized check below, making an unknown operation
            # name an exemption from evidence.
            errors.append(
                "Progress amendments[%d] declares unknown operation %r; "
                "known operations are %s, contract-amendment" %
                (index, amendment.get("operation"),
                 ", ".join(sorted(OPERATIONAL_AMENDMENT_OPERATIONS))))
            continue
        if (not isinstance(amendment, dict) or
                amendment.get("operation") not in
                runtime_state_contract.AMENDMENT_OPERATIONS_BY_EXECUTION_CAPABILITY[
                    runtime_state_contract.CROSS_LEDGER_AMENDMENT_CAPABILITY]):
            continue
        label = "Progress amendments[%d]" % index
        status = amendment.get("status")
        writeback = amendment.get("writeback_done")
        operation = amendment.get("operation")
        for field in ("id", "summary", "scope_version_before",
                      "scope_version_after", "coverage_proposal_path"):
            if not nonempty_string(amendment.get(field)):
                errors.append("%s %s must be a non-empty string" %
                              (label, field))
        for field in ("affected_pages", "affected_batches"):
            values = amendment.get(field)
            if (not isinstance(values, list) or
                    not all(nonempty_string(value) for value in values)):
                errors.append("%s %s must be an explicit string list" %
                              (label, field))
            elif values != sorted(values) or len(values) != len(set(values)):
                errors.append("%s %s must be sorted and unique" %
                              (label, field))
        scope_before = amendment.get("scope_version_before")
        scope_after = amendment.get("scope_version_after")
        if (operation in
                runtime_state_contract.SCOPE_PRESERVING_AMENDMENT_OPERATIONS and
                nonempty_string(scope_before) and
                scope_after != scope_before):
            errors.append(
                "%s %s must preserve scope_version" % (label, operation))
        elif (operation not in
                runtime_state_contract.SCOPE_PRESERVING_AMENDMENT_OPERATIONS and
              nonempty_string(scope_before) and
              nonempty_string(scope_after) and
              scope_before == scope_after):
            errors.append("%s cross-Ledger Amendment must change scope_version" %
                          label)
        queue_before = amendment.get("queue_revision_before")
        queue_after = amendment.get("queue_revision_after")
        expected_queue_after = (
            queue_before + 1
            if isinstance(queue_before, int) and
            not isinstance(queue_before, bool) else None)
        if (not isinstance(queue_before, int) or isinstance(queue_before, bool) or
                queue_before < 1 or not isinstance(queue_after, int) or
                isinstance(queue_after, bool) or
                queue_after != expected_queue_after):
            errors.append(
                "%s queue revision edge must increment by one" % label)
        state_before = amendment.get("state_revision_before")
        state_after = amendment.get("state_revision_after")
        if (not isinstance(state_before, int) or isinstance(state_before, bool) or
                state_before < 0 or not isinstance(state_after, int) or
                isinstance(state_after, bool)):
            errors.append("%s state revision edge must use non-negative integers" %
                          label)
        elif (operation in
              runtime_state_contract.STATE_REVISION_PRESERVING_AMENDMENT_OPERATIONS and
              state_after != state_before):
            errors.append("%s %s must preserve state_revision" %
                          (label, operation))
        elif (operation == "cancel-batch" and
              state_after != state_before + 1):
            errors.append("%s cancel-batch must increment state_revision by one" %
                          label)
        proposal_sha = amendment.get("coverage_proposal_sha256")
        if (not isinstance(proposal_sha, str) or
                not SHA256_RE.fullmatch(proposal_sha)):
            errors.append("%s coverage_proposal_sha256 must be sha256:<64 "
                          "lowercase hex>" % label)
        cancel_id = amendment.get("cancel_batch_id")
        if (operation in
                runtime_state_contract.CANCEL_ID_FORBIDDEN_AMENDMENT_OPERATIONS):
            if cancel_id is not None:
                errors.append("%s %s cancel_batch_id must be null" %
                              (label, operation))
            if (operation == "property-state-migration" and
                    amendment.get("affected_batches") != []):
                errors.append(
                    "%s property-state-migration affected_batches must be "
                    "empty" % label)
        elif (not nonempty_string(cancel_id) or
              amendment.get("affected_batches") != [cancel_id]):
            errors.append("%s cancel-batch must bind exactly cancel_batch_id" %
                          label)
        plan_path = amendment.get("plan_path")
        plan_sha = amendment.get("plan_sha256")
        proposal_path = amendment.get("coverage_proposal_path")
        plan = None
        for artifact_label, artifact_path, artifact_sha in (
                ("plan", plan_path, plan_sha),
                ("coverage proposal", proposal_path, proposal_sha)):
            if not nonempty_string(artifact_path):
                errors.append("%s %s path must be a non-empty string" %
                              (label, artifact_label))
                continue
            if not isinstance(artifact_sha, str) or not SHA256_RE.fullmatch(
                    artifact_sha):
                errors.append("%s %s SHA must be sha256:<64 lowercase hex>" %
                              (label, artifact_label))
                continue
            try:
                artifact = kblib.managed_repository_path(
                    root, artifact_path, runtime_paths.AMENDMENT_DELTA_ROOT,
                    suffixes=(".yaml", ".yml"), must_exist=True,
                )
                current_sha = kblib.sha256_file(artifact)
                if current_sha != artifact_sha:
                    errors.append("%s %s bytes differ from persisted SHA" %
                                  (label, artifact_label))
                if artifact_label == "plan":
                    plan = kblib.load_yaml_file(artifact)
            except (OSError, ValueError, kblib.YamlSubsetError) as exc:
                errors.append("%s %s is unsafe, missing, or invalid: %s" %
                              (label, artifact_label, exc))
        if (nonempty_string(plan_path) and nonempty_string(proposal_path) and
                os.path.normpath(plan_path) == os.path.normpath(proposal_path)):
            errors.append("%s plan and coverage proposal must be different files" %
                          label)
        if isinstance(plan, dict):
            plan_bindings = {
                "amendment_id": amendment.get("id"),
                "operation": operation,
                "affected_pages": amendment.get("affected_pages"),
                "affected_batches": amendment.get("affected_batches"),
                "scope_version_before": scope_before,
                "scope_version_after": scope_after,
                "queue_revision_before": queue_before,
                "queue_revision_after": queue_after,
                "state_revision_before": state_before,
                "state_revision_after": state_after,
                "coverage_proposal_path": proposal_path,
                "coverage_proposal_sha256": proposal_sha,
                "cancel_batch_id": cancel_id,
            }
            for field, value in plan_bindings.items():
                if plan.get(field) != value:
                    errors.append("%s plan %s=%r, expected %r" %
                                  (label, field, plan.get(field), value))
        errors.extend(operational_amendment_registration_errors(
            progress, amendment, label, current_catalog, historical_catalog,
            queue, coverage_sha, queue_sha, progress_sha,
        ))
        if status == "approved" and writeback is False:
            if scope_before != queue.get("scope_version"):
                errors.append("%s pending Amendment scope_version_before does "
                              "not match the live Queue" % label)
            expected_pending_queue_after = \
                queue.get("queue_revision", 0) + 1
            if (queue_before != queue.get("queue_revision") or
                    queue_after != expected_pending_queue_after):
                errors.append("%s pending Amendment must bind the next live "
                              "Queue revision" % label)
            if state_before != queue.get("state_revision"):
                errors.append("%s pending Amendment state_revision_before does "
                              "not match the live Queue" % label)
            for field in ("transaction_id", "verification_receipt",
                          "transaction_sequence",
                          "previous_transaction_commit_receipt"):
                if amendment.get(field) is not None:
                    errors.append("%s pending Amendment must not claim %s" %
                                  (label, field))
            pending_count += 1
            pending_seen = True
            continue
        if status == "withdrawn" and writeback is False:
            # K13/06 withdrawal: the row stays as immutable evidence and
            # authorizes nothing; the withdrawal receipt is validated with
            # the registration binding above.
            for field in ("transaction_id", "verification_receipt",
                          "transaction_sequence",
                          "previous_transaction_commit_receipt"):
                if amendment.get(field) is not None:
                    errors.append("%s withdrawn Amendment must not claim %s" %
                                  (label, field))
            continue
        if status != "verified" or writeback is not True:
            errors.append("%s cross-Ledger state must be approved/pending, "
                          "withdrawn, or verified/written-back" % label)
            continue
        if pending_seen:
            errors.append("%s verified transaction appears after a pending "
                          "cross-Ledger Amendment" % label)
        transaction_id = amendment.get("transaction_id")
        commit_id = amendment.get("verification_receipt")
        sequence = amendment.get("transaction_sequence")
        prior = amendment.get("previous_transaction_commit_receipt")
        if sequence != expected_sequence:
            errors.append("%s transaction_sequence=%r, expected %d" %
                          (label, sequence, expected_sequence))
        if prior != previous_commit:
            errors.append("%s previous transaction commit is %r, expected %r" %
                          (label, prior, previous_commit))
        if transaction_id in seen_transactions:
            errors.append("%s repeats transaction_id %r" %
                          (label, transaction_id))
        if commit_id in seen_commits:
            errors.append("%s repeats verification_receipt %r" %
                          (label, commit_id))
        seen_transactions.add(transaction_id)
        seen_commits.add(commit_id)
        receipt = require_receipt(
            historical_catalog, commit_id,
            "%s verification" % label, errors,
            expected={
                "tool": "apply_amendment",
                "tool_version": ANY_PRODUCER_ERA_VERSION,
                "check": "amendment_transaction",
                "target": amendment.get("id"),
                "transaction_phase": "commit",
                "transaction_id": transaction_id,
                "amendment_id": amendment.get("id"),
                "operation": amendment.get("operation"),
                "task_id": queue.get("task_id"),
                "actor_role": "integrator",
                "transaction_sequence": sequence,
                "previous_transaction_commit_receipt": prior,
                "registration_receipt":
                    amendment.get("registration_receipt"),
                "plan_path": plan_path,
                "plan_sha256": plan_sha,
                "coverage_proposal_path": proposal_path,
                "coverage_proposal_sha256": proposal_sha,
                "queue_revision_before": queue_before,
                "queue_revision_after": queue_after,
                "state_revision_before": state_before,
                "state_revision_after": state_after,
            },
        )
        if (receipt is not None and receipt.get("tool_version") not in
                SUPPORTED_APPLY_AMENDMENT_TOOL_VERSIONS):
            errors.append(
                "%s verification receipt has unsupported apply_amendment "
                "producer version %r" %
                (label, receipt.get("tool_version")))
        if (receipt is not None and operation ==
                "property-state-migration" and
                receipt.get("tool_version") != APPLY_AMENDMENT_TOOL_VERSION):
            errors.append(
                "%s property-state-migration requires apply_amendment %s" %
                (label, APPLY_AMENDMENT_TOOL_VERSION))
        if receipt is not None and operation == "property-state-migration":
            for field in PROPERTY_STATE_MIGRATION_BINDING_FIELDS:
                if receipt.get(field) != amendment.get(field):
                    errors.append(
                        "%s property-state-migration commit receipt does not "
                        "bind %s" % (label, field))
        if not nonempty_string(transaction_id):
            errors.append("%s verified transaction_id must be non-empty" % label)
        if receipt is not None and not SHA256_RE.fullmatch(
                str(receipt.get("plan_sha256", ""))):
            errors.append("%s verification receipt has invalid plan_sha256" % label)
        if receipt is not None:
            for phase in ("before", "after"):
                for state_name in runtime_state_contract.RUNTIME_LEDGER_IDS:
                    field = "%s_%s_sha256" % (phase, state_name)
                    if not SHA256_RE.fullmatch(str(receipt.get(field, ""))):
                        errors.append("%s verification receipt has invalid %s" %
                                      (label, field))
            errors.extend(_registration_execution_bridge_errors(
                amendment, label, historical_catalog, receipt,
                "before_queue_sha256",
            ))
        previous_commit = commit_id
        expected_sequence += 1
    if pending_count > 1:
        errors.append("Progress has %d pending cross-Ledger Amendments; exactly "
                      "one may be staged at a time" % pending_count)
    return errors


def pending_cross_ledger_amendments(progress):
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        return []
    return [
        amendment.get("id", "<unnamed>")
        for amendment in amendments
        if (isinstance(amendment, dict) and
            amendment.get("operation") in OPERATIONAL_AMENDMENT_OPERATIONS and
            amendment.get("status") == "approved" and
            amendment.get("writeback_done") is False)
    ]


def queue_replan_amendment_errors(
        root, progress, current_catalog, historical_catalog, queue, queue_sha,
        coverage_sha, progress_sha,
                                   allow_pending_receipts=False):
    """Validate durable evidence for same-scope Queue replans.

    A pending replan is an authorization for the *next* structural revision,
    not evidence that a write occurred.  A verified replan is historical
    evidence and therefore binds to one unique compile_queue receipt.  Older
    receipts remain valid after later replans or lifecycle transitions; only
    an Amendment whose two revision axes still equal the live Queue is
    expected to name the live bytes.

    ``allow_pending_receipts`` is reserved for compile_queue's in-memory
    preflight.  It lets that preflight inspect the receipt which will be
    appended by the same locked commit.  Normal validation never enables it,
    so persisted verified state must resolve to an on-disk receipt.
    """
    errors = []
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        return errors

    current_queue_revision = queue.get("queue_revision")
    current_state_revision = queue.get("state_revision")
    current_scope = queue.get("scope_version")
    seen_amendment_ids = set()
    receipt_owners = {}

    def valid_revision(value, minimum=0):
        return (isinstance(value, int) and not isinstance(value, bool) and
                value >= minimum)

    for index, amendment in enumerate(amendments):
        if (not isinstance(amendment, dict) or
                amendment.get("operation") != "queue-replan"):
            continue
        label = "Progress amendments[%d]" % index
        amendment_id = amendment.get("id")
        if not nonempty_string(amendment_id):
            errors.append("%s queue-replan id must be a non-empty string" % label)
        elif amendment_id in seen_amendment_ids:
            errors.append("%s repeats queue-replan Amendment id %s" %
                          (label, amendment_id))
        else:
            seen_amendment_ids.add(amendment_id)

        affected = amendment.get("affected_batches")
        if (not isinstance(affected, list) or not affected or
                not all(nonempty_string(value) and
                        BATCH_ID_RE.fullmatch(value) for value in affected)):
            errors.append("%s affected_batches must be a non-empty list of "
                          "valid batch ids" % label)
        elif len(affected) != len(set(affected)):
            errors.append("%s affected_batches must be unique" % label)
        elif affected != sorted(affected):
            errors.append("%s affected_batches must be sorted" % label)

        affected_pages = amendment.get("affected_pages")
        if (not isinstance(affected_pages, list) or
                not all(nonempty_string(value) for value in affected_pages)):
            errors.append("%s affected_pages must be an explicit string list" %
                          label)
        elif (len(affected_pages) != len(set(affected_pages)) or
              affected_pages != sorted(affected_pages)):
            errors.append("%s affected_pages must be sorted and unique" % label)

        proposal_path = amendment.get("coverage_proposal_path")
        proposal_sha = amendment.get("coverage_proposal_sha256")
        if not nonempty_string(proposal_path):
            errors.append("%s coverage_proposal_path must be non-empty" % label)
        else:
            try:
                proposal_file = kblib.managed_repository_path(
                    root, proposal_path, runtime_paths.REPLAN_DELTA_ROOT,
                    suffixes=(".coverage.yaml",), must_exist=True,
                )
                actual_proposal_sha = kblib.sha256_file(proposal_file)
                if actual_proposal_sha != proposal_sha:
                    errors.append("%s Coverage proposal SHA does not match %s" %
                                  (label, proposal_path))
            except (OSError, ValueError) as exc:
                errors.append("%s Coverage proposal is unsafe or missing: %s" %
                              (label, exc))
        if not isinstance(proposal_sha, str) or not SHA256_RE.fullmatch(
                proposal_sha):
            errors.append("%s coverage_proposal_sha256 must be sha256:<64 "
                          "lowercase hex>" % label)

        scope_before = amendment.get("scope_version_before")
        scope_after = amendment.get("scope_version_after")
        if (not nonempty_string(scope_before) or
                scope_after != scope_before):
            errors.append("%s same-scope replan must have one unchanged, "
                          "non-empty scope version" % label)

        revision_before = amendment.get("queue_revision_before")
        revision_after = amendment.get("queue_revision_after")
        revisions_valid = (valid_revision(revision_before, 1) and
                           valid_revision(revision_after, 1))
        if not revisions_valid or revision_after != revision_before + 1:
            errors.append("%s queue revisions must be integers with after = "
                          "before + 1" % label)

        state_before = amendment.get("queue_state_revision_before")
        state_after = amendment.get("queue_state_revision_after")
        states_valid = (valid_revision(state_before) and
                        valid_revision(state_after))
        if not states_valid or state_after != state_before:
            errors.append("%s same-scope replan must not change the Queue "
                          "state revision" % label)

        diff_sha = amendment.get("replan_diff_sha256")
        if not isinstance(diff_sha, str) or not SHA256_RE.fullmatch(diff_sha):
            errors.append("%s replan_diff_sha256 must be sha256:<64 lowercase "
                          "hex>" % label)

        status = amendment.get("status")
        writeback = amendment.get("writeback_done")
        errors.extend(operational_amendment_registration_errors(
            progress, amendment, label, current_catalog, historical_catalog,
            queue, coverage_sha, queue_sha, progress_sha,
        ))
        if status == "approved" and writeback is False:
            if scope_before != current_scope:
                errors.append("%s pending replan scope does not match the live "
                              "Queue" % label)
            if (revision_before != current_queue_revision or
                    revision_after != (current_queue_revision + 1
                                       if valid_revision(current_queue_revision,
                                                         1) else None)):
                errors.append("%s pending replan must authorize the next live "
                              "Queue revision" % label)
            if (state_before != current_state_revision or
                    state_after != current_state_revision):
                errors.append("%s pending replan state revision must match the "
                              "live Queue" % label)
            if (amendment.get("transaction_receipt_id") is not None or
                    amendment.get("transaction_id") is not None or
                    amendment.get("after_required_queue_sha256") is not None or
                    amendment.get("after_coverage_sha256") is not None):
                errors.append("%s pending replan must not claim committed "
                              "receipt/SHA evidence" % label)
            continue

        if status == "withdrawn" and writeback is False:
            # K13/06 withdrawal keeps the row as evidence; it never executes.
            continue
        if status != "verified" or writeback is not True:
            errors.append("%s queue-replan state must be approved/pending, "
                          "withdrawn, or verified/written-back" % label)
            continue

        if (revisions_valid and valid_revision(current_queue_revision, 1) and
                revision_after > current_queue_revision):
            errors.append("%s verified replan revision is newer than the live "
                          "Queue" % label)
        if (states_valid and valid_revision(current_state_revision) and
                state_after > current_state_revision):
            errors.append("%s verified replan state revision is newer than the "
                          "live Queue" % label)

        receipt_id = amendment.get("transaction_receipt_id")
        transaction_id = amendment.get("transaction_id")
        if not nonempty_string(transaction_id):
            errors.append("%s verified replan transaction_id must be non-empty" %
                          label)
        if nonempty_string(receipt_id):
            owner = receipt_owners.get(receipt_id)
            if owner is not None:
                errors.append("%s reuses transaction receipt %s already bound "
                              "to %s" % (label, receipt_id, owner))
            else:
                receipt_owners[receipt_id] = amendment_id or label
        receipt = require_receipt(
            historical_catalog, receipt_id, "%s queue-replan" % label, errors,
            expected={
                "tool": "compile_queue",
                "tool_version": ANY_PRODUCER_ERA_VERSION,
                "check": "queue_replan",
                "target": QUEUE_PATH,
                "task_id": queue.get("task_id"),
                "amendment_id": amendment_id,
                "transaction_id": transaction_id,
                "transaction_phase": "commit",
                "registration_receipt":
                    amendment.get("registration_receipt"),
                "actor_role": "integrator",
                "coverage_proposal_path": proposal_path,
                "coverage_proposal_sha256": proposal_sha,
                "affected_pages": affected_pages,
                "affected_batches": affected,
                "replan_diff_sha256": diff_sha,
                "before_queue_revision": revision_before,
                "after_queue_revision": revision_after,
                "queue_state_revision": state_after,
            },
        )
        catalog_entry = historical_catalog.get(receipt_id) if nonempty_string(
            receipt_id) else None
        if (catalog_entry is not None and catalog_entry[0] == "<pending-write>" and
                not allow_pending_receipts):
            errors.append("%s verified replan receipt %s is not persisted in "
                          "the repository" % (label, receipt_id))
        if receipt is None:
            continue
        if receipt.get("tool_version") not in \
                SUPPORTED_COMPILE_QUEUE_TOOL_VERSIONS:
            errors.append(
                "%s receipt has unsupported compile_queue producer version "
                "%r" % (label, receipt.get("tool_version")))

        errors.extend(_registration_execution_bridge_errors(
            amendment, label, historical_catalog, receipt,
            "before_required_queue_sha256",
        ))

        before_sha = receipt.get("before_required_queue_sha256")
        after_sha = receipt.get("after_required_queue_sha256")
        if not isinstance(before_sha, str) or not SHA256_RE.fullmatch(before_sha):
            errors.append("%s receipt has invalid before Required Queue SHA" %
                          label)
        if not isinstance(after_sha, str) or not SHA256_RE.fullmatch(after_sha):
            errors.append("%s receipt has invalid after Required Queue SHA" %
                          label)
        amendment_after_sha = amendment.get("after_required_queue_sha256")
        if (not isinstance(amendment_after_sha, str) or
                not SHA256_RE.fullmatch(amendment_after_sha)):
            errors.append("%s after_required_queue_sha256 must be sha256:<64 "
                          "lowercase hex>" % label)
        elif after_sha != amendment_after_sha:
            errors.append("%s Amendment after Required Queue SHA does not match "
                          "its receipt" % label)
        before_coverage_sha = receipt.get("before_coverage_sha256")
        after_coverage_sha = receipt.get("after_coverage_sha256")
        for field, value in (("before_coverage_sha256", before_coverage_sha),
                             ("after_coverage_sha256", after_coverage_sha),
                             ("before_progress_sha256",
                              receipt.get("before_progress_sha256")),
                             ("after_progress_sha256",
                              receipt.get("after_progress_sha256"))):
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                errors.append("%s receipt has invalid %s" % (label, field))
        amendment_after_coverage = amendment.get("after_coverage_sha256")
        if (not isinstance(amendment_after_coverage, str) or
                not SHA256_RE.fullmatch(amendment_after_coverage)):
            errors.append("%s after_coverage_sha256 must be sha256:<64 "
                          "lowercase hex>" % label)
        elif after_coverage_sha != amendment_after_coverage:
            errors.append("%s Amendment after Coverage SHA does not match its "
                          "receipt" % label)

        # A subsequent lifecycle transition changes Queue bytes without
        # changing queue_revision; therefore live-byte equality is required
        # only when *both* revision axes still name the current state.
        if (revision_after == current_queue_revision and
                state_after == current_state_revision and
                after_sha != queue_sha):
            errors.append("%s latest replan receipt does not match live Queue "
                          "bytes" % label)
        if (revision_after == current_queue_revision and
                state_after == current_state_revision and
                after_coverage_sha != coverage_sha):
            errors.append("%s latest replan receipt does not match live Coverage "
                          "bytes" % label)
    return errors


def initial_queue_receipt_errors(progress, catalog, queue, queue_sha,
                                  coverage_sha):
    """Bind every materialized Queue to its unique initial compiler receipt."""
    errors = []
    items = queue.get("required_queue")
    receipt_id = progress.get("initial_queue_receipt")
    if isinstance(items, list) and not items:
        if receipt_id is not None:
            errors.append("empty Queue must have initial_queue_receipt=null")
        return errors
    if not isinstance(items, list):
        return errors
    receipt = require_receipt(
        catalog, receipt_id, "Progress initial Queue", errors,
        expected={
            "tool": "compile_queue",
            "tool_version": ANY_PRODUCER_ERA_VERSION,
            "check": "queue_structure",
            "target": QUEUE_PATH,
            "task_id": queue.get("task_id"),
            "actor_role": "integrator",
        },
    )
    if receipt is None:
        return errors
    _, contract_errors = contract_anchor_chain(progress, catalog)
    errors.extend(contract_errors)
    before_revision = receipt.get("before_queue_revision")
    after_revision = receipt.get("after_queue_revision")
    if (not isinstance(before_revision, int) or isinstance(before_revision, bool) or
            not isinstance(after_revision, int) or isinstance(after_revision, bool) or
            after_revision < 1 or before_revision != after_revision - 1):
        errors.append("initial Queue receipt has invalid revision edge %r -> %r" %
                      (before_revision, after_revision))
    elif after_revision > queue.get("queue_revision", -1):
        errors.append("initial Queue receipt is newer than the live Queue revision")
    if receipt.get("queue_state_revision") != 0:
        errors.append("initial Queue receipt queue_state_revision must be 0")
    fingerprints = {}
    for field in (
            "before_required_queue_sha256", "after_required_queue_sha256",
            "before_coverage_sha256", "after_coverage_sha256",
            "before_progress_sha256", "after_progress_sha256"):
        value = receipt.get(field)
        fingerprints[field] = value
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            errors.append("initial Queue receipt has invalid %s" % field)
    # Before the first lifecycle transition/replan, the origin receipt still
    # names the exact live Queue and Coverage bytes. Later changes retain the
    # receipt as immutable provenance rather than pretending it is current.
    if (after_revision == queue.get("queue_revision") and
            queue.get("state_revision") == 0):
        if fingerprints.get("after_required_queue_sha256") != queue_sha:
            errors.append("initial Queue receipt does not match live Queue bytes")
        if fingerprints.get("after_coverage_sha256") != coverage_sha:
            errors.append("initial Queue receipt does not match live Coverage bytes")
    return errors
