"""Resolve the current AuditPlan evidence closure for Batch Review.

This module is a read-only consumer.  It deliberately depends only on the
already-admitted runtime projection, the current receipt catalog, and the
three Kernel-owned audit contracts.  In particular, it does not import a
producer CLI or ``check_queue``: Queue validation imports this module, so a
producer dependency here would create both a circular import and a second
interpretation of current runtime state.
"""

from contextlib import contextmanager
from copy import deepcopy
import os
import stat

import Tools.execution.audit.audit_fingerprint as audit_fingerprint
import Tools.execution.audit.audit_lifecycle_contract as audit_lifecycle_contract
import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection
import Tools.execution.audit.audit_plan_contract as audit_plan_contract
import Tools.execution.audit.audit_producer_chain as audit_producer_chain
import Tools.execution.audit.audit_reconciliation_contract as audit_reconciliation_contract
import Tools.execution.audit.audit_receipt_contract as audit_receipt_contract
import Tools.execution.audit.batch_close_audit as batch_close_audit
import Tools.execution.audit.batch_close_contract as batch_close_contract
import Tools.execution.audit.batch_review_obligation_contract as batch_review_obligation_contract
import Tools.execution.audit.batch_review_receipt_contract as batch_review_receipt_contract
import Tools.execution.evidence.receipt_reference_contract as receipt_reference_contract
import Tools.execution.evidence.receipt_type_contract as receipt_type_contract
import Tools.execution.evidence.evidence_attempt_runtime as evidence_attempt_runtime
import Tools.knowledge.rendering.changed_scope_rendering_checks as changed_scope_rendering_checks
import Tools.execution.audit.changed_scope_evidence_contract as changed_scope_evidence_contract
import Tools.execution.audit.changed_scope_evidence_runtime as changed_scope_evidence_runtime
import Tools.platform.common.kblib as kblib
import Tools.execution.evidence.metadata_gate_runtime as metadata_gate_runtime
import Tools.knowledge.metadata.metadata_property_state as metadata_property_state
import Tools.governance.profile.profile_batch_judgment_contract as profile_batch_judgment_contract
import Tools.governance.profile.profile_contract as profile_contract
import Tools.knowledge.rendering.rendering_verification_contract as rendering_verification_contract
import Tools.knowledge.rendering.profile_rendering_evidence_contract as profile_rendering
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.audit.substantive_review_contract as substantive_review_contract

from Tools.execution.task_runtime.queue_runtime.property_state import (
    current_opening_semantic_context,
)
from Tools.execution.task_runtime.queue_runtime.receipts import (
    current_receipt_catalog,
    historical_receipt_catalog,
    register_observation,
)
from Tools.platform.common.primitives import catalog_record


class AuditEvidenceError(ValueError):
    """The current AuditPlan or its evidence closure is not provable."""


class AuditEvidenceMissing(AuditEvidenceError):
    """One required AuditPlan obligation has no current evidence record."""


class AuditEvidenceAmbiguous(AuditEvidenceError):
    """One required AuditPlan obligation has multiple current records."""


class AuditPlanMissing(AuditEvidenceError):
    """The current batch has no AuditPlan candidate to validate."""


_PLAN_BINDING_FIELDS = audit_lifecycle_contract.PLAN_BINDING_FIELDS


class _EvidenceFacts:
    """Mechanical facts retained for one read-only evaluation, never authority.

    The context is private to a copied runtime view and is not returned or
    persisted. A new public invocation (including a writer's locked recheck)
    starts a new context. Record keys include their bytes, not just IDs;
    candidate selection and currentness are resolved by the consumer. Only
    an explicit evidence_observation scope can share a stage resolution.
    """

    def __init__(self, result, *, enabled=True):
        self.root = result["root"]
        self.evaluation = (result.get("_profile_authorized_view") or {}).get("_evaluation")
        self.enabled = enabled
        self._values = {}
        self._catalogs = {}

    def memo(self, key, compute):
        if not self.enabled:
            return compute()
        if key not in self._values:
            try:
                self._values[key] = (compute(), None)
            except (TypeError, ValueError) as exc:
                self._values[key] = (None, (type(exc), exc.args))
        value, error = self._values[key]
        if error is not None:
            kind, args = error
            raise kind(*args)
        return value

    def contract(self, owner):
        return self.memo(("contract", owner.__name__),
                         lambda: owner.load_contract(
                             self.root, cache_projection=self.enabled))

    def batch_registry(self):
        return self.memo(("batch-registry",), lambda:
            batch_review_obligation_contract.load_registry(
                self.root, cache_projection=self.enabled))

    def batch_record(self, record, registry):
        return self.memo(("batch-record", _record_sha256(registry), _record_sha256(record)),
            lambda: batch_review_obligation_contract.validate_producer_receipt(record, registry))

    def records(self, catalog, plan_id, obligation_id):
        # Retain the view itself so object IDs cannot be reused during this
        # evaluation. A candidate addition uses a new catalog; a new public
        # invocation (or locked recheck) gets an entirely new index.
        key = id(catalog)
        if not self.enabled or key not in self._catalogs:
            index = {}
            for identity, entry in catalog.items():
                record = catalog_record(entry)
                if not isinstance(record, dict) or record.get("receipt_id") != identity:
                    continue
                binding = (record.get("plan_id"), record.get("obligation_id"))
                if not all(isinstance(value, str) for value in binding):
                    continue
                index.setdefault(binding, []).append(record)
            for rows in index.values():
                rows.sort(key=lambda row: row.get("receipt_id") or "")
            if not self.enabled:
                return index.get((plan_id, obligation_id), [])
            self._catalogs[key] = (catalog, index)
        return self._catalogs[key][1].get((plan_id, obligation_id), [])

    def metadata_page(self, relative, profile_view):
        def capture():
            _contract, rules = self.memo(("metadata-rules",), lambda:
                metadata_property_state.authorized_profile_projection_rules(
                    self.root, profile_view))
            return metadata_property_state.semantic_page_snapshot(
                self.root, relative, rules=rules)
        return self.memo(("metadata-page", relative), capture)

    def chain(self, obligation):
        return audit_producer_chain.precursor_chain_for_obligation(
            obligation, root=self.root, evaluation=self.evaluation,
            contract_loader=self.contract)

    def validate(self, owner, validator, record, *, contract=None):
        contract = contract if contract is not None else self.contract(owner)
        return self.memo(("record", owner.__name__, validator,
                          _record_sha256(contract), _record_sha256(record)),
                         lambda: validator(record, contract=contract))

    def review(self, record, *, contract=None):
        return self.validate(substantive_review_contract,
            substantive_review_contract.validate_review_receipt,
            record, contract=contract)

    def review_pair(self, first, second):
        contract = self.contract(substantive_review_contract)
        return self.memo(("review-pair", _record_sha256(contract),
                          _record_sha256(first), _record_sha256(second)),
            lambda: substantive_review_contract.validate_review_pair(
                first, second, contract=contract, validate_receipt=self.review))

    def page_snapshot(self, relative):
        def capture():
            snapshot = kblib.repository_target_snapshot(
                self.root, relative, suffixes=(".md", ".MD"), singly_linked=True)
            if not snapshot.exists:
                raise AuditEvidenceError("artifact target does not exist: %s" % relative)
            return snapshot
        return self.memo(("page-snapshot", relative), capture)

    def page_artifact(self, relative):
        return self.memo(("page-artifact", relative),
            lambda: _current_page_artifact_fingerprint(
                self.root, relative, snapshot=self.page_snapshot(relative),
                contract=self.contract(audit_receipt_contract)))

    def page_sources(self, relative):
        return self.memo(("page-sources", relative), lambda:
            audit_fingerprint.sources_sha256(self.page_snapshot(relative).read_text()))

    def page_set_artifact(self, scope):
        return self.memo(("page-set-artifact", tuple(scope or ())), lambda:
            _current_page_set_artifact_fingerprint(self.root, scope, facts=self))


def evidence_evaluation(result):
    """Bind mechanical facts to one read-only evaluation of an admitted view.

    Producers may explicitly share this view before a write. Never persist it
    or reuse it after a write; lock-time admission must provide a fresh view.
    It neither admits runtime nor caches currentness or stage verdicts.
    """
    if "_audit_evidence_facts" in result:
        return result
    return {**result, "_audit_evidence_facts": _EvidenceFacts(result),
            "current_receipt_catalog": current_receipt_catalog(result),
            "receipt_catalog": historical_receipt_catalog(result)}


@contextmanager
def evidence_observation(result):
    """Share stage projections only within one explicitly read-only action.

    This is not a persistent valid-evidence cache. Each invocation, locked
    rebuild and resulting-state read starts another observation. Leaving the
    block retires its stage results even if a caller retains the view.
    """
    view = dict(result)
    view.pop("_audit_evidence_facts", None)
    view = evidence_evaluation(view)
    view["_audit_stage_resolutions"] = {}
    try:
        with audit_producer_chain.producer_chain_observation(
                view["_audit_evidence_facts"].memo), \
                audit_plan_contract.serialization_observation(
                    view["_audit_evidence_facts"].memo), \
                batch_review_obligation_contract.registry_observation(
                    view["root"]), \
                profile_batch_judgment_contract.judgment_observation(
                    view["_audit_evidence_facts"].memo), \
                audit_obligation_projection.obligation_projection_observation(
                    view["_audit_evidence_facts"].memo), \
                register_observation(view["_audit_evidence_facts"].memo):
            yield view
    finally:
        view.pop("_audit_stage_resolutions").clear()
        view.pop("_audit_evidence_facts", None)


@contextmanager
def continue_evidence_observation(result):
    """Join this admitted view's active read, or start a fresh standalone read.

    Explicit evidence_observation calls always create a new boundary. This
    continuation is only for nested read-only consumers of that same view.
    """
    if (isinstance(result.get("_audit_evidence_facts"), _EvidenceFacts) and
            "_audit_stage_resolutions" in result):
        yield result
    else:
        with evidence_observation(result) as observed:
            yield observed


def _current_page_artifact_fingerprint(root, relative, *, snapshot=None,
                                      contract=None):
    snapshot = snapshot or kblib.repository_target_snapshot(
        root, relative, suffixes=(".md", ".MD"), singly_linked=True)
    if not snapshot.exists:
        raise AuditEvidenceError(
            "artifact target does not exist: %s" % relative)
    return audit_fingerprint.page_artifact_fingerprint(
        relative, snapshot.read_text(), contract=contract)


def _current_page_set_artifact_fingerprint(root, scope, *, facts=None):
    if (not isinstance(scope, list) or not scope or
            len(scope) != len(set(scope))):
        raise AuditEvidenceError(
            "artifact scope must be a non-empty unique page list")
    pages = []
    for relative in scope:
        snapshot = (facts.page_snapshot(relative) if facts else
            kblib.repository_target_snapshot(
                root, relative, suffixes=(".md", ".MD"), singly_linked=True))
        if not snapshot.exists:
            raise AuditEvidenceError(
                "artifact target does not exist: %s" % relative)
        pages.append((relative, snapshot.read_text()))
    return audit_fingerprint.page_set_artifact_fingerprint(
        pages, contract=facts.contract(audit_receipt_contract) if facts else None)

_EVIDENCE_BINDING_FIELDS = audit_lifecycle_contract.EVIDENCE_BINDING_FIELDS

_RECONCILIATION_ROW_FIELDS = (
    "obligation_id", "due_stage", "selected_evidence_ref",
    "selected_disposition", "produced_evidence_refs",
    "reused_reserved_evidence_ref", "superseded_evidence_refs",
    "invalidated_evidence_refs", "unresolved", "unresolved_reason",
)

