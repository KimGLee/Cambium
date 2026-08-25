#!/usr/bin/env python3
"""Apply one approved scope Amendment across Coverage, Queue, and Progress.

The default is a dry run.  The apply path holds the shared runtime writer lock,
appends a durable prepare receipt, replaces the three canonical documents one
at a time, and rolls all three back on an ordinary failure.  A process crash
can interrupt those replacements; the surviving lock owner metadata and
prepare receipt bind every before/planned-after fingerprint for recovery.
The registered change-class/authority binding is re-derived before planning
and again under that same lock; a registration never authorizes different
proposal bytes merely because its Amendment id still matches.
"""

import contextlib
import copy
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import compile_queue
import kblib
import amendment_policy
import metadata_execution_contract
import metadata_property_state
import project_page_state

TOOL = "apply_amendment"
TOOL_VERSION = "1.4.0"
PLAN_PREFIX = ".cambium/deltas/amendments"
RECEIPT_PATH = ".cambium/receipts/amendments.jsonl"
OPERATIONS = (
    "scope-replan", "cancel-batch", "gap-routing-reconciliation",
    "property-state-migration",
)
PLAN_FIELDS = (
    "schema_version", "amendment_id", "operation", "affected_pages",
    "affected_batches", "scope_version_before", "scope_version_after",
    "queue_revision_before", "queue_revision_after",
    "state_revision_before", "state_revision_after",
    "coverage_proposal_path", "coverage_proposal_sha256", "cancel_batch_id",
)
AMENDMENT_BINDINGS = {
    "operation": "operation",
    "affected_pages": "affected_pages",
    "affected_batches": "affected_batches",
    "scope_version_before": "scope_version_before",
    "scope_version_after": "scope_version_after",
    "queue_revision_before": "queue_revision_before",
    "queue_revision_after": "queue_revision_after",
    "state_revision_before": "state_revision_before",
    "state_revision_after": "state_revision_after",
    "coverage_proposal_path": "coverage_proposal_path",
    "coverage_proposal_sha256": "coverage_proposal_sha256",
    "cancel_batch_id": "cancel_batch_id",
}

