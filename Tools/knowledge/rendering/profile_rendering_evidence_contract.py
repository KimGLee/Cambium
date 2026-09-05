"""Plan-bound Profile rendering evidence and its shared acceptance boundary.

Profile registrations choose constructs and predicates.  Actual compiler
reports remain distinct from the Kernel's rendering-record shape attestation.
The finalizer and batch consumer call this same validator.
"""

import re

import Tools.execution.audit.audit_fingerprint as audit_fingerprint
import Tools.execution.audit.audit_lifecycle_contract as lifecycle
import Tools.platform.common.kblib as kblib
import Tools.knowledge.rendering.changed_scope_rendering_checks as gap_checks


TOOL = "record_profile_rendering"
TOOL_VERSION = "1.0.0"
CHECK = "profile_rendering"
CAPABILITY_ID = "profile-rendering-evidence-v1"
EXTENSION_POINT = "k12-02-profile-rendering"
RECORD_KIND = "profile-rendering-evidence"
RECEIPT_TYPE_ID = "profile-rendering-evidence-v1"
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FIELDS = frozenset((
    "receipt_id", "receipt_type_id", "tool", "tool_version", "check",
    "target", "result", "details", "checked_at", "invalidated_by",
    "schema_version", "record_kind", "scope", "artifact_fingerprint",
    "dependency_fingerprint", "contract_fingerprint", "render_report",
    "rendering_contract_sha256", "construct", "render_bindings",
)) | frozenset(lifecycle.ATTEMPT_IDENTITY_FIELDS) | frozenset(
    lifecycle.OBLIGATION_BINDING_FIELDS)


def load_profile_admission(root, manifest=None, *, evaluation=None):
    """Use the sole Profile Gate; compiled values are not runtime authority."""
    from Tools.governance.profile import profile_admission
    if manifest is None:
        if evaluation is not None:
            raise ValueError("reused Profile evaluation requires its explicit manifest")
        admission, errors = profile_admission.admit_profile(root)
    else:
        admission, errors = profile_admission.admit_profile_manifest(
            root, manifest, evaluation=evaluation)
    if errors:
        raise ValueError("Profile rendering admission: " + "; ".join(errors))
    return admission


def rendering_contract(profile):
    value = getattr(profile, "rendering_contract", None)
    return value if value is not None and value.registration == "configured" else None


