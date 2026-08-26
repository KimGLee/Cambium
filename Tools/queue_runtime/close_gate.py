"""Does the independent merged-snapshot close gate hold.

Reviewer attestation, the per-page review-evidence subgraph, sealed
policy-exception dispositions, born-cold evidence binding, and revalidation
of the two pre-close gates from frozen history.  Re-deciding the pre-close
gates from the frozen snapshot rather than trusting their receipts is what
makes this gate independent instead of a second signature on the first one.
"""

import datetime
import os
import stat

import batch_close_contract
import candidate_lifecycle
import corpus_planning_contract
import kblib
import metadata_execution_contract
import metadata_property_state
import project_page_state
import profile_contract

from queue_runtime.canon import (
    ANY_PRODUCER_ERA_VERSION,
    BATCH_CLOSE_TOOL,
    BATCH_CLOSE_TOOL_VERSION,
    CORPUS_PLAN_TOOL,
    CORPUS_PLAN_TOOL_VERSION,
    GATE_CHECK,
    SHA256_RE,
    TOOL,
)
from queue_runtime.delta import close_settlement_binding_errors
from queue_runtime.evidence_identity import (
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    EVIDENCE_USE_TERMINAL_HISTORY,
    evidence_identity_errors,
)
from queue_runtime.policy_exceptions import sealed_policy_exception_errors
from queue_runtime.primitives import (
    nonempty_string,
    timestamp_value,
)
from queue_runtime.producer_era import producer_era_errors
from queue_runtime.receipts import (
    cold_path_within_root,
    require_receipt,
)


# Compatibility projection of the K12/09-owned machine registry. A close-gate
# receipt names one independently persisted pass receipt for every member; no
# omission or ad-hoc member can be hidden behind a generic "batch passed"
# assertion.
CLOSED_LIST_EVIDENCE_FIELDS = \
    batch_close_contract.CLOSED_LIST_EVIDENCE_FIELDS
# Sealed close bundles are validated against the Closed List their producer
# era actually ran (K12/10 producer-era identity): a bundle produced before
# ``manifest_page_contract`` joined the list carries seven members forever,
# and re-judging it against the current list would retroactively invalidate
# every prior close on a checker upgrade.
LEGACY_CLOSED_LIST_VERSIONS = \
    batch_close_contract.LEGACY_CLOSED_LIST_VERSIONS
LEGACY_CLOSED_LIST_EVIDENCE_FIELDS = \
    batch_close_contract.LEGACY_CLOSED_LIST_EVIDENCE_FIELDS

# Batch-close has a finite historical protocol catalog because its 1.4 era
# sealed a different Closed List shape.  A current action still accepts only
# BATCH_CLOSE_TOOL_VERSION; this set is used only while replaying an already
# recorded closed edge.  Other historical receipts are judged through
# :func:`accounted_standards_versions` instead of an unbounded version list.
SUPPORTED_BATCH_CLOSE_TOOL_VERSIONS = frozenset((
    BATCH_CLOSE_TOOL_VERSION, "1.11.0", "1.10.0", "1.9.0", "1.8.0", "1.7.0",
    "1.6.0", "1.5.0",
    *LEGACY_CLOSED_LIST_VERSIONS,
))
# A sealed close bundle keeps the child producer its batch-close era ran.
# Batch-close 1.7 is the first protocol that consumes corpus-plan 1.7; older
# supported bundles retain their 1.6 child identity during historical replay.
HISTORICAL_CORPUS_PLAN_TOOL_VERSIONS = {
    "1.11.0": "1.7.0",
    "1.10.0": "1.7.0",
    "1.9.0": "1.7.0",
    "1.8.0": "1.7.0",
    "1.7.0": "1.7.0",
    "1.6.0": "1.6.0",
    "1.5.0": "1.6.0",
    "1.4.0": "1.6.0",
}
# Producer eras whose batch-close protocol carries the policy-exception
# disposition.  K12/10 producer-era identity cuts both ways: an older bundle
# is never re-judged against members its era lacked, and it is never allowed
# to carry evidence its era could not have produced.  A 1.7 bundle claiming a
# policy-exception disposition is a forgery, not history.
POLICY_EXCEPTION_DISPOSITION_VERSIONS = frozenset((
    "1.8.0", "1.9.0", "1.10.0", "1.11.0", "1.12.0",
))

COMPACT_CLOSE_EVIDENCE_VERSIONS = frozenset((
    "1.9.0", "1.10.0", "1.11.0", "1.12.0",
))
CANDIDATE_CONTINUATION_VERSIONS = frozenset((
    "1.10.0", "1.11.0", "1.12.0"))


def candidate_evidence_binding_errors(root, label, relative, expected_sha,
                                       expected_bytes, expected_records):
    """Prove the born-cold evidence file is the one the attestation bound.

    The attestation carries this file's hash precisely because the full
    disposition detail was moved out of it; checking only that a file of
    the right length sits at the path re-creates the hole the externalizing
    was supposed to be safe under.  A same-length edit to an acceptance row
    would pass, and the next seal would then hash the edited bytes into the
    cold manifest and make the edit permanent evidence -- laundering a
    tamper through the very mechanism that exists to freeze history.  So
    the bytes are compared on every run, before any seal can adopt them.
    """
    errors = []
    if not cold_path_within_root(root, relative, errors):
        return errors
    full = os.path.join(root, relative)
    try:
        descriptor = os.lstat(full)
    except OSError:
        return ["%s candidate evidence file %s is missing (K12/07 "
                "fail-closed)" % (label, relative)]
    if os.path.islink(full) or not stat.S_ISREG(descriptor.st_mode):
        return ["%s candidate evidence file %s must be a regular file" %
                (label, relative)]
    if descriptor.st_nlink != 1:
        return ["%s candidate evidence file %s has %d hard links" %
                (label, relative, descriptor.st_nlink)]
    try:
        with open(full, "rb") as handle:
            payload = handle.read()
    except OSError as exc:
        return ["%s candidate evidence file %s is unreadable: %s" %
                (label, relative, exc)]
    if expected_bytes is not None and len(payload) != expected_bytes:
        errors.append("%s candidate evidence file %s is %d bytes on disk but "
                      "the attestation sealed %d (K12/07 fail-closed)" %
                      (label, relative, len(payload), expected_bytes))
    if isinstance(expected_sha, str) and SHA256_RE.fullmatch(expected_sha):
        actual = kblib.sha256_bytes(payload)
        if actual != expected_sha:
            errors.append(
                "%s candidate evidence file %s hashes to %s but the "
                "attestation bound %s; externalized detail is evidence only "
                "while its attestation still names these exact bytes (K12/07 "
                "fail-closed)" % (label, relative, actual, expected_sha))
    if (isinstance(expected_records, int) and
            not isinstance(expected_records, bool)):
        actual_records = payload.count(b"\n")
        if actual_records != expected_records:
            errors.append(
                "%s candidate evidence file %s holds %d record(s) but the "
                "attestation sealed %d" %
                (label, relative, actual_records, expected_records))
    return errors