PROPERTY_MIGRATION_BINDING_FIELDS = (
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
LEGACY_PROPERTY_ADOPTION_OPERATION = "legacy-property-adoption-v1"


# ---------------------------------------------------------------------------
# `--json` output (machine-readable receipts)
#
# Purely additive: without the flag not one byte of this tool's behaviour
# moves.  With it, everything written for a person goes to stderr and stdout
# carries this run's receipt objects, serialized verbatim as one canonical
# JSON array.
#
# Nothing is filtered or renamed.  `schemas/receipt.template.jsonl` guarantees
# only the base fields every receipt carries; extension fields differ per
# producer and are discoverable from the receipt itself, which is why that
# template says in its own text that its examples are "not the complete set".
# A field allowlist here would silently drop exactly the fields a caller came
# for.
#
# This tool's receipts are written from inside its transaction helpers, well
# below `main`, so the run collects them where they are handed to the receipt
# writer rather than threading an accumulator through every frame.
# ---------------------------------------------------------------------------
JSON_HELP = ("write this run's receipt objects to stdout as one canonical "
             "JSON array and move the human-readable report to stderr; "
             "receipt writing, verdicts, and exit codes are unchanged")

_JSON_RECEIPTS = []


def _record_receipts(receipts):
    """Remember the exact receipt objects handed to the receipt writer."""
    _JSON_RECEIPTS.extend(receipts)
    return receipts


def emit_json_receipts(receipts):
    """Write the exact receipt objects this run produced to real stdout.

    The one canonical serializer is `kblib.canonical_json_bytes`; this module
    owns no serializer of its own.  A run that produced no receipt writes
    nothing, which keeps the already-settled rejection shape (empty stdout,
    one line of reason on stderr, exit 1) intact.
    """
    if not receipts:
        return
    sys.stdout.write(
        kblib.canonical_json_bytes(list(receipts)).decode("utf-8") + "\n")


def _run_reporting_json(runner):
    """Run `runner`, reserving stdout for JSON and giving stderr the prose."""
    with contextlib.redirect_stdout(sys.stderr):
        exit_code = runner()
    emit_json_receipts(_JSON_RECEIPTS)
    return exit_code


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _load_managed(root, relative, prefix, must_exist=True):
    path = kblib.managed_repository_path(
        root, relative, prefix, suffixes=(".yaml", ".yml"),
        must_exist=must_exist,
    )
    if must_exist and not os.path.isfile(path):
        raise ValueError("managed YAML path is not a regular file: %s" % relative)
    raw = kblib.read_bytes(path)
    try:
        data = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("%s is not UTF-8: %s" % (relative, exc))
    if not isinstance(data, dict):
        raise ValueError("%s top level must be a mapping" % relative)
    return path, raw, data


def _canonical_list(value, label):
    if (not isinstance(value, list) or
            not all(_nonempty(item) for item in value)):
        raise ValueError("%s must be an explicit string list" % label)
    if len(value) != len(set(value)):
        raise ValueError("%s must not contain duplicates" % label)
    if value != sorted(value):
        raise ValueError("%s must be sorted for deterministic matching" % label)
    return value


def _validate_plan(plan):
    missing = [field for field in PLAN_FIELDS if field not in plan]
    extra = sorted(set(plan) - set(PLAN_FIELDS))
    if missing:
        raise ValueError("plan misses field(s): %s" % ", ".join(missing))
    if extra:
        raise ValueError("plan has unsupported field(s): %s" % ", ".join(extra))
    if plan.get("schema_version") != 1:
        raise ValueError("plan schema_version must be 1")
    if not _nonempty(plan.get("amendment_id")):
        raise ValueError("plan amendment_id must be a non-empty string")
    if plan.get("operation") not in OPERATIONS:
        raise ValueError("plan operation must be one of %s" %
                         ", ".join(OPERATIONS))
    _canonical_list(plan.get("affected_pages"), "affected_pages")
    _canonical_list(plan.get("affected_batches"), "affected_batches")
    before_scope = plan.get("scope_version_before")
    after_scope = plan.get("scope_version_after")
    if not _nonempty(before_scope) or not _nonempty(after_scope):
        raise ValueError("scope versions must be non-empty strings")
    if (plan["operation"] in (
            "gap-routing-reconciliation", "property-state-migration") and
            before_scope != after_scope):
        raise ValueError(
            "%s must preserve scope_version" % plan["operation"])
    if (plan["operation"] not in (
            "gap-routing-reconciliation", "property-state-migration") and
            before_scope == after_scope):
        raise ValueError("a scope/cancel Amendment must change scope_version")
    for field in ("queue_revision_before", "queue_revision_after",
                  "state_revision_before", "state_revision_after"):
        value = plan.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("%s must be a non-negative integer" % field)
    if plan["queue_revision_before"] < 1:
        raise ValueError("queue_revision_before must be at least 1")
    expected_queue_after = plan["queue_revision_before"] + 1
    if plan["queue_revision_after"] != expected_queue_after:
        raise ValueError("queue_revision_after must increment by exactly one")
    if plan["operation"] in (
            "scope-replan", "gap-routing-reconciliation",
            "property-state-migration"):
        if plan["state_revision_after"] != plan["state_revision_before"]:
            raise ValueError("%s must preserve state_revision" %
                             plan["operation"])
        if plan.get("cancel_batch_id") is not None:
            raise ValueError("%s cancel_batch_id must be null" %
                             plan["operation"])
    else:
        cancel_id = plan.get("cancel_batch_id")
        if not _nonempty(cancel_id):
            raise ValueError("cancel-batch requires cancel_batch_id")
        if plan["affected_batches"] != [cancel_id]:
            raise ValueError("cancel-batch affected_batches must contain only cancel_batch_id")
        if plan["state_revision_after"] != plan["state_revision_before"] + 1:
            raise ValueError("cancel-batch state_revision_after must increment by one")
    if (plan["operation"] == "property-state-migration" and
            plan["affected_batches"]):
        raise ValueError(
            "property-state-migration affected_batches must be empty")
    if not _nonempty(plan.get("coverage_proposal_path")):
        raise ValueError("coverage_proposal_path must be a non-empty string")
    if not check_queue.SHA256_RE.fullmatch(
            str(plan.get("coverage_proposal_sha256", ""))):
        raise ValueError("coverage_proposal_sha256 must be sha256:<64 lowercase hex>")


def _find_amendment(progress, plan, plan_path=None, plan_sha=None):
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        raise ValueError("Progress amendments must be an explicit list")
    matches = [entry for entry in amendments
               if isinstance(entry, dict) and
               entry.get("id") == plan["amendment_id"]]
    if len(matches) != 1:
        raise ValueError("Progress must contain exactly one matching Amendment %s" %
                         plan["amendment_id"])
    amendment = matches[0]
    if amendment.get("status") != "approved":
        raise ValueError("Progress Amendment status must be approved")
    if amendment.get("writeback_done") is not False:
        raise ValueError("Progress Amendment writeback_done must be false")
    if not _nonempty(amendment.get("approval_reference")):
        raise ValueError("Progress Amendment approval_reference must be non-empty")
    if not _nonempty(amendment.get("registration_receipt")):
        raise ValueError("Progress Amendment registration_receipt must be non-empty")
    if plan_path is not None and amendment.get("plan_path") != plan_path:
        raise ValueError("Progress Amendment plan_path does not match plan")
    if plan_sha is not None and amendment.get("plan_sha256") != plan_sha:
        raise ValueError("Progress Amendment plan_sha256 does not match plan")
    for amendment_field, plan_field in AMENDMENT_BINDINGS.items():
        if amendment.get(amendment_field) != plan.get(plan_field):
            raise ValueError("Progress Amendment %s does not match plan" %
                             amendment_field)
    pending = [entry for entry in amendments
               if isinstance(entry, dict) and
               entry.get("operation") in OPERATIONS and
               entry.get("status") == "approved" and
               entry.get("writeback_done") is False]
    if pending != [amendment]:
        raise ValueError("the selected plan must be the only pending "
                         "cross-Ledger Amendment")
    return amendment


def _transaction_chain_head(progress):
    verified = [entry for entry in progress.get("amendments", [])
                if isinstance(entry, dict) and
                entry.get("operation") in OPERATIONS and
                entry.get("status") == "verified" and
                entry.get("writeback_done") is True]
    if not verified:
        return 1, None
    last = verified[-1]
    sequence = last.get("transaction_sequence")
    receipt_id = last.get("verification_receipt")
    if (not isinstance(sequence, int) or isinstance(sequence, bool) or
            sequence < 1 or not _nonempty(receipt_id)):
        raise ValueError("verified Amendment transaction chain is malformed")
    return sequence + 1, receipt_id


def _map_by_id(values, field, label):
    if not isinstance(values, list):
        raise ValueError("%s must be an explicit list" % label)
    result = {}
    for index, value in enumerate(values):
        if not isinstance(value, dict) or not _nonempty(value.get(field)):
            raise ValueError("%s[%d] must have %s" % (label, index, field))
        key = value[field]
        if key in result:
            raise ValueError("%s repeats %s %s" % (label, field, key))
        result[key] = value
    return result


def _changed_keys(before, after):
    return sorted(key for key in set(before).union(after)
                  if before.get(key) != after.get(key))


def _property_state_migration_plan(
        root, current_pages, proposed_pages, affected_pages, profile_view):
    """Derive the exact legacy observation + page-removal subtransaction.

    The Amendment plan may declare the Coverage after-image, but it cannot
    declare that a historical date was earned.  This function therefore
    proves each marker against an immutable live page snapshot and composes
    its field set/value shapes from the authorized Profile plus the compiled
    Core metadata contract.  ``project_page_state`` remains the sole page
    transaction publisher.
    """
    selected = list(affected_pages)
    if selected != sorted(set(selected)):
        raise ValueError(
            "property-state-migration affected_pages must be sorted and "
            "unique")
    declared = {}
    for path in selected:
        before = current_pages.get(path)
        after = proposed_pages.get(path)
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise ValueError(
                "property-state-migration page %s is absent from one "
                "Coverage image" % path)
        if "property_state" in before:
            raise ValueError(
                "property-state-migration page %s already has current "
                "property_state" % path)
        if after.get("property_state") != {}:
            raise ValueError(
                "property-state-migration page %s must adopt explicit empty "
                "property_state" % path)
        legacy = after.get(check_queue.LEGACY_PROPERTY_STATE_FIELD, {})
        declared[path] = copy.deepcopy(legacy)
    metadata_contract, rules = \
        metadata_property_state.authorized_profile_projection_rules(
            root, profile_view)
    if not metadata_execution_contract.compiled_capability_supports(
            metadata_contract, LEGACY_PROPERTY_ADOPTION_OPERATION,
            LEGACY_PROPERTY_ADOPTION_OPERATION, kind="writer"):
        raise ValueError(
            "compiled metadata contract does not authorize the %s writer "
            "operation" % LEGACY_PROPERTY_ADOPTION_OPERATION)
    migration = metadata_property_state.build_legacy_property_removal_plan(
        root, selected, rules=rules, declared_legacy=declared)
    migration["metadata_execution_contract_fingerprint"] = \
        metadata_contract.contract_fingerprint
    migration["metadata_execution_rule_fingerprint"] = \
        migration["plan"].contract_rule_fingerprint
    migration["operation_capability"] = \
        LEGACY_PROPERTY_ADOPTION_OPERATION
    for field in (
            "selected_profile_manifest", "profile_snapshot_sha256",
            "profile_contract_fingerprint", "profile_load_inputs_sha256"):
        migration[field] = profile_view.get(field)
    return migration


def _property_state_migration_bindings(migration):
    return {
        "property_state_migration_records": copy.deepcopy(
            migration["records"]),
        "property_state_migration_count": migration["count"],
        "property_state_migration_set_sha256": migration["set_sha256"],
        "metadata_execution_contract_fingerprint": migration[
            "metadata_execution_contract_fingerprint"],
        "metadata_execution_rule_fingerprint": migration[
            "metadata_execution_rule_fingerprint"],
        "operation_capability": migration["operation_capability"],
        "selected_profile_manifest": migration[
            "selected_profile_manifest"],
        "profile_snapshot_sha256": migration["profile_snapshot_sha256"],
        "profile_contract_fingerprint": migration[
            "profile_contract_fingerprint"],
        "profile_load_inputs_sha256": migration[
            "profile_load_inputs_sha256"],
    }


def _require_property_state_migration_binding(amendment, migration):
    expected = _property_state_migration_bindings(migration)
    for field, value in expected.items():
        if amendment.get(field) != value:
            raise ValueError(
                "Progress Amendment %s does not match the current exact "
                "property migration" % field)


def _changed_gap_pages(current, proposal):
    changed_entries = set()
    for coverage, side in ((current, "current"), (proposal, "proposal")):
        gaps = coverage.get("open_gaps")
        if not isinstance(gaps, list):
            raise ValueError("%s Coverage open_gaps must be an explicit list" % side)
        encoded = []
        for index, gap in enumerate(gaps):
            if not isinstance(gap, dict) or not _nonempty(gap.get("page")):
                raise ValueError("%s Coverage open_gaps[%d] must name page" %
                                 (side, index))
            encoded.append((kblib.canonical_yaml({"gap": gap}), gap["page"]))
        if len(encoded) != len({entry[0] for entry in encoded}):
            raise ValueError("%s Coverage repeats an identical open gap" % side)
        if side == "current":
            current_entries = dict(encoded)
        else:
            proposal_entries = dict(encoded)
    for key in set(current_entries).symmetric_difference(proposal_entries):
        changed_entries.add((current_entries.get(key) or proposal_entries[key]))
    return changed_entries


def _validate_coverage_proposal(current, proposal, plan):
    if proposal.get("schema_version") != 1:
        raise ValueError("Coverage proposal schema_version must be 1")
    for field in ("task_id", "standards_version", "selected_profile_manifest"):
        if proposal.get(field) != current.get(field):
            raise ValueError("Coverage proposal may not change %s" % field)
    if current.get("scope_version") != plan["scope_version_before"]:
        raise ValueError("current Coverage scope_version does not match plan")
    if proposal.get("scope_version") != plan["scope_version_after"]:
        raise ValueError("Coverage proposal scope_version does not match plan")
    allowed_top_level = {
        "schema_version", "task_id", "updated_at", "scope_version",
        "standards_version", "selected_profile_manifest", "batch_specs",
        "maintenance_candidates", "pages", "open_gaps",
    }
    unexpected = sorted(
        field for field in (set(current).union(proposal)) - allowed_top_level
        if current.get(field) != proposal.get(field)
    )
    if unexpected:
        raise ValueError("Coverage proposal contains unsupported top-level "
                         "field(s): %s" % ", ".join(unexpected))
    if proposal.get("maintenance_candidates") != current.get(
            "maintenance_candidates"):
        raise ValueError(
            "scope/disposition Amendment may not rewrite "
            "maintenance_candidates"
        )
    current_pages = _map_by_id(current.get("pages"), "path", "Coverage pages")
    proposed_pages = _map_by_id(proposal.get("pages"), "path", "Coverage proposal pages")
    changed_pages = sorted(set(_changed_keys(current_pages, proposed_pages)).union(
        _changed_gap_pages(current, proposal)))
    if changed_pages != plan["affected_pages"]:
        raise ValueError("affected_pages does not exactly match Coverage changes; "
                         "found=%r expected=%r" %
                         (changed_pages, plan["affected_pages"]))
    current_specs = _map_by_id(current.get("batch_specs"), "id", "Coverage batch_specs")
    proposed_specs = _map_by_id(proposal.get("batch_specs"), "id",
                                "Coverage proposal batch_specs")
    changed_specs = _changed_keys(current_specs, proposed_specs)
    return current_pages, proposed_pages, changed_specs


def _structural_changes(before_queue, compiled_queue):
    before = _map_by_id(before_queue.get("required_queue"), "id", "Required Queue")
    after = _map_by_id(compiled_queue.get("required_queue"), "id",
                       "compiled Required Queue")
    fields = compile_queue.STRUCTURAL_FIELDS
    changed = []
    for item_id in sorted(set(before).union(after)):
        left = before.get(item_id)
        right = after.get(item_id)
        if (right is None and left is not None and
                left.get("state") in check_queue.TERMINAL_STATES):
            # Current batch_specs omits immutable Queue history by design.
            continue
        if left is None or right is None or any(
                left.get(field) != right.get(field) for field in fields):
            changed.append(item_id)
    return changed


def _sync_progress(progress, plan, queue, queue_text, transaction_id,
                   verification_receipt, transaction_sequence,
                   previous_transaction_commit_receipt, plan_path, plan_sha,
                   proposal_path, proposal_sha):
    result = copy.deepcopy(progress)
    contract = result.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("Progress contract must be a mapping")
    contract["scope_version"] = plan["scope_version_after"]
    result["queue_revision"] = queue["queue_revision"]
    result["queue_state_revision"] = queue["state_revision"]
    result["required_queue_sha256"] = kblib.sha256_bytes(queue_text)
    amendment = _find_amendment(result, plan)
    amendment["status"] = "verified"
    amendment["writeback_done"] = True
    amendment["transaction_id"] = transaction_id
    amendment["verification_receipt"] = verification_receipt
    amendment["transaction_sequence"] = transaction_sequence
    amendment["previous_transaction_commit_receipt"] = \
        previous_transaction_commit_receipt
    amendment["plan_path"] = plan_path
    amendment["plan_sha256"] = plan_sha
    amendment["coverage_proposal_path"] = proposal_path
    amendment["coverage_proposal_sha256"] = proposal_sha
    return result


def _new_transaction_receipt(phase, result, plan, transaction_id, plan_path,
                             plan_sha, proposal_path, proposal_sha,
                             transaction_sequence,
                             previous_transaction_commit_receipt, task_id,
                             registration_receipt):
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "amendment_transaction", plan["amendment_id"],
        result, "%s %s" % (phase, plan["operation"]),
        {"prepare": 1, "commit": 2, "abort": 3}[phase],
    )
    receipt.update({
        "transaction_phase": phase,
        "task_id": task_id,
        "transaction_id": transaction_id,
        "plan_path": plan_path,
        "plan_sha256": plan_sha,
        "coverage_proposal_path": proposal_path,
        "coverage_proposal_sha256": proposal_sha,
        "amendment_id": plan["amendment_id"],
        "operation": plan["operation"],
        "actor_role": "integrator",
        "transaction_sequence": transaction_sequence,
        "previous_transaction_commit_receipt":
            previous_transaction_commit_receipt,
        "registration_receipt": registration_receipt,
    })
    return receipt


