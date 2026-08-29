"""Resolve the current AuditPlan evidence closure for Batch Review.

This module is a read-only consumer.  It deliberately depends only on the
already-admitted runtime projection, the current receipt catalog, and the
three Kernel-owned audit contracts.  In particular, it does not import a
producer CLI or ``check_queue``: Queue validation imports this module, so a
producer dependency here would create both a circular import and a second
interpretation of current runtime state.
"""

import os
import stat

import audit_fingerprint
import audit_plan_contract
import audit_receipt_contract
import batch_close_audit
import batch_close_contract
import batch_review_obligation_contract
import changed_scope_rendering_checks
import changed_scope_evidence_contract
import kblib
import metadata_property_state
import profile_batch_judgment_contract
import rendering_verification_contract
import runtime_paths
import substantive_review_contract

from queue_runtime import current_opening_semantic_context
from queue_runtime.receipts import current_receipt_catalog


class AuditEvidenceError(ValueError):
    """The current AuditPlan or its evidence closure is not provable."""


_PLAN_BINDING_FIELDS = (
    "task_id", "batch_id", "opening_transition_receipt",
    "standards_version", "active_standards_sha256",
    "selected_profile_manifest", "profile_snapshot_sha256",
    "profile_contract_fingerprint",
)


def _current_page_artifact_fingerprint(root, relative):
    snapshot = kblib.repository_target_snapshot(
        root, relative, suffixes=(".md", ".MD"), singly_linked=True)
    if not snapshot.exists:
        raise AuditEvidenceError(
            "artifact target does not exist: %s" % relative)
    return audit_fingerprint.page_artifact_fingerprint(
        relative, snapshot.read_text())


def _current_page_set_artifact_fingerprint(root, scope):
    if (not isinstance(scope, list) or not scope or
            len(scope) != len(set(scope))):
        raise AuditEvidenceError(
            "artifact scope must be a non-empty unique page list")
    pages = []
    for relative in scope:
        snapshot = kblib.repository_target_snapshot(
            root, relative, suffixes=(".md", ".MD"), singly_linked=True)
        if not snapshot.exists:
            raise AuditEvidenceError(
                "artifact target does not exist: %s" % relative)
        pages.append((relative, snapshot.read_text()))
    return audit_fingerprint.page_set_artifact_fingerprint(pages)

_EVIDENCE_BINDING_FIELDS = (
    "obligation_id", "owner_kind", "owner_rule_id", "due_stage", "target",
    "evidence_role", "evidence_kind", "dimension", "evidence_ref",
    "evidence_sha256", "artifact_fingerprint", "dependency_fingerprint",
    "contract_fingerprint", "result", "reused", "reuse_reason",
)


def _record(entry):
    if isinstance(entry, tuple) and len(entry) == 2:
        return entry[1] if isinstance(entry[1], dict) else None
    return entry if isinstance(entry, dict) else None


def _current_record(catalog, receipt_id, label):
    if not isinstance(receipt_id, str) or not receipt_id:
        raise AuditEvidenceError("%s has no receipt identity" % label)
    receipt = _record(catalog.get(receipt_id))
    if not isinstance(receipt, dict):
        raise AuditEvidenceError(
            "%s %s is absent from the current receipt catalog" %
            (label, receipt_id))
    if receipt.get("receipt_id") != receipt_id:
        raise AuditEvidenceError(
            "%s catalog key does not match its receipt_id" % label)
    return receipt


def _plan_directory(root):
    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    current = root
    for part in runtime_paths.AUDIT_PLAN_ROOT.split("/"):
        current = os.path.join(current, part)
        try:
            descriptor = os.lstat(current)
        except FileNotFoundError as exc:
            raise AuditEvidenceError(
                "AuditPlan root is absent: %s" %
                runtime_paths.AUDIT_PLAN_ROOT) from exc
        if stat.S_ISLNK(descriptor.st_mode):
            raise AuditEvidenceError(
                "AuditPlan root must not traverse a symlink: %s" %
                os.path.relpath(current, root))
        if not stat.S_ISDIR(descriptor.st_mode):
            raise AuditEvidenceError(
                "AuditPlan root component is not a directory: %s" %
                os.path.relpath(current, root))
    return root, current


