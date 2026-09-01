#!/usr/bin/env python3
"""Freeze the complete registry-derived AuditPlan for one open batch.

Kernel base obligations are projected from their machine registries. An
authorized typed Profile is composed only through registered extension
points. The plan freezes obligation definitions, never the three actual
evidence fingerprints that become knowable when an obligation is due.
"""

from copy import deepcopy
import datetime
import os
import re
import sys

import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection
import Tools.execution.audit.audit_plan_contract as audit_plan_contract
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.audit.batch_review_obligation_contract as batch_review_obligation_contract
import Tools.knowledge.rendering.changed_scope_rendering_checks as changed_scope_rendering_checks
import Tools.knowledge.metadata.freshness_engine as freshness_engine
import Tools.platform.common.kblib as kblib
import Tools.knowledge.structure.markdown_structure_checks as markdown_structure_checks
import Tools.governance.profile.profile_batch_judgment_contract as profile_batch_judgment_contract
import Tools.governance.profile.profile_contract as profile_contract
import Tools.execution.task_runtime.queue_runtime.property_state as property_state_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.common import reporting


TOOL = "prepare_audit_plan"
TOOL_VERSION = "1.1.0"
_PROFILE_REVIEW_EXTENSION = profile_batch_judgment_contract.EXTENSION_POINT
_PROFILE_SCAN_EXTENSION = \
    audit_obligation_projection.PROFILE_REGISTERED_SCAN_EXTENSION
_BATCH_SCOPE_TARGET = "."


ProfileRenderingContractGap = \
    changed_scope_rendering_checks.ProfileRenderingContractGap


def _utc_now():
    return datetime.datetime.now(
        datetime.timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z")


def _validate_timestamp(value):
    if (not isinstance(value, str) or
            re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value)
            is None):
        raise audit_producer_runtime.AuditProducerError(
            "--at must be a canonical UTC timestamp ending in Z")
    try:
        datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise audit_producer_runtime.AuditProducerError(
            "--at is not a real UTC timestamp: %s" % exc)
    return value


def _coverage_rows(result):
    rows = (result.get("coverage") or {}).get("pages") or []
    by_path = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        if not isinstance(path, str) or not path:
            continue
        if path in by_path:
            raise audit_producer_runtime.AuditProducerError(
                "Coverage repeats page %s" % path)
        by_path[path] = row
    return by_path


def _profile_volatility_defaults(result):
    """Consume the admitted Profile linker's typed volatility policy."""
    view = result.get("_profile_authorized_view")
    if not isinstance(view, dict):
        raise audit_producer_runtime.AuditProducerError(
            "L-tier substantive-review trigger HOLD: runtime has no "
            "authorized Profile view")
    try:
        return dict(profile_contract.volatility_defaults_projection(
            view.get("_contract")))
    except (TypeError, profile_contract.ProfileContractError) as exc:
        raise audit_producer_runtime.AuditProducerError(
            "L-tier substantive-review trigger HOLD: authorized Profile "
            "has no valid typed volatility_defaults projection: %s" % exc
        ) from exc


def _rereview_paths(result):
    """Project only the K12/11 governed rereview gap marker."""
    gaps = (result.get("coverage") or {}).get("open_gaps")
    if gaps is None:
        gaps = []
    if not isinstance(gaps, list):
        raise audit_producer_runtime.AuditProducerError(
            "Coverage open_gaps must be an explicit list")
    return frozenset(
        gap.get("page") for gap in gaps
        if isinstance(gap, dict) and gap.get("type") == "rereview" and
        isinstance(gap.get("page"), str) and gap.get("page"))


def _page_frontmatter_with_owner_state(page, row):
    """Bind page policy values and overlay canonical completed events."""
    raw = kblib.extract_frontmatter(page.snapshot.read_text())
    if raw is None:
        return None, True
    try:
        frontmatter = kblib.parse_yaml_subset(raw)
    except (TypeError, ValueError, kblib.YamlSubsetError):
        return None, True
    if not isinstance(frontmatter, dict):
        return None, True
    frontmatter = dict(frontmatter)
    property_state = row.get("property_state")
    if property_state is None:
        property_state = {}
    if not isinstance(property_state, dict):
        raise audit_producer_runtime.AuditProducerError(
            "Coverage property_state for %s is not a mapping" % page.path)
    for field in (
            "last_content_modified", "last_verified", "last_reviewed"):
        record = property_state.get(field)
        if record is None:
            frontmatter.pop(field, None)
        elif isinstance(record, dict) and "value" in record:
            frontmatter[field] = record["value"]
        else:
            raise audit_producer_runtime.AuditProducerError(
                "Coverage property_state.%s for %s is not a current owner "
                "record" % (field, page.path))
    return frontmatter, False


