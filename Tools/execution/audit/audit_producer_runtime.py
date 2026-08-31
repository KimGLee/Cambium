"""Runtime bindings shared by AuditPlan evidence producers.

This module does not define an AuditPlan, a substantive-review receipt, or an
AuditReceipt.  Their closed shapes come from the Kernel-owned contract
loaders.  It only freezes the already-admitted adopter runtime and provides
the common compare-and-swap checks needed by the three writers.
"""

from dataclasses import dataclass
import json
import os
import re

import Tools.execution.task_runtime.queue_runtime.authority as runtime_authority
import Tools.execution.task_runtime.queue_runtime.profile_view as profile_view
import Tools.execution.task_runtime.queue_runtime.receipts as receipt_catalogs
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.execution.audit.audit_fingerprint as audit_fingerprint
import Tools.execution.audit.audit_lifecycle_contract as audit_lifecycle_contract
import Tools.platform.common.kblib as kblib
import Tools.knowledge.metadata.metadata_property_state as metadata_property_state
import Tools.knowledge.metadata.project_page_state as project_page_state
import Tools.execution.task_runtime.runtime_paths as runtime_paths


class AuditProducerError(ValueError):
    """A fail-closed producer refusal."""


def require_nonempty_string(value, label):
    """Return one trimmed producer input or refuse with the shared wording."""
    if not isinstance(value, str) or not value.strip():
        raise AuditProducerError("%s must be a non-empty string" % label)
    return value.strip()


@dataclass(frozen=True)
class FrozenPage:
    path: str
    page_sha256: str
    semantic_content_fingerprint: str
    snapshot: object


def admitted_runtime(root):
    """Return one successful runtime observation and its opaque authority."""
    canonical = os.path.realpath(os.path.abspath(os.fspath(root)))
    result = runtime_validation.validate_runtime(canonical)
    errors = result.get("errors") or []
    if errors:
        raise AuditProducerError(
            "runtime is not admitted: %s" % "; ".join(errors[:12]))
    return canonical, result, runtime_authority.runtime_authority_context(result)


def open_batch(result, batch_id):
    """Resolve exactly one current open Queue item."""
    item = (result.get("items_by_id") or {}).get(batch_id)
    if not isinstance(item, dict):
        raise AuditProducerError("unknown Queue batch %s" % batch_id)
    if item.get("state") != "open":
        raise AuditProducerError(
            "Queue batch %s must be open, found %r" %
            (batch_id, item.get("state")))
    manifest = item.get("manifest")
    if (not isinstance(manifest, list) or not manifest or
            manifest != sorted(manifest) or len(manifest) != len(set(manifest)) or
            any(not isinstance(path, str) or not path for path in manifest)):
        raise AuditProducerError(
            "Queue batch %s manifest must be non-empty, sorted, and unique" %
            batch_id)
    activation_id = item.get("activation_receipt")
    if not isinstance(activation_id, str) or not activation_id:
        raise AuditProducerError(
            "Queue batch %s has no current activation receipt" % batch_id)
    activation = receipt_by_id(result, activation_id)
    if (not isinstance(activation, dict) or
            activation.get("result") != "pass" or
            activation.get("invalidated_by") is not None):
        raise AuditProducerError(
            "Queue batch %s activation receipt is absent, failed, or invalid" %
            batch_id)
    return item, activation


def receipt_by_id(result, receipt_id):
    """Resolve one current hot receipt without interpreting its semantics."""
    entry = receipt_catalogs.current_receipt_catalog(result).get(receipt_id)
    if isinstance(entry, tuple) and len(entry) == 2:
        return entry[1]
    return entry if isinstance(entry, dict) else None


def obligation_attempt_records(result, *, tool=None, plan_id, obligation_id,
                               record_kind=None):
    """Return all hot attempts owned by one producer/plan obligation.

    The current receipt catalog is an authorization view, not an input-
    currentness view.  Callers must therefore pass every matching row to
    ``evidence_attempt_runtime`` rather than selecting the newest row here.
    This helper owns only the repeated catalog-unwrapping and identity filter.
    """
    records = []
    for catalog_id, entry in receipt_catalogs.current_receipt_catalog(
            result).items():
        record = entry[1] if isinstance(entry, tuple) and len(entry) == 2 \
            else entry
        if not isinstance(record, dict):
            continue
        if ((tool is not None and record.get("tool") != tool) or
                record.get("plan_id") != plan_id or
                record.get("obligation_id") != obligation_id or
                (record_kind is not None and
                 record.get("record_kind") != record_kind)):
            continue
        if record.get("receipt_id") != catalog_id:
            raise AuditProducerError(
                "evidence attempt catalog key differs from receipt_id")
        records.append(record)
    return tuple(sorted(records, key=lambda row: row["receipt_id"]))