def _transaction_fields(receipt, before, after):
    for name in ("coverage", "progress", "queue"):
        receipt["before_%s_sha256" % name] = before[name]
        receipt["after_%s_sha256" % name] = after[name]


def _lock_operation(plan, transaction_id, plan_sha, before, after,
                    prepare_receipt_id, transaction_sequence,
                    previous_transaction_commit_receipt,
                    task_id, plan_path=None, receipt_path=None):
    operation = {
        "tool": TOOL,
        "task_id": task_id,
        "action": plan["operation"],
        "amendment_id": plan["amendment_id"],
        "transaction_id": transaction_id,
        "plan_sha256": plan_sha,
        "prepare_receipt_id": prepare_receipt_id,
        "actor_role": "integrator",
        "transaction_sequence": transaction_sequence,
        "previous_transaction_commit_receipt":
            previous_transaction_commit_receipt,
        "plan_path": plan_path,
        "coverage_proposal_path": plan["coverage_proposal_path"],
        "coverage_proposal_sha256": plan["coverage_proposal_sha256"],
        "receipt_path": receipt_path,
    }
    for name in ("coverage", "progress", "queue"):
        operation["before_%s_sha256" % name] = before[name]
        operation["planned_after_%s_sha256" % name] = after[name]
    return operation


def _cancel_queue(queue, plan, now, transition_receipt):
    result = copy.deepcopy(queue)
    items = _map_by_id(result.get("required_queue"), "id", "Required Queue")
    item_id = plan["cancel_batch_id"]
    item = items.get(item_id)
    if item is None:
        raise ValueError("cancel_batch_id %s is absent from Queue" % item_id)
    if item.get("state") not in ("queued", "open"):
        raise ValueError("cancel-batch requires a queued/open batch")
    dependents = sorted(other_id for other_id, other in items.items()
                        if item_id in (other.get("depends_on") or []))
    if dependents:
        raise ValueError("cancel-batch requires a leaf batch; depended on by %s" %
                         ", ".join(dependents))
    history = item.get("transition_receipts")
    if history is None:
        history = []
    if not isinstance(history, list):
        raise ValueError("cancelled batch transition_receipts must be a list")
    item["state"] = "cancelled"
    item["hold_state"] = "none"
    item.pop("hold_reason", None)
    item["cancelled_at"] = now
    item["cancellation_amendment"] = plan["amendment_id"]
    item["transition_receipts"] = history + [transition_receipt["receipt_id"]]
    result["scope_version"] = plan["scope_version_after"]
    result["queue_revision"] = plan["queue_revision_after"]
    result["state_revision"] = plan["state_revision_after"]
    return result, item