def _review_evidence_state(row, page, *, rereview_marked=False,
                           hold_context):
    """Resolve only the governed semantic-review evidence state.

    Coverage ``property_state`` and its governed rereview gap are the sole
    authority here. Page frontmatter is deliberately not a fallback: an
    unmanaged marker outside the owner/evidence loop cannot make an existing
    page look reviewed.
    """
    status = row.get("authoring_status")
    if status not in {"unassessed", "outline", "drafted", "reviewed"}:
        raise audit_producer_runtime.AuditProducerError(
            "%s trigger HOLD for %s: "
            "authoring_status %r is outside the K08 closed vocabulary" %
            (hold_context, page.path, status))
    property_state = row.get("property_state") or {}
    if not isinstance(property_state, dict):
        raise audit_producer_runtime.AuditProducerError(
            "%s trigger HOLD for %s: property_state is not a mapping" %
            (hold_context, page.path))
    last_reviewed = property_state.get("last_reviewed")
    if rereview_marked or (
            isinstance(last_reviewed, dict) and
            "value" in last_reviewed and last_reviewed["value"] is None):
        return status, last_reviewed, "needs_rereview"
    if last_reviewed is None:
        if status == "reviewed":
            raise audit_producer_runtime.AuditProducerError(
                "%s trigger HOLD for %s: reviewed status has no current "
                "last_reviewed owner evidence" %
                (hold_context, page.path))
        return status, None, "new"
    if not isinstance(last_reviewed, dict) or "value" not in last_reviewed:
        raise audit_producer_runtime.AuditProducerError(
            "%s trigger HOLD for %s: last_reviewed is not a current owner "
            "record" % (hold_context, page.path))
    return status, last_reviewed, "current"


def _l_review_trigger(row, page, generated_at, volatility_defaults,
                      rereview_marked=False):
    """Return one existing K12/12 trigger, no trigger, or fail closed.

    ``None`` means the page already has current substantive review evidence
    and its Profile-resolved review deadline has not arrived.
    """
    status, _last_reviewed, evidence_state = _review_evidence_state(
        row, page, rereview_marked=rereview_marked,
        hold_context="L-tier substantive-review")
    if evidence_state != "current":
        return evidence_state

    frontmatter, frontmatter_error = \
        _page_frontmatter_with_owner_state(page, row)
    opened = datetime.datetime.strptime(
        generated_at, "%Y-%m-%dT%H:%M:%SZ").date()
    run = freshness_engine.evaluate_freshness((
        freshness_engine.PageSnapshot(
            path=page.path,
            frontmatter=frontmatter,
            modified_on=opened,
            frontmatter_error=frontmatter_error,
            excluded=row.get("coverage_disposition") == "excluded"),
    ), freshness_engine.FreshnessPolicy(
        as_of=opened, volatility_defaults=volatility_defaults))
    outcome = run.outcomes[0]
    if outcome.kind == freshness_engine.MODIFIED_SINCE_REVIEW:
        return "needs_rereview"
    if outcome.kind == freshness_engine.OVERDUE:
        return "review_by_expired"
    if not outcome.is_candidate and status == "reviewed":
        return None
    raise audit_producer_runtime.AuditProducerError(
        "L-tier substantive-review trigger HOLD for %s: freshness outcome "
        "%s and authoring_status %s do not uniquely select new, "
        "needs_rereview, review_by_expired, or current exemption" %
        (page.path, outcome.kind, status))


def _m_review_trigger(row, page, *, rereview_marked=False):
    """Fold governed semantic-review evidence into M's existing two states.

    A page with no accepted review evidence for any governed predecessor is
    ``new``.  Current, expired, invalidated, or explicitly targeted prior
    review evidence all select ``needs_rereview`` because an M page present in
    this batch still completes its checklist inside Batch Review.  Prior
    evidence therefore prevents a false initial-review label but never exempts
    the current batch from M review.
    """
    _status, _last_reviewed, evidence_state = _review_evidence_state(
        row, page, rereview_marked=rereview_marked,
        hold_context="M-tier batch-review")
    if evidence_state == "new":
        return "new"
    return "needs_rereview"