def _current_record(catalog, receipt_id, label):
    if not isinstance(receipt_id, str) or not receipt_id:
        raise AuditEvidenceError("%s has no receipt identity" % label)
    entry = catalog.get(receipt_id)
    if entry is None and hasattr(catalog, "resolve"):
        entry = catalog.resolve(receipt_id)
    receipt = catalog_record(entry)
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
            raise AuditPlanMissing(
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
        "upstream_revision_id": view.get("upstream_revision_id"),
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
    try:
        view = result.get("_profile_authorized_view")
        from Tools.governance.profile.profile_admission import contract_from_admitted_view
        contract = contract_from_admitted_view(result["root"], view)
        audit_obligation_projection.validate_plan_definition_authority(
            plan, contract, root=result.get("root"))
        actual_snapshot = audit_plan_contract.\
            plan_contract_snapshot_sha256(plan)
        if plan.get("contract_snapshot_sha256") != actual_snapshot:
            raise ValueError(
                "AuditPlan contract_snapshot_sha256 does not bind its "
                "frozen definitions")
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        errors.append(str(exc))
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
    if not candidates and not rejected:
        raise AuditPlanMissing(
            "batch %s has no current AuditPlan" % item.get("id"))
    if len(candidates) != 1:
        detail = ""
        if rejected:
            detail = "; rejected candidate(s): %s" % " | ".join(rejected)
        raise AuditEvidenceError(
            "batch %s requires exactly one current AuditPlan, found %d%s"
            % (item.get("id"), len(candidates), detail))
    return candidates[0]


def _require_current_profile_rendering_contract_state(result, item, plan):
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
    profile = (result.get("_profile_authorized_view") or {}).get("_contract")
    profile_rendering.require_plan_applicability(plan, pages, profile, root=root)


def resolve_stage_plan(result, item, due_stage, required_state=None,
                       plan_path=None):
    """Resolve one immutable plan and its exact obligations due at a stage.

    This is the sole public plan-scanning boundary for pre-merge and
    post-Delta consumers.  It filters the already-frozen plan; it never
    reprojects, adds, or mutates an obligation.  ``plan_path`` is only an
    exact-path assertion after unique resolution; it never selects a
    candidate.
    """
    contract_values = audit_plan_contract.validate_contract(
        audit_plan_contract.load_contract(result.get("root")))
    if due_stage not in contract_values["due_stages"]:
        raise AuditEvidenceError(
            "unregistered AuditPlan due stage %r" % due_stage)
    catalog = current_receipt_catalog(result)
    relative, plan, digest = _resolve_current_plan(
        result, item, catalog, required_state=required_state)
    if plan_path is not None and relative != plan_path:
        raise AuditEvidenceError(
            "resolved current AuditPlan path %s differs from requested %s" %
            (relative, plan_path))
    _require_current_profile_rendering_contract_state(result, item, plan)
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


def _receipt_plan_binding_errors(
        receipt, plan, plan_sha256, obligation, *, require_pass=True):
    errors = audit_lifecycle_contract.attempt_binding_mismatches(
        receipt, plan, plan_sha256, obligation)
    expected = {
        "invalidated_by": None,
        "reused_receipt_id": None,
        "reuse_reason": None,
    }
    if require_pass:
        expected["result"] = "passed"
    errors.extend(field for field, value in expected.items()
                  if receipt.get(field) != value)
    scope = receipt.get("scope")
    if (not isinstance(scope, list) or
            obligation["target"] not in scope):
        errors.append("scope")
    return errors


def _producer_evidence_errors(root, catalog, plan, plan_sha256,
                              obligation, receipt, *, require_pass=True,
                              require_current=True, result=None, item=None):
    errors = []
    facts = (result or {}).get("_audit_evidence_facts") or _EvidenceFacts(
        result or {"root": root})
    reference = receipt.get("evidence_ref")
    try:
        evidence = _current_record(
            catalog, reference, "AuditReceipt producer evidence")
    except AuditEvidenceError as exc:
        return [str(exc)]
    try:
        chain = facts.chain(obligation)
        if not audit_producer_chain.precursor_record_matches(evidence, chain):
            raise audit_producer_chain.AuditProducerChainError(
                "record differs from the registered precursor identity")
    except audit_producer_chain.AuditProducerChainError as exc:
        return ["AuditReceipt producer chain: %s" % exc]
    errors.extend(audit_lifecycle_contract.attempt_binding_mismatches(
        evidence, plan, plan_sha256, obligation))
    expected = {
        "check": obligation["producer_check"],
        "invalidated_by": None,
    }
    if require_pass:
        expected["result"] = "pass"
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
    if chain["execution_route"] == "substantive-review":
        review_contract = None
        try:
            review_contract = facts.contract(substantive_review_contract)
            facts.review(evidence, contract=review_contract)
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
                facts.review_pair(first, evidence)
            except (OSError, TypeError, UnicodeError, ValueError,
                    kblib.YamlSubsetError) as exc:
                errors.append("substantive-review pair: %s" % exc)
        if require_pass and evidence.get("verdict") != "passed":
            errors.append("verdict")
        if require_current:
            try:
                expected_artifact = facts.page_artifact(obligation["target"])
                if evidence.get("artifact_fingerprint") != expected_artifact:
                    errors.append("artifact_fingerprint")
                if evidence.get("sources_sha256") != facts.page_sources(obligation["target"]):
                    errors.append("sources_sha256/current-input")
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
    elif chain["execution_route"] == "profile-rendering":
        try:
            profile_rendering.validate_record_for_obligation(
                evidence, plan, plan_sha256, obligation, root=root,
                evaluation=((result or {}).get("_profile_authorized_view") or {}).get("_evaluation"),
                require_current=require_current)
        except (OSError, TypeError, UnicodeError, ValueError, RuntimeError) as exc:
            errors.append("Profile rendering evidence: %s" % exc)
    elif chain["execution_route"] == "rendering-verification":
        try:
            contract = facts.contract(rendering_verification_contract)
            facts.memo(("rendering-binding", plan_sha256,
                        _record_sha256(obligation), _record_sha256(evidence),
                        _record_sha256(contract)), lambda:
                rendering_verification_contract.validate_record_for_obligation(
                    evidence, plan, plan_sha256, obligation, contract))
            if not isinstance(item, dict) or evidence.get("scope") != sorted(item.get("manifest") or []):
                errors.append("rendering-verification scope differs from the batch manifest")
            if require_current and evidence.get("artifact_fingerprint") != \
                    facts.page_set_artifact(evidence.get("scope")):
                errors.append("artifact_fingerprint")
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            errors.append("rendering-verification contract: %s" % exc)
    elif chain["execution_route"] == "deterministic-audit-precursor":
        try:
            current_artifact = None
            target = obligation.get("target")
            if (require_current and isinstance(target, str) and
                    target.lower().endswith(".md")):
                current_artifact = facts.page_artifact(target)
            changed_scope_evidence_contract.validate_record_for_plan(
                evidence, plan, plan_sha256, obligation, root=root,
                artifact_fingerprint=current_artifact)
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            errors.append("changed-scope evidence contract: %s" % exc)
        if require_current:
            if not isinstance(result, dict) or not isinstance(item, dict):
                errors.append(
                    "current changed-scope runtime context is unavailable")
            else:
                try:
                    changed_scope_evidence_runtime.validate_current_record(
                        evidence, root=root, result=result, item=item,
                        plan=plan, plan_sha256=plan_sha256,
                        obligation=obligation)
                except (OSError, TypeError, UnicodeError, ValueError,
                        kblib.YamlSubsetError) as exc:
                    errors.append("current changed-scope input: %s" % exc)
    else:
        errors.append(
            "AuditReceipt producer chain has unsupported execution route")
    return sorted(set(errors))


def _record_sha256(record):
    return kblib.sha256_bytes(kblib.canonical_json_bytes(record))


def _batch_page_binding_errors(result, catalog, root, plan, plan_sha256,
                               obligation, record, *, require_pass=True,
                               require_current=True):
    errors = []
    try:
        facts = result.get("_audit_evidence_facts") or _EvidenceFacts({**result, "root": root})
        registry = facts.batch_registry()
        facts.batch_record(record, registry)
        spec = batch_review_obligation_contract.obligation_spec_for_rule(
            obligation.get("owner_rule_id"), registry)
        current_receipt_ids = (catalog.selected_ids
                               if isinstance(catalog, _FrozenEvidenceView) else None)
        if require_current:
            current_receipt_ids = frozenset()
            if (spec.get("tier") == "M" and
                    spec.get("evidence_role") == "consumes"):
                current_receipt_ids = current_consumption_evidence_ids(
                    result, (result.get("items_by_id") or {}).get(
                        plan["batch_id"], {}), plan, plan_sha256,
                    obligation, registry)
        consumed = batch_review_obligation_contract.validate_receipt_consumption(
            plan, plan_sha256, record, catalog, registry,
            current_receipt_ids=current_receipt_ids,
            validate_record=facts.batch_record)
        if require_current:
            snapshot, semantic_fingerprint = facts.metadata_page(
                obligation["target"], result.get("_profile_authorized_view"))
            batch_review_obligation_contract.validate_input_binding(
                record, obligation["target"], snapshot.read_text(),
                semantic_fingerprint, consumed_records=consumed)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        return ["batch-page-review contract: %s" % exc]
    errors = audit_lifecycle_contract.attempt_binding_mismatches(
        record, plan, plan_sha256, obligation)
    expected = {
        "record_kind": "batch-page-review-record",
        "invalidated_by": None,
    }
    if require_pass:
        expected.update({"verdict": "passed", "result": "pass"})
    errors.extend(field for field, value in expected.items()
                  if record.get(field) != value)
    return sorted(set(errors))


def _changed_scope_rule_ids(root):
    return frozenset(
        row["rule_id"] for row in
        changed_scope_evidence_contract.normalized_base_rules(root=root))


def _direct_binding_errors(
        root, plan, plan_sha256, obligation, record, result=None, *,
        require_pass=True, require_current=True):
    """Validate a plan-bound Gate or candidate-set evidence record.

    These records intentionally remain their registered evidence kind.  They
    are not promoted to a dimension-specific AuditReceipt merely so a common
    consumer can count them.
    """
    is_profile_scan = obligation.get("kernel_extension_point") == \
        changed_scope_evidence_contract.PROFILE_SCAN_EXTENSION
    if (obligation.get("owner_rule_id") in _changed_scope_rule_ids(root) or
            is_profile_scan):
        try:
            current_artifact = None
            target = obligation.get("target")
            if (require_current and isinstance(target, str) and
                    target.lower().endswith(".md")):
                current_artifact = _current_page_artifact_fingerprint(
                    root, target)
            profile_view = (result or {}).get("_profile_authorized_view") or {}
            if require_current and not is_profile_scan:
                changed_scope_evidence_runtime.validate_current_direct_record(
                    record, root=root, plan=plan, plan_sha256=plan_sha256,
                    obligation=obligation, result=result,
                    artifact_fingerprint=current_artifact)
            else:
                changed_scope_evidence_contract.validate_record_for_plan(
                    record, plan, plan_sha256, obligation, root=root,
                    artifact_fingerprint=current_artifact,
                    evaluation=profile_view.get("_evaluation") if is_profile_scan else None)
            if is_profile_scan:
                if not profile_view:
                    raise ValueError(
                        "runtime has no authorized typed Profile view")
                scan = metadata_gate_runtime.registered_scan_for_id(
                    profile_view, obligation.get("owner_rule_id"))
                metadata_gate_runtime.validate_registered_scan_input_binding(
                    root, profile_view, scan, record,
                    expected_repository_snapshot=
                        record.get("artifact_fingerprint"),
                    require_current_repository=require_current)
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
    if not require_pass:
        allowed_results.add("fail")
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
                                     obligation, record, *,
                                     require_current=True):
    view = result.get("_profile_authorized_view") or {}
    from Tools.governance.profile.profile_admission import contract_from_admitted_view
    try:
        contract = contract_from_admitted_view(result["root"], view)
    except ValueError as exc:
        return [str(exc)]
    if obligation.get("kernel_extension_point") != \
            profile_batch_judgment_contract.EXTENSION_POINT:
        return ["kernel_extension_point"]
    return profile_batch_judgment_contract.receipt_binding_errors(
        result["root"], plan, plan_sha256, contract, item, record, view,
        require_current=require_current)


def _artifact_state(root, obligation, record, *, evaluation=None, facts=None):
    """Classify one attempt against the current observable after-image.

    ``unknown`` means that currentness is owned by the evidence-kind-specific
    validator rather than a page fingerprint.  A stale page-bound attempt is
    still valid history; it simply cannot discharge the current obligation.
    """
    if record.get("invalidated_by") is not None:
        return "invalidated"
    # A full AuditReceipt is a plan-bound terminal wrapper.  Its scope may
    # include the obligation target in addition to the producer's artifact
    # scope, so it is not itself an artifact-domain input.  Currentness is
    # proved below by the evidence-kind-specific validator against the cited
    # producer record.  Reinterpreting the wrapper scope as a page set makes a
    # valid receipt self-invalidate whenever the obligation target is a batch,
    # Gate, or other non-page identity.
    if record.get("record_kind") == "audit-receipt":
        return "unknown"
    target = obligation.get("target")
    try:
        if isinstance(target, str) and target.lower().endswith(".md"):
            expected = (facts.page_artifact(target) if facts else
                        _current_page_artifact_fingerprint(root, target))
            return ("current" if record.get("artifact_fingerprint") ==
                    expected else "stale")
        chain = None
        if obligation.get("evidence_kind") == "audit-receipt":
            try:
                chain = (facts.chain(obligation) if facts else
                    audit_producer_chain.precursor_chain_for_obligation(
                        obligation, root=root, evaluation=evaluation))
            except audit_producer_chain.AuditProducerChainError:
                return "invalid"
        if isinstance(chain, dict) and \
                chain.get("execution_route") == "rendering-verification":
            expected = (facts.page_set_artifact(record.get("scope")) if facts else
                _current_page_set_artifact_fingerprint(root, record.get("scope")))
            return ("current" if record.get("artifact_fingerprint") ==
                    expected else "stale")
    except (OSError, TypeError, UnicodeError, ValueError,
            AuditEvidenceError, kblib.YamlSubsetError):
        return "invalid"
    return "unknown"