def _compact_attestation_errors(attestation, attestation_id, item_id,
                                root=None, receipt_version=None):
    """Validate a compact-era reviewer attestation (K12/09, 1.9.0+).

    A compact bundle keeps the authorization surface inline -- counts, the
    per-type counts, the accepted-set fingerprint, and every
    policy-exception disposition with its sealed decision facts -- and
    externalizes the full candidate detail to one born-cold evidence file
    that the hot path never deserializes.  What must therefore hold here:
    the inline numbers are coherent with each other, the evidence file is
    bound by path, byte size, record count and content hash, and when a
    repository root is available the bound file actually exists at exactly
    its sealed size (fail closed; the full hash is re-proven on
    dereference and under ``seal_receipts.py --verify``).
    """
    errors = []
    label = "%s declared reviewer attestation %s" % (item_id, attestation_id)
    count = attestation.get("accepted_candidate_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        errors.append("%s accepted_candidate_count must be a non-negative "
                      "integer" % label)
        count = None
    accepted_types = attestation.get("accepted_candidate_types")
    if not isinstance(accepted_types, list) or any(
            not nonempty_string(value) for value in accepted_types):
        errors.append("%s accepted_candidate_types must be a string list" %
                      label)
        accepted_types = []
    if len(accepted_types) != len(set(accepted_types)):
        errors.append("%s repeats an accepted candidate type" % label)
    type_counts = attestation.get("accepted_by_type_counts")
    if not isinstance(type_counts, dict):
        errors.append("%s accepted_by_type_counts must be a mapping" % label)
        type_counts = {}
    else:
        bad_values = [key for key, value in type_counts.items()
                      if not isinstance(value, int) or
                      isinstance(value, bool) or value < 0]
        if bad_values:
            errors.append("%s accepted_by_type_counts values must be "
                          "non-negative integers" % label)
        if sorted(type_counts) != sorted(set(accepted_types)):
            errors.append("%s accepted_by_type_counts keys must equal "
                          "accepted_candidate_types" % label)
        elif count is not None and not bad_values and \
                sum(type_counts.values()) != count:
            errors.append("%s accepted_by_type_counts sum to %d, expected "
                          "accepted_candidate_count %d" %
                          (label, sum(type_counts.values()), count))
    set_sha = attestation.get("candidate_set_sha256")
    if not isinstance(set_sha, str) or not SHA256_RE.fullmatch(set_sha):
        errors.append("%s candidate_set_sha256 must be a sha256 fingerprint "
                      "over the sorted accepted candidate IDs" % label)
    evidence_path = attestation.get("candidate_evidence_path")
    evidence_sha = attestation.get("candidate_evidence_sha256")
    evidence_bytes = attestation.get("candidate_evidence_bytes")
    evidence_records = attestation.get("candidate_evidence_records")
    if (not nonempty_string(evidence_path) or
            not evidence_path.startswith(
                kblib.RECEIPT_COLD_EVIDENCE_PREFIX + "/") or
            not evidence_path.endswith(".jsonl")):
        errors.append("%s candidate_evidence_path must be a .jsonl file "
                      "under %s" %
                      (label, kblib.RECEIPT_COLD_EVIDENCE_PREFIX))
        evidence_path = None
    if not isinstance(evidence_sha, str) or not SHA256_RE.fullmatch(
            evidence_sha):
        errors.append("%s candidate_evidence_sha256 must be a sha256 "
                      "fingerprint" % label)
    if (not isinstance(evidence_bytes, int) or
            isinstance(evidence_bytes, bool) or evidence_bytes < 0):
        errors.append("%s candidate_evidence_bytes must be a non-negative "
                      "integer" % label)
        evidence_bytes = None
    if (not isinstance(evidence_records, int) or
            isinstance(evidence_records, bool) or evidence_records < 0):
        errors.append("%s candidate_evidence_records must be a non-negative "
                      "integer" % label)
    elif count is not None and evidence_records != count:
        errors.append("%s candidate_evidence_records=%d does not equal "
                      "accepted_candidate_count=%d" %
                      (label, evidence_records, count))
    if root is not None and evidence_path is not None:
        errors.extend(candidate_evidence_binding_errors(
            root, label, evidence_path, evidence_sha, evidence_bytes,
            evidence_records))
    dispositions = attestation.get("candidate_dispositions")
    if not isinstance(dispositions, list):
        errors.append("%s candidate_dispositions must be a list carrying "
                      "exactly the policy-exception dispositions" % label)
        dispositions = []
    for index, disposition in enumerate(dispositions):
        disposition_label = "%s candidate_dispositions[%d]" % (
            item_id, index)
        if not isinstance(disposition, dict):
            errors.append("%s must be a mapping" % disposition_label)
            continue
        candidate_id = disposition.get("candidate_id")
        candidate_type = disposition.get("candidate_type")
        if (not nonempty_string(candidate_id) or
                not candidate_id.startswith("candidate-sha256:") or
                not SHA256_RE.fullmatch(candidate_id.replace(
                    "candidate-sha256:", "sha256:", 1))):
            errors.append("%s has invalid stable candidate_id" %
                          disposition_label)
        if not nonempty_string(candidate_type) or ":" not in candidate_type:
            errors.append("%s has invalid candidate_type" % disposition_label)
        accepted_by = disposition.get("accepted_by")
        if (not isinstance(accepted_by, str) or
                not accepted_by.startswith("policy-exception:")):
            errors.append(
                "%s a compact attestation carries only policy-exception "
                "dispositions inline; ordinary dispositions live in the "
                "bound candidate evidence file" % disposition_label)
            continue
        decision_id = accepted_by.split(":", 1)[1]
        sealed = disposition.get("policy_exception")
        if not nonempty_string(decision_id):
            errors.append("%s has empty policy-exception decision" %
                          disposition_label)
        elif not isinstance(sealed, dict):
            errors.append("%s policy-exception disposition seals no "
                          "decision facts" % disposition_label)
        else:
            errors.extend(sealed_policy_exception_errors(
                sealed, decision_id, candidate_type, disposition_label))
    if receipt_version in CANDIDATE_CONTINUATION_VERSIONS:
        errors.extend(candidate_lifecycle.continuation_attestation_errors(
            attestation, label))
    return errors