def _authorized_profile_contract(result, bindings):
    view = result.get("_profile_authorized_view")
    contract = view.get("_contract") if isinstance(view, dict) else None
    if contract is None or not getattr(contract, "authorized", False):
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan projection requires an authorized typed Profile")
    if getattr(contract, "manifest_repo_path", None) != \
            bindings["selected_profile_manifest"]:
        raise audit_producer_runtime.AuditProducerError(
            "authorized typed Profile selects a different manifest")
    if getattr(contract, "profile_contract_fingerprint", None) != \
            bindings["profile_contract_fingerprint"]:
        raise audit_producer_runtime.AuditProducerError(
            "authorized typed Profile fingerprint differs from runtime")
    return contract


def _judgment(contract, judgment_item_id):
    matches = [row for row in getattr(contract, "judgment_items", ())
               if row.judgment_item_id == judgment_item_id]
    if len(matches) != 1:
        raise audit_producer_runtime.AuditProducerError(
            "Profile registration %s has no unique Judgment Item" %
            judgment_item_id)
    return matches[0]


def _resolve(spec, target, *, trigger=None, dimension=None,
             registered_dimensions=None):
    definition = audit_obligation_projection.resolve_obligation_definition(
        spec, target, trigger=trigger, dimension=dimension,
        registered_dimensions=registered_dimensions)
    return audit_obligation_projection.required_obligation(definition)


def _contract_snapshot(state, profile, standards, opening, obligations):
    return audit_plan_contract.contract_snapshot_sha256(
        task_id=state["task_id"],
        upstream_revision_id=standards["upstream_revision_id"],
        active_standards_sha256=standards["active_standards_sha256"],
        selected_profile_manifest=profile["selected_profile_manifest"],
        profile_snapshot_sha256=profile["profile_snapshot_sha256"],
        profile_contract_fingerprint=profile[
            "profile_contract_fingerprint"],
        opening_transition_receipt=opening["opening_transition_receipt"],
        accepted_baseline_sha256=opening[
            "manifest_semantic_before_set_sha256"],
        obligations=obligations,
    )


def _plan_id(task_id, batch_id, opening_transition_receipt):
    safe_batch = re.sub(r"[^A-Za-z0-9_-]+", "-", batch_id).strip("-")
    if not safe_batch:
        safe_batch = "batch"
    digest = kblib.sha256_bytes(kblib.canonical_json_bytes({
        "task_id": task_id,
        "batch_id": batch_id,
        "opening_transition_receipt": opening_transition_receipt,
    }))
    return "audit-plan-%s-%s" % (
        safe_batch, digest.split(":", 1)[1][:16])


def _plan_path(plan_id):
    return runtime_paths.child_path(
        runtime_paths.AUDIT_PLAN_ROOT, "%s.yaml" % plan_id)


def _has_frontmatter(page):
    text = page.snapshot.read_text()
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    return any(line.strip() == "---" for line in lines[1:])


def _has_mermaid_fence(page):
    return markdown_structure_checks.has_mermaid_fence(
        page.snapshot.read_text())


def _has_markdown_table(page):
    return markdown_structure_checks.has_markdown_table(
        page.snapshot.read_text())


def _profile_rendering_contract_gap_targets(frozen):
    """Return complex constructs that cannot yet be bound by typed Profile.

    Cambium currently exposes no typed Profile Rendering Contract slot.  File
    presence, prose, or a Host capability therefore cannot be treated as a
    valid binding.  Only constructs whose selector is already machine-owned by
    a Kernel base predicate can enter this decision.  Formula, image, embed,
    asset, and callout syntax remains an explicitly reported contract-design
    gap; this Tool does not guess that applicability from bytes.  Pages without
    a selector-owned construct remain not-applicable to this limited route;
    pages with one HOLD plan publication until the typed extension exists.
    """
    return changed_scope_rendering_checks.\
        profile_rendering_contract_gap_targets(
            ((page.path, page.snapshot.read_text()) for page in frozen),
            contract_is_bound_and_valid=False)