def _prepare_result(root, plan_path, expected, admitted_runtime=None):
    root = os.path.realpath(os.path.abspath(root))
    plan_file, plan_raw, plan = _load_managed(
        root, plan_path, PLAN_PREFIX, must_exist=True)
    _validate_plan(plan)
    plan_relative = os.path.relpath(plan_file, root).replace(os.sep, "/")
    plan_sha = kblib.sha256_bytes(plan_raw)
    proposal_path = plan["coverage_proposal_path"]
    if os.path.normpath(proposal_path) == os.path.normpath(plan_path):
        raise ValueError("plan and Coverage proposal must be different files")
    proposal_file, proposal_raw, proposal = _load_managed(
        root, proposal_path, PLAN_PREFIX, must_exist=True)
    proposal_sha = kblib.sha256_bytes(proposal_raw)
    if proposal_sha != plan["coverage_proposal_sha256"]:
        raise ValueError("Coverage proposal SHA does not match plan")

    migration_admission = plan["operation"] == "property-state-migration"
    current = (check_queue.validate_runtime(
                   root,
                   allow_legacy_property_state_for_migration=
                       migration_admission)
               if admitted_runtime is None else admitted_runtime)
    if (not isinstance(current, dict) or
            current.get("root") != root):
        raise ValueError(
            "admitted runtime belongs to a different repository root")
    if current["errors"]:
        raise ValueError("current runtime is inconsistent: %s" %
                         "; ".join(current["errors"]))
    authority = check_queue.runtime_authority_context(current)
    authority_kwargs = check_queue.runtime_authority_validation_kwargs(
        authority)
    barrier = check_queue.delta_apply_write_barrier(
        current, "apply_amendment", "apply")
    if barrier:
        raise ValueError(barrier)
    if current.get("_writer_locks"):
        raise ValueError("runtime has an active or interrupted writer lock")
    coverage = current["coverage"]
    queue = current["queue"]
    progress = current["progress"]
    state_paths = {
        "coverage": kblib.managed_repository_path(
            root, check_queue.COVERAGE_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True),
        "queue": current["queue_path"],
        "progress": kblib.managed_repository_path(
            root, check_queue.PROGRESS_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True),
    }
    before_raw = {}
    for name, path in state_paths.items():
        with open(path, "rb") as fh:
            before_raw[name] = fh.read()
    before_sha = {name: kblib.sha256_bytes(raw)
                  for name, raw in before_raw.items()}
    for name in ("coverage", "progress", "queue"):
        if expected[name] != before_sha[name]:
            raise ValueError("expected %s SHA does not match current bytes" % name)
    if (queue.get("scope_version") != plan["scope_version_before"] or
            queue.get("queue_revision") != plan["queue_revision_before"] or
            queue.get("state_revision") != plan["state_revision_before"]):
        raise ValueError("plan before scope/revisions do not match current Queue")
    amendment = _find_amendment(
        progress, plan, plan_path=plan_relative, plan_sha=plan_sha)
    current_pages, proposed_pages, changed_specs = \
        _validate_coverage_proposal(coverage, proposal, plan)
    impact = amendment_policy.derive_amendment_impact(
        coverage, proposal, queue)
    if impact["writer_operation"] != plan["operation"]:
        raise ValueError(
            "plan operation %s does not match derived writer operation %s" %
            (plan["operation"], impact["writer_operation"])
        )
    amendment_policy.require_decision_binding(
        progress.get("contract") or {}, impact, amendment)

    proposal_relative = os.path.relpath(proposal_file, root).replace(os.sep, "/")
    transaction_id = "txn-%s-%s" % (plan["amendment_id"], uuid.uuid4().hex)
    registration_receipt = amendment["registration_receipt"]
    transaction_sequence, previous_transaction_commit_receipt = \
        _transaction_chain_head(progress)
    prepare = _new_transaction_receipt(
        "prepare", "candidate", plan, transaction_id,
        plan_relative, plan_sha, proposal_relative, proposal_sha,
        transaction_sequence, previous_transaction_commit_receipt,
        queue.get("task_id"), registration_receipt)
    commit = _new_transaction_receipt(
        "commit", "pass", plan, transaction_id,
        plan_relative, plan_sha, proposal_relative, proposal_sha,
        transaction_sequence, previous_transaction_commit_receipt,
        queue.get("task_id"), registration_receipt)
    transition = None
    property_migration = None

    if plan["operation"] == "scope-replan":
        compile_base = copy.deepcopy(queue)
        compile_base["scope_version"] = plan["scope_version_after"]
        compiled, _ = compile_queue.compile_document(compile_base, proposal)
        diff = compile_queue.replan_diff(queue, compiled, before_sha["queue"])
        queue_new = compile_queue._build_replanned_queue(queue, compiled, diff)
        queue_new["scope_version"] = plan["scope_version_after"]
        queue_new["queue_revision"] = plan["queue_revision_after"]
        queue_new["state_revision"] = plan["state_revision_after"]
        changed_batches = sorted(set(changed_specs).union(
            _structural_changes(queue, compiled)))
        if changed_batches != plan["affected_batches"]:
            raise ValueError("affected_batches does not exactly match replan; "
                             "found=%r expected=%r" %
                             (changed_batches, plan["affected_batches"]))
    elif plan["operation"] == "gap-routing-reconciliation":
        compile_base = copy.deepcopy(queue)
        compiled, _ = compile_queue.compile_document(compile_base, proposal)
        changed_batches = _structural_changes(queue, compiled)
        if changed_batches:
            raise ValueError(
                "gap-routing-reconciliation may not change Queue structure: %s" %
                ", ".join(changed_batches))
        queue_new = copy.deepcopy(queue)
        queue_new["queue_revision"] = plan["queue_revision_after"]
        queue_new["state_revision"] = plan["state_revision_after"]
        if plan["affected_batches"] != impact["affected_batches"]:
            raise ValueError(
                "affected_batches does not match gap-routing impact; "
                "found=%r expected=%r" %
                (impact["affected_batches"], plan["affected_batches"]))
    elif plan["operation"] == "property-state-migration":
        if proposed_pages.keys() != current_pages.keys():
            raise ValueError(
                "property-state-migration may not add or remove Coverage pages")
        if changed_specs:
            raise ValueError(
                "property-state-migration may not change batch_specs")
        if plan["affected_batches"] or impact["affected_batches"]:
            raise ValueError(
                "property-state-migration may not affect Queue batches")
        property_migration = _property_state_migration_plan(
            root, current_pages, proposed_pages, plan["affected_pages"],
            authority["profile_view"])
        _require_property_state_migration_binding(
            amendment, property_migration)
        queue_new = copy.deepcopy(queue)
        # Coverage changed even though Queue membership did not.  Advance the
        # cross-ledger revision so the initial Queue receipt is not asked to
        # authorize a different Coverage after-image.
        queue_new["queue_revision"] = plan["queue_revision_after"]
        queue_new["state_revision"] = plan["state_revision_after"]
    else:
        if proposed_pages.keys() != current_pages.keys():
            raise ValueError("cancel-batch may not add or remove Coverage pages")
        if changed_specs != [plan["cancel_batch_id"]]:
            raise ValueError("cancel-batch must remove exactly its own current "
                             "batch_specs entry")
        current_specs = _map_by_id(
            coverage.get("batch_specs"), "id", "Coverage batch_specs")
        proposed_specs = _map_by_id(
            proposal.get("batch_specs"), "id", "Coverage proposal batch_specs")
        if (plan["cancel_batch_id"] not in current_specs or
                plan["cancel_batch_id"] in proposed_specs):
            raise ValueError("cancel-batch must retire cancel_batch_id from "
                             "the current batch_specs proposal")
        current_item = current["items_by_id"].get(plan["cancel_batch_id"])
        if current_item is None:
            raise ValueError("cancel_batch_id is absent from Queue")
        manifest = sorted(current_item.get("manifest") or [])
        if plan["affected_pages"] != manifest:
            raise ValueError("cancel-batch affected_pages must equal its manifest")
        for object_path in manifest:
            page = proposed_pages[object_path]
            if page.get("coverage_disposition") == "required":
                raise ValueError("cancelled object %s remains Required" % object_path)
            if page.get("next_batch") == plan["cancel_batch_id"]:
                raise ValueError("cancelled object %s still routes to the batch" %
                                 object_path)
        cancellation_time = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        transition = kblib.make_receipt(
            TOOL, TOOL_VERSION, "queue_transition", plan["cancel_batch_id"],
            "pass", "cancelled by cross-Ledger Amendment %s" %
            plan["amendment_id"], 10,
        )
        queue_new, cancelled_item = _cancel_queue(
            queue, plan, cancellation_time,
            transition,
        )
        transition.update({
            "checked_at": cancellation_time,
            "task_id": queue.get("task_id"),
            "queue_revision": queue_new.get("queue_revision"),
            "before_state": current_item.get("state"),
            "after_state": "cancelled",
            "before_hold_state": current_item.get("hold_state"),
            "after_hold_state": "none",
            "before_state_revision": queue.get("state_revision"),
            "after_state_revision": queue_new.get("state_revision"),
            "before_required_queue_sha256": before_sha["queue"],
            "actor_role": "integrator",
            "amendment_id": plan["amendment_id"],
        })

    queue_text = kblib.canonical_yaml(queue_new)
    if transition is not None:
        transition["after_required_queue_sha256"] = \
            kblib.sha256_bytes(queue_text)
    progress_new = _sync_progress(
        progress, plan, queue_new, queue_text, transaction_id,
        commit["receipt_id"], transaction_sequence,
        previous_transaction_commit_receipt,
        plan_relative, plan_sha, proposal_relative, proposal_sha,
    )
    coverage_text = kblib.canonical_yaml(proposal)
    progress_text = kblib.canonical_yaml(progress_new)
    after_text = {
        "coverage": coverage_text,
        "queue": queue_text,
        "progress": progress_text,
    }
    after_sha = {name: kblib.sha256_bytes(text)
                 for name, text in after_text.items()}
    before_contract = progress.get("contract") or {}
    after_contract = progress_new.get("contract") or {}
    contract_fields = {
        "before_contract_sha256": check_queue.contract_sha256(progress),
        "after_contract_sha256": check_queue.contract_sha256(progress_new),
        "before_contract_version": before_contract.get("contract_version"),
        "after_contract_version": after_contract.get("contract_version"),
        "before_contract_scope_version": before_contract.get("scope_version"),
        "after_contract_scope_version": after_contract.get("scope_version"),
    }
    for receipt in (prepare, commit):
        _transaction_fields(receipt, before_sha, after_sha)
        receipt.update(contract_fields)
        receipt["queue_revision_before"] = plan["queue_revision_before"]
        receipt["queue_revision_after"] = plan["queue_revision_after"]
        receipt["state_revision_before"] = plan["state_revision_before"]
        receipt["state_revision_after"] = plan["state_revision_after"]
        if property_migration is not None:
            receipt.update(_property_state_migration_bindings(
                property_migration))

    overrides = {
        check_queue.COVERAGE_PATH: (coverage_text, proposal),
        check_queue.QUEUE_PATH: (queue_text, queue_new),
        check_queue.PROGRESS_PATH: (progress_text, progress_new),
    }
    pending = [commit]
    if transition is not None:
        pending.append(transition)
    final_check = check_queue.validate_runtime(
        root, state_overrides=overrides, extra_receipts=pending,
        page_projection_overrides=(
            property_migration["after_text_by_path"]
            if property_migration is not None else None),
        **authority_kwargs)
    if final_check["errors"]:
        raise ValueError("planned final state fails check_queue: %s" %
                         "; ".join(final_check["errors"]))
    return {
        "plan": plan, "plan_file": plan_file, "plan_path": plan_relative,
        "plan_sha": plan_sha, "proposal_file": proposal_file,
        "proposal_path": proposal_relative, "proposal_sha": proposal_sha,
        "paths": state_paths,
        "before_raw": before_raw, "before_sha": before_sha,
        "after_text": after_text, "after_sha": after_sha,
        "contract_fields": contract_fields,
        "prepare": prepare, "commit": commit, "transition": transition,
        "transaction_id": transaction_id,
        "transaction_sequence": transaction_sequence,
        "previous_transaction_commit_receipt":
            previous_transaction_commit_receipt,
        "registration_receipt": registration_receipt,
        "task_id": queue.get("task_id"),
        "impact": impact,
        "proposal": proposal,
        "property_state_migration": property_migration,
        "authority": authority,
    }