def rendering_source(text):
    """Retain exact body bytes, excluding non-rendered YAML frontmatter."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], 1):
            if line.strip() in {"---", "..."}:
                return "".join(lines[index + 1:])
        raise ValueError("rendering source has unclosed frontmatter")
    return text


def selected_constructs(text, profile, *, root):
    """Use the sole AST selector for syntax requiring parsing.

    A dollar sign is only a conservative parser-launch candidate, never a
    second math grammar. Plain unconfigured pages retain their no-Node path;
    ambiguous dollar-bearing input fails closed if the parser is unavailable.
    """
    source = rendering_source(text)
    if rendering_contract(profile) is None and "$" not in source:
        return gap_checks.selector_owned_profile_rendering_constructs(text)
    from Tools.knowledge.rendering import static_render_runtime
    return static_render_runtime.select_constructs(source, root=root)


def require_bindings(pages, profile, *, root):
    """Return exact construct targets or fail closed on an unbound construct."""
    contract = rendering_contract(profile)
    selected = {}
    missing = []
    for target, text in pages:
        constructs = selected_constructs(text, profile, root=root)
        selected[target] = tuple(constructs)
        absent = [kind for kind in constructs if contract is None or
                  contract.binding_for_construct(kind) is None]
        if absent:
            missing.append((target, absent))
    if missing:
        raise gap_checks.ProfileRenderingContractGap(missing)
    return selected


def require_plan_applicability(plan, pages, profile, *, root):
    """Reject construct-set drift without rewriting the opening-frozen plan."""
    selected = require_bindings(pages, profile, root=root)
    contract = rendering_contract(profile)
    expected = {
        (target, contract.binding_for_construct(kind).rule_id)
        for target, kinds in selected.items() for kind in kinds
    }
    planned = {
        (row.get("target"), row.get("owner_rule_id"))
        for row in plan.get("obligations", [])
        if row.get("kernel_extension_point") == EXTENSION_POINT
    }
    missing = sorted(expected - planned)
    obsolete = sorted(planned - expected)
    if missing or obsolete:
        raise ValueError(
            "Profile rendering contract-gap/HOLD: frozen AuditPlan "
            "applicability differs from current constructs; "
            "missing=%s; obsolete=%s; the frozen plan is not rewritten" %
            (missing, obsolete))
    return selected


def rule_for_obligation(profile, obligation):
    contract = rendering_contract(profile)
    matches = [] if contract is None else [
        rule for rule in contract.rules
        if rule.rule_id == obligation.get("owner_rule_id")]
    if len(matches) != 1:
        raise ValueError("rendering obligation has no unique configured Profile rule")
    return matches[0]


def report_dependency_fingerprint(report):
    return kblib.sha256_bytes(kblib.canonical_json_bytes({
        "protocol": RECEIPT_TYPE_ID,
        "report_sha256": report.get("report_sha256"),
        "runtime_sha256": report.get("runtime_sha256"),
        "bindings_sha256": report.get("bindings_sha256"),
    }))


def contract_fingerprint(plan, obligation, contract):
    return audit_fingerprint.obligation_contract_fingerprint(
        plan, obligation, additional={
            "profile_rendering_contract_sha256": contract.fingerprint})


def current_receipt_errors(record, *, root=None):
    """Validate stable record shape without executing or loading live authority."""
    del root
    if not isinstance(record, dict) or set(record) != _FIELDS:
        return ["Profile rendering evidence fields are not closed"]
    expected = {
        "schema_version": 1, "record_kind": RECORD_KIND,
        "receipt_type_id": RECEIPT_TYPE_ID, "tool": TOOL,
        "tool_version": TOOL_VERSION, "check": CHECK,
        "owner_kind": "profile-extension",
        "kernel_extension_point": EXTENSION_POINT,
        "evidence_kind": "audit-receipt", "evidence_role": "emits",
        "dimension": "rendering", "due_stage": "pre-merge",
        "consumer_gate_id": "batch-review",
        "producer_capability": CAPABILITY_ID, "producer_gate_id": None,
        "producer_check": CHECK, "fingerprint_binding": "evidence-time",
    }
    errors = [field for field, value in expected.items() if record.get(field) != value]
    if record.get("result") not in {"pass", "fail"}:
        errors.append("result")
    for field in ("artifact_fingerprint", "dependency_fingerprint",
                  "contract_fingerprint", "rendering_contract_sha256",
                  "audit_plan_sha256", "active_standards_sha256",
                  "profile_snapshot_sha256", "profile_contract_fingerprint"):
        if not isinstance(record.get(field), str) or not _SHA.fullmatch(record[field]):
            errors.append(field)
    for field in ("receipt_id", "target", "checked_at", "plan_id",
                  "obligation_id", "task_id", "batch_id",
                  "opening_transition_receipt", "upstream_revision_id",
                  "selected_profile_manifest", "owner_rule_id", "construct",
                  "acceptance_predicate"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            errors.append(field)
    if record.get("scope") != [record.get("target")]:
        errors.append("scope")
    if not isinstance(record.get("render_bindings"), dict):
        errors.append("render_bindings")
    report = record.get("render_report")
    if not isinstance(report, dict):
        errors.append("render_report")
    else:
        material = {key: value for key, value in report.items() if key != "report_sha256"}
        if report.get("report_sha256") != kblib.sha256_bytes(kblib.canonical_json_bytes(material)):
            errors.append("render_report.report_sha256")
        if record.get("dependency_fingerprint") != report_dependency_fingerprint(report):
            errors.append("dependency_fingerprint")
        if record.get("result") != report.get("result"):
            errors.append("render_report.result")
    return errors


def validate_record_for_obligation(record, plan, plan_sha256, obligation, *,
                                   root, evaluation=None, text=None,
                                   require_current=True):
    errors = current_receipt_errors(record)
    errors.extend(lifecycle.attempt_binding_mismatches(record, plan, plan_sha256, obligation))
    if errors:
        raise ValueError("Profile rendering evidence: %s" % ", ".join(errors))
    if not require_current:
        return record
    admission = load_profile_admission(
        root, plan["selected_profile_manifest"], evaluation=evaluation)
    profile = admission.contract
    if (admission.profile_snapshot_sha256 != plan.get("profile_snapshot_sha256") or
            profile.fingerprint != plan.get("profile_contract_fingerprint")):
        raise ValueError("Profile rendering selection differs from the frozen AuditPlan")
    contract = rendering_contract(profile)
    rule = rule_for_obligation(profile, obligation)
    if text is None:
        page = kblib.repository_target_snapshot(root, obligation["target"],
            suffixes=(".md", ".MD"), singly_linked=True)
        if not page.exists:
            raise ValueError("Profile rendering target no longer exists")
        text = page.read_text()
    kinds = require_bindings([(obligation["target"], text)], profile, root=root)[obligation["target"]]
    bindings = {kind: contract.binding_for_construct(kind).acceptance for kind in kinds}
    expected = {
        "construct": rule.construct, "render_bindings": bindings,
        "rendering_contract_sha256": contract.fingerprint,
        "artifact_fingerprint": audit_fingerprint.page_artifact_fingerprint(obligation["target"], text),
        "contract_fingerprint": contract_fingerprint(plan, obligation, contract),
    }
    errors = [field for field, value in expected.items() if record.get(field) != value]
    if rule.construct not in kinds:
        errors.append("obligation construct is absent from current source")
    from Tools.knowledge.rendering import static_render_runtime
    errors.extend(static_render_runtime.validate_render_result(
        record["render_report"], rendering_source(text), bindings, root=root))
    instances = [row for row in record["render_report"].get("constructs", [])
                 if row.get("kind") == rule.construct]
    if record["render_report"].get("target") != obligation["target"]:
        errors.append("render report targets a different page")
    if not instances or any(row.get("acceptance") != rule.acceptance for row in instances):
        errors.append("render report does not cover the registered acceptance")
    if errors:
        raise ValueError("Profile rendering evidence is not current: %s" % "; ".join(errors))
    return record