def _audit_receipt_attempt_errors(
        result, item, catalog, plan, plan_sha256, obligation, record, *,
        require_current):
    """Validate a passing or failing full AuditReceipt as one attempt.

    A failed receipt is a valid historical outcome, not a discharge.  This
    validator proves its shape, producer, plan binding, and result agreement
    without silently upgrading it to a pass.
    """
    errors = []
    try:
        facts = result.get("_audit_evidence_facts") or _EvidenceFacts(result)
        facts.validate(audit_receipt_contract,
                       audit_receipt_contract.validate_audit_receipt, record)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        return ["AuditReceipt contract: %s" % exc]
    errors.extend(_receipt_plan_binding_errors(
        record, plan, plan_sha256, obligation, require_pass=False))
    errors.extend(_producer_evidence_errors(
        result["root"], catalog, plan, plan_sha256, obligation, record,
        require_pass=False, require_current=require_current,
        result=result, item=item))
    evidence = catalog_record(catalog.get(record.get("evidence_ref")))
    if isinstance(evidence, dict):
        expected_result = "passed" if evidence.get("result") == "pass" \
            else "failed" if evidence.get("result") == "fail" else None
        if record.get("result") != expected_result:
            errors.append("result/producer-result")
    else:
        errors.append("producer evidence")
    return sorted(set(errors))


def _audit_receipt_final_errors(result, item, plan, plan_sha256, catalog,
                                obligation, record, require_current):
    return _audit_receipt_attempt_errors(
        result, item, catalog, plan, plan_sha256, obligation, record,
        require_current=require_current)


def _batch_page_final_errors(result, item, plan, plan_sha256, catalog,
                             obligation, record, require_current):
    return _batch_page_binding_errors(
        result, catalog, result["root"], plan, plan_sha256, obligation,
        record, require_pass=False, require_current=require_current)


def _profile_judgment_final_errors(result, item, plan, plan_sha256, catalog,
                                   obligation, record, require_current):
    return _profile_judgment_binding_errors(
        result, item, plan, plan_sha256, obligation, record,
        require_current=require_current)


def _direct_final_errors(result, item, plan, plan_sha256, catalog,
                         obligation, record, require_current):
    return _direct_binding_errors(
        result["root"], plan, plan_sha256, obligation, record, result,
        require_pass=False, require_current=require_current)


def _profile_judgment_pass(_obligation, record):
    return record.get("result") == "pass"


def _audit_receipt_pass(_obligation, record):
    return record.get("result") == "passed"


def _batch_page_pass(_obligation, record):
    return (record.get("result") == "pass" and
            record.get("verdict") == "passed")


def _direct_pass(obligation, record):
    allowed = {"pass", "passed"}
    if obligation.get("evidence_role") == "triggers":
        allowed.add("candidate")
    return record.get("result") in allowed


# One implementation table owns both terminal validation and pass
# interpretation.  Adding a producer kind without adding its final consumer,
# or giving one kind two competing interpretations, is therefore visible as a
# single closure error rather than two drifting switch statements.
_FINAL_EVIDENCE_HANDLERS = {
    "audit-receipt": (_audit_receipt_final_errors, _audit_receipt_pass),
    "batch-page-review-record": (_batch_page_final_errors,
                                 _batch_page_pass),
    profile_batch_judgment_contract.RECORD_KIND:
        (_profile_judgment_final_errors, _profile_judgment_pass),
    "gate-receipt": (_direct_final_errors, _direct_pass),
    "candidate-set-receipt": (_direct_final_errors, _direct_pass),
}


def terminal_evidence_kinds():
    """Return evidence kinds with one installed final-consumer contract."""
    return frozenset(_FINAL_EVIDENCE_HANDLERS)


def _final_attempt_errors(result, item, plan, plan_sha256, catalog,
                          obligation, record, *, require_current):
    kind = obligation["evidence_kind"]
    handler = _FINAL_EVIDENCE_HANDLERS.get(kind)
    if handler is None:
        return ["stage consumer has no validator for evidence kind %s" % kind]
    return handler[0](
        result, item, plan, plan_sha256, catalog, obligation, record,
        require_current)


def _is_terminal_pass(obligation, record):
    handler = _FINAL_EVIDENCE_HANDLERS.get(obligation["evidence_kind"])
    return False if handler is None else handler[1](obligation, record)


def _attempt_summary(record, state, reason=None):
    return {
        "receipt_id": record.get("receipt_id"),
        "record_kind": record.get("record_kind"),
        "result": record.get("result"),
        "artifact_fingerprint": record.get("artifact_fingerprint"),
        "invalidated_by": record.get("invalidated_by"),
        "state": state,
        "reason": reason,
    }


def _invalid_history_reason(label, attempts):
    details = sorted({
        row.get("reason") for row in attempts
        if row.get("state") == "invalid" and row.get("reason")
    })
    return "%s: %s" % (label, "; ".join(details)) if details else label


def _negative_status(root, catalog, obligation, record, *, evaluation=None,
                     facts=None):
    try:
        chain = (facts.chain(obligation) if facts else
                 audit_producer_chain.precursor_chain_for_obligation(
                     obligation, root=root, evaluation=evaluation))
    except audit_producer_chain.AuditProducerChainError:
        chain = None
    if isinstance(chain, dict) and \
            chain.get("execution_route") == "substantive-review":
        producer = catalog_record(catalog.get(record.get("evidence_ref"))) \
            if record.get("record_kind") == "audit-receipt" else record
        if isinstance(producer, dict) and producer.get("verdict") == \
                "escalated":
            return "escalated"
    return "needs-correction"


def _producer_validation_receipt(evidence, obligation):
    scope = evidence.get("scope")
    projected_scope = (sorted(set(scope + [obligation["target"]]))
                       if isinstance(scope, list)
                       else [obligation["target"]])
    return {
        "evidence_ref": evidence.get("receipt_id"),
        "verifier": evidence.get("tool"),
        "method": "%s@%s/%s" % (
            evidence.get("tool"), evidence.get("tool_version"),
            evidence.get("check")),
        "checked_at": evidence.get("checked_at"),
        "artifact_fingerprint": evidence.get("artifact_fingerprint"),
        "dependency_fingerprint": evidence.get("dependency_fingerprint"),
        "contract_fingerprint": evidence.get("contract_fingerprint"),
        "scope": projected_scope,
    }


def _producer_attempt_errors(root, catalog, plan, plan_sha256, obligation,
                             record, *, require_current, result=None,
                             item=None):
    receipt = _producer_validation_receipt(record, obligation)
    errors = _producer_evidence_errors(
        root, catalog, plan, plan_sha256, obligation, receipt,
        require_pass=False, require_current=require_current,
        result=result, item=item)
    return sorted(set(errors))


def _substantive_precursor_resolution(
        result, plan, plan_sha256, catalog, obligation, records, *,
        require_current=True, selected_ref=None):
    root = result["root"]
    invalidation = result.get("evidence_invalidation_view") or {}
    affected = invalidation.get("affected") or {}
    if affected:
        history = historical_receipt_catalog(result)
        withdrawn = []
        for receipt_id in sorted(affected):
            entry = history.resolve(receipt_id)
            record = entry[1] if isinstance(entry, tuple) else entry
            if not (isinstance(record, dict) and
                    record.get("record_kind") == "substantive-review-evidence" and
                    record.get("plan_id") == plan["plan_id"] and
                    record.get("obligation_id") == obligation["obligation_id"]):
                continue
            stable_errors = _producer_attempt_errors(
                root, history, plan, plan_sha256, obligation, record,
                require_current=False, result=result,
                item=(result.get("items_by_id") or {}).get(plan["batch_id"]))
            if stable_errors:
                return "invalid", None, [_attempt_summary(record, "invalid")], (
                    "withdrawn L history cannot be proved: %s" % "; ".join(stable_errors))
            withdrawn.append(record)
        if withdrawn:
            return "escalated", None, [
                _attempt_summary(row, "invalidated", "correction event: %s" %
                                 ", ".join(affected[row["receipt_id"]]))
                for row in withdrawn], (
                "L review was withdrawn; preserve its rounds and escalate under K12/12; "
                "invalidation does not authorize a new first round")
    attempts = []
    valid = []
    invalid = []
    for record in records:
        artifact_state = (_artifact_state(
            root, obligation, record,
            evaluation=(result.get("_profile_authorized_view") or {}).get("_evaluation"),
            facts=result.get("_audit_evidence_facts"))
                          if require_current else
                          ("invalidated"
                           if record.get("invalidated_by") is not None
                           else "unknown"))
        if artifact_state == "invalid":
            errors = ["current target cannot be fingerprinted"]
        elif artifact_state == "invalidated":
            errors = []
        else:
            errors = _producer_attempt_errors(
                root, catalog, plan, plan_sha256, obligation, record,
                require_current=False, result=result,
                item=(result.get("items_by_id") or {}).get(plan["batch_id"]))
        if errors:
            reason = "; ".join(errors)
            attempts.append(_attempt_summary(record, "invalid", reason))
            invalid.append(record)
        elif artifact_state == "invalidated":
            attempts.append(_attempt_summary(record, "invalidated"))
        else:
            current_errors = (_producer_attempt_errors(
                root, catalog, plan, plan_sha256, obligation, record,
                require_current=True, result=result,
                item=(result.get("items_by_id") or {}).get(plan["batch_id"]))
                if require_current else [])
            state = "stale" if (
                artifact_state == "stale" or current_errors or
                (not require_current and
                 record.get("receipt_id") != selected_ref)) else "current"
            attempts.append(_attempt_summary(record, state))
            valid.append((record, state))
    if invalid:
        return "invalid", None, attempts, (
            _invalid_history_reason(
                "substantive-review attempt history contains invalid "
                "evidence", attempts))

    current = [record for record, state in valid if state == "current"]
    if require_current:
        # A corrected artifact does not retire the finding set or reset the
        # bounded review. Resolve that history before preferring a current
        # record. This is shared by direct producers and all consumers.
        confirmations = [record for record, _state in valid
                         if record.get("round") == 2]
        finding_sets = [record for record, _state in valid
                        if record.get("round") == 1 and
                        record.get("verdict") == "changes-required"]
        if len(confirmations) > 1 or len(finding_sets) > 1:
            return "ambiguous", None, attempts, (
                "multiple confirmation attempts or round-1 finding sets "
                "claim the same bounded review")
        anchor = (confirmations[0].get("round_1_receipt_id")
                  if confirmations else finding_sets[0]["receipt_id"]
                  if finding_sets else None)
        if anchor is not None and (
                any(row.get("round") == 1 and
                    row.get("receipt_id") != anchor for row in current) or
                any(row.get("receipt_id") != anchor for row in finding_sets)):
            return "invalid", None, attempts, (
                "a new round 1 cannot replace the bounded review finding set")
        if confirmations and confirmations[0] not in current:
            return "escalated", confirmations[0], attempts, (
                "the bounded confirmation after-image changed after round 2")
    if len(current) > 1:
        # One round-2 record and its cited round-1 record are a single legal
        # pair, not two competing terminal attempts.
        round_twos = [row for row in current if row.get("round") == 2]
        if len(round_twos) == 1 and len(current) == 2 and \
                round_twos[0].get("round_1_receipt_id") in {
                    row.get("receipt_id") for row in current}:
            current = round_twos
        else:
            return "ambiguous", None, attempts, (
                "multiple current substantive-review attempts")
    if current:
        record = current[0]
        if record.get("round") == 2:
            if record.get("verdict") == "passed":
                return "ready-for-completion", record, attempts, None
            if record.get("verdict") == "escalated":
                return "escalated", record, attempts, (
                    "round 2 retains unresolved blocking findings")
            return "invalid", None, attempts, (
                "round 2 has no legal terminal verdict")
        if record.get("verdict") == "passed":
            return "ready-for-completion", record, attempts, None
        if record.get("verdict") == "changes-required":
            return "needs-correction", record, attempts, (
                "round 1 has open blocking findings")
        return "invalid", None, attempts, (
            "round 1 has no legal lifecycle verdict")

    stale_round_twos = [record for record, state in valid
                        if state == "stale" and record.get("round") == 2]
    if stale_round_twos:
        return "escalated", stale_round_twos[-1], attempts, (
            "the bounded confirmation after-image changed after round 2")
    stale_changes = [record for record, state in valid
                     if state == "stale" and record.get("round") == 1 and
                     record.get("verdict") == "changes-required"]
    if len(stale_changes) == 1:
        return "needs-confirmation", stale_changes[0], attempts, (
            "round 1 findings await confirmation against the corrected "
            "after-image")
    if len(stale_changes) > 1:
        return "ambiguous", None, attempts, (
            "multiple round-1 finding sets claim the same obligation")
    return "missing", None, attempts, "no current producer evidence"


