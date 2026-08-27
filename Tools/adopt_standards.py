#!/usr/bin/env python3
"""Atomically adopt an approved Standards/Profile identity for an active task.

The restricted-YAML plan is the canonical machine revision record.  The
default is a dry run.  ``--apply --actor-role integrator`` is the only write
path; it holds the shared runtime writer lock, appends prepare/commit/abort
evidence, preserves unrelated state exactly, and rolls ordinary failures back
to the four frozen before images (the three task Ledgers plus adopter state).
"""

import contextlib
import copy
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib
import profile_contract
import runtime_paths
import runtime_state_contract
import standards_state

TOOL = "adopt_standards"
TOOL_VERSION = "1.8.0"
GATE_ID = "standards-adoption"
# The `Check` cell K00/12 registers for this Gate; every receipt this
# tool offers as gate evidence carries it verbatim.
GATE_CHECK = "standards_adoption"
PLAN_PREFIX = check_queue.STANDARDS_ADOPTION_PLAN_PREFIX
RECEIPT_PATH = runtime_paths.STANDARDS_ADOPTION_RECEIPT_PATH
ALLOWED_TASK_STATES = runtime_state_contract.STANDARDS_ADOPTION_TASK_STATES
LOAD_FIELDS = (
    "selected_route_ids", "selected_card_paths",
    "selected_profile_route_ids", "selected_read_sets",
    "loaded_module_paths",
)
PRODUCER_ERA_LOAD_PATH_FIELDS = (
    "selected_card_paths", "selected_read_sets",
)


def _producer_era_load_contract_after(plan):
    """Return the exact current component paths proposed by this plan."""
    return {
        field: copy.deepcopy(plan.get(field + "_after"))
        for field in PRODUCER_ERA_LOAD_PATH_FIELDS
    }


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


def _make_receipt(check, target, result, details, seq, identity=None):
    """Build one producer-era adoption receipt with its stable Gate ID.

    Adoption receipts are built before the state write and consumed after it,
    so the identity they bind is the planned post-adoption Queue identity
    (:func:`_plan_identity`), never the bytes currently on disk.
    """
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, check, target, result, details, seq,
        identity=identity)
    receipt["gate_id"] = GATE_ID
    return receipt


def _plan_identity(plan):
    """Return the Required Queue identity this adoption leaves behind."""
    return {
        "task_id": plan["task_id"],
        "standards_version": plan["standards_version_after"],
        "selected_profile_manifest":
            plan["selected_profile_manifest_after"],
    }


def _after_profile_evidence(root, plan, *, expected=None, phase):
    """Load and CAS the candidate Profile without publishing its receipt.

    ``standards_adoption_plan_errors`` performs the admission judgment.  This
    helper is intentionally called again at transaction boundaries: admission
    is not a lease on mutable Profile bytes.  ``expected`` is the evidence
    captured immediately after admission and therefore binds both the plan's
    explicit tree snapshot, typed dependency contract, and root-owned
    profile-load inputs that admission actually authorized.
    """
    manifest = plan["selected_profile_manifest_after"]
    evidence, errors = check_queue.profile_load_evidence(root, manifest)
    if errors:
        raise ValueError(
            "%s candidate Profile failed profile-load: %s" %
            (phase, "; ".join(errors)))
    if evidence["selected_profile_manifest"] != manifest:
        raise ValueError(
            "%s candidate Profile manifest changed after plan admission" %
            phase)
    if (evidence["profile_snapshot_sha256"] !=
            plan["profile_snapshot_sha256_after"]):
        raise ValueError(
            "%s candidate Profile snapshot changed after plan admission" %
            phase)
    if (evidence["profile_contract_fingerprint"] !=
            plan["profile_contract_fingerprint_after"]):
        raise ValueError(
            "%s candidate Profile typed contract differs from the admitted "
            "plan" % phase)
    if (evidence["profile_load_inputs_sha256"] !=
            plan["profile_load_inputs_sha256_after"]):
        raise ValueError(
            "%s candidate Profile load inputs differ from the admitted "
            "plan" % phase)
    if expected is not None:
        for field in profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS:
            if evidence.get(field) != expected.get(field):
                raise ValueError(
                    "%s candidate Profile %s changed after plan admission" %
                    (phase, field))
    return evidence