def _load_plans(root):
    """Load every direct managed YAML plan and prove its exact bytes."""
    root, directory = _plan_directory(root)
    contract = audit_plan_contract.load_contract(root)
    plans = []
    try:
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda row: row.name)
    except OSError as exc:
        raise AuditEvidenceError("cannot inspect AuditPlan root: %s" % exc)
    for entry in entries:
        relative = runtime_paths.child_path(
            runtime_paths.AUDIT_PLAN_ROOT, entry.name)
        try:
            descriptor = entry.stat(follow_symlinks=False)
        except OSError as exc:
            raise AuditEvidenceError(
                "cannot inspect AuditPlan entry %s: %s" %
                (relative, exc))
        if stat.S_ISLNK(descriptor.st_mode):
            raise AuditEvidenceError(
                "AuditPlan namespace contains symlink %s" % relative)
        if not entry.name.endswith(".yaml"):
            raise AuditEvidenceError(
                "AuditPlan namespace admits only direct .yaml files: %s" %
                relative)
        if not stat.S_ISREG(descriptor.st_mode):
            raise AuditEvidenceError(
                "AuditPlan entry must be a direct regular file: %s" %
                relative)
        if descriptor.st_nlink != 1:
            raise AuditEvidenceError(
                "AuditPlan file must have exactly one hard link: %s" %
                relative)
        try:
            snapshot = kblib.repository_target_snapshot(
                root, relative, suffixes=(".yaml",), singly_linked=True)
            text = snapshot.read_text()
            plan = kblib.parse_yaml_subset(text)
            audit_plan_contract.validate_plan(plan, contract=contract)
            canonical = kblib.canonical_yaml(plan)
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            raise AuditEvidenceError(
                "invalid AuditPlan %s: %s" % (relative, exc)) from exc
        if text != canonical:
            raise AuditEvidenceError(
                "AuditPlan bytes are not canonical: %s" % relative)
        if entry.name != "%s.yaml" % plan["plan_id"]:
            raise AuditEvidenceError(
                "AuditPlan filename does not match plan_id: %s" % relative)
        digest = kblib.sha256_bytes(text.encode("utf-8"))
        if digest != snapshot.sha256 or digest != \
                audit_plan_contract.plan_sha256(plan, contract=contract):
            raise AuditEvidenceError(
                "AuditPlan byte identity is inconsistent: %s" % relative)
        plans.append((relative, plan, digest))
    return plans


def _live_profile_bindings(result):
    view = result.get("_profile_authorized_view")
    if not isinstance(view, dict):
        raise AuditEvidenceError(
            "runtime has no authorized current Profile view")
    return {
        "selected_profile_manifest": view.get("selected_profile_manifest"),
        "profile_snapshot_sha256": view.get("profile_snapshot_sha256"),
        "profile_contract_fingerprint":
            view.get("profile_contract_fingerprint"),
    }


def _live_standards_bindings(result):
    view = result.get("_active_standards_authorized_view")
    if not isinstance(view, dict):
        raise AuditEvidenceError(
            "runtime has no authorized current Standards view")
    return {
        "standards_version": view.get("standards_version"),
        "active_standards_sha256": view.get("active_standards_sha256"),
    }