def _audit_precursor_resolution(
        result, plan, plan_sha256, catalog, obligation, records, *,
        require_current=True, selected_ref=None):
    try:
        chain = (result.get("_audit_evidence_facts") or _EvidenceFacts(result)).chain(obligation)
    except audit_producer_chain.AuditProducerChainError as exc:
        return "invalid", None, [], str(exc)
    if chain["execution_route"] == "substantive-review":
        return _substantive_precursor_resolution(
            result, plan, plan_sha256, catalog, obligation, records,
            require_current=require_current, selected_ref=selected_ref)
    root = result["root"]
    attempts = []
    current = []
    invalid = []
    for record in records:
        artifact_state = (_artifact_state(
            root, obligation, record,
            evaluation=(result.get("_profile_authorized_view") or {}).get("_evaluation"),
            facts=result.get("_audit_evidence_facts"))
                          if require_current else
                          ("invalidated"
                           if record.get("invalidated_by") is not None
                           else "unknown"))
        if artifact_state == "invalid":
            errors = ["current target cannot be fingerprinted"]
        elif artifact_state == "invalidated":
            errors = []
        else:
            errors = _producer_attempt_errors(
                root, catalog, plan, plan_sha256, obligation, record,
                require_current=False, result=result,
                item=(result.get("items_by_id") or {}).get(plan["batch_id"]))
        if errors:
            reason = "; ".join(errors)
            attempts.append(_attempt_summary(record, "invalid", reason))
            invalid.append(record)
        elif artifact_state == "invalidated":
            attempts.append(_attempt_summary(record, "invalidated"))
        else:
            current_errors = (_producer_attempt_errors(
                root, catalog, plan, plan_sha256, obligation, record,
                require_current=True, result=result,
                item=(result.get("items_by_id") or {}).get(plan["batch_id"]))
                if require_current else [])
            if (artifact_state == "stale" or current_errors or
                    (not require_current and
                     record.get("receipt_id") != selected_ref)):
                attempts.append(_attempt_summary(
                    record, "stale", "; ".join(current_errors) or
                    ("artifact_fingerprint changed" if artifact_state == "stale" else None)))
            else:
                attempts.append(_attempt_summary(record, "current"))
                current.append(record)
    if invalid:
        return "invalid", None, attempts, (
            _invalid_history_reason(
                "producer attempt history contains invalid evidence",
                attempts))
    if len(current) > 1:
        return "ambiguous", None, attempts, (
            "multiple current producer attempts")
    if not current:
        reasons = sorted({row["reason"] for row in attempts if row.get("reason")})
        return "missing", None, attempts, (
            "no current producer evidence" + (": " + "; ".join(reasons) if reasons else ""))
    record = current[0]
    if record.get("result") == "pass":
        return "ready-for-completion", record, attempts, None
    if record.get("result") == "fail":
        return "needs-correction", record, attempts, (
            "current deterministic producer attempt did not pass")
    return "invalid", None, attempts, "producer result is not pass/fail"


def _audit_precursor_records(records, obligation, root, *, evaluation=None,
                             facts=None):
    """Return only the producer attempts owned by one AuditReceipt row."""
    chain = (facts.chain(obligation) if facts else
             audit_producer_chain.precursor_chain_for_obligation(
                 obligation, root=root, evaluation=evaluation))
    return [
        row for row in records
        if row.get("record_kind") != "audit-receipt" and
        audit_producer_chain.precursor_record_matches(row, chain) and
        row.get("target") == obligation.get("target")
    ]


def _terminal_with_precursor_resolution(
        result, plan, plan_sha256, catalog, obligation, records,
        terminal_resolution, *, require_current):
    """Reconcile a full AuditReceipt with its producer-attempt lifecycle.

    The full receipt remains the selected terminal evidence. Its producer
    attempts still belong to the same obligation history, so an invalid or
    ambiguous precursor chain must make the terminal closure unresolved.
    """
    terminal = terminal_resolution.get("record")
    terminal_ref = (terminal.get("evidence_ref")
                    if isinstance(terminal, dict) else None)
    try:
        precursors = _audit_precursor_records(
            records, obligation, result["root"],
            evaluation=(result.get("_profile_authorized_view") or {}).get("_evaluation"),
            facts=result.get("_audit_evidence_facts"))
    except audit_producer_chain.AuditProducerChainError as exc:
        resolution = dict(terminal_resolution)
        resolution.update({
            "status": "invalid",
            "reason": "AuditReceipt producer chain is invalid: %s" % exc,
        })
        return resolution
    precursor_status, precursor, precursor_attempts, precursor_reason = \
        _audit_precursor_resolution(
            result, plan, plan_sha256, catalog, obligation, precursors,
            require_current=require_current, selected_ref=terminal_ref)
    resolution = dict(terminal_resolution)
    resolution["attempts"] = (
        list(terminal_resolution.get("attempts") or ()) +
        list(precursor_attempts))
    if not isinstance(terminal, dict):
        return resolution

    precursor_ref = (precursor.get("receipt_id")
                     if isinstance(precursor, dict) else None)
    terminal_status = terminal_resolution.get("status")
    expected_precursor_statuses = (
        {"ready-for-completion"} if terminal_status == "satisfied" else
        {"needs-correction", "escalated"}
        if terminal_status in {"needs-correction", "escalated"} else set())
    if precursor_status in {"invalid", "ambiguous"}:
        resolution.update({
            "status": precursor_status,
            "reason": "AuditReceipt precursor chain is %s: %s" % (
                precursor_status, precursor_reason or "not provable"),
        })
    elif expected_precursor_statuses and (
            precursor_status not in expected_precursor_statuses or
            precursor_ref != terminal_ref):
        resolution.update({
            "status": "invalid",
            "reason": (
                "AuditReceipt selected producer %r does not match the "
                "resolved %s precursor %r" % (
                    terminal_ref, precursor_status, precursor_ref)),
        })
    return resolution


def _required_obligation_resolution_unchecked(
        result, item, plan, plan_sha256, catalog, obligation, *,
        require_current):
    """Resolve history, current attempt, and terminal evidence separately."""
    if obligation["status"] == "reused":
        return {
            "status": "invalid", "record": None, "reused": True,
            "reason": "the installed AuditPlan producer does not produce "
                      "reused obligations; reserved reuse rows cannot enter "
                      "the execution closure",
            "attempts": [],
        }

    records = result["_audit_evidence_facts"].records(
        catalog, plan["plan_id"], obligation["obligation_id"])
    final_records = [row for row in records if row.get("record_kind") ==
                     obligation["evidence_kind"]]
    attempts = []
    accepted = []
    rejected = []
    invalid = []
    for record in final_records:
        explicitly_invalidated = record.get("receipt_id") in set(
            result.get("invalidated_evidence_receipt_ids") or ())
        artifact_state = ("invalidated" if explicitly_invalidated else _artifact_state(
            result["root"], obligation, record,
            evaluation=(result.get("_profile_authorized_view") or {}).get("_evaluation"),
            facts=result.get("_audit_evidence_facts")) if require_current else
            ("invalidated" if explicitly_invalidated or record.get("invalidated_by") is not None
             else "unknown"))
        if artifact_state == "invalid":
            errors = ["current target cannot be fingerprinted"]
        elif artifact_state == "invalidated":
            errors = []
        else:
            errors = _final_attempt_errors(
                result, item, plan, plan_sha256, catalog, obligation, record,
                require_current=False)
        if errors:
            reason = "; ".join(errors)
            attempts.append(_attempt_summary(record, "invalid", reason))
            invalid.append(record)
        elif artifact_state == "invalidated":
            attempts.append(_attempt_summary(record, "invalidated"))
        else:
            current_errors = (_final_attempt_errors(
                result, item, plan, plan_sha256, catalog, obligation, record,
                require_current=True) if require_current else [])
            if artifact_state == "stale" or current_errors:
                attempts.append(_attempt_summary(record, "stale"))
            elif _is_terminal_pass(obligation, record):
                attempts.append(_attempt_summary(record, "accepted"))
                accepted.append(record)
            else:
                attempts.append(_attempt_summary(record, "rejected"))
                rejected.append(record)
    if invalid:
        resolution = {
            "status": "invalid", "record": None, "reused": False,
            "reason": _invalid_history_reason(
                "evidence attempt history contains invalid records",
                attempts),
            "attempts": attempts,
        }
        if obligation["evidence_kind"] == "audit-receipt":
            return _terminal_with_precursor_resolution(
                result, plan, plan_sha256, catalog, obligation, records,
                resolution, require_current=require_current)
        return resolution
    if len(accepted) + len(rejected) > 1:
        resolution = {
            "status": "ambiguous", "record": None, "reused": False,
            "reason": "multiple current terminal evidence attempts",
            "attempts": attempts,
        }
        if obligation["evidence_kind"] == "audit-receipt":
            return _terminal_with_precursor_resolution(
                result, plan, plan_sha256, catalog, obligation, records,
                resolution, require_current=require_current)
        return resolution
    if accepted:
        resolution = {
            "status": "satisfied", "record": accepted[0],
            "reused": False, "reason": None, "attempts": attempts,
        }
        if obligation["evidence_kind"] == "audit-receipt":
            return _terminal_with_precursor_resolution(
                result, plan, plan_sha256, catalog, obligation, records,
                resolution, require_current=require_current)
        return resolution
    if rejected:
        resolution = {
            "status": _negative_status(
                result["root"], catalog, obligation, rejected[0],
                evaluation=(result.get("_profile_authorized_view") or {}).get("_evaluation"),
                facts=result.get("_audit_evidence_facts")),
            "record": rejected[0], "reused": False,
            "reason": "current terminal evidence did not satisfy the "
                      "acceptance predicate", "attempts": attempts,
        }
        if obligation["evidence_kind"] == "audit-receipt":
            return _terminal_with_precursor_resolution(
                result, plan, plan_sha256, catalog, obligation, records,
                resolution, require_current=require_current)
        return resolution
    if obligation["evidence_kind"] == "audit-receipt":
        # Only the producer declared by the frozen obligation participates in
        # its attempt lifecycle.  Supporting receipts may share plan and
        # obligation bindings, but they are inputs to that producer rather
        # than competing attempts.
        try:
            precursors = _audit_precursor_records(
                records, obligation, result["root"],
                evaluation=(result.get("_profile_authorized_view") or {}).get("_evaluation"),
                facts=result.get("_audit_evidence_facts"))
        except audit_producer_chain.AuditProducerChainError as exc:
            return {
                "status": "invalid", "record": None, "reused": False,
                "reason": "AuditReceipt producer chain is invalid: %s" % exc,
                "attempts": attempts,
            }
        status, record, precursor_attempts, reason = \
            _audit_precursor_resolution(
                result, plan, plan_sha256, catalog, obligation, precursors,
                require_current=require_current)
        return {
            "status": status, "record": record, "reused": False,
            "reason": reason, "attempts": attempts + precursor_attempts,
        }
    return {
        "status": "missing", "record": None, "reused": False,
        "reason": "no current terminal evidence", "attempts": attempts,
    }


def _required_obligation_resolution(
        result, item, plan, plan_sha256, catalog, obligation, *,
        require_current):
    """Resolve one obligation once in the existing read-only stage window.

    M consumption edges and the outer stage may ask about the same source
    obligation. They share this result only for the same inputs and catalog;
    live and frozen queries remain distinct. Candidate catalogs are distinct
    observations. Outside evidence_observation there is no result reuse.
    """
    cache = result.get("_audit_stage_resolutions")
    key = None
    if cache is not None:
        key = ("obligation", _record_sha256(item), _record_sha256(plan),
               plan_sha256, id(catalog), _record_sha256(obligation),
               require_current)
        if key in cache:
            return deepcopy(cache[key])
    result = evidence_evaluation(result)
    resolution = _required_obligation_resolution_unchecked(
        result, item, plan, plan_sha256, catalog, obligation,
        require_current=require_current)
    try:
        resolution = audit_lifecycle_contract.validate_resolution(resolution)
    except audit_lifecycle_contract.AuditLifecycleContractError as exc:
        raise AuditEvidenceError(str(exc)) from exc
    if cache is not None:
        cache[key] = deepcopy(resolution)
    return resolution