def _restore(paths, before_raw):
    failures = []
    for name in ("coverage", "queue", "progress"):
        try:
            text = before_raw[name].decode("utf-8")
            kblib.atomic_write_text(paths[name], text,
                                    validator=kblib.parse_yaml_subset)
        except Exception as exc:  # preserve every attempted rollback failure
            failures.append("%s: %s" % (name, exc))
    for name in ("coverage", "queue", "progress"):
        try:
            with open(paths[name], "rb") as fh:
                live = fh.read()
            if live != before_raw[name]:
                failures.append("%s bytes differ after rollback" % name)
        except Exception as exc:
            failures.append("%s verification: %s" % (name, exc))
    return failures


def _commit_transaction(root, prepared, receipt_path):
    plan = prepared["plan"]
    authority = prepared["authority"]
    authority_kwargs = check_queue.runtime_authority_validation_kwargs(
        authority)
    abort = _new_transaction_receipt(
        "abort", "fail", plan, prepared["transaction_id"],
        prepared["plan_path"], prepared["plan_sha"],
        prepared["proposal_path"], prepared["proposal_sha"],
        prepared["transaction_sequence"],
        prepared["previous_transaction_commit_receipt"],
        prepared["task_id"], prepared["registration_receipt"],
    )
    _transaction_fields(abort, prepared["before_sha"], prepared["after_sha"])
    abort.update(prepared["contract_fields"])
    if prepared.get("property_state_migration") is not None:
        abort.update(_property_state_migration_bindings(
            prepared["property_state_migration"]))
    operation = _lock_operation(
        plan, prepared["transaction_id"], prepared["plan_sha"],
        prepared["before_sha"], prepared["after_sha"],
        prepared["prepare"]["receipt_id"],
        prepared["transaction_sequence"],
        prepared["previous_transaction_commit_receipt"],
        prepared["task_id"],
        plan_path=prepared["plan_path"],
        receipt_path=os.path.relpath(receipt_path, root),
    )
    operation["registration_receipt"] = prepared["registration_receipt"]
    operation.update({
        "commit_receipt_id": prepared["commit"]["receipt_id"],
        "abort_receipt_id": abort["receipt_id"],
        "transition_receipt_id": (
            prepared["transition"]["receipt_id"]
            if prepared["transition"] is not None else None
        ),
    })
    operation.update(check_queue.runtime_authority_lock_fields(authority))
    if prepared.get("property_state_migration") is not None:
        operation.update({
            "operation_capability": LEGACY_PROPERTY_ADOPTION_OPERATION,
            "property_state_migration_set_sha256": prepared[
                "property_state_migration"]["set_sha256"],
            "metadata_execution_rule_fingerprint": prepared[
                "property_state_migration"][
                    "metadata_execution_rule_fingerprint"],
        })
    with kblib.runtime_write_lock(root, owner_metadata=operation) as lock:
        with kblib.no_authoritative_write_guard(lock):
            for name, path in prepared["paths"].items():
                with open(path, "rb") as fh:
                    live = fh.read()
                if kblib.sha256_bytes(live) != prepared["before_sha"][name]:
                    raise ValueError(
                        "%s changed after transaction planning" % name)
            locked = check_queue.validate_runtime(
                root,
                allow_legacy_property_state_for_migration=(
                    plan["operation"] == "property-state-migration"),
                **authority_kwargs)
            if locked["errors"]:
                raise ValueError("runtime changed before write: %s" %
                                 "; ".join(locked["errors"]))
            check_queue.require_runtime_authority_current(
                root, authority, "runtime authority changed under lock")
            barrier = check_queue.delta_apply_write_barrier(
                locked, "apply_amendment", "apply")
            if barrier:
                raise ValueError(barrier)
            if kblib.sha256_file(prepared["plan_file"]) != prepared["plan_sha"]:
                raise ValueError("Amendment plan changed after transaction planning")
            if kblib.sha256_file(
                    prepared["proposal_file"]) != prepared["proposal_sha"]:
                raise ValueError(
                    "Coverage proposal changed after transaction planning")
            locked_amendment = _find_amendment(
                locked["progress"], prepared["plan"],
                plan_path=prepared["plan_path"],
                plan_sha=prepared["plan_sha"])
            locked_impact = amendment_policy.derive_amendment_impact(
                locked["coverage"], prepared["proposal"], locked["queue"])
            amendment_policy.require_decision_binding(
                locked["progress"].get("contract") or {},
                locked_impact, locked_amendment)
            if prepared.get("property_state_migration") is not None:
                locked_pages = _map_by_id(
                    locked["coverage"].get("pages"), "path",
                    "Coverage pages")
                proposed_pages = _map_by_id(
                    prepared["proposal"].get("pages"), "path",
                    "Coverage proposal pages")
                locked_migration = _property_state_migration_plan(
                    root, locked_pages, proposed_pages,
                    plan["affected_pages"], authority["profile_view"])
                _require_property_state_migration_binding(
                    locked_amendment, locked_migration)
                if (_property_state_migration_bindings(locked_migration) !=
                        _property_state_migration_bindings(
                            prepared["property_state_migration"])):
                    raise ValueError(
                        "property-state-migration page plan changed under "
                        "the writer lock")
                prepared["property_state_migration"] = locked_migration
        page_transaction = None
        if prepared.get("property_state_migration") is not None:
            page_plan = prepared["property_state_migration"]["plan"]
            if any(page.changed for page in page_plan.pages):
                page_transaction = project_page_state.stage_projection_plan(
                    root, page_plan, lock,
                    transaction_id="amendment-property-%s" %
                    prepared["transaction_id"])
        final_receipts = ([prepared["transition"]]
                          if prepared["transition"] else []) + [
                              prepared["commit"]]
        outcomes = {
            "prepare": "not-attempted",
            "final": "not-attempted",
            "commit": "not-attempted",
            "abort": "not-attempted",
        }
        try:
            commit_before = kblib.receipt_append_observation(
                receipt_path, [prepared["commit"]]
            )
            final_before = kblib.receipt_append_observation(
                receipt_path, final_receipts
            )
        except Exception:
            commit_before = None
            final_before = None
        try:
            check_queue.require_runtime_authority_current(
                root, authority,
                "runtime authority changed before prepare receipt")
            outcome, append_error, _ = kblib.write_receipts_observed(
                receipt_path, _record_receipts([prepared["prepare"]])
            )
            outcomes["prepare"] = outcome
            if append_error is not None:
                raise append_error
            check_queue.require_runtime_authority_current(
                root, authority,
                "runtime authority changed during prepare receipt")
            for name in ("coverage", "queue", "progress"):
                check_queue.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed before %s write" % name)
                kblib.atomic_write_text(
                    prepared["paths"][name], prepared["after_text"][name],
                    validator=kblib.parse_yaml_subset,
                )
                check_queue.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed during %s write" % name)
            if page_transaction is not None:
                page_transaction.publish()
            post = check_queue.validate_runtime(
                root,
                extra_receipts=(
                    [prepared["commit"], prepared["transition"]]
                    if prepared["transition"] else [prepared["commit"]]),
                **authority_kwargs,
            )
            if post["errors"]:
                raise ValueError("post-write check_queue failed: %s" %
                                 "; ".join(post["errors"]))
            check_queue.require_runtime_authority_current(
                root, authority,
                "runtime authority changed before final receipts")
            outcome, append_error, _ = kblib.write_receipts_observed(
                receipt_path, _record_receipts(final_receipts),
                before=final_before
            )
            outcomes["final"] = outcome
            outcomes["commit"] = (
                kblib.receipt_outcome_from(
                    receipt_path, [prepared["commit"]], commit_before
                ) if commit_before is not None else "uncertain"
            )
            if append_error is not None:
                raise append_error
            check_queue.require_runtime_authority_current(
                root, authority,
                "runtime authority changed during final receipts")
            persisted = check_queue.validate_runtime(
                root, **authority_kwargs)
            if persisted["errors"]:
                raise ValueError("persisted transaction evidence failed "
                                 "check_queue: %s" %
                                 "; ".join(persisted["errors"]))
            if page_transaction is not None:
                page_transaction.commit()
        except Exception as exc:
            if (page_transaction is not None and
                    page_transaction.state == "commit-cleanup-failed"):
                raise ValueError(
                    "property migration committed but page recovery cleanup "
                    "is incomplete; inspect the retained writer journal: %s" %
                    exc) from exc
            rollback_failures = []
            if (page_transaction is not None and
                    page_transaction.state not in
                    ("rolled-back", "committed")):
                try:
                    page_transaction.rollback()
                except Exception as page_error:
                    rollback_failures.append(
                        "page projection: %s" % page_error)
            rollback_failures.extend(_restore(
                prepared["paths"], prepared["before_raw"]))
            if outcomes["final"] == "not-attempted":
                outcomes["final"] = (
                    kblib.receipt_outcome_from(
                        receipt_path, final_receipts, final_before
                    ) if final_before is not None else "uncertain"
                )
            if outcomes["commit"] == "not-attempted":
                outcomes["commit"] = (
                    kblib.receipt_outcome_from(
                        receipt_path, [prepared["commit"]], commit_before
                    ) if commit_before is not None else "uncertain"
                )
            abort["failure"] = str(exc)
            abort["rollback_failures"] = rollback_failures
            abort_error = None
            if outcomes["prepare"] in ("present", "uncertain"):
                outcomes["abort"], abort_error, _ = (
                    kblib.write_receipts_observed(
                        receipt_path, _record_receipts([abort]))
                )
            attempted = [
                value for key, value in outcomes.items()
                if key != "commit" and value != "not-attempted"
            ]
            all_attempted_absent = (
                bool(attempted) and
                all(value == "absent" for value in attempted) and
                outcomes["commit"] == "absent"
            )
            handled_prepare_failure = (
                outcomes["prepare"] == "present" and
                outcomes["abort"] == "present" and
                outcomes["final"] == "absent" and
                outcomes["commit"] == "absent"
            )
            receipt_recovery_closed = (
                all_attempted_absent or handled_prepare_failure
            )
            if rollback_failures or not receipt_recovery_closed:
                recovery = (
                    "receipt outcomes prepare=%s final=%s commit=%s abort=%s" %
                    (outcomes["prepare"], outcomes["final"],
                     outcomes["commit"], outcomes["abort"])
                )
                if abort_error is not None:
                    recovery += "; abort append: %s" % abort_error
                suffix = (("; " + "; ".join(rollback_failures))
                          if rollback_failures else "")
                raise ValueError(
                    "transaction failed and recovery was incomplete: %s; %s%s" %
                    (exc, recovery, suffix))
            lock.mark_reconciled()
            raise


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Apply one approved cross-Ledger Amendment transaction")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--plan", required=True,
                        help=".cambium/deltas/amendments/*.yaml plan")
    parser.add_argument("--expected-coverage-sha256", required=True,
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Coverage; planning is "
                             "refused when the live bytes differ")
    parser.add_argument("--expected-progress-sha256", required=True,
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Progress; planning is "
                             "refused when the live bytes differ")
    parser.add_argument("--expected-queue-sha256", required=True,
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Queue; planning is "
                             "refused when the live bytes differ")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker",
                        help="declared caller role; only integrator may "
                             "apply an Amendment transaction")
    parser.add_argument("--receipts", default=RECEIPT_PATH,
                        help="receipt JSONL path under .cambium/receipts")
    parser.add_argument("--apply", action="store_true",
                        help="write the transaction; omit for a dry run")
    parser.add_argument("--json", action="store_true", help=JSON_HELP)
    args = parser.parse_args(argv)
    if not args.json:
        return _run(args)
    return _run_reporting_json(lambda: _run(args))