def _changed_scope_targets(spec, *, item, frozen, coverage):
    """Resolve one registered applicability only from existing typed input.

    ``None`` means the current registry row cannot be projected faithfully;
    the caller reports every such gap together and refuses plan publication.
    """
    applicability = spec["applicability"]
    manifest = tuple(page.path for page in frozen)
    if applicability == "every-batch-close":
        return ("Progress.guidance_queue",), None
    if applicability == \
            "changed-scope-includes-coverage-or-required-routing-state":
        return tuple(sorted(manifest)), None
    if applicability == \
            "changed-scope-includes-page-contract-applicable-markdown":
        return tuple(sorted(manifest)), None
    if applicability == "changed-scope-includes-frontmatter":
        return tuple(sorted(
            page.path for page in frozen if _has_frontmatter(page))), None
    if applicability == \
            "batch-contract-freezes-machine-checkable-component-references":
        return (item["id"],), None
    if applicability == "every-changed-markdown-page":
        return tuple(sorted(manifest)), None
    if applicability == "changed-scope-includes-mermaid-fence":
        return tuple(sorted(
            page.path for page in frozen if _has_mermaid_fence(page))), None
    if applicability == "changed-scope-includes-markdown-table":
        return tuple(sorted(
            page.path for page in frozen if _has_markdown_table(page))), None
    if applicability == "every-batch":
        return (item["id"],), None

    # These draft rows currently lack either an executable selector or a
    # faithful codification boundary.  Keeping the reasons beside projection
    # prevents a Tool fallback from silently turning optional/prose rules into
    # new blocking obligations.
    gap_by_applicability = {
        "changed-scope-includes-knowledge-markdown":
            "empty/short threshold and unit are not uniquely registered",
        "changed-scope-includes-source-note":
            "draft row duplicates page-contract missingness and upgrades "
            "optional fields",
        "changed-scope-includes-research-synthesis":
            "draft row promotes prose-template fields into blocking checks",
        "changed-scope-includes-source-driven-page-type":
            "draft row upgrades optional applicability/relationship fields",
        "changed-scope-includes-renderable-artifact":
            "draft aggregate combines distinct structure and rendering "
            "judgment dimensions",
        "changed-scope-declares-rendering-level-2-through-4":
            "no opening-frozen typed rendering-level declaration exists",
    }
    reason = gap_by_applicability.get(applicability)
    if reason is None:
        reason = "registry applicability has no installed exact selector"
    return None, reason