def obligation_evidence_resolution(result, item, plan, plan_sha256,
                                   obligation, *, proposed_record=None):
    """Resolve a live obligation for either production or consumption.

    A proposed record is evaluated against the complete catalog without
    publishing it. It cannot hide competing attempts or replace an existing
    identity. Callers must separately re-admit runtime and inputs before a
    durable write; this read-only result is not a write authorization.
    """
    result = evidence_evaluation(result)
    catalog = current_receipt_catalog(result)
    if proposed_record is not None:
        identity = proposed_record.get("receipt_id")
        if not isinstance(identity, str) or not identity:
            raise AuditEvidenceError("proposed evidence has no receipt identity")
        if identity in catalog:
            raise AuditEvidenceError("proposed evidence identity already exists")
        if (proposed_record.get("plan_id") != plan["plan_id"] or
                proposed_record.get("obligation_id") != obligation["obligation_id"]):
            raise AuditEvidenceError("proposed evidence differs from the obligation")
        catalog = {**catalog, identity: proposed_record}
    return _required_obligation_resolution(
        result, item, plan, plan_sha256, catalog, obligation,
        require_current=True)


def require_substantive_review_attempt(result, item, plan, plan_sha256,
                                      obligation, *, round_number,
                                      round_1_receipt_id=None):
    """Return the exact predecessor for the one legal next review action."""
    result = evidence_evaluation(result)
    chain = result["_audit_evidence_facts"].chain(obligation)
    if chain["execution_route"] != "substantive-review":
        raise AuditEvidenceError("obligation is not a substantive review")
    resolution = obligation_evidence_resolution(
        result, item, plan, plan_sha256, obligation)
    if (resolution["status"] == "missing" and round_number == 1 and
            round_1_receipt_id is None):
        return None
    prior = resolution.get("record")
    if (resolution["status"] == "needs-confirmation" and round_number == 2 and
            isinstance(prior, dict) and
            round_1_receipt_id == prior.get("receipt_id")):
        return prior
    raise AuditEvidenceError(
        "substantive-review attempt is not admitted (%s): %s" % (
            resolution["status"], resolution.get("reason") or
            "current evidence exists or the requested round/predecessor differs"))


def require_completion_evidence(result, item, plan, plan_sha256, obligation,
                                evidence_id):
    """Return (unique passing precursor, existing full receipt or None).

    Completion and the final consumer share the same whole-obligation
    acceptance, including predecessor relations and competing precursors.
    Selecting an ID never filters the set used to decide currentness.
    """
    if (obligation.get("status") != "required" or
            obligation.get("evidence_kind") != "audit-receipt" or
            obligation.get("evidence_role") != "emits" or
            obligation.get("dimension") is None):
        raise AuditEvidenceError(
            "only a required dimension-specific AuditReceipt may be completed")
    resolution = obligation_evidence_resolution(
        result, item, plan, plan_sha256, obligation)
    if resolution["status"] not in {"ready-for-completion", "satisfied"}:
        raise AuditEvidenceError("AuditReceipt completion is %s: %s" % (
            resolution["status"], resolution.get("reason") or "not provable"))
    existing = resolution["record"] if resolution["status"] == "satisfied" else None
    evidence = (_current_record(current_receipt_catalog(result),
                                existing.get("evidence_ref"), "producer evidence")
                if existing is not None else resolution["record"])
    if evidence.get("receipt_id") != evidence_id:
        raise AuditEvidenceError("selected precursor differs from the unique current evidence")
    return evidence, existing


def _historical_attempt_summaries(result, plan, obligation, attempts):
    """Add plan-bound history removed from the current-use catalog.

    Current-use filtering is an authorization boundary, not deletion.  A
    reconciliation therefore reads immutable history for accounting while
    continuing to select terminal evidence only from the current catalog.
    """
    rows = {
        row.get("receipt_id"): dict(row)
        for row in attempts
        if isinstance(row, dict) and isinstance(row.get("receipt_id"), str)
    }
    current = current_receipt_catalog(result)
    invalidated_ids = set(
        result.get("invalidated_evidence_receipt_ids") or ())
    facts = result.get("_audit_evidence_facts") or _EvidenceFacts(result)
    historical = facts.memo(("historical-catalog",), lambda: historical_receipt_catalog(result))
    for record in facts.records(historical, plan["plan_id"], obligation["obligation_id"]):
        key = record["receipt_id"]
        if key in rows:
            continue
        if key in invalidated_ids or record.get("invalidated_by") is not None:
            rows[key] = _attempt_summary(
                record, "invalidated",
                record.get("invalidated_by") or
                "removed by the current runtime invalidation set")
        elif key not in current:
            rows[key] = _attempt_summary(
                record, "invalid",
                "historical evidence is absent from the current-use catalog "
                "without an explicit invalidation classification")
    return [rows[key] for key in sorted(rows)]


def _reconciliation_row(result, plan, obligation, resolution):
    attempts = _historical_attempt_summaries(
        result, plan, obligation, resolution.get("attempts") or ())
    selected = resolution.get("record")
    candidate_id = (selected.get("receipt_id")
                    if isinstance(selected, dict) else None)
    selectable_ids = {
        row["receipt_id"] for row in attempts
        if row.get("state") in {"accepted", "current", "rejected"} and
        isinstance(row.get("receipt_id"), str)
    }
    selected_id = candidate_id if candidate_id in selectable_ids else None
    produced = {
        row["receipt_id"] for row in attempts
        if row.get("state") in {"accepted", "current"} and
        isinstance(row.get("receipt_id"), str)
    }
    if selected_id is not None:
        produced.add(selected_id)
    attempt_ids = {
        row["receipt_id"] for row in attempts
        if isinstance(row.get("receipt_id"), str) and row["receipt_id"]
    }
    # ``invalidated_by`` may name either a successor receipt or an invalidation
    # event.  Only a resolvable receipt in this obligation's own attempt chain
    # proves supersession; every other explicit invalidation remains an
    # invalidation.  Staleness is a direct K12/07 invalidation, not an implicit
    # successor relationship manufactured by this projection.
    superseded = sorted({
        row["receipt_id"] for row in attempts
        if row.get("state") == "invalidated" and
        isinstance(row.get("receipt_id"), str) and
        row.get("invalidated_by") in attempt_ids
    })
    invalidated = sorted({
        row["receipt_id"] for row in attempts
        if isinstance(row.get("receipt_id"), str) and (
            row.get("state") == "stale" or
            (row.get("state") == "invalidated" and
             row.get("receipt_id") not in superseded))
    })
    invalid_attempts = [
        row for row in attempts if row.get("state") == "invalid"]
    unsupported_reuse = obligation.get("status") == "reused"
    unresolved = (
        resolution.get("status") != "satisfied" or
        bool(invalid_attempts) or unsupported_reuse)
    reason = resolution.get("reason") if unresolved else None
    if unresolved and reason is None:
        reason = "obligation resolution is %s" % resolution.get("status")
    if invalid_attempts:
        invalid_reason = _invalid_history_reason(
            "evidence history contains invalid records", invalid_attempts)
        reason = "%s; %s" % (reason, invalid_reason) if reason else \
            invalid_reason
    disposition = (
        "reused-reserved" if unsupported_reuse else
        "produced" if selected_id is not None else "unresolved")
    row = {
        "obligation_id": obligation["obligation_id"],
        "due_stage": obligation["due_stage"],
        "selected_evidence_ref": selected_id,
        "selected_disposition": disposition,
        "produced_evidence_refs": sorted(produced),
        "reused_reserved_evidence_ref": (
            obligation.get("reused_receipt_id") if unsupported_reuse else None),
        "superseded_evidence_refs": superseded,
        "invalidated_evidence_refs": invalidated,
        "unresolved": unresolved,
        "unresolved_reason": reason,
    }
    if tuple(row) != _RECONCILIATION_ROW_FIELDS:
        raise AssertionError("audit evidence reconciliation fields drifted")
    return row


def _reconciliation_projection(rows):
    ordered = sorted((dict(row) for row in rows),
                     key=lambda row: row.get("obligation_id") or "")
    identifiers = [row.get("obligation_id") for row in ordered]
    if (not all(isinstance(value, str) and value for value in identifiers) or
            len(identifiers) != len(set(identifiers))):
        raise AuditEvidenceError(
            "audit evidence reconciliation obligation IDs must be unique")
    for index, row in enumerate(ordered):
        if tuple(row) != _RECONCILIATION_ROW_FIELDS:
            raise AuditEvidenceError(
                "audit evidence reconciliation row %d fields are not closed" %
                index)
        for field in (
                "produced_evidence_refs", "superseded_evidence_refs",
                "invalidated_evidence_refs"):
            values = row.get(field)
            if (not isinstance(values, list) or values != sorted(set(values)) or
                    not all(isinstance(value, str) and value for value in values)):
                raise AuditEvidenceError(
                    "audit evidence reconciliation %s must be sorted and "
                    "unique" % field)
        selected = row.get("selected_evidence_ref")
        if selected is not None and (not isinstance(selected, str) or
                                     not selected):
            raise AuditEvidenceError(
                "audit evidence reconciliation selected evidence must be a "
                "receipt ID or null")
        reserved = row.get("reused_reserved_evidence_ref")
        if reserved is not None and (not isinstance(reserved, str) or
                                     not reserved):
            raise AuditEvidenceError(
                "audit evidence reconciliation reserved reuse must be a "
                "receipt ID or null")
        disposition = row.get("selected_disposition")
        expected_disposition = (
            "reused-reserved" if reserved is not None else
            "produced" if selected is not None else "unresolved")
        if disposition != expected_disposition:
            raise AuditEvidenceError(
                "audit evidence reconciliation selected disposition does "
                "not match its selected evidence")
        if selected is not None and selected not in \
                row["produced_evidence_refs"]:
            raise AuditEvidenceError(
                "audit evidence reconciliation selected evidence is absent "
                "from produced evidence")
        categories = (
            set(row["produced_evidence_refs"]),
            set(row["superseded_evidence_refs"]),
            set(row["invalidated_evidence_refs"]),
        )
        if (categories[0].intersection(categories[1]) or
                categories[0].intersection(categories[2]) or
                categories[1].intersection(categories[2])):
            raise AuditEvidenceError(
                "audit evidence reconciliation receipt categories overlap")
        if row.get("due_stage") not in {"pre-merge", "post-delta-close"}:
            raise AuditEvidenceError(
                "audit evidence reconciliation due stage is not registered")
        if not isinstance(row.get("unresolved"), bool):
            raise AuditEvidenceError(
                "audit evidence reconciliation unresolved must be boolean")
        if row["unresolved"] != (row.get("unresolved_reason") is not None):
            raise AuditEvidenceError(
                "audit evidence reconciliation unresolved reason is not "
                "paired with its status")
    digest = kblib.sha256_bytes(kblib.canonical_json_bytes(ordered))
    return dict(zip(
        audit_reconciliation_contract.projection_fields(),
        (ordered, digest, sum(1 for row in ordered if row["unresolved"]))))


def validate_plan_reconciliation(projection):
    """Return one canonical reconciliation after proving fields and hash."""
    if not isinstance(projection, dict):
        raise AuditEvidenceError(
            "audit evidence reconciliation projection must be a mapping")
    if set(projection) != set(
            audit_reconciliation_contract.projection_fields()):
        raise AuditEvidenceError(
            "audit evidence reconciliation projection fields are not closed")
    expected = _reconciliation_projection(
        projection.get("audit_evidence_reconciliation") or ())
    for field in audit_reconciliation_contract.projection_fields():
        if projection.get(field) != expected[field]:
            raise AuditEvidenceError(
                "audit evidence reconciliation %s does not match its rows" %
                field)
    return expected