def _current_plan_errors(result, item, plan, catalog, *, required_state=None):
    """Check durable plan identity without comparing mutable Queue revisions.

    Queue revision, state revision, and Queue bytes are opening-time facts in
    the immutable plan.  Normal ``open -> merge-ready -> closed`` execution
    changes all three, so they are deliberately not compared to the live
    runtime.  The current Profile, Standards, task, batch, and exact opening
    receipt remain authority bindings and therefore must still agree.
    """
    errors = []
    queue = result.get("queue") or {}
    item_id = item.get("id")
    if required_state is not None and item.get("state") != required_state:
        errors.append(
            "Queue item %r must be %s, found %r" %
            (item_id, required_state, item.get("state")))
    current_item = (result.get("items_by_id") or {}).get(item_id)
    if not isinstance(current_item, dict) or current_item != item:
        errors.append("Queue item is not the current admitted item")
    expected = {
        "task_id": queue.get("task_id"),
        "batch_id": item_id,
    }
    try:
        expected.update(_live_profile_bindings(result))
        expected.update(_live_standards_bindings(result))
        opening = current_opening_semantic_context(result, item_id)
        expected["opening_transition_receipt"] = opening[
            "opening_transition_receipt"]
        expected["accepted_baseline_sha256"] = opening[
            "manifest_semantic_before_set_sha256"]
    except (AuditEvidenceError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    for field, value in expected.items():
        if plan.get(field) != value:
            errors.append(
                "AuditPlan %s=%r does not match current value %r" %
                (field, plan.get(field), value))
    return errors


def _resolve_current_plan(result, item, catalog, *, required_state=None):
    if not isinstance(result, dict) or not isinstance(item, dict):
        raise AuditEvidenceError(
            "runtime result and Queue item must be mappings")
    root = result.get("root")
    if not isinstance(root, str) or not root:
        raise AuditEvidenceError("runtime result has no repository root")
    candidates = []
    rejected = []
    for relative, plan, digest in _load_plans(root):
        if plan.get("batch_id") != item.get("id"):
            continue
        errors = _current_plan_errors(
            result, item, plan, catalog, required_state=required_state)
        if errors:
            rejected.append("%s: %s" % (relative, "; ".join(errors)))
        else:
            candidates.append((relative, plan, digest))
    if len(candidates) != 1:
        detail = ""
        if rejected:
            detail = "; rejected candidate(s): %s" % " | ".join(rejected)
        raise AuditEvidenceError(
            "batch %s requires exactly one current AuditPlan, found %d%s"
            % (item.get("id"), len(candidates), detail))
    return candidates[0]


def _require_current_profile_rendering_contract_state(result, item):
    """Re-evaluate the tri-state against current bytes without editing plan."""
    root = result.get("root")
    manifest = item.get("manifest")
    if (not isinstance(root, str) or not root or
            not isinstance(manifest, list) or not manifest):
        raise AuditEvidenceError(
            "current Profile rendering state has no manifest boundary")
    pages = []
    for relative in manifest:
        snapshot = kblib.repository_target_snapshot(
            root, relative, suffixes=(".md", ".MD"), singly_linked=True)
        if not snapshot.exists:
            raise AuditEvidenceError(
                "current Profile rendering target is absent: %s" % relative)
        pages.append((relative, snapshot.read_text()))
    changed_scope_rendering_checks.require_profile_rendering_contract_state(
        pages, contract_is_bound_and_valid=False)


def resolve_stage_plan(result, item, due_stage, required_state=None):
    """Resolve one immutable plan and its exact obligations due at a stage.

    This is the sole public plan-scanning boundary for pre-merge and
    post-Delta consumers.  It filters the already-frozen plan; it never
    reprojects, adds, or mutates an obligation.
    """
    contract_values = audit_plan_contract.validate_contract(
        audit_plan_contract.load_contract(result.get("root")))
    if due_stage not in contract_values["due_stages"]:
        raise AuditEvidenceError(
            "unregistered AuditPlan due stage %r" % due_stage)
    catalog = current_receipt_catalog(result)
    relative, plan, digest = _resolve_current_plan(
        result, item, catalog, required_state=required_state)
    _require_current_profile_rendering_contract_state(result, item)
    obligations = tuple(
        dict(row) for row in plan["obligations"]
        if row.get("due_stage") == due_stage)
    if not obligations:
        raise AuditEvidenceError(
            "AuditPlan %s has no obligations due at %s" %
            (plan["plan_id"], due_stage))
    return {
        "audit_plan_id": plan["plan_id"],
        "audit_plan_path": relative,
        "audit_plan_sha256": digest,
        "plan": plan,
        "obligations": obligations,
    }


def _receipt_plan_binding_errors(receipt, plan, plan_sha256, obligation):
    expected = {
        field: plan[field] for field in _PLAN_BINDING_FIELDS
    }
    expected.update({
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "due_stage": obligation["due_stage"],
        "evidence_role": obligation["evidence_role"],
        "evidence_kind": obligation["evidence_kind"],
        "dimension": obligation["dimension"],
        "acceptance_predicate": obligation["acceptance_predicate"],
        "producer_check": obligation["producer_check"],
        "producer_capability": obligation["producer_capability"],
        "producer_gate_id": obligation["producer_gate_id"],
        "consumer_gate_id": obligation["consumer_gate_id"],
        "fingerprint_binding": obligation["fingerprint_binding"],
        "review_due": obligation["review_due"],
        "result": "passed",
        "invalidated_by": None,
        "reused_receipt_id": None,
        "reuse_reason": None,
    })
    errors = [field for field, value in expected.items()
              if receipt.get(field) != value]
    scope = receipt.get("scope")
    if (not isinstance(scope, list) or
            obligation["target"] not in scope):
        errors.append("scope")
    return errors


def _producer_evidence_errors(root, catalog, plan, plan_sha256,
                              obligation, receipt):
    errors = []
    reference = receipt.get("evidence_ref")
    try:
        evidence = _current_record(
            catalog, reference, "AuditReceipt producer evidence")
    except AuditEvidenceError as exc:
        return [str(exc)]
    expected = {
        "check": obligation["producer_check"],
        "target": obligation["target"],
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "task_id": plan["task_id"],
        "batch_id": plan["batch_id"],
        "opening_transition_receipt":
            plan["opening_transition_receipt"],
        "standards_version": plan["standards_version"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "fingerprint_binding": obligation["fingerprint_binding"],
        "result": "pass",
        "invalidated_by": None,
    }
    errors.extend(field for field, value in expected.items()
                  if evidence.get(field) != value)
    expected_method = "%s@%s/%s" % (
        evidence.get("tool"), evidence.get("tool_version"),
        evidence.get("check"))
    if receipt.get("verifier") != evidence.get("tool"):
        errors.append("verifier")
    if receipt.get("method") != expected_method:
        errors.append("method")
    if receipt.get("checked_at") != evidence.get("checked_at"):
        errors.append("checked_at")
    for field in (
            "artifact_fingerprint", "dependency_fingerprint",
            "contract_fingerprint"):
        if receipt.get(field) != evidence.get(field):
            errors.append(field)
    evidence_scope = evidence.get("scope")
    if isinstance(evidence_scope, list):
        expected_scope = sorted(set(
            evidence_scope + [obligation["target"]]))
        if receipt.get("scope") != expected_scope:
            errors.append("scope")
    if obligation["producer_check"] == "substantive_review":
        review_contract = None
        try:
            review_contract = substantive_review_contract.load_contract(root)
            substantive_review_contract.validate_review_receipt(
                evidence, contract=review_contract)
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            errors.append("substantive-review contract: %s" % exc)
        if evidence.get("round") == 2 and review_contract is not None:
            try:
                first = _current_record(
                    catalog, evidence.get("round_1_receipt_id"),
                    "round-1 substantive-review evidence")
                if first.get("invalidated_by") is not None:
                    raise AuditEvidenceError(
                        "round-1 substantive-review evidence is invalidated")
                substantive_review_contract.validate_review_pair(
                    first, evidence, contract=review_contract)
            except (OSError, TypeError, UnicodeError, ValueError,
                    kblib.YamlSubsetError) as exc:
                errors.append("substantive-review pair: %s" % exc)
        if evidence.get("verdict") != "passed":
            errors.append("verdict")
        try:
            expected_artifact = _current_page_artifact_fingerprint(
                root, obligation["target"])
            if evidence.get("artifact_fingerprint") != expected_artifact:
                errors.append("artifact_fingerprint")
        except (OSError, TypeError, UnicodeError, ValueError,
                AuditEvidenceError, kblib.YamlSubsetError) as exc:
            errors.append("artifact_fingerprint: %s" % exc)
        if evidence.get("sources_sha256") != \
                receipt.get("dependency_fingerprint"):
            errors.append("sources_sha256")
        if evidence.get("acceptance_predicate") != \
                obligation["acceptance_predicate"]:
            errors.append("acceptance_predicate")
        if evidence.get("contract_fingerprint") != \
                audit_fingerprint.obligation_contract_fingerprint(
                    plan, obligation):
            errors.append("contract_fingerprint")
    elif obligation["producer_check"] == \
            "changed_scope_rendering_escalation_record":
        try:
            contract = rendering_verification_contract.load_contract(root)
            rendering_verification_contract.validate_record_for_obligation(
                evidence, plan, plan_sha256, obligation, contract)
            if evidence.get("artifact_fingerprint") != \
                    _current_page_set_artifact_fingerprint(
                        root, evidence.get("scope")):
                errors.append("artifact_fingerprint")
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            errors.append("rendering-verification contract: %s" % exc)
    elif changed_scope_evidence_contract.pure_check_owner(
            obligation.get("owner_rule_id"),
            obligation.get("producer_check")) is not None:
        try:
            current_artifact = None
            target = obligation.get("target")
            if isinstance(target, str) and target.lower().endswith(".md"):
                current_artifact = _current_page_artifact_fingerprint(
                    root, target)
            changed_scope_evidence_contract.validate_record_for_plan(
                evidence, plan, plan_sha256, obligation, root=root,
                artifact_fingerprint=current_artifact)
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            errors.append("changed-scope evidence contract: %s" % exc)
    return sorted(set(errors))


def validate_audit_receipt_for_obligation(root, catalog, plan, plan_sha256,
                                          obligation, receipt):
    """Validate one full AuditReceipt through the sole runtime consumer.

    Callers that need a dimension-specific AuditReceipt must use this boundary
    instead of reimplementing a weaker subset of the Kernel contract.  The
    function proves both the receipt's closed machine shape and the referenced
    producer evidence, including the original plan, obligation, current
    authority, and evidence-time fingerprints.
    """
    if not isinstance(obligation, dict) or \
            obligation.get("evidence_kind") != "audit-receipt":
        raise AuditEvidenceError(
            "AuditReceipt validation requires one audit-receipt obligation")
    if not isinstance(receipt, dict):
        raise AuditEvidenceError("AuditReceipt must be a mapping")
    try:
        contract = audit_receipt_contract.load_contract(root)
        audit_receipt_contract.validate_audit_receipt(
            receipt, contract=contract)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        raise AuditEvidenceError(
            "invalid full AuditReceipt %r: %s" %
            (receipt.get("receipt_id"), exc)) from exc
    errors = _receipt_plan_binding_errors(
        receipt, plan, plan_sha256, obligation)
    errors.extend(_producer_evidence_errors(
        root, catalog, plan, plan_sha256, obligation, receipt))
    errors = sorted(set(errors))
    if errors:
        raise AuditEvidenceError(
            "AuditReceipt %s does not discharge obligation %s in: %s" %
            (receipt.get("receipt_id"), obligation.get("obligation_id"),
             ", ".join(errors)))
    return receipt


def _record_sha256(record):
    return kblib.sha256_bytes(kblib.canonical_json_bytes(record))


def _batch_page_binding_errors(result, catalog, root, plan, plan_sha256,
                               obligation, record):
    errors = []
    try:
        registry = batch_review_obligation_contract.load_registry(root)
        batch_review_obligation_contract.validate_producer_receipt(
            record, registry)
        batch_review_obligation_contract.validate_receipt_consumption(
            plan, plan_sha256, record, catalog, registry)
        profile_view = result.get("_profile_authorized_view")
        _metadata_contract, rules = metadata_property_state.\
            authorized_profile_projection_rules(root, profile_view)
        snapshot, semantic_fingerprint = \
            metadata_property_state.semantic_page_snapshot(
                root, obligation["target"], rules=rules)
        batch_review_obligation_contract.validate_page_fingerprint_binding(
            record, obligation["target"], snapshot.read_text(),
            semantic_fingerprint)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        return ["batch-page-review contract: %s" % exc]
    expected = {
        field: plan[field] for field in _PLAN_BINDING_FIELDS
    }
    expected.update({
        "record_kind": "batch-page-review-record",
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "target": obligation["target"],
        "partition": obligation["partition"],
        "due_stage": obligation["due_stage"],
        "evidence_role": obligation["evidence_role"],
        "evidence_kind": obligation["evidence_kind"],
        "dimension": obligation["dimension"],
        "acceptance_predicate": obligation["acceptance_predicate"],
        "producer_capability": obligation["producer_capability"],
        "consumer_gate_id": obligation["consumer_gate_id"],
        "fingerprint_binding": obligation["fingerprint_binding"],
        "verdict": "passed",
        "result": "pass",
        "invalidated_by": None,
    })
    errors.extend(field for field, value in expected.items()
                  if record.get(field) != value)
    return sorted(set(errors))


def _changed_scope_rule_ids(root):
    return frozenset(
        row["rule_id"] for row in
        changed_scope_evidence_contract.normalized_base_rules(root=root))


def _direct_binding_errors(root, plan, plan_sha256, obligation, record):
    """Validate a plan-bound Gate or candidate-set evidence record.

    These records intentionally remain their registered evidence kind.  They
    are not promoted to a dimension-specific AuditReceipt merely so a common
    consumer can count them.
    """
    if obligation.get("owner_rule_id") in _changed_scope_rule_ids(root):
        try:
            current_artifact = None
            target = obligation.get("target")
            if isinstance(target, str) and target.lower().endswith(".md"):
                current_artifact = _current_page_artifact_fingerprint(
                    root, target)
            changed_scope_evidence_contract.validate_record_for_plan(
                record, plan, plan_sha256, obligation, root=root,
                artifact_fingerprint=current_artifact)
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            return ["changed-scope direct evidence contract: %s" % exc]
        return []

    expected = {
        field: plan[field] for field in _PLAN_BINDING_FIELDS
    }
    expected.update({
        "record_kind": obligation["evidence_kind"],
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "target": obligation["target"],
        "partition": obligation["partition"],
        "due_stage": obligation["due_stage"],
        "evidence_role": obligation["evidence_role"],
        "evidence_kind": obligation["evidence_kind"],
        # The dimension on the AuditPlan is the obligation's planning and
        # coverage placement.  A Gate/candidate producer remains dimensionless
        # evidence and must not be made to impersonate an AuditReceipt.
        "dimension": None,
        "acceptance_predicate": obligation["acceptance_predicate"],
        "producer_check": obligation["producer_check"],
        "producer_capability": obligation["producer_capability"],
        "producer_gate_id": obligation["producer_gate_id"],
        "consumer_gate_id": obligation["consumer_gate_id"],
        "fingerprint_binding": obligation["fingerprint_binding"],
        "invalidated_by": None,
    })
    errors = [field for field, value in expected.items()
              if record.get(field) != value]
    if (obligation["producer_gate_id"] is not None and
            record.get("gate_id") != obligation["producer_gate_id"]):
        errors.append("gate_id")
    allowed_results = {"pass", "passed"}
    if obligation["evidence_role"] == "triggers":
        allowed_results.add("candidate")
    if record.get("result") not in allowed_results:
        errors.append("result")
    for field in (
            "artifact_fingerprint", "dependency_fingerprint",
            "contract_fingerprint"):
        value = record.get(field)
        if not audit_plan_contract.is_sha256(value):
            errors.append(field)
    return sorted(set(errors))


def _profile_judgment_binding_errors(result, item, plan, plan_sha256,
                                     obligation, record):
    view = result.get("_profile_authorized_view") or {}
    contract = view.get("_contract")
    if contract is None or not getattr(contract, "authorized", False):
        return ["runtime has no authorized typed Profile contract"]
    if obligation.get("kernel_extension_point") != \
            profile_batch_judgment_contract.EXTENSION_POINT:
        return ["kernel_extension_point"]
    return profile_batch_judgment_contract.receipt_binding_errors(
        result["root"], plan, plan_sha256, contract, item, record, view)


def _required_stage_records(result, item, plan, plan_sha256, catalog,
                            due_stage):
    root = result["root"]
    obligations = [row for row in plan["obligations"]
                   if row["due_stage"] == due_stage]
    candidates = {row["obligation_id"]: [] for row in obligations
                  if row["status"] == "required"}
    for key, entry in catalog.items():
        record = _record(entry)
        if not isinstance(record, dict) or record.get("receipt_id") != key:
            continue
        if record.get("plan_id") != plan["plan_id"]:
            continue
        obligation_id = record.get("obligation_id")
        if obligation_id not in candidates:
            continue
        candidates[obligation_id].append(record)

    selected = []
    for obligation in obligations:
        if obligation["status"] == "reused":
            record = _current_record(
                catalog, obligation["evidence_ref"],
                "reused AuditPlan evidence")
            if record.get("invalidated_by") is not None:
                raise AuditEvidenceError(
                    "reused evidence %s is invalidated" %
                    obligation["evidence_ref"])
            semantic = {
                "owner_kind": obligation["owner_kind"],
                "owner_rule_id": obligation["owner_rule_id"],
                "kernel_extension_point":
                    obligation["kernel_extension_point"],
                "due_stage": obligation["due_stage"],
                "evidence_role": obligation["evidence_role"],
                "evidence_kind": obligation["evidence_kind"],
                "dimension": obligation["dimension"],
                "acceptance_predicate": obligation["acceptance_predicate"],
                "producer_check": obligation["producer_check"],
                "producer_capability": obligation["producer_capability"],
                "producer_gate_id": obligation["producer_gate_id"],
                "consumer_gate_id": obligation["consumer_gate_id"],
            }
            mismatches = [field for field, value in semantic.items()
                          if record.get(field) != value]
            scope = record.get("scope")
            if record.get("target") != obligation["target"] and not (
                    isinstance(scope, list) and
                    obligation["target"] in scope):
                mismatches.append("target/scope")
            if mismatches:
                raise AuditEvidenceError(
                    "reused evidence %s differs from obligation %s in: %s" %
                    (record.get("receipt_id"), obligation["obligation_id"],
                     ", ".join(sorted(set(mismatches)))))
            selected.append((obligation, record, True))
            continue

        matches = [record for record in candidates[obligation["obligation_id"]]
                   if record.get("record_kind") ==
                   obligation["evidence_kind"]]
        if len(matches) != 1:
            raise AuditEvidenceError(
                "required AuditPlan obligation %s needs exactly one current "
                "%s, found %d" %
                (obligation["obligation_id"],
                 obligation["evidence_kind"], len(matches)))
        record = matches[0]
        kind = obligation["evidence_kind"]
        if kind == "audit-receipt":
            validate_audit_receipt_for_obligation(
                root, catalog, plan, plan_sha256, obligation, record)
        elif kind == "batch-page-review-record":
            errors = _batch_page_binding_errors(
                result, catalog, root, plan, plan_sha256, obligation, record)
            if errors:
                raise AuditEvidenceError(
                    "batch-page evidence %s does not discharge obligation %s "
                    "in: %s" %
                    (record.get("receipt_id"), obligation["obligation_id"],
                     ", ".join(errors)))
        elif kind == profile_batch_judgment_contract.RECORD_KIND:
            errors = _profile_judgment_binding_errors(
                result, item, plan, plan_sha256, obligation, record)
            if errors:
                raise AuditEvidenceError(
                    "Profile Batch Review evidence %s does not discharge "
                    "obligation %s in: %s" %
                    (record.get("receipt_id"), obligation["obligation_id"],
                     ", ".join(errors)))
        elif kind in {"gate-receipt", "candidate-set-receipt"}:
            errors = _direct_binding_errors(
                root, plan, plan_sha256, obligation, record)
            if errors:
                raise AuditEvidenceError(
                    "%s %s does not discharge obligation %s in: %s" %
                    (kind, record.get("receipt_id"),
                     obligation["obligation_id"], ", ".join(errors)))
        else:
            raise AuditEvidenceError(
                "stage consumer has no validator for evidence kind %s" % kind)
        selected.append((obligation, record, False))
    return selected


def stage_evidence_closure(result, item, due_stage, required_state=None):
    """Resolve every obligation due at one stage across all evidence kinds."""
    catalog = current_receipt_catalog(result)
    relative, plan, plan_sha256 = _resolve_current_plan(
        result, item, catalog, required_state=required_state)
    _require_current_profile_rendering_contract_state(result, item)
    selected = _required_stage_records(
        result, item, plan, plan_sha256, catalog, due_stage)
    bindings = []
    audit_receipts = []
    for obligation, record, reused in selected:
        binding = {
            "obligation_id": obligation["obligation_id"],
            "owner_kind": obligation["owner_kind"],
            "owner_rule_id": obligation["owner_rule_id"],
            "due_stage": obligation["due_stage"],
            "target": obligation["target"],
            "evidence_role": obligation["evidence_role"],
            "evidence_kind": obligation["evidence_kind"],
            "dimension": obligation["dimension"],
            "evidence_ref": record["receipt_id"],
            "evidence_sha256": _record_sha256(record),
            "artifact_fingerprint": record["artifact_fingerprint"],
            "dependency_fingerprint": record["dependency_fingerprint"],
            "contract_fingerprint": record["contract_fingerprint"],
            "result": record["result"],
            "reused": reused,
            "reuse_reason": obligation["reuse_reason"] if reused else None,
        }
        if tuple(binding) != _EVIDENCE_BINDING_FIELDS:
            raise AssertionError("audit evidence binding fields drifted")
        bindings.append(binding)
        if obligation["evidence_kind"] == "audit-receipt":
            audit_receipts.append(record)
    bindings.sort(key=lambda row: row["obligation_id"])
    audit_receipts.sort(key=lambda row: row["receipt_id"])
    return {
        "audit_plan_id": plan["plan_id"],
        "audit_plan_path": relative,
        "audit_plan_sha256": plan_sha256,
        "audit_evidence_bindings": bindings,
        "audit_evidence_set_sha256": kblib.sha256_bytes(
            kblib.canonical_json_bytes(bindings)),
        "audit_receipt_ids": [row["receipt_id"] for row in audit_receipts],
        "audit_receipt_set_sha256":
            audit_receipt_contract.receipt_set_sha256(
                audit_receipts,
                contract=audit_receipt_contract.load_contract(
                    result["root"])),
    }


def batch_review_evidence(result, item, required_state="open"):
    """Return the exact heterogeneous pre-merge closure Batch Review binds."""
    return stage_evidence_closure(
        result, item, "pre-merge", required_state=required_state)


def wrapper_binding_errors(result, item, wrapper, required_state="open"):
    """Return fail-closed differences from the current audit evidence set."""
    if not isinstance(wrapper, dict):
        return ["batch-review wrapper must be a mapping"]
    try:
        expected = batch_review_evidence(
            result, item, required_state=required_state)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        return ["batch-review audit evidence is invalid: %s" % exc]
    errors = []
    for field in (
            "audit_plan_id", "audit_plan_path", "audit_plan_sha256",
            "audit_evidence_bindings", "audit_evidence_set_sha256",
            "audit_receipt_ids", "audit_receipt_set_sha256"):
        if wrapper.get(field) != expected[field]:
            errors.append(
                "batch-review wrapper %s does not match the current "
                "AuditPlan evidence closure" % field)
    return errors


def closed_plan_closure_errors(result, item, close_receipt):
    """Validate the pre-merge and post-Delta halves of one immutable plan."""
    errors = []
    if not isinstance(close_receipt, dict):
        return ["batch-close aggregate must be a mapping"]
    catalog = current_receipt_catalog(result)
    batch_receipts = item.get("batch_receipts") or []
    if (not isinstance(batch_receipts, list) or
            len(batch_receipts) != 1):
        return ["merge-ready batch must bind exactly one Batch Review wrapper"]
    try:
        wrapper = _current_record(
            catalog, batch_receipts[0], "Batch Review wrapper")
        errors.extend(wrapper_binding_errors(
            result, item, wrapper, required_state="merge-ready"))
        premerge = batch_review_evidence(
            result, item, required_state="merge-ready")
        stage_plan = resolve_stage_plan(
            result, item, "post-delta-close",
            required_state="merge-ready")
        profile_view = result.get("_profile_authorized_view") or {}
        profile_contract = profile_view.get("_contract") or result.get(
            "_profile_contract")
        projection = batch_close_audit.resolve_post_delta_projection(
            stage_plan,
            batch_close_contract.closed_list_member_rows(result["root"]),
            profile_contract)
        raw_bindings = close_receipt.get("post_delta_evidence_bindings")
        if not isinstance(raw_bindings, list):
            raise AuditEvidenceError(
                "batch-close aggregate has no post-Delta evidence bindings")
        evidence_by_id = {}
        for binding in raw_bindings:
            if not isinstance(binding, dict):
                raise AuditEvidenceError(
                    "post-Delta evidence binding must be a mapping")
            evidence_ref = binding.get("evidence_ref")
            evidence_by_id[evidence_ref] = _current_record(
                catalog, evidence_ref, "post-Delta evidence")
        postdelta = batch_close_audit.validate_post_delta_evidence_set(
            stage_plan, projection, raw_bindings, evidence_by_id,
            close_receipt.get("merged_snapshot_sha256"))
        expected_close = {
            "audit_plan_id": stage_plan["audit_plan_id"],
            "audit_plan_path": stage_plan["audit_plan_path"],
            "audit_plan_sha256": stage_plan["audit_plan_sha256"],
            "post_delta_evidence_count": len(postdelta["bindings"]),
            "post_delta_evidence_set_sha256":
                postdelta["evidence_set_sha256"],
            "post_delta_audit_receipt_ids":
                postdelta["audit_receipt_ids"],
            "post_delta_audit_receipt_set_sha256":
                postdelta["audit_receipt_set_sha256"],
        }
        errors.extend(
            "batch-close aggregate %s does not match the post-Delta closure" %
            field for field, value in expected_close.items()
            if close_receipt.get(field) != value)
        if premerge["audit_plan_id"] != stage_plan["audit_plan_id"] or \
                premerge["audit_plan_sha256"] != \
                stage_plan["audit_plan_sha256"]:
            errors.append(
                "pre-merge and post-Delta evidence bind different AuditPlans")
        closed_ids = {
            row["obligation_id"]
            for row in premerge["audit_evidence_bindings"]
        }
        closed_ids.update(
            row["obligation_id"] for row in postdelta["bindings"])
        expected_ids = {
            row["obligation_id"] for row in stage_plan["plan"]["obligations"]
        }
        if closed_ids != expected_ids:
            errors.append(
                "closed transition does not consume the complete AuditPlan "
                "obligation set")
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        errors.append("closed AuditPlan evidence is invalid: %s" % exc)
    return sorted(set(errors))


__all__ = [
    "AuditEvidenceError", "batch_review_evidence",
    "closed_plan_closure_errors", "resolve_stage_plan",
    "stage_evidence_closure",
    "validate_audit_receipt_for_obligation", "wrapper_binding_errors",
]