def validate_obligation_attempt_binding(record, plan, plan_sha256,
                                        obligation):
    """Validate the shared immutable plan/obligation identity of an attempt.

    Record-specific contracts still own their closed fields and predicates.
    This projection only removes the repeated mechanical comparison every
    AuditPlan evidence producer previously performed independently.
    """
    mismatches = audit_lifecycle_contract.attempt_binding_mismatches(
        record, plan, plan_sha256, obligation)
    if mismatches:
        raise AuditProducerError(
            "evidence attempt differs from AuditPlan in: %s" %
            ", ".join(sorted(mismatches)))
    return record


def profile_bindings(result):
    """Project the public Profile binding from the admitted runtime."""
    view = result.get("_profile_authorized_view")
    if not isinstance(view, dict):
        raise AuditProducerError("runtime has no authorized Profile view")
    return profile_view.public_profile_load_evidence(view)


def standards_bindings(result):
    """Project active Standards identity without copying its contract."""
    view = result.get("_active_standards_authorized_view")
    if not isinstance(view, dict):
        raise AuditProducerError("runtime has no authorized Standards view")
    fields = (
        "upstream_revision_id", "active_standards_path",
        "active_standards_sha256", "standards_state_revision",
        "upstream_source_ref", "upstream_revision_id",
    )
    values = {field: view.get(field) for field in fields}
    if (not isinstance(values["upstream_revision_id"], str) or
            not isinstance(values["active_standards_sha256"], str)):
        raise AuditProducerError("active Standards view is incomplete")
    return values


def runtime_state_bindings(result):
    """Return exact canonical state revisions and byte fingerprints."""
    queue = result.get("queue") or {}
    values = {
        "task_id": queue.get("task_id"),
        "queue_revision": queue.get("queue_revision"),
        "queue_state_revision": queue.get("state_revision"),
        "required_queue_sha256": result.get("queue_sha256"),
        "coverage_ledger_sha256": result.get("coverage_sha256"),
        "progress_ledger_sha256": result.get("progress_sha256"),
    }
    if (not isinstance(values["task_id"], str) or not values["task_id"] or
            not all(isinstance(values[field], int) for field in
                    ("queue_revision", "queue_state_revision")) or
            not all(isinstance(values[field], str) for field in
                    ("required_queue_sha256", "coverage_ledger_sha256",
                     "progress_ledger_sha256"))):
        raise AuditProducerError("runtime state binding is incomplete")
    return values


def freeze_manifest_pages(root, result, item):
    """Freeze exact page bytes and the authorized semantic fingerprints."""
    view = result.get("_profile_authorized_view")
    _contract, rules = metadata_property_state.\
        authorized_profile_projection_rules(root, view)
    frozen = []
    for relative in item["manifest"]:
        snapshot = kblib.repository_target_snapshot(
            root, relative, suffixes=(".md", ".MD"), singly_linked=True)
        if not snapshot.exists:
            raise AuditProducerError(
                "batch manifest page does not exist: %s" % relative)
        text = snapshot.read_text()
        frozen.append(FrozenPage(
            path=relative,
            page_sha256=snapshot.sha256,
            semantic_content_fingerprint=
                project_page_state.semantic_content_fingerprint(
                    relative, text, rules),
            snapshot=snapshot,
        ))
    return tuple(frozen)


def frozen_manifest_page(frozen, page):
    """Return the unique frozen manifest member for ``page``, or ``None``.

    This is only the structural lookup shared by audit producers.  Each
    producer retains its own refusal wording because an L review describes
    membership in the open batch while an M/S review describes the frozen
    manifest carried by its AuditPlan.
    """
    matches = [value for value in frozen if value.path == page]
    return matches[0] if len(matches) == 1 else None


def page_records(frozen):
    """Return the serializable projection of frozen page objects."""
    return [{
        "path": page.path,
        "page_sha256": page.page_sha256,
        "semantic_content_fingerprint": page.semantic_content_fingerprint,
    } for page in frozen]


def page_set_sha256(frozen):
    return kblib.sha256_bytes(kblib.canonical_json_bytes(page_records(frozen)))


def page_artifact_fingerprint(page):
    """Project one frozen page through the Kernel-owned K12/07 contract."""
    return audit_fingerprint.page_artifact_fingerprint(
        page.path, page.snapshot.read_text())


def page_set_artifact_fingerprint(frozen):
    """Project a frozen page set through the Kernel-owned K12/07 contract."""
    return audit_fingerprint.page_set_artifact_fingerprint([
        (page.path, page.snapshot.read_text()) for page in frozen
    ])