def reconciliation_from_bindings(bindings, producer_evidence_refs=None):
    """Project already-validated fresh evidence bindings deterministically.

    K12/09 post-Delta members are always freshly produced.  Their producer
    supplies the exact selected binding and, for AuditReceipt rows, the cited
    producer-level evidence.  This helper records those facts without
    reinterpreting the member contract or manufacturing reuse.
    """
    producers = producer_evidence_refs or {}
    if not isinstance(bindings, (list, tuple)) or not isinstance(
            producers, dict):
        raise AuditEvidenceError(
            "evidence bindings and producer references must be structured")
    rows = []
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            raise AuditEvidenceError(
                "evidence binding %d must be a mapping" % index)
        obligation_id = binding.get("obligation_id")
        selected = binding.get("evidence_ref")
        if not isinstance(obligation_id, str) or not obligation_id or \
                not isinstance(selected, str) or not selected:
            raise AuditEvidenceError(
                "evidence binding %d has no obligation/evidence identity" %
                index)
        extra = producers.get(obligation_id)
        if extra is None:
            extra_values = []
        elif isinstance(extra, str):
            extra_values = [extra]
        elif isinstance(extra, (list, tuple)):
            extra_values = list(extra)
        else:
            raise AuditEvidenceError(
                "producer evidence for %s must be a string or list" %
                obligation_id)
        produced = sorted(set([selected] + extra_values))
        if not all(isinstance(value, str) and value for value in produced):
            raise AuditEvidenceError(
                "producer evidence references must be non-empty strings")
        row = {
            "obligation_id": obligation_id,
            "due_stage": binding.get("due_stage") or "post-delta-close",
            "selected_evidence_ref": selected,
            "selected_disposition": "produced",
            "produced_evidence_refs": produced,
            "reused_reserved_evidence_ref": None,
            "superseded_evidence_refs": [],
            "invalidated_evidence_refs": [],
            "unresolved": False,
            "unresolved_reason": None,
        }
        rows.append(row)
    return _reconciliation_projection(rows)


def combine_plan_reconciliations(*projections):
    """Combine disjoint stage projections for one immutable AuditPlan."""
    rows = []
    for projection in projections:
        validated = validate_plan_reconciliation(projection)
        rows.extend(validated["audit_evidence_reconciliation"])
    return _reconciliation_projection(rows)


def terminal_plan_reconciliation(result):
    """Derive Terminal Proof receipt lists from closed batch evidence.

    The Proof is a claim, not the owner of this count.  Closed batch receipts
    carry the immutable plan reconciliation accepted by their transition; the
    current runtime invalidation set is then applied at the Terminal boundary.
    """
    if not isinstance(result, dict):
        raise AuditEvidenceError("Terminal reconciliation needs runtime state")
    current = current_receipt_catalog(result)
    history = historical_receipt_catalog(result)
    invalidated_now = set(
        result.get("invalidated_evidence_receipt_ids") or ())
    superseded = set()
    invalidated = set()
    unresolved = set()
    items = result.get("items_by_id")
    if not isinstance(items, dict):
        raise AuditEvidenceError(
            "Terminal reconciliation has no canonical Queue item view")
    for item_id, item in sorted(items.items()):
        if not isinstance(item, dict) or item.get("state") != "closed":
            continue
        close_id = item.get("close_gate_receipt")
        # A withdrawn close is still an executed historical fact. Read its
        # immutable reconciliation only to report unresolved dependencies;
        # it cannot supply current completion authority. Unclassified absence
        # never authorizes a fallback to history.
        selected_catalog = history if close_id in invalidated_now else current
        close = catalog_record(selected_catalog.resolve(close_id))
        if not isinstance(close, dict) or close.get("receipt_id") != close_id:
            raise AuditEvidenceError(
                "closed batch %s has no current close receipt" % item_id)
        raw_projection = {
            field: close.get(field)
            for field in audit_reconciliation_contract.projection_fields()
        }
        projection = validate_plan_reconciliation(raw_projection)
        plan_id = close.get("audit_plan_id")
        if not isinstance(plan_id, str) or not plan_id:
            raise AuditEvidenceError(
                "closed batch %s reconciliation has no AuditPlan identity" %
                item_id)
        if close_id in invalidated_now or close.get("invalidated_by") is not None:
            invalidated.add(close_id)
            unresolved.add((plan_id, "<close-receipt>"))
        for row in projection["audit_evidence_reconciliation"]:
            obligation_key = (plan_id, row["obligation_id"])
            # The current AuditPlan producer has no legal reuse producer.
            # ``reused-reserved`` rows are deliberately unresolved and cannot
            # reach a closed receipt, so current Terminal reconciliation has
            # no path that can populate reused receipts.
            superseded.update(row["superseded_evidence_refs"])
            invalidated.update(row["invalidated_evidence_refs"])
            if row["unresolved"]:
                unresolved.add(obligation_key)
            active_refs = set(row["produced_evidence_refs"])
            if row["selected_evidence_ref"] is not None:
                active_refs.add(row["selected_evidence_ref"])
            newly_invalidated = active_refs.intersection(invalidated_now)
            if newly_invalidated:
                invalidated.update(newly_invalidated)
                unresolved.add(obligation_key)
    return {
        "reused_receipts": [],
        "superseded_receipts": sorted(superseded),
        "invalidated_receipts": sorted(invalidated),
        "unresolved_invalidations": len(unresolved),
    }


_TERMINAL_DIMENSION_EVIDENCE_FIELDS = (
    "batch_id", "plan_id", "obligation_id", "dimension",
    "evidence_kind", "evidence_ref",
)


def _dimension_evidence_is_applicable(obligation, record):
    """Return whether one selected dimension row actually ran.

    M-tier conditional atoms remain frozen in every AuditPlan.  Their
    producer record is also the owner of the applicable/not-applicable
    disposition, so a reasoned not-applicable atom must not make the whole
    dimension look as though it ran.  Other admitted dimension evidence kinds
    are projected only when their obligation exists and has already passed
    its own final-evidence validator.
    """
    if obligation.get("dimension") is None:
        return False
    if record.get("record_kind") == "batch-page-review-record" and \
            record.get("review_variant") == "m-atomic-item":
        disposition = record.get("applicability_disposition")
        if disposition == "not-applicable":
            return False
        if disposition != "applicable":
            raise AuditEvidenceError(
                "M-tier dimension evidence has no valid applicability "
                "disposition")
    return True


def _post_delta_evidence_closure(
        result, item, close_receipt, *, required_state):
    """Resolve and validate the one K12/09 after-image closure.

    ``check_batch_close`` produces the eight registry members as one atomic
    post-Delta set.  Both the merge-ready close transition and the later
    Terminal projection consume that same set through the K12/09 registry and
    :mod:`batch_close_audit`; neither consumer may reinterpret a member as a
    generic AuditReceipt attempt or discover a nearby record by scanning the
    Receipt namespace.
    """
    if not isinstance(close_receipt, dict):
        raise AuditEvidenceError(
            "post-Delta closure requires one batch-close aggregate")
    catalog = current_receipt_catalog(result)
    stage_plan = resolve_stage_plan(
        result, item, "post-delta-close", required_state=required_state)
    profile_view = result.get("_profile_authorized_view") or {}
    selected_profile = profile_view.get("_contract")
    projection = batch_close_audit.resolve_post_delta_projection(
        stage_plan,
        batch_close_contract.closed_list_member_rows(result["root"]),
        selected_profile)

    bindings = close_receipt.get("post_delta_evidence_bindings")
    if not isinstance(bindings, list):
        raise AuditEvidenceError(
            "batch-close aggregate has no post-Delta evidence bindings")
    if len(bindings) != len(projection):
        raise AuditEvidenceError(
            "batch-close post-Delta binding count differs from the K12/09 "
            "registry")

    evidence_by_id = {}
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            raise AuditEvidenceError(
                "post-Delta evidence binding %d must be a mapping" %
                (index + 1))
        evidence_ref = binding.get("evidence_ref")
        if evidence_ref in evidence_by_id:
            raise AuditEvidenceError(
                "post-Delta evidence bindings repeat receipt %r" %
                evidence_ref)
        evidence_by_id[evidence_ref] = _current_record(
            catalog, evidence_ref, "post-Delta evidence")

    producer_refs = close_receipt.get("closed_list_producer_evidence")
    if not isinstance(producer_refs, dict):
        raise AuditEvidenceError(
            "batch-close aggregate has no producer-evidence mapping")
    expected_members = {
        pair["member"]["member_id"] for pair in projection
    }
    if set(producer_refs) != expected_members:
        raise AuditEvidenceError(
            "batch-close producer-evidence members do not equal the "
            "post-Delta registry")

    producer_records = {}
    final_by_obligation = {}
    producer_by_obligation = {}
    for pair, binding in zip(projection, bindings):
        member = pair["member"]
        obligation = pair["obligation"]
        member_id = member["member_id"]
        final_ref = binding.get("evidence_ref")
        final_record = evidence_by_id.get(final_ref)
        if not isinstance(final_record, dict):
            raise AuditEvidenceError(
                "%s post-Delta final evidence is unavailable" % member_id)
        precursor_ref = producer_refs.get(member_id)
        if member["evidence_kind"] == "gate-receipt":
            if precursor_ref != final_ref:
                raise AuditEvidenceError(
                    "%s producer evidence must be the original Gate record" %
                    member_id)
            precursor = final_record
        else:
            if final_record.get("evidence_ref") != precursor_ref:
                raise AuditEvidenceError(
                    "%s AuditReceipt does not cite its declared producer "
                    "evidence" % member_id)
            precursor = _current_record(
                catalog, precursor_ref,
                "%s post-Delta producer evidence" % member_id)
        producer_records[member_id] = precursor
        obligation_id = obligation["obligation_id"]
        final_by_obligation[obligation_id] = final_record
        producer_by_obligation[obligation_id] = precursor

    closure = batch_close_audit.validate_post_delta_evidence_set(
        stage_plan, projection, bindings, evidence_by_id,
        close_receipt.get("merged_snapshot_sha256"),
        producer_evidence_by_member=producer_records,
        producer_tool=close_receipt.get("tool"),
        producer_tool_version=close_receipt.get("tool_version"))
    reconciliation = reconciliation_from_bindings(
        closure["bindings"], {
            obligation_id: record["receipt_id"]
            for obligation_id, record in producer_by_obligation.items()
        })
    return {
        "stage_plan": stage_plan,
        "projection": projection,
        "bindings": closure["bindings"],
        "evidence_set_sha256": closure["evidence_set_sha256"],
        "final_by_obligation": final_by_obligation,
        "producer_by_obligation": producer_by_obligation,
        "reconciliation": reconciliation,
    }


class _FrozenEvidenceView(dict):
    """Enumerate frozen candidates; read exact dependencies without selecting them.

    Constructed only by the stage owner after validating its bound projection.
    Neither the source catalog nor this observation-local view is a new owner.
    """

    def __init__(self, result, catalog, rows):
        super().__init__()
        self.selected_ids = frozenset(row["selected_evidence_ref"] for row in rows)
        self._bodies = {}
        invalidated = set(result.get("invalidated_evidence_receipt_ids") or ())

        def body(receipt_id):
            if receipt_id not in self._bodies:
                record = _current_record(catalog, receipt_id, "frozen evidence dependency")
                if receipt_id in invalidated or record.get("invalidated_by") is not None:
                    raise AuditEvidenceError("frozen evidence dependency %s is invalidated" % receipt_id)
                self._bodies[receipt_id] = record
            return self._bodies[receipt_id]

        for row in rows:
            if (row["unresolved"] or row["selected_disposition"] != "produced" or
                    row["selected_evidence_ref"] not in row["produced_evidence_refs"]):
                raise AuditEvidenceError("frozen obligation %s has no produced selection" % row["obligation_id"])
            for receipt_id in row["produced_evidence_refs"]:
                self[receipt_id] = body(receipt_id)

        facts = result.get("_audit_evidence_facts") or _EvidenceFacts(result)
        registry = facts.memo(("receipt-type-registry",), lambda:
            receipt_type_contract.load_receipt_type_registry(result["root"]))
        def source_kind(record):
            return receipt_type_contract.reference_source_kind(record, registry=registry)

        for record in self.values():
            kind = source_kind(record)
            if kind is not None:
                receipt_reference_contract.walk_body_dependencies(
                    record, kind, body, source_kind, acceptance_only=True)

    def get(self, key, default=None):
        return self._bodies.get(key, default)