def _project_obligations(root, result, item, frozen, generated_at,
                         state, profile, opening):
    coverage = _coverage_rows(result)
    manifest = [page.path for page in frozen]
    missing = [path for path in manifest if path not in coverage]
    if missing:
        raise audit_producer_runtime.AuditProducerError(
            "batch manifest lacks Coverage rows: %s" % ", ".join(missing))
    tiers = {path: coverage[path].get("tier") for path in manifest}
    invalid = [path for path in manifest
               if tiers[path] not in {"L", "M", "S"}]
    if invalid:
        raise audit_producer_runtime.AuditProducerError(
            "batch manifest has unregistered review tiers: %s" %
            ", ".join(invalid))

    contract = _authorized_profile_contract(result, profile)
    rendering_gaps = _profile_rendering_contract_gap_targets(frozen)
    if rendering_gaps:
        raise ProfileRenderingContractGap(rendering_gaps)
    try:
        composed, dimensions = \
            audit_obligation_projection.composed_obligation_specs(
                contract, root=root)
    except (TypeError, ValueError) as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc
    base_specs = tuple(row for row in composed
                       if row["owner_kind"] == "kernel")
    extensions = tuple(row for row in composed
                       if row["owner_kind"] == "profile-extension")

    l_specs = tuple(row for row in base_specs if row["tier"] == "L")
    m_specs = tuple(row for row in base_specs if row["tier"] == "M")
    s_specs = tuple(row for row in base_specs if row["tier"] == "S")
    if len(l_specs) != 1 or not m_specs or len(s_specs) != 1:
        raise audit_producer_runtime.AuditProducerError(
            "Kernel page-review projection does not expose one L template, "
            "a non-empty M registry, and one S template")

    obligations = []
    rereview_paths = _rereview_paths(result)
    volatility_defaults = None
    for page in frozen:
        tier = tiers[page.path]
        if tier == "L":
            row = coverage[page.path]
            last_reviewed = (row.get("property_state") or {}).get(
                "last_reviewed") if isinstance(
                    row.get("property_state") or {}, dict) else None
            needs_policy = (
                isinstance(last_reviewed, dict) and
                last_reviewed.get("value") is not None and
                page.path not in rereview_paths)
            if needs_policy and volatility_defaults is None:
                volatility_defaults = _profile_volatility_defaults(result)
            trigger = _l_review_trigger(
                row, page, generated_at, volatility_defaults or {},
                rereview_marked=page.path in rereview_paths)
            if trigger is not None:
                obligations.append(_resolve(
                    l_specs[0], page.path, trigger=trigger,
                    registered_dimensions=dimensions))
        elif tier == "M":
            trigger = _m_review_trigger(
                coverage[page.path], page,
                rereview_marked=page.path in rereview_paths)
            for spec in m_specs:
                obligations.append(_resolve(
                    spec, page.path, trigger=trigger,
                    registered_dimensions=dimensions))

    s_population = sorted(path for path in manifest if tiers[path] == "S")
    batch_registry = batch_review_obligation_contract.load_registry(root)
    selection = batch_review_obligation_contract.select_s_targets(
        s_population, task_id=state["task_id"], batch_id=item["id"],
        opening_transition_receipt=opening["opening_transition_receipt"],
        registry=batch_registry)
    for target in selection["sample_selected_targets"]:
        obligations.append(_resolve(
            s_specs[0], target, registered_dimensions=dimensions))

    changed_specs = tuple(
        row for row in base_specs
        if row["source_registry"] ==
        audit_obligation_projection.CHANGED_SCOPE_REGISTRY_PATH)
    selector_gaps = []
    for spec in changed_specs:
        targets, gap = _changed_scope_targets(
            spec, item=item, frozen=frozen, coverage=coverage)
        if gap is not None:
            selector_gaps.append("%s: %s" % (spec["owner_rule_id"], gap))
            continue
        for target in targets:
            obligations.append(_resolve(
                spec, target, registered_dimensions=dimensions))
    if selector_gaps:
        raise audit_producer_runtime.AuditProducerError(
            "changed-scope registry cannot be faithfully projected: %s" %
            "; ".join(selector_gaps))

    close_specs = tuple(
        row for row in base_specs
        if row["source_registry"] ==
        audit_obligation_projection.BATCH_CLOSE_REGISTRY_PATH)
    required_scan = getattr(contract, "required_scan", None)
    if required_scan is None:
        raise audit_producer_runtime.AuditProducerError(
            "typed Profile has no unique K12/09 item 6 scan")
    item6_dimension = _judgment(
        contract, required_scan.judgment_item_id).dimension_id
    for spec in close_specs:
        dimension = (item6_dimension
                     if spec["dimension_binding"] == "profile-registration"
                     else None)
        obligations.append(_resolve(
            spec, _BATCH_SCOPE_TARGET, dimension=dimension,
            registered_dimensions=dimensions))

    for spec in extensions:
        if spec["kernel_extension_point"] == _PROFILE_SCAN_EXTENSION:
            targets = (_BATCH_SCOPE_TARGET,)
        elif spec["kernel_extension_point"] == _PROFILE_REVIEW_EXTENSION:
            try:
                expanded = profile_batch_judgment_contract.\
                    expand_requirements(contract, item)
            except (TypeError, ValueError) as exc:
                raise audit_producer_runtime.AuditProducerError(
                    str(exc)) from exc
            targets = tuple(
                row["target"] for row in expanded
                if row["judgment_item_id"] == spec["owner_rule_id"])
            if not targets:
                raise audit_producer_runtime.AuditProducerError(
                    "Profile Batch Review Requirement has no expanded target")
        else:
            raise audit_producer_runtime.AuditProducerError(
                "Profile obligation uses an unsupported extension point")
        for target in targets:
            obligations.append(_resolve(
                spec, target, registered_dimensions=dimensions))

    obligations.sort(key=lambda row: row["obligation_id"])
    identifiers = [row["obligation_id"] for row in obligations]
    if len(identifiers) != len(set(identifiers)):
        raise audit_producer_runtime.AuditProducerError(
            "projected AuditPlan repeats an obligation identity")
    return obligations, tiers, batch_registry