def sources_sha256(text):
    """Hash the exact authoritative H2 Sources section and no other prose."""
    lines = text.splitlines(keepends=True)
    start = None
    end = len(lines)
    fenced = False
    fence_marker = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        marker = "```" if stripped.startswith("```") else (
            "~~~" if stripped.startswith("~~~") else None)
        if marker is not None:
            if not fenced:
                fenced = True
                fence_marker = marker
            elif marker == fence_marker:
                fenced = False
                fence_marker = None
            continue
        if fenced:
            continue
        match = re.match(
            r"^(#{1,6})\s+(.+?)\s*#*\s*$", line.rstrip("\r\n"))
        if match is None:
            continue
        level = len(match.group(1))
        heading = match.group(2).strip()
        if start is None and level == 2 and heading.casefold() == "sources":
            start = index
            continue
        if start is not None and level <= 2:
            end = index
            break
    material = "" if start is None else "".join(lines[start:end])
    return kblib.sha256_bytes(material)


def obligation_contract_fingerprint(plan, obligation, *, additional=None):
    """Fingerprint the current control state relevant to one obligation.

    K12/07 owns the meaning of ``contract_fingerprint``.  This helper only
    serializes the already-frozen Standards/Profile identity and obligation
    definition so every producer uses one deterministic projection.  It
    intentionally excludes plan and Queue revision identities, allowing a
    receipt to be considered for explicit reuse when its actual contract and
    scope are unchanged.
    """
    return audit_fingerprint.obligation_contract_fingerprint(
        plan, obligation, additional=additional)


def require_pages_current(root, frozen, phase):
    """Reject publication if any retained page identity or byte moved."""
    changed = []
    for page in frozen:
        try:
            current = kblib.repository_target_snapshot(
                root, page.path, suffixes=(".md", ".MD"),
                singly_linked=True)
        except (OSError, ValueError) as exc:
            changed.append("%s (%s)" % (page.path, exc))
            continue
        before = page.snapshot
        if (not current.exists or current.repository_path != before.repository_path or
                current.dev != before.dev or current.ino != before.ino or
                current.mode != before.mode or current.nlink != before.nlink or
                current.size != before.size or
                current.mtime_ns != before.mtime_ns or
                current.ctime_ns != before.ctime_ns or
                current.data != before.data):
            changed.append(page.path)
    if changed:
        raise AuditProducerError(
            "manifest page changed %s: %s" % (phase, ", ".join(changed)))


def require_runtime_current(root, authority, phase):
    """Run the standard primary-authority CAS for one publication phase."""
    runtime_authority.require_runtime_authority_current(
        root, authority, phase)
    kwargs = runtime_authority.runtime_authority_validation_kwargs(authority)
    current = runtime_validation.validate_runtime(root, **kwargs)
    if current.get("errors"):
        raise AuditProducerError(
            "runtime changed %s: %s" %
            (phase, "; ".join(current["errors"][:12])))
    return current


def managed_plan_path(root, relative, *, must_exist=False):
    """Resolve one direct child of the registered AuditPlan namespace."""
    prefix = runtime_paths.AUDIT_PLAN_ROOT
    if (not isinstance(relative, str) or
            os.path.dirname(relative) != prefix or
            not relative.endswith(".yaml")):
        raise AuditProducerError(
            "AuditPlan path must name one YAML file directly under %s/" %
            prefix)
    return kblib.managed_repository_path(
        root, relative, prefix, suffixes=(".yaml",),
        must_exist=must_exist)


def managed_receipt_path(root, relative, *, must_exist=False):
    return kblib.managed_repository_path(
        root, relative, runtime_paths.RECEIPT_ROOT,
        suffixes=(".jsonl",), must_exist=must_exist)


def read_receipt_records(path):
    """Read one JSONL register strictly for resulting-state verification."""
    records = []
    text = kblib.read_text(path)
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (ValueError, json.JSONDecodeError) as exc:
            raise AuditProducerError(
                "receipt register line %d is invalid JSON: %s" %
                (line_number, exc))
        if not isinstance(record, dict):
            raise AuditProducerError(
                "receipt register line %d is not an object" % line_number)
        records.append(record)
    return records


def runtime_lock_metadata(tool, action, result, authority, **extra):
    values = {
        "tool": tool,
        "action": action,
        "before_coverage_sha256": result.get("coverage_sha256"),
        "planned_after_coverage_sha256": result.get("coverage_sha256"),
        "before_queue_sha256": result.get("queue_sha256"),
        "planned_after_queue_sha256": result.get("queue_sha256"),
        "before_progress_sha256": result.get("progress_sha256"),
        "planned_after_progress_sha256": result.get("progress_sha256"),
    }
    values.update(runtime_authority.runtime_authority_lock_fields(authority))
    values.update(extra)
    return values