def _frozen_stage_resolution(result, item, plan, plan_sha256, projection, due_stage):
    """Verify the selected stage without replacing its immutable history."""
    projection = validate_plan_reconciliation(projection)
    rows = projection["audit_evidence_reconciliation"]
    obligations = {row["obligation_id"]: row for row in plan["obligations"]
                   if row["due_stage"] == due_stage}
    if {row["obligation_id"] for row in rows} != set(obligations) or any(
            row["due_stage"] != due_stage for row in rows):
        raise AuditEvidenceError("frozen reconciliation differs from the complete stage obligation set")
    view = _FrozenEvidenceView(result, current_receipt_catalog(result), rows)
    resolved = []
    for row in rows:
        obligation = obligations[row["obligation_id"]]
        resolution = _required_obligation_resolution(
            result, item, plan, plan_sha256, view, obligation, require_current=False)
        record = resolution.get("record")
        if (resolution["status"] != "satisfied" or not isinstance(record, dict) or
                record.get("receipt_id") != row["selected_evidence_ref"]):
            raise AuditEvidenceError("frozen obligation %s is %s: %s" % (
                row["obligation_id"], resolution["status"], resolution.get("reason")))
        # Recompute only produced identities. Preserve the original stale and
        # superseded history; a narrowed read view cannot reconstruct it.
        produced = {attempt["receipt_id"] for attempt in resolution["attempts"]
                    if attempt["state"] in {"accepted", "current"}}
        if produced != set(row["produced_evidence_refs"]):
            raise AuditEvidenceError("frozen obligation %s has unbound produced evidence" % row["obligation_id"])
        resolved.append((obligation, resolution))
    return resolved, projection


def _bound_review_projection(result, item, plan, relative, plan_sha256):
    """Read the sole Batch Review already frozen by the admitted Queue item."""
    references = item.get("batch_receipts")
    if not isinstance(references, list) or len(references) != 1:
        raise AuditEvidenceError("batch must bind exactly one Batch Review wrapper")
    wrapper = _current_record(current_receipt_catalog(result), references[0], "Batch Review wrapper")
    _validate_review_identity(result, item, plan, relative, plan_sha256, wrapper)
    return wrapper


def _validate_review_identity(result, item, plan, relative, plan_sha256, wrapper):
    """Stable wrapper identity, shared by live attempts and frozen consumption."""
    errors = batch_review_receipt_contract.current_receipt_errors(wrapper)
    expected = {
        "audit_plan_id": plan["plan_id"], "audit_plan_path": relative,
        "audit_plan_sha256": plan_sha256, "batch_id": item["id"],
        "activation_receipt_id": item.get("activation_receipt"),
        **{field: plan[field] for field in (
            "task_id", "upstream_revision_id", "selected_profile_manifest")},
    }
    errors.extend(field for field, value in expected.items() if wrapper.get(field) != value)
    if wrapper["receipt_id"] in set(result.get("invalidated_evidence_receipt_ids") or ()):
        errors.append("invalidated wrapper")
    if errors:
        raise AuditEvidenceError("frozen Batch Review binding is invalid: %s" % ", ".join(errors))


def current_batch_review_receipt(result, item, delta):
    """Select the unique live wrapper, retaining legal stale attempts as history.

    This is an observation, not attestation or write authorization. The
    producer still confirms the exact statement and re-admits under its lock.
    """
    from Tools.execution.task_runtime.queue_runtime import review as queue_review
    result, relative, plan, plan_sha256, resolved, _frozen = _resolve_stage_evidence(
        result, item, "pre-merge", "open")
    live = _stage_projection(result, relative, plan, plan_sha256, resolved)
    catalog = current_receipt_catalog(result)
    attempts = []
    invalidated = set(result.get("invalidated_evidence_receipt_ids") or ())
    for identity, entry in catalog.items():
        record = catalog_record(entry)
        if not isinstance(record, dict) or record.get("receipt_type_id") != \
                batch_review_receipt_contract.RECEIPT_TYPE_ID:
            continue
        if record.get("batch_id") != item["id"] and record.get("target") != item["id"]:
            continue
        if identity != record.get("receipt_id"):
            raise AuditEvidenceError("Batch Review catalog identity differs from its body")
        if identity in invalidated or record.get("invalidated_by") is not None:
            continue
        attempts.append(record)

    def stable(record):
        _validate_review_identity(result, item, plan, relative, plan_sha256, record)
        _review_stage_evidence(result, item, plan, relative, plan_sha256, record)
        errors = queue_review.batch_review_receipt_errors(
            catalog, record["receipt_id"], item_id=item["id"], task_id=plan["task_id"],
            activation_receipt_id=item.get("activation_receipt"),
            delta_page_receipt_ids=record["delta_page_receipt_ids"])
        if errors:
            raise AuditEvidenceError("; ".join(errors))

    def current(record):
        errors = _wrapper_projection_errors(record, live)
        errors.extend(queue_review.batch_review_judgment_errors(result, item, record))
        expected = {"delta_path": delta.get("path"), "delta_sha256": delta.get("sha256"),
                    "delta_page_receipt_ids": sorted(set(delta.get("page_receipt_ids") or []))}
        errors.extend("Batch Review %s differs from current Delta" % field
                      for field, value in expected.items() if record.get(field) != value)
        if errors:
            raise AuditEvidenceError("; ".join(errors))

    try:
        return evidence_attempt_runtime.unique_current_attempt(
            attempts, validate_stable=stable, validate_current=current,
            label="Batch Review wrapper")
    except evidence_attempt_runtime.EvidenceAttemptError as exc:
        raise AuditEvidenceError(str(exc)) from exc


def _review_stage_evidence(result, item, plan, relative, plan_sha256, wrapper):
    """Verify one wrapper's audit and Profile bindings through their owners."""
    rows, history = _frozen_stage_resolution(
        result, item, plan, plan_sha256,
        {field: wrapper[field] for field in audit_reconciliation_contract.projection_fields()},
        "pre-merge")
    bound = _stage_projection(result, relative, plan, plan_sha256, rows, history)
    errors = _wrapper_projection_errors(wrapper, bound)
    judgments = [resolution["record"] for obligation, resolution in rows
                 if obligation["evidence_kind"] == profile_batch_judgment_contract.RECORD_KIND]
    expected = batch_review_receipt_contract.judgment_binding(judgments)
    activation = _current_record(current_receipt_catalog(result), item.get("activation_receipt"),
                                 "Batch Review activation")
    expected["review_requirement_set_sha256"] = activation.get("review_requirement_set_sha256")
    errors.extend("Batch Review %s differs from its frozen Profile binding" % field
                  for field, value in expected.items() if wrapper.get(field) != value)
    if errors:
        raise AuditEvidenceError("; ".join(errors))
    return rows, bound


def _closed_batch_dimension_evidence(
        result, item, catalog, terminal_dimensions):
    """Resolve one closed batch's exact plan-bound dimension evidence.

    The close reconciliation is the immutable selection made by the guarded
    close.  The AuditPlan supplies dimension and evidence-kind identity, and
    the existing final-evidence handlers revalidate every selected record
    through its own owner contract.  Neither the close receipt nor Terminal
    Proof may infer a dimension from an arbitrary current record.
    """
    batch_id = item.get("id")
    close_id = item.get("close_gate_receipt")
    close = _current_record(catalog, close_id, "closed batch receipt")
    invalidated = set(result.get("invalidated_evidence_receipt_ids") or ())
    if close_id in invalidated or close.get("invalidated_by") is not None:
        raise AuditEvidenceError(
            "closed batch %s close receipt is invalidated" % batch_id)
    if close.get("result") != "pass":
        raise AuditEvidenceError(
            "closed batch %s close receipt did not pass" % batch_id)

    projection = validate_plan_reconciliation({
        field: close.get(field)
        for field in audit_reconciliation_contract.projection_fields()
    })
    reconciliation = {
        row["obligation_id"]: row
        for row in projection["audit_evidence_reconciliation"]
    }
    postdelta = _post_delta_evidence_closure(
        result, item, close, required_state="closed")
    relative = postdelta["stage_plan"]["audit_plan_path"]
    plan = postdelta["stage_plan"]["plan"]
    plan_sha256 = postdelta["stage_plan"]["audit_plan_sha256"]
    expected_close = {
        "audit_plan_id": plan["plan_id"],
        "audit_plan_path": relative,
        "audit_plan_sha256": plan_sha256,
    }
    drift = sorted(
        field for field, value in expected_close.items()
        if close.get(field) != value)
    if drift:
        raise AuditEvidenceError(
            "closed batch %s close receipt differs from its AuditPlan in: %s"
            % (batch_id, ", ".join(drift)))

    obligations = {
        row["obligation_id"]: row for row in plan["obligations"]
    }
    if set(obligations) != set(reconciliation):
        raise AuditEvidenceError(
            "closed batch %s reconciliation does not cover its complete "
            "AuditPlan" % batch_id)

    # The same bound stage consumer serves close, closed and Terminal. Do
    # not create a produced-only catalog here or rediscover earlier choices.
    premerge = batch_review_evidence(result, item, required_state="closed")
    if any(premerge.get(field) != value for field, value in expected_close.items()):
        raise AuditEvidenceError("closed batch stages bind different AuditPlans")
    premerge_rows = {row["obligation_id"]: row for row in
                     premerge["audit_evidence_reconciliation"]}
    premerge_bindings = {row["obligation_id"]: row for row in
                         premerge["audit_evidence_bindings"]}

    rows = []
    selected_refs = set()
    postdelta_rows = {
        row["obligation_id"]: row for row in
        postdelta["reconciliation"]["audit_evidence_reconciliation"]
    }
    for obligation_id in sorted(obligations):
        obligation = obligations[obligation_id]
        reconciled = reconciliation[obligation_id]
        if obligation.get("due_stage") == "post-delta-close":
            expected_row = postdelta_rows.get(obligation_id)
            record = postdelta["final_by_obligation"].get(obligation_id)
            resolution_status = "satisfied" if (
                isinstance(record, dict) and expected_row == reconciled
            ) else "invalid"
        else:
            binding = premerge_bindings.get(obligation_id)
            record = (_current_record(catalog, binding["evidence_ref"],
                                      "frozen Terminal evidence")
                      if isinstance(binding, dict) else None)
            resolution_status = "satisfied" if (
                isinstance(record, dict) and premerge_rows.get(obligation_id) == reconciled
            ) else "invalid"
        selected = (record.get("receipt_id")
                    if isinstance(record, dict) else None)
        if (resolution_status != "satisfied" or
                not isinstance(selected, str) or not selected or
                reconciled.get("unresolved") or
                reconciled.get("selected_evidence_ref") != selected or
                reconciled.get("selected_disposition") != "produced" or
                reconciled.get("due_stage") != obligation.get("due_stage")):
            raise AuditEvidenceError(
                "closed batch %s obligation %s has no current selected "
                "evidence matching its close reconciliation" %
                (batch_id, obligation_id))
        if selected in invalidated:
            raise AuditEvidenceError(
                "closed batch %s obligation %s selects invalidated evidence "
                "%s" % (batch_id, obligation_id, selected))
        if selected in selected_refs:
            raise AuditEvidenceError(
                "closed batch %s selects evidence %s for more than one "
                "AuditPlan obligation" % (batch_id, selected))
        selected_refs.add(selected)
        if not _dimension_evidence_is_applicable(obligation, record):
            continue
        dimension = obligation.get("dimension")
        if not isinstance(dimension, str) or not dimension:
            raise AuditEvidenceError(
                "applicable dimension evidence has no registered dimension")
        if dimension not in terminal_dimensions:
            # A review-only Profile extension is still a required AuditPlan
            # obligation and has already passed its owner and close
            # reconciliation above.  It is not a Terminal receipt dimension.
            continue
        row = {
            "batch_id": batch_id,
            "plan_id": plan["plan_id"],
            "obligation_id": obligation_id,
            "dimension": dimension,
            "evidence_kind": obligation["evidence_kind"],
            "evidence_ref": selected,
        }
        if tuple(row) != _TERMINAL_DIMENSION_EVIDENCE_FIELDS:
            raise AssertionError(
                "Terminal dimension evidence fields drifted")
        rows.append(row)
    return rows