def _page_review_acceptance_errors(
        catalog, aggregate, aggregate_id, *, item_id, task_id, manifest,
        integrator_id, reviewer_id, attestation_id, merged_snapshot_sha256,
        root=None, historical=False, selected_profile_manifest=None,
        profile_snapshot_sha256=None, profile_contract_fingerprint=None,
        profile_load_inputs_sha256=None,
        metadata_execution_contract_fingerprint=None,
        authorized_profile_contract=None,
        authorized_metadata_contract=None,
        authorized_page_semantic_fingerprints=None):
    """Validate the 1.11 exact per-page review-evidence subgraph.

    ``authorized_page_semantic_fingerprints`` is a same-transaction
    orchestration input, not persisted authority: the producer may pass the
    hashes it just computed from its frozen target snapshots and must still
    perform the final exact-byte/identity CAS.  Independent consumers omit it
    and this validator re-reads every current page before accepting the hash.
    """
    errors = []
    label = "%s batch-close gate receipt %s" % (item_id, aggregate_id)

    if (not isinstance(manifest, list) or
            any(not nonempty_string(value) for value in manifest)):
        errors.append(
            "%s current page-review protocol requires an explicit manifest "
            "page-path list" % label)
        expected_targets = []
    else:
        expected_targets = sorted(manifest)
        if len(expected_targets) != len(set(expected_targets)):
            errors.append("%s manifest page paths must be unique" % label)
    expected_target_set = set(expected_targets)

    frozen_semantics = None
    if not historical and authorized_page_semantic_fingerprints is not None:
        if not isinstance(authorized_page_semantic_fingerprints, dict):
            errors.append(
                "%s authorized page semantic fingerprints must be a "
                "target-to-sha256 mapping" % label)
        else:
            supplied_targets = set(authorized_page_semantic_fingerprints)
            bad_values = sorted(
                target for target, value in
                authorized_page_semantic_fingerprints.items()
                if (not nonempty_string(target) or
                    not isinstance(value, str) or
                    not SHA256_RE.fullmatch(value)))
            if supplied_targets != expected_target_set:
                errors.append(
                    "%s authorized page semantic fingerprint targets do not "
                    "equal the exact manifest" % label)
            if bad_values:
                errors.append(
                    "%s authorized page semantic fingerprints have invalid "
                    "values for: %s" % (label, ", ".join(bad_values)))
            if supplied_targets == expected_target_set and not bad_values:
                frozen_semantics = dict(
                    authorized_page_semantic_fingerprints)

    ids = aggregate.get("page_review_receipts")
    if (not isinstance(ids, list) or
            any(not nonempty_string(value) for value in ids)):
        errors.append("%s page_review_receipts must be a string list" % label)
        ids = []
    elif ids != sorted(ids):
        errors.append("%s page_review_receipts must be sorted" % label)
    if len(ids) != len(set(ids)):
        errors.append("%s page_review_receipts must be unique" % label)
    reserved_receipt_ids = {
        value for value in (
            aggregate_id,
            aggregate.get("global_review_receipt"),
            aggregate.get("reviewer_attestation_receipt"),
            aggregate.get("queue_consistency_receipt"),
            aggregate.get("delta_apply_receipt"),
            aggregate.get("corpus_plan_receipt"),
        ) if nonempty_string(value)
    }
    evidence = aggregate.get("closed_list_evidence")
    if isinstance(evidence, dict):
        reserved_receipt_ids.update(
            value for value in evidence.values()
            if nonempty_string(value))
    overlaps = sorted(set(ids).intersection(reserved_receipt_ids))
    if overlaps:
        errors.append(
            "%s page review children must use receipt IDs distinct from "
            "the aggregate and its non-page evidence: %s" %
            (label, ", ".join(overlaps)))
    count = aggregate.get("page_review_receipt_count")
    if (not isinstance(count, int) or isinstance(count, bool) or
            count < 0 or count != len(ids)):
        errors.append(
            "%s page_review_receipt_count must equal the exact receipt list" %
            label)
    set_sha = aggregate.get("page_review_receipt_set_sha256")
    expected_set_sha = candidate_lifecycle.candidate_set_sha256(ids)
    if (not isinstance(set_sha, str) or not SHA256_RE.fullmatch(set_sha) or
            set_sha != expected_set_sha):
        errors.append(
            "%s page_review_receipt_set_sha256 does not bind the exact "
            "sorted receipt-ID set" % label)

    profile_bindings = {
        field: aggregate.get(field)
        for field in profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS
    }
    expected_profile = dict(zip(
        profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS,
        (
            selected_profile_manifest,
            profile_snapshot_sha256,
            profile_contract_fingerprint,
            profile_load_inputs_sha256,
        ),
    ))
    live_profile_view = dict(profile_bindings)
    live_profile_view.update({
        field: value for field, value in expected_profile.items()
        if value is not None
    })
    metadata_fingerprint = aggregate.get(
        "metadata_execution_contract_fingerprint")

    projection_rules = None
    live_metadata_fingerprint = None
    if not historical:
        if root is None:
            errors.append(
                "%s current page-review validation requires repository root" %
                label)
        else:
            try:
                contract = authorized_metadata_contract
                if contract is None:
                    contract = metadata_execution_contract.\
                        load_metadata_execution_contract(root)
                elif not isinstance(
                        contract,
                        metadata_execution_contract.
                        CompiledMetadataExecutionContract):
                    raise ValueError(
                        "authorized metadata contract has the wrong type")
                live_metadata_fingerprint = contract.contract_fingerprint
                extension_gates = getattr(
                    authorized_profile_contract, "extension_gates", None)
                if extension_gates is None:
                    raise ValueError(
                        "no authorized typed Profile contract was supplied")
                if (getattr(authorized_profile_contract, "authorized", False)
                        is not True or
                        getattr(
                            authorized_profile_contract,
                            "manifest_repo_path", None) !=
                        profile_bindings["selected_profile_manifest"] or
                        getattr(
                            authorized_profile_contract,
                            "profile_contract_fingerprint", None) !=
                        profile_bindings["profile_contract_fingerprint"]):
                    raise ValueError(
                        "typed Profile contract does not match the exact "
                        "authorized fingerprint")
                projection_rules = metadata_property_state.\
                    profile_gate_projection_rules(
                        root, extension_gates, metadata_contract=contract,
                        authorized_profile_contract=
                            authorized_profile_contract)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(
                    "%s cannot authorize current metadata/Profile execution "
                    "context: %s" %
                    (label, exc))
    errors.extend(evidence_identity_errors(
        aggregate, label,
        use=(EVIDENCE_USE_TERMINAL_HISTORY if historical else
             EVIDENCE_USE_CURRENT_AUTHORIZATION),
        profile_view=live_profile_view,
        metadata_contract_fingerprint=live_metadata_fingerprint))

    targets = []
    for index, page_receipt_id in enumerate(ids):
        child_label = "%s page review child[%d]" % (item_id, index)
        child = require_receipt(
            catalog, page_receipt_id, child_label, errors,
            expected={
                "tool": BATCH_CLOSE_TOOL,
                "tool_version": BATCH_CLOSE_TOOL_VERSION,
                "check": "page_review_acceptance",
                "result": "pass",
                "task_id": task_id,
                "batch_id": item_id,
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "reviewer_attestation_receipt": attestation_id,
                "merged_snapshot_sha256": merged_snapshot_sha256,
                "metadata_execution_contract_fingerprint":
                    metadata_fingerprint,
                **profile_bindings,
            },
        )
        if not isinstance(child, dict):
            continue
        target = child.get("target")
        if not nonempty_string(target):
            errors.append("%s target must be a non-empty page path" %
                          child_label)
            continue
        targets.append(target)
        checked_at = timestamp_value(child.get("checked_at"))
        reviewed_on = child.get("reviewed_on")
        if checked_at is None:
            errors.append("%s checked_at must be an RFC 3339 instant" %
                          child_label)
        expected_date = (checked_at.date().isoformat()
                         if checked_at is not None else None)
        try:
            parsed_date = datetime.date.fromisoformat(reviewed_on)
        except (TypeError, ValueError):
            parsed_date = None
        if parsed_date is None or reviewed_on != expected_date:
            errors.append(
                "%s reviewed_on must equal its own checked_at UTC date" %
                child_label)
        semantic = child.get("semantic_content_sha256")
        if not isinstance(semantic, str) or not SHA256_RE.fullmatch(semantic):
            errors.append(
                "%s semantic_content_sha256 must be a sha256 fingerprint" %
                child_label)
        if (not historical and root is not None and
                projection_rules is not None and
                target in expected_target_set):
            if frozen_semantics is not None:
                current_semantic = frozen_semantics[target]
            else:
                try:
                    page = kblib.repository_target_snapshot(
                        root, target, suffixes=".md", singly_linked=True)
                    if not page.exists:
                        raise ValueError("page does not exist")
                    current_semantic = \
                        project_page_state.semantic_content_fingerprint(
                            target, page.read_text(), projection_rules)
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append("%s cannot re-read exact target: %s" %
                                  (child_label, exc))
                    current_semantic = None
            if (current_semantic is not None and
                    semantic != current_semantic):
                errors.append(
                    "%s semantic_content_sha256 does not match the "
                    "authorized current page content" % child_label)

    if sorted(targets) != expected_targets:
        errors.append(
            "%s page review child targets %r do not equal exact manifest %r" %
            (label, sorted(targets), expected_targets))
    elif len(targets) != len(set(targets)):
        errors.append("%s page review child targets must be unique" % label)
    return errors, ids