def _load_plan(root, relative):
    path = kblib.managed_repository_path(
        root, relative, PLAN_PREFIX, suffixes=(".yaml",), must_exist=True)
    raw = kblib.read_bytes(path)
    try:
        plan = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("adoption plan is not UTF-8: %s" % exc)
    if not isinstance(plan, dict):
        raise ValueError("adoption plan top level must be a mapping")
    return path, raw, plan


def _state_paths(root, current):
    return {
        "coverage": kblib.managed_repository_path(
            root, check_queue.COVERAGE_PATH, runtime_paths.STATE_ROOT,
            suffixes=(".yaml",), must_exist=True),
        "queue": current["queue_path"],
        "progress": kblib.managed_repository_path(
            root, check_queue.PROGRESS_PATH, runtime_paths.STATE_ROOT,
            suffixes=(".yaml",), must_exist=True),
        "standards": kblib.managed_repository_path(
            root, standards_state.STATE_PATH, runtime_paths.GOVERNANCE_ROOT,
            suffixes=(".yaml",), must_exist=True),
    }


def _read_state_bytes(paths):
    result = {}
    for name, path in paths.items():
        with open(path, "rb") as fh:
            result[name] = fh.read()
    return result


def _ids(rows, field):
    return sorted(row[field] for row in rows)


def _non_adoption_projection(name, document):
    """Remove only the fields this writer is authorized to change."""
    value = copy.deepcopy(document)
    if name == "coverage":
        value.pop("standards_version", None)
        value.pop("selected_profile_manifest", None)
    elif name == "queue":
        value.pop("standards_version", None)
        value.pop("selected_profile_manifest", None)
        value.pop("queue_revision", None)
    elif name == "progress":
        value.pop("standards_adoptions", None)
        value.pop("queue_revision", None)
        value.pop("required_queue_sha256", None)
        contract = value.get("contract")
        if isinstance(contract, dict):
            for field in (
                    "contract_version", "standards_version",
                    "selected_profile_manifest") + LOAD_FIELDS:
                contract.pop(field, None)
    elif name == "standards":
        for field in (
                "state_revision", "standards_version", "status",
                "effective_date", "selected_profile_manifest",
                "latest_adoption_receipt", "upstream_source_ref",
                "upstream_revision_id"):
            value.pop(field, None)
    return value


def _projection_sha(name, document):
    return kblib.sha256_bytes(kblib.canonical_yaml(
        _non_adoption_projection(name, document)))


def _assert_only_permitted_changes(before, after):
    for name in ("coverage", "queue", "progress", "standards"):
        if _non_adoption_projection(name, before[name]) != \
                _non_adoption_projection(name, after[name]):
            raise ValueError(
                "planned adoption changes forbidden %s fields" % name)
    if before["queue"].get("state_revision") != after["queue"].get(
            "state_revision"):
        raise ValueError("Standards adoption may not change state_revision")
    before_items = before["queue"].get("required_queue")
    after_items = after["queue"].get("required_queue")
    if before_items != after_items:
        raise ValueError("Standards adoption may not change Queue items")
    if before["progress"].get("task_state") != after["progress"].get(
            "task_state"):
        raise ValueError("Standards adoption may not change task_state")