def terminal_dimension_evidence(result):
    """Project current plan-bound dimension evidence for Terminal Proof.

    Only evidence selected by the complete reconciliation of a currently
    admitted closed batch can enter this projection.  Each selected record is
    first resolved by the evidence-kind-specific final handler.  Records that
    merely happen to be current, dimensionless Gate evidence, and conditional
    M atoms with a proved not-applicable disposition are deliberately absent.
    """
    if not isinstance(result, dict):
        raise AuditEvidenceError(
            "Terminal dimension evidence needs runtime state")
    errors = result.get("errors")
    if errors:
        raise AuditEvidenceError(
            "Terminal dimension evidence requires an admitted runtime: %s" %
            "; ".join(str(value) for value in errors))
    items = result.get("items_by_id")
    if not isinstance(items, dict):
        raise AuditEvidenceError(
            "Terminal dimension evidence has no canonical Queue item view")
    catalog = current_receipt_catalog(result)
    profile_view = result.get("_profile_authorized_view")
    try:
        from Tools.governance.profile.profile_admission import contract_from_admitted_view
        contract = contract_from_admitted_view(result["root"], profile_view)
        terminal_dimensions = frozenset(
            profile_contract.terminal_receipt_dimensions_projection(
                contract))
    except (TypeError, ValueError) as exc:
        raise AuditEvidenceError(
            "Terminal dimension evidence has no authorized Profile "
            "dimension projection: %s" % exc) from exc
    rows = []
    for batch_id, item in sorted(items.items()):
        if not isinstance(item, dict):
            raise AuditEvidenceError(
                "Queue item %s is not a mapping" % batch_id)
        if item.get("state") != "closed":
            continue
        rows.extend(_closed_batch_dimension_evidence(
            result, item, catalog, terminal_dimensions))
    rows.sort(key=lambda row: (
        row["batch_id"], row["plan_id"], row["obligation_id"],
        row["evidence_ref"]))
    refs = [row["evidence_ref"] for row in rows]
    if len(refs) != len(set(refs)):
        raise AuditEvidenceError(
            "Terminal dimension evidence repeats a selected evidence ref")
    return tuple(rows)


def _accepted_obligation_records(result, plan, rows, *, reconciliation_rows=None):
    selected = []
    for obligation, resolution in rows:
        status = resolution["status"]
        if status == "missing":
            raise AuditEvidenceMissing(
                "required AuditPlan obligation %s has no current terminal %s" %
                (obligation["obligation_id"], obligation["evidence_kind"]))
        if status == "ambiguous":
            raise AuditEvidenceAmbiguous(
                "required AuditPlan obligation %s has ambiguous current %s" %
                (obligation["obligation_id"], obligation["evidence_kind"]))
        if status != "satisfied":
            raise AuditEvidenceError(
                "required AuditPlan obligation %s is %s: %s" %
                (obligation["obligation_id"], status,
                 resolution.get("reason") or "not discharged"))
        selected.append((
            obligation, resolution["record"], resolution["reused"]))
        if reconciliation_rows is not None:
            reconciliation_rows.append(_reconciliation_row(
                result, plan, obligation, resolution))
    return selected


def _resolve_stage_evidence(result, item, due_stage, required_state):
    cache = result.get("_audit_stage_resolutions")
    # The item and catalog are immutable inputs during this scoped action.
    # A caller projecting a candidate uses a different catalog identity.
    key = (_record_sha256(item), id(current_receipt_catalog(result)),
           due_stage, required_state)
    if cache is not None and key in cache:
        return cache[key]
    result = evidence_evaluation(result)
    catalog = current_receipt_catalog(result)
    relative, plan, plan_sha256 = _resolve_current_plan(
        result, item, catalog, required_state=required_state)
    obligations = [row for row in plan["obligations"]
                   if row["due_stage"] == due_stage]
    frozen = None
    if due_stage == "pre-merge" and item.get("state") in {"merge-ready", "closed"}:
        wrapper = _bound_review_projection(result, item, plan, relative, plan_sha256)
        resolved, frozen = _review_stage_evidence(result, item, plan, relative, plan_sha256, wrapper)
    elif ((due_stage == "pre-merge" and item.get("state") == "open") or
          (due_stage == "post-delta-close" and item.get("state") == "merge-ready")):
        _require_current_profile_rendering_contract_state(result, item, plan)
        resolved = [(obligation, _required_obligation_resolution(
            result, item, plan, plan_sha256, catalog, obligation,
            require_current=True)) for obligation in obligations]
    else:
        raise AuditEvidenceError("stage %s cannot be resolved in Queue state %r" %
                                 (due_stage, item.get("state")))
    value = result, relative, plan, plan_sha256, resolved, frozen
    if cache is not None:
        cache[key] = value
    return value


def stage_evidence_status(result, item, due_stage, required_state=None):
    """Project routing fields from the same complete stage resolution.

    Runner and candidate-page selection consume statuses and exact evidence
    references, not a second accounting projection. Historical reconciliation
    is produced by the closure/Terminal consumers when actually required.
    """
    result, relative, plan, plan_sha256, resolved, _frozen = _resolve_stage_evidence(
        result, item, due_stage, required_state)
    if not resolved:
        raise AuditEvidenceError(
            "AuditPlan %s has no obligations due at %s" %
            (plan["plan_id"], due_stage))
    rows = []
    for obligation, resolution in resolved:
        status = resolution["status"]
        record = resolution["record"]
        reason = resolution["reason"]
        rows.append({
            "obligation": dict(obligation),
            "status": status,
            "evidence_ref": record.get("receipt_id")
                if isinstance(record, dict) else None,
            "reason": reason,
        })
    return {
        "audit_plan_id": plan["plan_id"],
        "audit_plan_path": relative,
        "audit_plan_sha256": plan_sha256,
        "due_stage": due_stage,
        "obligations": rows,
    }


def current_consumption_evidence_ids(result, item, plan, plan_sha256,
                                     consuming_obligation, registry=None):
    """Resolve only the current evidence selected by one M consumption edge."""
    result = evidence_evaluation(result)
    registry = registry or result["_audit_evidence_facts"].batch_registry()
    dependency_ids = frozenset(
        batch_review_obligation_contract.consumption_dependency_obligation_ids(
            plan.get("obligations") or (), consuming_obligation, registry))
    if not dependency_ids:
        return frozenset()
    catalog = current_receipt_catalog(result)
    receipt_ids = []
    found = set()
    for obligation in plan.get("obligations") or ():
        obligation_id = obligation.get("obligation_id")
        if obligation_id not in dependency_ids:
            continue
        found.add(obligation_id)
        resolution = _required_obligation_resolution(
            result, item, plan, plan_sha256, catalog, obligation,
            require_current=True)
        if resolution["status"] in {"invalid", "ambiguous"}:
            raise AuditEvidenceError(
                "cannot resolve current consumption evidence for %s: %s" % (
                    obligation_id,
                    resolution.get("reason") or resolution["status"]))
        record = resolution.get("record")
        if resolution["status"] == "satisfied" and isinstance(record, dict):
            receipt_ids.append(record["receipt_id"])
    missing = sorted(dependency_ids - found)
    if missing:
        raise AuditEvidenceError(
            "M consumption selector names absent AuditPlan obligations: %s" %
            ", ".join(missing))
    return frozenset(receipt_ids)


def stage_evidence_closure(result, item, due_stage, required_state=None):
    """Resolve every obligation due at one stage across all evidence kinds."""
    result, relative, plan, plan_sha256, resolved, frozen = _resolve_stage_evidence(
        result, item, due_stage, required_state)
    if frozen is not None:
        return dict(frozen)
    return _stage_projection(result, relative, plan, plan_sha256, resolved)


def _stage_projection(result, relative, plan, plan_sha256, resolved, reconciliation=None):
    """Project bindings once; frozen consumers retain the source history."""
    reconciliation_rows = []
    selected = _accepted_obligation_records(
        result, plan, resolved,
        reconciliation_rows=reconciliation_rows if reconciliation is None else None)
    if reconciliation is None:
        reconciliation = _reconciliation_projection(reconciliation_rows)
    if reconciliation["audit_evidence_unresolved_count"] != 0:
        raise AuditEvidenceError(
            "audit evidence reconciliation contains unresolved obligations")
    bindings = []
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
    bindings.sort(key=lambda row: row["obligation_id"])
    return {
        "audit_plan_id": plan["plan_id"],
        "audit_plan_path": relative,
        "audit_plan_sha256": plan_sha256,
        "audit_evidence_bindings": bindings,
        "audit_evidence_set_sha256": kblib.sha256_bytes(
            kblib.canonical_json_bytes(bindings)),
        **reconciliation,
    }


def batch_review_evidence(result, item, required_state="open"):
    """Return the exact heterogeneous pre-merge closure Batch Review binds."""
    return stage_evidence_closure(
        result, item, "pre-merge", required_state=required_state)


def candidate_page_evidence(result, item):
    """Project current page evidence from the existing heterogeneous resolver.

    A candidate need not discharge every audit obligation yet. Only uniquely
    accepted terminal page evidence (or its accepted terminal precursor) can
    be referenced. Final AuditReceipts are unwrapped through their validated
    producer edge, not treated as a differently spelled passing Gate.
    """
    status = stage_evidence_status(result, item, "pre-merge", required_state="open")
    catalog = current_receipt_catalog(result)
    selected = {path: set() for path in item["manifest"]}
    for row in status["obligations"]:
        obligation = row["obligation"]
        target = obligation["target"]
        if target not in selected:
            continue
        if row["status"] in {"invalid", "ambiguous"}:
            raise AuditEvidenceError("candidate page evidence %s is %s: %s" %
                (obligation["obligation_id"], row["status"], row.get("reason")))
        if row["status"] not in {"satisfied", "ready-for-completion"}:
            continue
        record = _current_record(catalog, row["evidence_ref"], "candidate page evidence")
        if obligation["evidence_kind"] == "audit-receipt" and row["status"] == "satisfied":
            record = _current_record(catalog, record.get("evidence_ref"), "candidate page producer")
        if record.get("result") == "pass" and record.get("target") == target:
            selected[target].add(record["receipt_id"])
    return {target: sorted(refs) for target, refs in selected.items()}


def candidate_page_evidence_errors(result, item, delta, *, resolved=None):
    """Check supplied references without replacing semantics or accepting latest."""
    selected = candidate_page_evidence(result, item) if resolved is None else resolved
    errors = []
    for page in delta.get("pages") or []:
        if not isinstance(page, dict) or page.get("path") not in selected:
            continue  # The Coverage/Delta owner reports structure/manifest errors.
        refs = page.get("gate_receipts")
        if not isinstance(refs, list) or not refs:
            errors.append("%s has no current plan-bound page evidence" % page["path"])
        elif any(ref not in selected[page["path"]] for ref in refs):
            errors.append("%s references evidence outside its current AuditPlan producer closure" % page["path"])
    return errors


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
    return _wrapper_projection_errors(wrapper, expected)


def _wrapper_projection_errors(wrapper, expected):
    """Compare an already resolved projection, without re-running its owner."""
    errors = []
    for field in (
            "audit_plan_id", "audit_plan_path", "audit_plan_sha256",
            "audit_evidence_bindings", "audit_evidence_set_sha256",
            *audit_reconciliation_contract.projection_fields()):
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
    result = evidence_evaluation(result)
    catalog = current_receipt_catalog(result)
    batch_receipts = item.get("batch_receipts") or []
    if (not isinstance(batch_receipts, list) or
            len(batch_receipts) != 1):
        return ["merge-ready batch must bind exactly one Batch Review wrapper"]
    try:
        wrapper = _current_record(
            catalog, batch_receipts[0], "Batch Review wrapper")
        premerge = batch_review_evidence(
            result, item, required_state="merge-ready")
        errors.extend(_wrapper_projection_errors(wrapper, premerge))
        postdelta = _post_delta_evidence_closure(
            result, item, close_receipt, required_state="merge-ready")
        stage_plan = postdelta["stage_plan"]
        postdelta_reconciliation = postdelta["reconciliation"]
        premerge_reconciliation = {
            field: premerge[field]
            for field in audit_reconciliation_contract.projection_fields()
        }
        complete_reconciliation = combine_plan_reconciliations(
            premerge_reconciliation, postdelta_reconciliation)
        expected_close = {
            "audit_plan_id": stage_plan["audit_plan_id"],
            "audit_plan_path": stage_plan["audit_plan_path"],
            "audit_plan_sha256": stage_plan["audit_plan_sha256"],
            "post_delta_evidence_count": len(postdelta["bindings"]),
            "post_delta_evidence_set_sha256":
                postdelta["evidence_set_sha256"],
            **complete_reconciliation,
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
        if complete_reconciliation["audit_evidence_unresolved_count"] != 0:
            errors.append(
                "closed transition has unresolved AuditPlan evidence")
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        errors.append("closed AuditPlan evidence is invalid: %s" % exc)
    return sorted(set(errors))


__all__ = [
    'current_batch_review_receipt',
    'AuditPlanMissing',
    'batch_review_evidence',
    'candidate_page_evidence',
    'candidate_page_evidence_errors',
    'closed_plan_closure_errors',
    'combine_plan_reconciliations',
    'current_consumption_evidence_ids',
    'evidence_observation',
    'reconciliation_from_bindings',
    'resolve_stage_plan',
    'terminal_dimension_evidence',
    'terminal_plan_reconciliation',
    'stage_evidence_closure',
    'stage_evidence_status',
    'wrapper_binding_errors',
]