def close_gate_receipt_errors(catalog, receipt_id, *, item_id, task_id,
                              root=None,
                              queue_revision, queue_state_revision,
                              required_queue_sha256,
                              coverage_ledger_sha256,
                              progress_ledger_sha256, delta_sha256,
                              queue_consistency_receipt,
                              delta_apply_receipt,
                              work_spec_path=None,
                              work_spec_sha256=None,
                              manifest=None,
                              selected_profile_manifest=None,
                              profile_snapshot_sha256=None,
                              profile_contract_fingerprint=None,
                              profile_load_inputs_sha256=None,
                              metadata_execution_contract_fingerprint=None,
                              authorized_profile_contract=None,
                              authorized_metadata_contract=None,
                              authorized_page_semantic_fingerprints=None,
                              corpus_plan_required=None,
                              corpus_plan_triggers=None,
                              corpus_plan_expected_binding=None,
                              current_repository_snapshot_sha256=None,
                              historical=False):
    """Validate the independent merged-snapshot gate consumed by close.

    The gate is deliberately distinct from both the in-batch ``batch_gate``
    receipts and the K13/08 Queue consistency receipt.  It binds the exact
    post-apply/pre-close runtime bytes and the independently recomputed
    repository-content snapshot, then closes its producer era's K12/09 set
    with independently persisted evidence IDs.
    """
    errors = []
    label = "%s batch-close gate" % item_id
    # The producer version is validated separately below: a new close action
    # must use the current producer, while replay of a closed edge keeps the
    # finite protocol era whose shape its sealed bundle records.
    expected = {
        "tool": BATCH_CLOSE_TOOL,
        "check": "batch_close_gate",
        "target": item_id,
        "batch_id": item_id,
        "task_id": task_id,
        "queue_revision": queue_revision,
        "queue_state_revision": queue_state_revision,
        "required_queue_sha256": required_queue_sha256,
        "coverage_ledger_sha256": coverage_ledger_sha256,
        "progress_ledger_sha256": progress_ledger_sha256,
        "delta_sha256": delta_sha256,
        "queue_consistency_receipt": queue_consistency_receipt,
        "delta_apply_receipt": delta_apply_receipt,
    }
    receipt = require_receipt(
        catalog, receipt_id, label, errors,
        expected=expected,
    )
    if receipt is None:
        return errors
    receipt_version = receipt.get("tool_version")
    allowed_versions = (SUPPORTED_BATCH_CLOSE_TOOL_VERSIONS
                        if historical else
                        frozenset((BATCH_CLOSE_TOOL_VERSION,)))
    if receipt_version not in allowed_versions:
        protocol = ("historical producer era" if historical else
                    "current close action")
        errors.append(
            "%s receipt %s has unsupported tool_version=%r for %s; "
            "expected one of %s" % (
                label, receipt_id, receipt_version, protocol,
                sorted(allowed_versions))
        )
    if receipt_version == BATCH_CLOSE_TOOL_VERSION:
        errors.extend(close_settlement_binding_errors(
            receipt, "%s receipt %s" % (label, receipt_id)))
    for field, value in (
            ("work_spec_path", work_spec_path),
            ("work_spec_sha256", work_spec_sha256)):
        if field not in receipt:
            errors.append(
                "%s receipt %s misses explicit %s" %
                (label, receipt_id, field)
            )
        elif receipt.get(field) != value:
            errors.append(
                "%s receipt %s has %s=%r, expected %r" %
                (label, receipt_id, field, receipt.get(field), value)
            )
    if (corpus_plan_required is not None and
            receipt.get("corpus_plan_required") != corpus_plan_required):
        errors.append(
            "%s receipt %s has corpus_plan_required=%r, expected %r" %
            (label, receipt_id, receipt.get("corpus_plan_required"),
             corpus_plan_required)
        )
    if (corpus_plan_triggers is not None and
            receipt.get("corpus_plan_triggers") != corpus_plan_triggers):
        errors.append(
            "%s receipt %s has corpus_plan_triggers=%r, expected %r" %
            (label, receipt_id, receipt.get("corpus_plan_triggers"),
             corpus_plan_triggers)
        )
    entry = catalog.get(receipt_id)
    if entry is not None and entry[0] == "<pending-write>":
        errors.append("%s receipt %s is not persisted in the repository" %
                      (label, receipt_id))

    merged_snapshot_sha256 = receipt.get("merged_snapshot_sha256")
    if (not isinstance(merged_snapshot_sha256, str) or
            not SHA256_RE.fullmatch(merged_snapshot_sha256)):
        errors.append("%s receipt %s merged_snapshot_sha256 must be a valid "
                      "sha256 fingerprint" % (label, receipt_id))
    elif (current_repository_snapshot_sha256 is not None and
          merged_snapshot_sha256 != current_repository_snapshot_sha256):
        errors.append(
            "%s receipt %s merged_snapshot_sha256=%r does not match the "
            "current repository snapshot %r" %
            (label, receipt_id, merged_snapshot_sha256,
             current_repository_snapshot_sha256)
        )

    actual_corpus_required = receipt.get("corpus_plan_required")
    actual_corpus_triggers = receipt.get("corpus_plan_triggers")
    corpus_receipt_id = receipt.get("corpus_plan_receipt")
    if not isinstance(actual_corpus_required, bool):
        errors.append(
            "%s receipt %s corpus_plan_required must be an explicit boolean" %
            (label, receipt_id))
    trigger_issues = corpus_planning_contract.close_trigger_issues(
        actual_corpus_required, actual_corpus_triggers)
    if any(issue["code"] == "trigger_list" for issue in trigger_issues):
        actual_corpus_triggers = []
    for issue in trigger_issues:
        if issue["code"] == "trigger_list":
            errors.append(
                "%s receipt %s corpus_plan_triggers must be an explicit "
                "string list" % (label, receipt_id))
        elif issue["code"] == "trigger_order":
            errors.append(
                "%s receipt %s corpus_plan_triggers must be unique and "
                "sorted" % (label, receipt_id))
        elif issue["code"] == "trigger_unsupported":
            errors.append(
                "%s receipt %s has unsupported corpus-plan trigger(s): %s" %
                (label, receipt_id, ", ".join(issue["values"])))
        elif issue["code"] == "inactive_triggers":
            errors.append(
                "%s receipt %s non-applicable corpus plan must use no "
                "triggers" % (label, receipt_id))
        elif issue["code"] == "required_trigger_missing":
            errors.append(
                "%s receipt %s required corpus plan has no trigger" %
                (label, receipt_id))
    if actual_corpus_required is False:
        if corpus_receipt_id is not None:
            errors.append(
                "%s receipt %s non-applicable corpus plan must use "
                "corpus_plan_receipt=null" % (label, receipt_id))
    elif actual_corpus_required is True:
        corpus_tool_version = CORPUS_PLAN_TOOL_VERSION
        if historical and receipt_version != BATCH_CLOSE_TOOL_VERSION:
            corpus_tool_version = \
                HISTORICAL_CORPUS_PLAN_TOOL_VERSIONS.get(receipt_version)
            if corpus_tool_version is None:
                errors.append(
                    "%s receipt %s has no registered historical Corpus "
                    "Planning child protocol for batch-close %r" %
                    (label, receipt_id, receipt_version))
        corpus_expected = {
            "tool": CORPUS_PLAN_TOOL,
            "tool_version": corpus_tool_version,
            "check": "corpus_plan",
            "result": "pass",
            "task_id": task_id,
            "queue_revision": queue_revision,
            "queue_state_revision": queue_state_revision,
            "required_queue_sha256": required_queue_sha256,
            "coverage_ledger_sha256": coverage_ledger_sha256,
            "progress_ledger_sha256": progress_ledger_sha256,
            "repository_snapshot_sha256": merged_snapshot_sha256,
        }
        if selected_profile_manifest is not None:
            corpus_expected.update({
                "target": selected_profile_manifest,
                "selected_profile_manifest": selected_profile_manifest,
            })
        corpus_receipt = require_receipt(
            catalog, corpus_receipt_id,
            "%s Corpus Planning child" % item_id, errors,
            expected=corpus_expected,
        )
        if isinstance(corpus_receipt, dict):
            if corpus_plan_expected_binding is not None:
                if not isinstance(corpus_plan_expected_binding, dict):
                    errors.append(
                        "%s Corpus Planning expected binding must be a "
                        "mapping" % item_id)
                else:
                    differences = corpus_planning_contract.\
                        receipt_binding_differences(
                            corpus_receipt, corpus_plan_expected_binding,
                            fields=sorted(corpus_plan_expected_binding))
                    for difference in differences:
                        errors.append(
                            "%s Corpus Planning child %s has %s=%r, "
                            "expected current %r" % (
                                item_id, corpus_receipt_id,
                                difference["field"], difference["actual"],
                                difference["expected"]))
            applicability = corpus_receipt.get("corpus_plan_applicability")
            if applicability not in \
                    corpus_planning_contract.APPLICABILITY_STATES:
                errors.append(
                    "%s Corpus Planning child %s has invalid applicability %r" %
                    (item_id, corpus_receipt_id, applicability))
            if (corpus_planning_contract.CLOSE_ROUTE_TRIGGER in
                    actual_corpus_triggers and applicability !=
                    corpus_planning_contract.CONFIGURED_STATE):
                errors.append(
                    "%s R13 close requires a configured Corpus Planning child" %
                    item_id)
            for issue in corpus_planning_contract.\
                    receipt_path_currentness_issues(
                        corpus_receipt, applicability):
                path_field = issue["path_field"]
                sha_field = issue["sha256_field"]
                if issue["code"] == "required_path":
                    errors.append(
                        "%s Corpus Planning child %s lacks %s" %
                        (item_id, corpus_receipt_id, path_field))
                elif issue["code"] == "required_sha256":
                    errors.append(
                        "%s Corpus Planning child %s has invalid %s" %
                        (item_id, corpus_receipt_id, sha_field))
                elif issue["code"] == "inactive_pair_missing":
                    errors.append(
                        "%s inactive Corpus Planning child %s must "
                        "explicitly bind null %s/%s" % (
                            item_id, corpus_receipt_id, path_field, sha_field))
                else:
                    errors.append(
                        "%s inactive Corpus Planning child %s must use null "
                        "%s/%s" % (
                            item_id, corpus_receipt_id, path_field, sha_field))

    require_receipt(
        catalog, queue_consistency_receipt,
        "%s Queue consistency snapshot" % item_id, errors,
        expected={
            "tool": TOOL,
            # K12/10 producer-era identity: a close bundle sealed under an
            # accounted era keeps the consistency snapshot its own runtime
            # produced; it is never re-judged against this checker's
            # current constant after an upgrade.
            "tool_version": ANY_PRODUCER_ERA_VERSION,
            "check": "required_queue",
            "queue_check_mode": "consistency",
            "repository_snapshot_sha256": merged_snapshot_sha256,
        },
    )

    global_review_id = receipt.get("global_review_receipt")
    global_review = require_receipt(
        catalog, global_review_id, "%s global review" % item_id, errors,
        expected={
            "tool": BATCH_CLOSE_TOOL,
            "tool_version": receipt_version,
            "check": "batch_global_review",
            "target": item_id,
            "batch_id": item_id,
            "task_id": task_id,
            "merged_snapshot_sha256": merged_snapshot_sha256,
        },
    )

    integrator_id = receipt.get("integrator_id")
    reviewer_id = receipt.get("reviewer_id")
    for field, value in (("integrator_id", integrator_id),
                         ("reviewer_id", reviewer_id)):
        if not nonempty_string(value):
            errors.append("%s receipt %s %s must be a non-empty declared label" %
                          (label, receipt_id, field))
    if (nonempty_string(integrator_id) and nonempty_string(reviewer_id) and
            integrator_id.casefold() == reviewer_id.casefold()):
        errors.append("%s receipt %s integrator and reviewer must use "
                      "different declared labels" % (label, receipt_id))

    attestation_id = receipt.get("reviewer_attestation_receipt")
    if isinstance(global_review, dict):
        for field, value in (("integrator_id", integrator_id),
                             ("reviewer_id", reviewer_id),
                             ("reviewer_attestation_receipt", attestation_id)):
            if global_review.get(field) != value:
                errors.append("%s global review receipt %s has %s=%r, "
                              "expected %r" %
                              (item_id, global_review_id, field,
                               global_review.get(field), value))
    attestation = require_receipt(
        catalog, attestation_id, "%s declared reviewer attestation" %
        item_id, errors,
        expected={
            "tool": BATCH_CLOSE_TOOL,
            "tool_version": receipt_version,
            "check": "batch_global_review_attestation",
            "target": item_id,
            "batch_id": item_id,
            "task_id": task_id,
            "integrator_id": integrator_id,
            "reviewer_id": reviewer_id,
            "merged_snapshot_sha256": merged_snapshot_sha256,
        },
    )
    if (isinstance(attestation, dict) and
            receipt_version in COMPACT_CLOSE_EVIDENCE_VERSIONS):
        if not nonempty_string(attestation.get("details")):
            errors.append("%s declared reviewer attestation %s has no "
                          "review statement" % (item_id, attestation_id))
        errors.extend(_compact_attestation_errors(
            attestation, attestation_id, item_id, root=root,
            receipt_version=receipt_version))
    elif isinstance(attestation, dict):
        if not nonempty_string(attestation.get("details")):
            errors.append("%s declared reviewer attestation %s has no "
                          "review statement" % (item_id, attestation_id))
        accepted_ids = attestation.get("accepted_candidate_ids")
        accepted_types = attestation.get("accepted_candidate_types")
        dispositions = attestation.get("candidate_dispositions")
        if not isinstance(accepted_ids, list) or any(
                not nonempty_string(value) for value in accepted_ids):
            errors.append("%s declared reviewer attestation %s "
                          "accepted_candidate_ids must be a string list" %
                          (item_id, attestation_id))
            accepted_ids = []
        if not isinstance(accepted_types, list) or any(
                not nonempty_string(value) for value in accepted_types):
            errors.append("%s declared reviewer attestation %s "
                          "accepted_candidate_types must be a string list" %
                          (item_id, attestation_id))
            accepted_types = []
        if len(accepted_ids) != len(set(accepted_ids)):
            errors.append("%s declared reviewer attestation %s repeats an "
                          "accepted candidate ID" % (item_id, attestation_id))
        if len(accepted_types) != len(set(accepted_types)):
            errors.append("%s declared reviewer attestation %s repeats an "
                          "accepted candidate type" %
                          (item_id, attestation_id))
        if not isinstance(dispositions, list):
            errors.append("%s declared reviewer attestation %s "
                          "candidate_dispositions must be a list" %
                          (item_id, attestation_id))
            dispositions = []
        disposition_ids = []
        disposition_types = []
        for index, disposition in enumerate(dispositions):
            disposition_label = "%s candidate_dispositions[%d]" % (
                item_id, index)
            if not isinstance(disposition, dict):
                errors.append("%s must be a mapping" % disposition_label)
                continue
            candidate_id = disposition.get("candidate_id")
            candidate_type = disposition.get("candidate_type")
            if (not nonempty_string(candidate_id) or
                    not candidate_id.startswith("candidate-sha256:") or
                    not SHA256_RE.fullmatch(candidate_id.replace(
                        "candidate-sha256:", "sha256:", 1))):
                errors.append("%s has invalid stable candidate_id" %
                              disposition_label)
            else:
                disposition_ids.append(candidate_id)
            if (not nonempty_string(candidate_type) or
                    ":" not in candidate_type):
                errors.append("%s has invalid candidate_type" %
                              disposition_label)
            else:
                disposition_types.append(candidate_type)
            accepted_by = disposition.get("accepted_by")
            if isinstance(accepted_by, str) and accepted_by.startswith(
                    "policy-exception:"):
                # K00/07: a priority-quota excess is consumed only through a
                # bounded contract exception.  The disposition seals the
                # decision facts so this receipt replays as history even
                # after the exception is revoked or the task ends; replay
                # validates the sealed record, never current contract state.
                decision_id = accepted_by.split(":", 1)[1]
                if receipt_version not in \
                        POLICY_EXCEPTION_DISPOSITION_VERSIONS:
                    errors.append(
                        "%s claims a policy-exception disposition, but its "
                        "producer era %s predates that protocol; an older "
                        "bundle cannot carry evidence its era could not "
                        "have produced" % (disposition_label,
                                           receipt_version))
                sealed = disposition.get("policy_exception")
                if not nonempty_string(decision_id):
                    errors.append("%s has empty policy-exception decision" %
                                  disposition_label)
                elif not isinstance(sealed, dict):
                    errors.append(
                        "%s policy-exception disposition seals no decision "
                        "facts" % disposition_label)
                else:
                    errors.extend(sealed_policy_exception_errors(
                        sealed, decision_id, candidate_type,
                        disposition_label))
            elif accepted_by not in ("candidate-id", "candidate-type"):
                errors.append("%s has invalid accepted_by" %
                              disposition_label)
        if sorted(disposition_ids) != sorted(accepted_ids):
            errors.append("%s declared reviewer attestation %s accepted "
                          "candidate IDs do not equal its dispositions" %
                          (item_id, attestation_id))
        if sorted(set(disposition_types)) != sorted(accepted_types):
            errors.append("%s declared reviewer attestation %s accepted "
                          "candidate types do not equal its dispositions" %
                          (item_id, attestation_id))

    page_review_ids = []
    if receipt_version == BATCH_CLOSE_TOOL_VERSION:
        page_review_errors, page_review_ids = \
            _page_review_acceptance_errors(
                catalog, receipt, receipt_id,
                item_id=item_id, task_id=task_id, manifest=manifest,
                integrator_id=integrator_id, reviewer_id=reviewer_id,
                attestation_id=attestation_id,
                merged_snapshot_sha256=merged_snapshot_sha256,
                root=root, historical=historical,
                selected_profile_manifest=selected_profile_manifest,
                profile_snapshot_sha256=profile_snapshot_sha256,
                profile_contract_fingerprint=profile_contract_fingerprint,
                profile_load_inputs_sha256=profile_load_inputs_sha256,
                metadata_execution_contract_fingerprint=
                    metadata_execution_contract_fingerprint,
                authorized_profile_contract=authorized_profile_contract,
                authorized_metadata_contract=authorized_metadata_contract,
                authorized_page_semantic_fingerprints=
                    authorized_page_semantic_fingerprints,
            )
        errors.extend(page_review_errors)

    evidence = receipt.get("closed_list_evidence")
    # The Closed List a bundle answers to is the one its producer era ran:
    # a pre-1.5.0 bundle carries seven members forever (K12/10 producer-era
    # identity), a current bundle carries the full list.
    era_fields = \
        batch_close_contract.closed_list_evidence_fields_for_producer_version(
            receipt_version)
    expected_fields = set(era_fields)
    if not isinstance(evidence, dict):
        errors.append("%s receipt %s closed_list_evidence must be a mapping" %
                      (label, receipt_id))
        return errors
    missing = sorted(expected_fields - set(evidence))
    extra = sorted(set(evidence) - expected_fields)
    if missing:
        errors.append("%s receipt %s closed_list_evidence misses: %s" %
                      (label, receipt_id, ", ".join(missing)))
    if extra:
        errors.append("%s receipt %s closed_list_evidence has unsupported "
                      "member(s): %s" %
                      (label, receipt_id, ", ".join(extra)))
    evidence_ids = []
    for field in era_fields:
        evidence_id = evidence.get(field)
        if not nonempty_string(evidence_id):
            errors.append("%s receipt %s closed_list_evidence.%s must identify "
                          "a receipt" % (label, receipt_id, field))
            continue
        evidence_ids.append(evidence_id)
        require_receipt(
            catalog, evidence_id,
            "%s Closed List member %s" % (item_id, field), errors,
            expected={
                "tool": BATCH_CLOSE_TOOL,
                "tool_version": receipt_version,
                "check": "closed_list_%s" % field,
                "target": ".",
                "batch_id": item_id,
                "task_id": task_id,
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "merged_snapshot_sha256": merged_snapshot_sha256,
            },
        )
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("%s receipt %s closed_list_evidence must use one "
                      "distinct receipt ID per Closed List member" %
                      (label, receipt_id))
    if receipt_id in evidence_ids:
        errors.append("%s receipt %s cannot cite itself as Closed List "
                      "evidence" % (label, receipt_id))
    if global_review_id in evidence_ids or global_review_id == receipt_id:
        errors.append("%s receipt %s global_review_receipt must be a distinct "
                      "record from the aggregator and the Closed List members" %
                      (label, receipt_id))
    if attestation_id in evidence_ids or attestation_id in (
            global_review_id, receipt_id):
        errors.append("%s receipt %s reviewer attestation must be a distinct "
                      "record from the aggregator, global review, and the Closed "
                      "List members" % (label, receipt_id))
    if page_review_ids:
        reserved = set(evidence_ids + [
            receipt_id, global_review_id, attestation_id,
            queue_consistency_receipt, delta_apply_receipt,
        ])
        if corpus_receipt_id is not None:
            reserved.add(corpus_receipt_id)
        reused = sorted(set(page_review_ids).intersection(reserved))
        if reused:
            errors.append(
                "%s receipt %s page-review children must be distinct from "
                "the aggregator and every other close-evidence record: %s" %
                (label, receipt_id, ", ".join(reused)))
    if (isinstance(global_review, dict) and
            global_review.get("closed_list_evidence") != evidence):
        errors.append("%s global review receipt %s does not bind the same "
                      "Closed List evidence mapping" %
                      (item_id, global_review_id))
    if corpus_receipt_id is not None and corpus_receipt_id in (
            evidence_ids + [receipt_id, global_review_id, attestation_id,
                            queue_consistency_receipt, delta_apply_receipt]):
        errors.append(
            "%s receipt %s Corpus Planning child must be distinct from the "
            "aggregator and all other close evidence" % (label, receipt_id))
    return errors