def _new_receipt(phase, result, plan, transaction_id, plan_path, plan_sha,
                 before, after, before_sha, after_sha, projection_shas,
                 immediate_receipts):
    receipt = _make_receipt(
        GATE_CHECK, plan["adoption_id"],
        result,
        "%s Standards adoption %s -> %s" % (
            phase, plan["standards_version_before"],
            plan["standards_version_after"]),
        {"prepare": 1, "commit": 2, "abort": 3}[phase],
        identity=_plan_identity(plan),
    )
    before_contract = before["progress"]["contract"]
    after_contract = after["progress"]["contract"]
    receipt.update({
        "transaction_phase": phase,
        "transaction_id": transaction_id,
        "actor_role": "integrator",
        "task_id": plan["task_id"],
        "adoption_id": plan["adoption_id"],
        "plan_path": plan_path,
        "plan_sha256": plan_sha,
        "before_coverage_sha256": before_sha["coverage"],
        "before_queue_sha256": before_sha["queue"],
        "before_progress_sha256": before_sha["progress"],
        "before_standards_state_sha256": before_sha["standards"],
        "after_coverage_sha256": after_sha["coverage"],
        "after_queue_sha256": after_sha["queue"],
        "after_progress_sha256": after_sha["progress"],
        "after_standards_state_sha256": after_sha["standards"],
        "before_contract_sha256": check_queue.contract_sha256(
            before["progress"]),
        "after_contract_sha256": check_queue.contract_sha256(
            after["progress"]),
        "before_contract_version": before_contract.get("contract_version"),
        "after_contract_version": after_contract.get("contract_version"),
        "before_contract_scope_version": before_contract.get("scope_version"),
        "after_contract_scope_version": after_contract.get("scope_version"),
        "contract_version_before": plan["contract_version_before"],
        "contract_version_after": plan["contract_version_after"],
        "standards_version_before": plan["standards_version_before"],
        "standards_version_after": plan["standards_version_after"],
        "standards_effective_date_after":
            plan["standards_effective_date_after"],
        "selected_profile_manifest_before":
            plan["selected_profile_manifest_before"],
        "selected_profile_manifest_after":
            plan["selected_profile_manifest_after"],
        "governance_revision_ref": plan["governance_revision_ref"],
        "governance_revision_sha256": plan["governance_revision_sha256"],
        "upstream_source_ref": plan["upstream_source_ref"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "standards_snapshot_sha256_after":
            plan["standards_snapshot_sha256_after"],
        "profile_snapshot_sha256_after":
            plan["profile_snapshot_sha256_after"],
        "profile_contract_fingerprint_after":
            plan["profile_contract_fingerprint_after"],
        "profile_load_inputs_sha256_after":
            plan["profile_load_inputs_sha256_after"],
        "queue_revision_before": plan["queue_revision_before"],
        "queue_revision_after": plan["queue_revision_after"],
        "state_revision_before": plan["queue_state_revision_before"],
        "state_revision_after": plan["queue_state_revision_before"],
        "task_state_before": plan["task_state_before"],
        "task_state_after": plan["task_state_before"],
        "selected_route_ids_before": before_contract["selected_route_ids"],
        "selected_route_ids_after": plan["selected_route_ids_after"],
        "selected_card_paths_before": before_contract["selected_card_paths"],
        "selected_card_paths_after": plan["selected_card_paths_after"],
        "selected_profile_route_ids_before":
            before_contract["selected_profile_route_ids"],
        "selected_profile_route_ids_after":
            plan["selected_profile_route_ids_after"],
        "selected_read_sets_before": before_contract["selected_read_sets"],
        "selected_read_sets_after": plan["selected_read_sets_after"],
        "loaded_module_paths_before": before_contract["loaded_module_paths"],
        "loaded_module_paths_after": plan["loaded_module_paths_after"],
        "changed_predicate_ids": _ids(
            plan["changed_predicates"], "predicate_id"),
        "invalidated_evidence_receipt_ids": _ids(
            plan["invalidated_evidence"], "receipt_id"),
        "invalidation_boundary_ids": _ids(
            plan["invalidation_boundaries"], "boundary_id"),
        "immediate_gate_reruns": plan["immediate_gate_reruns"],
        "immediate_gate_receipts": immediate_receipts,
        "boundary_gate_reruns": plan["boundary_gate_reruns"],
        "preserved_coverage_projection_sha256": projection_shas["coverage"],
        "preserved_queue_projection_sha256": projection_shas["queue"],
        "preserved_progress_projection_sha256": projection_shas["progress"],
    })
    return receipt


def _prepare_result(root, plan_relative):
    root = os.path.realpath(os.path.abspath(root))
    plan_file, plan_raw, plan = _load_plan(root, plan_relative)
    current = check_queue.validate_runtime(
        root,
        allow_invalid_current_profile_for_corrective_adoption=True,
        allow_active_standards_mismatch_for_adoption=True,
        producer_era_load_contract_after=
            _producer_era_load_contract_after(plan))
    if current["errors"]:
        raise ValueError("current runtime is inconsistent: %s" %
                         "; ".join(current["errors"]))
    if current.get("_writer_locks"):
        raise ValueError("runtime has an active or interrupted writer lock")
    producer_era_path_migrations = list(
        (current.get("task_runtime") or {}).get(
            "producer_era_path_migrations") or [])
    barrier = check_queue.delta_apply_write_barrier(
        current, TOOL, "apply")
    if barrier:
        raise ValueError(barrier)
    queue = current["queue"]
    coverage = current["coverage"]
    progress = current["progress"]
    if progress.get("task_state") not in ALLOWED_TASK_STATES:
        raise ValueError("Standards adoption requires task_state active or paused")
    catalog = current.get("receipt_catalog") or {}
    plan_errors = check_queue.standards_adoption_plan_errors(
        root, plan, catalog=catalog, queue=queue, progress=progress,
        validate_current=True)
    if plan_errors:
        raise ValueError("invalid Standards adoption plan: %s" %
                         "; ".join(plan_errors))
    # Capture the after-image's semantic contract only after the complete plan
    # has been admitted.  This is in-memory transaction evidence, never a
    # current-task receipt: until commit the Queue still owns the before
    # Profile identity.
    profile_evidence = _after_profile_evidence(
        root, plan, phase="post-admission")

    paths = _state_paths(root, current)
    before_raw = _read_state_bytes(paths)
    before_sha = {name: kblib.sha256_bytes(raw)
                  for name, raw in before_raw.items()}
    expected_sha = {
        "coverage": plan["coverage_sha256_before"],
        "queue": plan["required_queue_sha256_before"],
        "progress": plan["progress_sha256_before"],
        "standards": plan["standards_state_sha256_before"],
    }
    for name in ("coverage", "queue", "progress", "standards"):
        if before_sha[name] != expected_sha[name]:
            raise ValueError("plan %s SHA does not match current bytes" % name)
    try:
        standards_before, standards_errors = standards_state.parse(
            before_raw["standards"].decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("current Standards state is not UTF-8: %s" % exc)
    if standards_errors:
        raise ValueError("current Standards state is invalid: %s" %
                         "; ".join(standards_errors))
    contract = progress["contract"]
    expected_identity = {
        "task_id": plan["task_id"],
        "task_state": plan["task_state_before"],
        "standards_version": plan["standards_version_before"],
        "selected_profile_manifest":
            plan["selected_profile_manifest_before"],
        "contract_version": plan["contract_version_before"],
        "queue_revision": plan["queue_revision_before"],
        "state_revision": plan["queue_state_revision_before"],
    }
    actual_identity = {
        "task_id": queue.get("task_id"),
        "task_state": progress.get("task_state"),
        "standards_version": queue.get("standards_version"),
        "selected_profile_manifest": queue.get("selected_profile_manifest"),
        "contract_version": contract.get("contract_version"),
        "queue_revision": queue.get("queue_revision"),
        "state_revision": queue.get("state_revision"),
    }
    for field, expected in expected_identity.items():
        if actual_identity[field] != expected:
            raise ValueError("plan before %s=%r, current value is %r" %
                             (field, expected, actual_identity[field]))
    if (standards_before["standards_version"] !=
            plan["standards_version_before"] or
            standards_before["selected_profile_manifest"] !=
            plan["selected_profile_manifest_before"]):
        raise ValueError(
            "current adopter Standards state differs from the plan before "
            "identity")
    existing = progress.get("standards_adoptions")
    if not isinstance(existing, list):
        raise ValueError("Progress standards_adoptions is malformed")
    if any(isinstance(record, dict) and
           record.get("id") == plan["adoption_id"] for record in existing):
        raise ValueError("adoption_id already exists in Progress")

    before = {
        "coverage": copy.deepcopy(coverage),
        "queue": copy.deepcopy(queue),
        "progress": copy.deepcopy(progress),
        "standards": copy.deepcopy(standards_before),
    }
    after = copy.deepcopy(before)
    after["coverage"]["standards_version"] = plan["standards_version_after"]
    after["coverage"]["selected_profile_manifest"] = \
        plan["selected_profile_manifest_after"]
    after["queue"]["standards_version"] = plan["standards_version_after"]
    after["queue"]["selected_profile_manifest"] = \
        plan["selected_profile_manifest_after"]
    after["queue"]["queue_revision"] = plan["queue_revision_after"]
    after_contract = after["progress"]["contract"]
    after_contract["contract_version"] = plan["contract_version_after"]
    after_contract["standards_version"] = plan["standards_version_after"]
    after_contract["selected_profile_manifest"] = \
        plan["selected_profile_manifest_after"]
    for field in LOAD_FIELDS:
        after_contract[field] = copy.deepcopy(plan[field + "_after"])
    after["progress"]["queue_revision"] = plan["queue_revision_after"]

    coverage_text = kblib.canonical_yaml(after["coverage"])
    queue_text = kblib.canonical_yaml(after["queue"])
    after_coverage_sha = kblib.sha256_bytes(coverage_text)
    after_queue_sha = kblib.sha256_bytes(queue_text)
    after["progress"]["required_queue_sha256"] = after_queue_sha

    plan_path = os.path.relpath(plan_file, root).replace(os.sep, "/")
    plan_sha = kblib.sha256_bytes(plan_raw)
    transaction_id = "txn-%s-%s" % (plan["adoption_id"], uuid.uuid4().hex)
    # Commit id/time are known before serializing Progress, avoiding a
    # self-referential after-Progress hash while retaining an exact reference.
    commit_stub = _make_receipt(
        GATE_CHECK, plan["adoption_id"],
        "pass", "Standards adoption commit", 2,
        identity=_plan_identity(plan))
    standards_after = standards_state.next_state(
        standards_before,
        standards_version=plan["standards_version_after"],
        effective_date=plan["standards_effective_date_after"],
        selected_profile_manifest=plan["selected_profile_manifest_after"],
        latest_adoption_receipt=commit_stub["receipt_id"],
        upstream_source_ref=plan["upstream_source_ref"],
        upstream_revision_id=plan["upstream_revision_id"],
    )
    standards_text = standards_state.canonical_text(standards_after)
    after["standards"] = standards_after
    # The immediate consistency receipt is produced against the committed
    # after-image.  Allocate it after the commit identity so its timestamp is
    # never earlier than ``record.adopted_at``; the same receipt can then
    # discharge the aggregate's immediate owner claim without an impossible
    # second Queue run while every batch is held for revalidation.
    gate_stub = kblib.make_receipt(
        check_queue.TOOL, check_queue.TOOL_VERSION, "required_queue",
        check_queue.QUEUE_PATH, "pass",
        "post-adoption required Queue consistency", 90)
    immediate_receipts = [gate_stub["receipt_id"]]
    record = {
        "id": plan["adoption_id"],
        "adopted_at": commit_stub["checked_at"],
        "plan_path": plan_path,
        "plan_sha256": plan_sha,
        "verification_receipt": commit_stub["receipt_id"],
        "transaction_id": transaction_id,
        "task_state_before": plan["task_state_before"],
        "contract_version_before": plan["contract_version_before"],
        "contract_version_after": plan["contract_version_after"],
        "standards_version_before": plan["standards_version_before"],
        "standards_version_after": plan["standards_version_after"],
        "standards_effective_date_after":
            plan["standards_effective_date_after"],
        "standards_state_sha256_before":
            plan["standards_state_sha256_before"],
        "after_standards_state_sha256":
            kblib.sha256_bytes(standards_text),
        "selected_profile_manifest_before":
            plan["selected_profile_manifest_before"],
        "selected_profile_manifest_after":
            plan["selected_profile_manifest_after"],
        "governance_revision_ref": plan["governance_revision_ref"],
        "governance_revision_sha256": plan["governance_revision_sha256"],
        "upstream_source_ref": plan["upstream_source_ref"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "standards_snapshot_sha256_after":
            plan["standards_snapshot_sha256_after"],
        "profile_snapshot_sha256_after":
            plan["profile_snapshot_sha256_after"],
        "profile_contract_fingerprint_after":
            plan["profile_contract_fingerprint_after"],
        "profile_load_inputs_sha256_after":
            plan["profile_load_inputs_sha256_after"],
        "selected_route_ids_after": plan["selected_route_ids_after"],
        "selected_card_paths_after": plan["selected_card_paths_after"],
        "selected_profile_route_ids_after":
            plan["selected_profile_route_ids_after"],
        "selected_read_sets_after": plan["selected_read_sets_after"],
        "loaded_module_paths_after": plan["loaded_module_paths_after"],
        "queue_revision_before": plan["queue_revision_before"],
        "queue_revision_after": plan["queue_revision_after"],
        "queue_state_revision_before": plan["queue_state_revision_before"],
        "coverage_sha256_before": before_sha["coverage"],
        "required_queue_sha256_before": before_sha["queue"],
        "progress_sha256_before": before_sha["progress"],
        "after_coverage_sha256": after_coverage_sha,
        "after_required_queue_sha256": after_queue_sha,
        "changed_predicate_ids": _ids(
            plan["changed_predicates"], "predicate_id"),
        "invalidated_evidence_receipt_ids": _ids(
            plan["invalidated_evidence"], "receipt_id"),
        "invalidation_boundary_ids": _ids(
            plan["invalidation_boundaries"], "boundary_id"),
        "immediate_gate_reruns": plan["immediate_gate_reruns"],
        "immediate_gate_receipts": immediate_receipts,
        "boundary_gate_reruns": plan["boundary_gate_reruns"],
    }
    after["progress"]["standards_adoptions"] = copy.deepcopy(existing) + [record]
    progress_text = kblib.canonical_yaml(after["progress"])
    after_text = {
        "coverage": coverage_text,
        "queue": queue_text,
        "progress": progress_text,
        "standards": standards_text,
    }
    after_sha = {name: kblib.sha256_bytes(text)
                 for name, text in after_text.items()}
    _assert_only_permitted_changes(before, after)
    projection_shas = {name: _projection_sha(name, before[name])
                       for name in before}

    prepare = _new_receipt(
        "prepare", "candidate", plan, transaction_id, plan_path, plan_sha,
        before, after, before_sha, after_sha, projection_shas,
        immediate_receipts)
    commit = _new_receipt(
        "commit", "pass", plan, transaction_id, plan_path, plan_sha,
        before, after, before_sha, after_sha, projection_shas,
        immediate_receipts)
    # Preserve the already embedded commit identity/time.
    commit["receipt_id"] = commit_stub["receipt_id"]
    commit["checked_at"] = commit_stub["checked_at"]

    synthetic = {
        "root": root,
        "queue": after["queue"],
        "coverage": after["coverage"],
        "progress": after["progress"],
        "queue_sha256": after_sha["queue"],
        "coverage_sha256": after_sha["coverage"],
        "progress_sha256": after_sha["progress"],
        "remaining": sum(
            1 for item in after["queue"].get("required_queue", [])
            if not isinstance(item, dict) or
            item.get("state") not in check_queue.TERMINAL_STATES),
    }
    gate = check_queue.make_check_receipt(
        synthetic, "pass", "post-adoption Queue consistency passed",
        "consistency")
    gate["receipt_id"] = gate_stub["receipt_id"]
    gate["checked_at"] = gate_stub["checked_at"]

    overrides = {
        check_queue.COVERAGE_PATH: (coverage_text, after["coverage"]),
        check_queue.QUEUE_PATH: (queue_text, after["queue"]),
        check_queue.PROGRESS_PATH: (progress_text, after["progress"]),
    }
    final = check_queue.validate_runtime(
        root, state_overrides=overrides,
        active_standards_state_override=standards_text,
        extra_receipts=[gate, commit])
    if final["errors"]:
        raise ValueError("planned final state fails check_queue: %s" %
                         "; ".join(final["errors"]))
    return {
        "root": root, "plan": plan, "plan_path": plan_path,
        "plan_sha": plan_sha, "paths": paths, "before": before,
        "after": after, "before_raw": before_raw, "before_sha": before_sha,
        "after_text": after_text, "after_sha": after_sha,
        "prepare": prepare, "commit": commit, "gate": gate,
        "transaction_id": transaction_id,
        "projection_shas": projection_shas,
        "profile_evidence": profile_evidence,
        "producer_era_path_migrations": producer_era_path_migrations,
    }


def _restore(paths, before_raw):
    failures = []
    for name in ("coverage", "queue", "progress", "standards"):
        try:
            kblib.atomic_write_text(
                paths[name], before_raw[name].decode("utf-8"),
                validator=kblib.parse_yaml_subset)
        except Exception as exc:
            failures.append("%s: %s" % (name, exc))
    for name, path in paths.items():
        try:
            with open(path, "rb") as fh:
                if fh.read() != before_raw[name]:
                    failures.append("%s bytes differ after rollback" % name)
        except Exception as exc:
            failures.append("%s verification: %s" % (name, exc))
    return failures


def _lock_operation(prepared, receipt_path, abort_id):
    return {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "action": "standards-adoption",
        "target": prepared["plan"]["adoption_id"],
        "task_id": prepared["plan"]["task_id"],
        "transaction_id": prepared["transaction_id"],
        "plan_path": prepared["plan_path"],
        "plan_sha256": prepared["plan_sha"],
        "receipt_path": os.path.relpath(
            receipt_path, prepared["root"]).replace(os.sep, "/"),
        "prepare_receipt_id": prepared["prepare"]["receipt_id"],
        "commit_receipt_id": prepared["commit"]["receipt_id"],
        "abort_receipt_id": abort_id,
        "immediate_gate_receipt_id": prepared["gate"]["receipt_id"],
        "before_coverage_sha256": prepared["before_sha"]["coverage"],
        "planned_after_coverage_sha256": prepared["after_sha"]["coverage"],
        "before_required_queue_sha256": prepared["before_sha"]["queue"],
        "planned_after_required_queue_sha256": prepared["after_sha"]["queue"],
        "before_progress_sha256": prepared["before_sha"]["progress"],
        "planned_after_progress_sha256": prepared["after_sha"]["progress"],
        "before_standards_state_sha256":
            prepared["before_sha"]["standards"],
        "planned_after_standards_state_sha256":
            prepared["after_sha"]["standards"],
        "selected_profile_manifest_after":
            prepared["profile_evidence"]["selected_profile_manifest"],
        "profile_snapshot_sha256_after":
            prepared["profile_evidence"]["profile_snapshot_sha256"],
        "profile_contract_fingerprint_after":
            prepared["profile_evidence"]["profile_contract_fingerprint"],
        "profile_load_inputs_sha256_after":
            prepared["profile_evidence"]["profile_load_inputs_sha256"],
    }


def _commit_transaction(prepared, receipt_path):
    abort = copy.deepcopy(prepared["prepare"])
    abort.update(_make_receipt(
        GATE_CHECK,
        prepared["plan"]["adoption_id"], "fail",
        "Standards adoption aborted and before state restored", 3,
        identity=_plan_identity(prepared["plan"])))
    abort["transaction_phase"] = "abort"
    abort["transaction_id"] = prepared["transaction_id"]
    operation = _lock_operation(prepared, receipt_path, abort["receipt_id"])
    with kblib.runtime_write_lock(
            prepared["root"], owner_metadata=operation) as lock:
        with kblib.no_authoritative_write_guard(lock):
            for name, path in prepared["paths"].items():
                with open(path, "rb") as fh:
                    live = fh.read()
                if kblib.sha256_bytes(live) != prepared["before_sha"][name]:
                    raise ValueError("%s changed after adoption planning" % name)
            locked = check_queue.validate_runtime(
                prepared["root"],
                allow_invalid_current_profile_for_corrective_adoption=True,
                allow_active_standards_mismatch_for_adoption=True,
                producer_era_load_contract_after=
                    _producer_era_load_contract_after(prepared["plan"]))
            if locked["errors"]:
                raise ValueError("runtime changed before write: %s" %
                                 "; ".join(locked["errors"]))
            if locked.get("_writer_locks") and len(locked["_writer_locks"]) > 1:
                raise ValueError("another runtime writer lock appeared")
            if list((locked.get("task_runtime") or {}).get(
                    "producer_era_path_migrations") or []) != \
                    prepared["producer_era_path_migrations"]:
                raise ValueError(
                    "producer-era component path migration changed after "
                    "adoption planning")
            _after_profile_evidence(
                prepared["root"], prepared["plan"],
                expected=prepared["profile_evidence"],
                phase="locked pre-write")

        prepare_before = kblib.receipt_append_observation(
            receipt_path, [prepared["prepare"]])
        final_receipts = [prepared["gate"], prepared["commit"]]
        prepare_outcome = "not-attempted"
        final_outcome = "not-attempted"
        commit_before = None
        try:
            prepare_outcome, error, _ = kblib.write_receipts_observed(
                receipt_path, _record_receipts([prepared["prepare"]]),
                before=prepare_before)
            if error is not None:
                raise error
            # The prepare record is an intentional append.  Observe the final
            # gate/commit baseline only after it is durable; otherwise the
            # later append would be compared with a stale file image and the
            # prepare line could be mistaken for an uncertain append.
            final_before = kblib.receipt_append_observation(
                receipt_path, final_receipts)
            commit_before = kblib.receipt_append_observation(
                receipt_path, [prepared["commit"]])
            for name in ("coverage", "queue", "progress", "standards"):
                kblib.atomic_write_text(
                    prepared["paths"][name], prepared["after_text"][name],
                    validator=kblib.parse_yaml_subset)
            _after_profile_evidence(
                prepared["root"], prepared["plan"],
                expected=prepared["profile_evidence"],
                phase="post-write")
            post = check_queue.validate_runtime(
                prepared["root"], extra_receipts=final_receipts)
            if post["errors"]:
                raise ValueError("post-write check_queue failed: %s" %
                                 "; ".join(post["errors"]))
            # Runtime validation can be arbitrarily expensive.  Re-CAS the
            # candidate immediately before publishing its final evidence so a
            # mutation during that check cannot inherit the earlier pass.
            _after_profile_evidence(
                prepared["root"], prepared["plan"],
                expected=prepared["profile_evidence"],
                phase="pre-final-receipt")
            # The gate was computed from these exact after bytes during
            # preparation and is consumed only after the locked revalidation.
            final_outcome, error, _ = kblib.write_receipts_observed(
                receipt_path, _record_receipts(final_receipts),
                before=final_before)
            if error is not None:
                raise error
            # The append is itself an external I/O boundary.  A Profile
            # mutation racing that append must enter the transaction recovery
            # path too.  Because the commit receipt may now be durable, the
            # existing reconciliation predicate deliberately keeps the writer
            # lock even after state rollback and abort evidence.
            _after_profile_evidence(
                prepared["root"], prepared["plan"],
                expected=prepared["profile_evidence"],
                phase="post-final-receipt")
        except Exception as exc:
            rollback_failures = _restore(
                prepared["paths"], prepared["before_raw"])
            commit_outcome = (
                kblib.receipt_outcome_from(
                    receipt_path, [prepared["commit"]], commit_before)
                if commit_before is not None else "absent"
            )
            abort["failure"] = str(exc)
            abort["rollback_failures"] = rollback_failures
            abort_outcome = "not-attempted"
            abort_error = None
            if prepare_outcome in ("present", "uncertain"):
                abort_outcome, abort_error, _ = kblib.write_receipts_observed(
                    receipt_path, _record_receipts([abort]))
            fully_reconciled = (
                not rollback_failures and
                commit_outcome == "absent" and
                ((prepare_outcome == "absent") or
                 (prepare_outcome == "present" and
                  abort_outcome == "present"))
            )
            if fully_reconciled:
                lock.mark_reconciled()
                raise
            raise ValueError(
                "Standards adoption failed and recovery is incomplete: %s; "
                "prepare=%s final=%s commit=%s abort=%s abort_error=%s "
                "rollback=%s" % (
                    exc, prepare_outcome, final_outcome, commit_outcome,
                    abort_outcome, abort_error,
                    "; ".join(rollback_failures) or "none"))


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Adopt one approved Standards/Profile revision")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--plan", required=True,
                        help="%s/*.yaml" %
                        runtime_paths.STANDARDS_ADOPTION_DELTA_ROOT)
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker",
                        help="declared caller role; only integrator may "
                             "apply a Standards adoption")
    parser.add_argument("--receipts", default=RECEIPT_PATH,
                        help="receipt JSONL path under %s" %
                        runtime_paths.RECEIPT_ROOT)
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
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False)
        prepared = _prepare_result(root, args.plan)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc)
        return 1
    plan = prepared["plan"]
    print("Standards adoption %s: %s -> %s; queue_revision %s -> %s" % (
        plan["adoption_id"], plan["standards_version_before"],
        plan["standards_version_after"], plan["queue_revision_before"],
        plan["queue_revision_after"]))
    for name in ("coverage", "queue", "progress", "standards"):
        print("%s_sha256=%s -> %s" % (
            name, prepared["before_sha"][name], prepared["after_sha"][name]))
    if not args.apply:
        print("dry run; add --apply --actor-role integrator with unchanged plan/state bytes")
        return 0
    if args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may apply a Standards adoption")
        return 1
    try:
        _commit_transaction(prepared, receipt_path)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] Standards adoption transaction: %s" % exc)
        return 1
    print("[PASS] Standards adoption %s committed; transaction_id=%s" % (
        plan["adoption_id"], prepared["transaction_id"]))
    print("immediate_gate_receipt=%s" % prepared["gate"]["receipt_id"])
    print("verification_receipt=%s" % prepared["commit"]["receipt_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
