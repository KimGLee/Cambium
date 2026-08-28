"""Runtime bindings used only by the three incremental-audit producers.

This module does not define an AuditPlan, a substantive-review receipt, or an
AuditReceipt.  Their closed shapes come from the Kernel-owned contract
loaders.  It only freezes the already-admitted adopter runtime and provides
the common compare-and-swap checks needed by the three writers.
"""

from dataclasses import dataclass
import json
import os
import re

import check_queue
import audit_fingerprint
import kblib
import metadata_property_state
import profile_contract
import project_page_state
import runtime_paths


class AuditProducerError(ValueError):
    """A fail-closed producer refusal."""


@dataclass(frozen=True)
class FrozenPage:
    path: str
    page_sha256: str
    semantic_content_fingerprint: str
    snapshot: object


def admitted_runtime(root):
    """Return one successful runtime observation and its opaque authority."""
    canonical = os.path.realpath(os.path.abspath(os.fspath(root)))
    result = check_queue.validate_runtime(canonical)
    errors = result.get("errors") or []
    if errors:
        raise AuditProducerError(
            "runtime is not admitted: %s" % "; ".join(errors[:12]))
    return canonical, result, check_queue.runtime_authority_context(result)


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
    entry = check_queue.current_receipt_catalog(result).get(receipt_id)
    if isinstance(entry, tuple) and len(entry) == 2:
        return entry[1]
    return entry if isinstance(entry, dict) else None


def profile_bindings(result):
    """Project the public Profile binding from the admitted runtime."""
    view = result.get("_profile_authorized_view")
    if not isinstance(view, dict):
        raise AuditProducerError("runtime has no authorized Profile view")
    return check_queue.public_profile_load_evidence(view)


def standards_bindings(result):
    """Project active Standards identity without copying its contract."""
    view = result.get("_active_standards_authorized_view")
    if not isinstance(view, dict):
        raise AuditProducerError("runtime has no authorized Standards view")
    fields = (
        "standards_version", "active_standards_path",
        "active_standards_sha256", "standards_state_revision",
        "upstream_source_ref", "upstream_revision_id",
    )
    values = {field: view.get(field) for field in fields}
    if (not isinstance(values["standards_version"], str) or
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
    check_queue.require_runtime_authority_current(root, authority, phase)
    kwargs = check_queue.runtime_authority_validation_kwargs(authority)
    current = check_queue.validate_runtime(root, **kwargs)
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
        "before_required_queue_sha256": result.get("queue_sha256"),
        "planned_after_required_queue_sha256": result.get("queue_sha256"),
        "before_progress_sha256": result.get("progress_sha256"),
        "planned_after_progress_sha256": result.get("progress_sha256"),
    }
    values.update(check_queue.runtime_authority_lock_fields(authority))
    values.update(extra)
    return values


def profile_projection_fields():
    """Expose the one Profile evidence field set for contract adapters."""
    return tuple(profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS)