def closed_bundle_seal_state(item, catalog):
    """Classify one closed item's evidence trio against the cold index.

    The trio -- batch-close gate, pre-close Queue consistency snapshot, and
    Coverage delta application -- is sealed together or not at all, because
    a half-sealed bundle can neither replay the hot revalidation nor claim
    the sealed short-circuit.  Returns ``"hot"``, ``"sealed"``, or
    ``"mixed"``.
    """
    cold = getattr(catalog, "cold", None) or {}
    trio = [item.get("close_gate_receipt"),
            item.get("queue_consistency_receipt"),
            item.get("delta_apply_receipt")]
    sealed = [receipt_id for receipt_id in trio
              if nonempty_string(receipt_id) and receipt_id in cold]
    if not sealed:
        return "hot"
    if len(sealed) != len([r for r in trio if nonempty_string(r)]):
        return "mixed"
    return "sealed"


def sealed_closed_bundle_errors(item, transition, catalog, queue):
    """Validate one sealed close bundle through its thin projections.

    Reading a projection is sound here only because ``cold_receipt_store``
    has already proved, this run, that each projection hashes to the exact
    sealed record it names and that the seal receipt which produced it
    still binds the whole index row set byte for byte.  Without those two
    proofs a projection would be an editable side table asserting its own
    correctness, and this function would be reading the claim instead of
    the evidence.

    Given them, the per-run obligation drops to identity: the projections
    still name the receipts this item and its close transition bind, with
    the identities their producers recorded.  Body-level bindings (snapshot
    hashes, delta hashes, disposition schemas) were proven at seal time
    against exactly the bytes still on disk, and sealing refuses any bundle
    whose full frozen-history revalidation does not pass at that moment.
    """
    errors = []
    item_id = item.get("id", "<unknown>")
    cold = getattr(catalog, "cold", None) or {}
    close_gate_id = item.get("close_gate_receipt")
    consistency_id = item.get("queue_consistency_receipt")
    delta_apply_id = item.get("delta_apply_receipt")
    expectations = (
        (close_gate_id, "%s sealed batch-close gate" % item_id, {
            "tool": BATCH_CLOSE_TOOL,
            "check": "batch_close_gate",
            "target": item_id,
            "batch_id": item_id,
            "task_id": queue.get("task_id"),
            "result": "pass",
        }),
        (consistency_id, "%s sealed Queue consistency gate" % item_id, {
            "tool": TOOL,
            "check": GATE_CHECK,
            "queue_check_mode": "consistency",
            "task_id": queue.get("task_id"),
            "result": "pass",
        }),
        (delta_apply_id, "%s sealed delta application" % item_id, {
            "tool": "apply_delta",
            "check": "delta_apply",
            "target": item_id,
            "batch_id": item_id,
            "task_id": queue.get("task_id"),
            "result": "pass",
        }),
    )
    for receipt_id, label, expected in expectations:
        projection = cold.get(receipt_id)
        if projection is None:
            errors.append("%s projection is absent from the cold index" %
                          label)
            continue
        for field, value in expected.items():
            if projection.get(field) != value:
                errors.append("%s projection has %s=%r, expected %r" %
                              (label, field, projection.get(field), value))
    close_projection = cold.get(close_gate_id) or {}
    close_version = close_projection.get("tool_version")
    if close_version not in SUPPORTED_BATCH_CLOSE_TOOL_VERSIONS:
        errors.append("%s sealed batch-close gate has unsupported producer "
                      "era %r" % (item_id, close_version))
    if transition is None:
        return errors
    if transition.get("queue_consistency_receipt") != consistency_id:
        errors.append("%s close transition does not bind Queue consistency "
                      "receipt %s" % (item_id, consistency_id))
    if transition.get("close_gate_receipt") != close_gate_id:
        errors.append("%s close transition does not bind batch-close gate "
                      "receipt %s" % (item_id, close_gate_id))
    if transition.get("evidence_receipt") != close_gate_id:
        errors.append("%s close transition evidence_receipt must be the "
                      "independent batch-close gate" % item_id)
    if transition.get("delta_apply_receipt") != delta_apply_id:
        errors.append("%s close transition does not bind delta application "
                      "receipt %s" % (item_id, delta_apply_id))
    return errors