def build_plan(root, result, item, activation, *, generated_at):
    """Derive and validate one complete immutable AuditPlan."""
    del activation  # Card delivery is not an AuditPlan definition binding.
    frozen = audit_producer_runtime.freeze_manifest_pages(root, result, item)
    artifact_snapshot = audit_producer_runtime.page_set_sha256(frozen)
    state = audit_producer_runtime.runtime_state_bindings(result)
    profile = audit_producer_runtime.profile_bindings(result)
    standards = audit_producer_runtime.standards_bindings(result)
    opening = check_queue_opening_context(result, item["id"])
    obligations, tiers, batch_registry = _project_obligations(
        root, result, item, frozen, generated_at, state, profile, opening)
    contract_snapshot = _contract_snapshot(
        state, profile, standards, opening, obligations)
    plan_contract = audit_plan_contract.load_contract(root)
    plan = {
        "schema_version": plan_contract["schema_version"],
        "plan_id": _plan_id(
            state["task_id"], item["id"],
            opening["opening_transition_receipt"]),
        "task_id": state["task_id"],
        "batch_id": item["id"],
        "generated_at": generated_at,
        "queue_revision": state["queue_revision"],
        "queue_state_revision": state["queue_state_revision"],
        "required_queue_sha256": state["required_queue_sha256"],
        "upstream_revision_id": standards["upstream_revision_id"],
        "active_standards_sha256": standards["active_standards_sha256"],
        "selected_profile_manifest": profile["selected_profile_manifest"],
        "profile_snapshot_sha256": profile["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            profile["profile_contract_fingerprint"],
        "opening_transition_receipt":
            opening["opening_transition_receipt"],
        "artifact_snapshot_sha256": artifact_snapshot,
        "contract_snapshot_sha256": contract_snapshot,
        "accepted_baseline_sha256":
            opening["manifest_semantic_before_set_sha256"],
        "obligations": obligations,
    }
    audit_plan_contract.validate_plan(plan, plan_contract)
    batch_review_obligation_contract.validate_plan_base_closure(
        plan, sorted(item["manifest"]), tiers, registry=batch_registry)
    return plan, frozen


def check_queue_opening_context(result, batch_id):
    """Read the opening baseline from the Queue runtime public API."""
    return property_state_contract.current_opening_semantic_context(
        result, batch_id)


def require_plan_current(plan, root, result, item, activation, frozen=None):
    """Validate only immutable opening, Profile, and Standards bindings.

    Queue revisions, Queue bytes, lifecycle state, and page bytes normally
    move after ``open``. They are historical publication observations, not
    reasons to rewrite or replace the opening-frozen plan.
    """
    del activation
    audit_plan_contract.validate_plan(
        plan, audit_plan_contract.load_contract(root))
    state = audit_producer_runtime.runtime_state_bindings(result)
    profile = audit_producer_runtime.profile_bindings(result)
    standards = audit_producer_runtime.standards_bindings(result)
    opening = check_queue_opening_context(result, item["id"])
    expected = {
        "task_id": state["task_id"],
        "batch_id": item["id"],
        "upstream_revision_id": standards["upstream_revision_id"],
        "active_standards_sha256": standards["active_standards_sha256"],
        "selected_profile_manifest": profile["selected_profile_manifest"],
        "profile_snapshot_sha256": profile["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            profile["profile_contract_fingerprint"],
        "opening_transition_receipt":
            opening["opening_transition_receipt"],
        "accepted_baseline_sha256":
            opening["manifest_semantic_before_set_sha256"],
    }
    mismatches = [field for field, value in expected.items()
                  if plan.get(field) != value]
    if mismatches:
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan is no longer current in: %s" % ", ".join(mismatches))
    if frozen is None:
        frozen = audit_producer_runtime.freeze_manifest_pages(
            root, result, item)
    contract = _authorized_profile_contract(result, profile)
    try:
        audit_obligation_projection.validate_plan_definition_authority(
            plan, contract, root=root)
    except (TypeError, ValueError) as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc
    expected_contract_snapshot = _contract_snapshot(
        state, profile, standards, opening, plan["obligations"])
    if plan["contract_snapshot_sha256"] != expected_contract_snapshot:
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan contract_snapshot_sha256 does not bind its current "
            "registered definitions")
    changed_scope_rendering_checks.require_profile_rendering_contract_state(
        ((page.path, page.snapshot.read_text()) for page in frozen),
        contract_is_bound_and_valid=False)
    return frozen


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Prepare the complete immutable AuditPlan for an open "
                    "batch")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True,
                        help="current open Queue batch ID")
    parser.add_argument("--at", default=None,
                        help="canonical UTC generation time; defaults to now")
    parser.add_argument("--apply", action="store_true",
                        help="write the plan; omit for dry-run")
    args = parser.parse_args(argv)

    try:
        generated_at = _validate_timestamp(args.at) if args.at else _utc_now()
        root, result, authority = audit_producer_runtime.admitted_runtime(
            args.root)
        item, activation = audit_producer_runtime.open_batch(
            result, args.batch)
        plan, frozen = build_plan(
            root, result, item, activation, generated_at=generated_at)
        relative = _plan_path(plan["plan_id"])
        absolute = audit_producer_runtime.managed_plan_path(root, relative)
        text = kblib.canonical_yaml(plan)
    except ProfileRenderingContractGap as exc:
        reporting.write_canonical_json({
            "applied": False,
            "contract_owner": "profile-rendering-contract",
            "errors": [],
            "hold_reason": "contract-gap",
            "status": "hold",
            "targets": [dict(row) for row in exc.targets],
        })
        return 2
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        reporting.write_canonical_json(
            {"applied": False, "errors": [str(exc)], "status": "invalid"})
        return 1

    if os.path.exists(absolute):
        try:
            existing = kblib.read_text(absolute)
            existing_plan = kblib.parse_yaml_subset(existing)
            require_plan_current(
                existing_plan, root, result, item, activation)
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            reporting.write_canonical_json({
                "applied": False,
                "errors": ["existing AuditPlan conflicts: %s" % exc],
                "status": "invalid",
                "plan_path": relative,
            })
            return 1
        reporting.write_canonical_json({
            "applied": args.apply,
            "errors": [],
            "status": "already-present",
            "plan_id": existing_plan["plan_id"],
            "plan_path": relative,
            "plan_sha256": audit_plan_contract.plan_sha256(existing_plan),
            "required_obligations": len(
                audit_plan_contract.required_obligation_ids(existing_plan)),
        })
        return 0

    if not args.apply:
        reporting.write_canonical_json({
            "applied": False,
            "errors": [],
            "status": "planned",
            "plan_id": plan["plan_id"],
            "plan_path": relative,
            "plan_sha256": audit_plan_contract.plan_sha256(plan),
            "required_obligations": len(
                audit_plan_contract.required_obligation_ids(plan)),
        })
        return 0

    operation = audit_producer_runtime.runtime_lock_metadata(
        TOOL, "prepare-audit-plan", result, authority,
        batch_id=args.batch, plan_id=plan["plan_id"], plan_path=relative)
    try:
        with kblib.runtime_write_lock(root, owner_metadata=operation):
            locked = audit_producer_runtime.require_runtime_current(
                root, authority, "before AuditPlan publication")
            locked_item, locked_activation = \
                audit_producer_runtime.open_batch(locked, args.batch)
            require_plan_current(
                plan, root, locked, locked_item, locked_activation,
                frozen=frozen)
            audit_producer_runtime.require_pages_current(
                root, frozen, "before AuditPlan publication")
            if os.path.exists(absolute):
                raise audit_producer_runtime.AuditProducerError(
                    "AuditPlan path appeared before publication")
            kblib.atomic_write_text(
                absolute, text, validator=kblib.parse_yaml_subset)
    except (OSError, TypeError, ValueError,
            kblib.RuntimeStateLockedError) as exc:
        reporting.write_canonical_json({
            "applied": False,
            "errors": [str(exc)],
            "status": "uncertain",
            "plan_id": plan["plan_id"],
            "plan_path": relative,
        })
        return 1

    try:
        persisted_text = kblib.read_text(absolute)
        persisted = kblib.parse_yaml_subset(persisted_text)
        if persisted != plan:
            raise audit_producer_runtime.AuditProducerError(
                "published AuditPlan did not read back exactly")
        require_plan_current(persisted, root, result, item, activation)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        reporting.write_canonical_json({
            "applied": True,
            "errors": [str(exc)],
            "status": "uncertain",
            "plan_id": plan["plan_id"],
            "plan_path": relative,
        })
        return 1

    reporting.write_canonical_json({
        "applied": True,
        "errors": [],
        "status": "recorded",
        "plan_id": plan["plan_id"],
        "plan_path": relative,
        "plan_sha256": audit_plan_contract.plan_sha256(plan),
        "required_obligations": len(
            audit_plan_contract.required_obligation_ids(plan)),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