def _run(args):
    """This tool's own run; `main` above owns only argument parsing."""
    root = os.path.realpath(os.path.abspath(args.root))
    expected = {
        "coverage": args.expected_coverage_sha256,
        "progress": args.expected_progress_sha256,
        "queue": args.expected_queue_sha256,
    }
    for name, value in expected.items():
        if not check_queue.SHA256_RE.fullmatch(value):
            print("[FAIL] expected %s SHA must be sha256:<64 lowercase hex>" % name)
            return 1
    admission = None
    if args.apply:
        strict_admission = check_queue.validate_runtime(root)
        if not strict_admission["errors"]:
            # Preserve the ordinary writer invariant: a healthy runtime must
            # pass the global applied-delta barrier before this command opens
            # or interprets an Amendment plan.
            barrier = check_queue.delta_apply_write_barrier(
                strict_admission, "apply_amendment", "apply")
            if barrier:
                print("[FAIL] %s" % barrier)
                return 1
            admission = strict_admission
        # A legacy property-state before-image is intentionally not healthy
        # under the current validator.  In that one case only _prepare_result
        # may read the exact plan and select the narrowly-scoped migration
        # admission while validating the complete proposal.  Non-migration
        # plans simply re-run strict admission there and remain rejected.
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False)
        prepared = _prepare_result(
            root, args.plan, expected,
            admitted_runtime=admission)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc)
        return 1
    print("amendment transaction: %s operation=%s scope=%s->%s "
          "queue_revision=%s->%s state_revision=%s->%s" % (
              prepared["plan"]["amendment_id"],
              prepared["plan"]["operation"],
              prepared["plan"]["scope_version_before"],
              prepared["plan"]["scope_version_after"],
              prepared["plan"]["queue_revision_before"],
              prepared["plan"]["queue_revision_after"],
              prepared["plan"]["state_revision_before"],
              prepared["plan"]["state_revision_after"],
          ))
    for name in ("coverage", "queue", "progress"):
        print("%s_sha256=%s -> %s" % (
            name, prepared["before_sha"][name], prepared["after_sha"][name]))
    if not args.apply:
        print("dry run; add --apply --actor-role integrator with the same expected SHAs")
        return 0
    if args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may apply an Amendment transaction")
        return 1
    try:
        _commit_transaction(root, prepared, receipt_path)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] Amendment transaction: %s" % exc)
        return 1
    print("[PASS] Amendment %s committed; transaction_id=%s" % (
        prepared["plan"]["amendment_id"], prepared["transaction_id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