def closed_gate_errors(item, transition, catalog, queue,
                        accounted_versions=frozenset(), root=None):
    """Revalidate the two independent pre-close gates from frozen history."""
    errors = []
    item_id = item.get("id", "<unknown>")
    consistency_id = item.get("queue_consistency_receipt")
    close_gate_id = item.get("close_gate_receipt")
    close_gate_entry = catalog.get(close_gate_id)
    close_gate_identity = (close_gate_entry[1]
                           if close_gate_entry is not None else {})
    consistency_expected = {
        "tool": TOOL,
        "check": "required_queue",
        "queue_check_mode": "consistency",
        "task_id": queue.get("task_id"),
    }
    if transition is not None:
        consistency_expected.update({
            "queue_revision": transition.get("queue_revision"),
            "queue_state_revision": transition.get("before_state_revision"),
            "required_queue_sha256":
                transition.get("before_required_queue_sha256"),
            "coverage_ledger_sha256":
                transition.get("before_coverage_sha256"),
            "progress_ledger_sha256":
                transition.get("before_progress_sha256"),
        })
    consistency_receipt = require_receipt(
        catalog, consistency_id, "%s Queue consistency gate" % item_id,
        errors, expected=consistency_expected,
    )
    # Historical: a closed batch's pre-close Queue consistency gate, bound to
    # the frozen before-bytes of a transition that already happened.
    errors.extend(producer_era_errors(
        consistency_receipt, consistency_id,
        "%s Queue consistency gate" % item_id, accounted_versions))
    if transition is None:
        # Transition-history validation reports the missing edge.  Avoid
        # inventing live-state bindings for an unanchored historical gate.
        return errors
    if transition.get("queue_consistency_receipt") != consistency_id:
        errors.append("%s close transition does not bind Queue consistency "
                      "receipt %s" % (item_id, consistency_id))
    if transition.get("close_gate_receipt") != close_gate_id:
        errors.append("%s close transition does not bind batch-close gate "
                      "receipt %s" % (item_id, close_gate_id))
    if transition.get("evidence_receipt") != close_gate_id:
        errors.append("%s close transition evidence_receipt must be the "
                      "independent batch-close gate" % item_id)
    errors.extend(close_gate_receipt_errors(
        catalog, close_gate_id,
        item_id=item_id,
        root=root,
        task_id=queue.get("task_id"),
        queue_revision=transition.get("queue_revision"),
        queue_state_revision=transition.get("before_state_revision"),
        required_queue_sha256=
            transition.get("before_required_queue_sha256"),
        coverage_ledger_sha256=transition.get("before_coverage_sha256"),
        progress_ledger_sha256=transition.get("before_progress_sha256"),
        delta_sha256=item.get("delta_sha256"),
        queue_consistency_receipt=consistency_id,
        delta_apply_receipt=transition.get("delta_apply_receipt"),
        work_spec_path=item.get("work_spec_path"),
        work_spec_sha256=item.get("work_spec_sha256"),
        manifest=item.get("manifest"),
        # Historical closure is checked against the identity frozen by its
        # producer.  A later Standards adoption must not reinterpret a valid
        # closed edge using the live Profile.
        selected_profile_manifest=close_gate_identity.get(
            "selected_profile_manifest"),
        historical=True,
    ))
    return errors


def close_gate_reuse_errors(items_by_id):
    """Reject one snapshot-specific close assertion owning two histories."""
    errors = []
    owners = {}
    for item_id, item in sorted(items_by_id.items()):
        receipt_id = item.get("close_gate_receipt")
        if not nonempty_string(receipt_id):
            continue
        previous = owners.get(receipt_id)
        if previous is not None and previous != item_id:
            errors.append("batch-close gate receipt %s is reused by %s and %s" %
                          (receipt_id, previous, item_id))
        else:
            owners[receipt_id] = item_id
    return errors
