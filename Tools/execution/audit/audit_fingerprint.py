"""Pure K12/07 fingerprint projections shared by producers and consumers."""

import re

import os
from Tools.platform.repository.repository import repository_source_root
import Tools.execution.audit.audit_plan_contract as _support
from Tools.platform.common.primitives import (
    document_projection, require_trimmed_string, validated_document,
)
import Tools.platform.common.kblib as kblib
from Tools.platform.repository.path_contract import \
    canonical_repository_relative_path


AUDIT_FINGERPRINT_CONTRACT_PATH = (
    "kernel/K12 Quality Assurance/audit-fingerprint-contract.yaml")
_PAGE_ARTIFACT_FIELDS = {
    "protocol_id", "digest_serialization", "page_material_fields",
    "path_binding", "body_binding",
    "frontmatter_normalization", "included_frontmatter_fields",
    "excluded_frontmatter_policy", "absent_included_field_policy",
    "opening_frontmatter_marker", "closing_frontmatter_markers",
    "page_set_protocol_id", "page_set_material_fields",
    "page_set_member_fields", "page_set_order",
}
_SUPPORTED_PAGE_ARTIFACT = {
    "protocol_id": "cambium-page-artifact-v1",
    "digest_serialization": "sha256-prefixed-canonical-json-utf8",
    "page_material_fields": ("protocol_id", "path", "frontmatter", "body"),
    "path_binding": "canonical-repository-relative-posix",
    "body_binding": "exact-bytes-after-frontmatter",
    "frontmatter_normalization": "restricted-yaml-semantic",
    "excluded_frontmatter_policy": "all-other-fields",
    "absent_included_field_policy": "omit",
    "opening_frontmatter_marker": "---",
    "closing_frontmatter_markers": ("---", "..."),
    "page_set_protocol_id": "cambium-page-artifact-set-v1",
    "page_set_material_fields": ("protocol_id", "members"),
    "page_set_member_fields": ("path", "artifact_fingerprint"),
    "page_set_order": "canonical-path-ascending",
}


def validate_contract(document):
    """Validate the sole Kernel page-artifact fingerprint contract."""
    return document_projection(document, _validate_contract)


def _validate_contract(document):
    if not isinstance(document, dict) or set(document) != {
            "schema_version", "contract_id", "semantic_owner",
            "page_artifact_fingerprint"}:
        raise ValueError("audit fingerprint contract fields are not closed")
    if (document.get("schema_version") != 1 or
            document.get("contract_id") != "cambium-audit-fingerprint" or
            document.get("semantic_owner") != "K12/07"):
        raise ValueError("audit fingerprint contract identity is invalid")
    page_artifact = document.get("page_artifact_fingerprint")
    if (not isinstance(page_artifact, dict) or
            set(page_artifact) != _PAGE_ARTIFACT_FIELDS):
        raise ValueError(
            "page artifact fingerprint contract fields are not closed")
    for field in _PAGE_ARTIFACT_FIELDS - {
            "included_frontmatter_fields", "page_material_fields",
            "closing_frontmatter_markers", "page_set_material_fields",
            "page_set_member_fields"}:
        require_trimmed_string(
            page_artifact.get(field),
            "page_artifact_fingerprint.%s" % field)
    included_fields = _support.closed_string_list(
        page_artifact.get("included_frontmatter_fields"),
        "page_artifact_fingerprint.included_frontmatter_fields")
    page_material_fields = _support.closed_string_list(
        page_artifact.get("page_material_fields"),
        "page_artifact_fingerprint.page_material_fields")
    closing_markers = _support.closed_string_list(
        page_artifact.get("closing_frontmatter_markers"),
        "page_artifact_fingerprint.closing_frontmatter_markers")
    page_set_material_fields = _support.closed_string_list(
        page_artifact.get("page_set_material_fields"),
        "page_artifact_fingerprint.page_set_material_fields")
    page_set_member_fields = _support.closed_string_list(
        page_artifact.get("page_set_member_fields"),
        "page_artifact_fingerprint.page_set_member_fields")
    normalized_page_artifact = {
        **page_artifact,
        "included_frontmatter_fields": included_fields,
        "closing_frontmatter_markers": closing_markers,
        "page_material_fields": page_material_fields,
        "page_set_material_fields": page_set_material_fields,
        "page_set_member_fields": page_set_member_fields,
    }
    for field, supported in _SUPPORTED_PAGE_ARTIFACT.items():
        if normalized_page_artifact.get(field) != supported:
            qualifier = " supported ordered closed set" if isinstance(
                supported, tuple) else " supported value"
            raise ValueError(
                "page_artifact_fingerprint.%s must equal its%s" %
                (field, qualifier))
    return {"page_artifact_fingerprint": normalized_page_artifact}


def load_contract(root=None, snapshots=None, *, cache_projection=False):
    """Load the current Kernel-owned page-artifact fingerprint contract."""
    if root is None:
        root = repository_source_root(__file__)
    snapshot = (snapshots or {}).get(AUDIT_FINGERPRINT_CONTRACT_PATH)
    if snapshot is not None:
        text = snapshot.read_text()
    else:
        text = kblib.read_text(os.path.join(
            root, *AUDIT_FINGERPRINT_CONTRACT_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    return validated_document(document, _validate_contract,
                              cache_projection=cache_projection)


def page_artifact_fingerprint_contract(contract=None):
    """Return the validated K12/07 page-artifact protocol projection."""
    contract = contract or _SHIPPED_CONTRACT
    return validate_contract(contract)["page_artifact_fingerprint"]


_SHIPPED_CONTRACT = load_contract(cache_projection=True)


_OBLIGATION_CONTRACT_FIELDS = (
    "owner_kind", "owner_rule_id", "kernel_extension_point", "partition",
    "due_stage", "target", "applicability", "evidence_role",
    "evidence_kind", "dimension", "acceptance_predicate",
    "producer_check", "producer_capability", "producer_gate_id",
    "consumer_gate_id", "fingerprint_binding",
)


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


def _frontmatter_and_body(text, protocol):
    """Parse complete frontmatter while retaining exact post-fence body."""
    if not isinstance(text, str):
        raise TypeError("page text must be a string")
    lines = text.splitlines(keepends=True)
    if (not lines or lines[0].strip() !=
            protocol["opening_frontmatter_marker"]):
        return {}, text
    closing_markers = set(protocol["closing_frontmatter_markers"])
    closing_index = next((
        index for index, line in enumerate(lines[1:], 1)
        if line.strip() in closing_markers
    ), None)
    if closing_index is None:
        raise ValueError("page begins frontmatter but has no closing marker")
    raw_frontmatter = "".join(lines[1:closing_index])
    parsed = kblib.parse_yaml_subset(raw_frontmatter)
    if not isinstance(parsed, dict):
        raise ValueError("page frontmatter must be a mapping")
    return parsed, "".join(lines[closing_index + 1:])


def _page_artifact_material(relative_path, text, protocol):
    relative_path = canonical_repository_relative_path(
        relative_path, "page path")
    frontmatter, body = _frontmatter_and_body(text, protocol)
    included = protocol["included_frontmatter_fields"]
    normalized_frontmatter = {
        field: frontmatter[field]
        for field in included if field in frontmatter
    }
    return {
        "protocol_id": protocol["protocol_id"],
        "path": relative_path,
        "frontmatter": normalized_frontmatter,
        "body": body,
    }


def page_artifact_fingerprint(relative_path, text, *, contract=None):
    """Hash one page under the exact K12/07 artifact projection."""
    protocol = page_artifact_fingerprint_contract(
        contract)
    material = _page_artifact_material(relative_path, text, protocol)
    return kblib.sha256_bytes(kblib.canonical_json_bytes(material))


def page_set_artifact_fingerprint(pages, *, contract=None):
    """Hash a page set in canonical-path order, independent of input order.

    ``pages`` is a list or tuple of ``(repository_relative_path, text)``
    pairs. Duplicate paths are rejected rather than silently coalesced.
    """
    if not isinstance(pages, (list, tuple)):
        raise TypeError("page set must be a list or tuple of (path, text) pairs")
    protocol = page_artifact_fingerprint_contract(
        contract)
    members = []
    paths = []
    for index, pair in enumerate(pages):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(
                "page set member %d must be one (path, text) pair" % index)
        relative_path = canonical_repository_relative_path(
            pair[0], "page path")
        material = _page_artifact_material(relative_path, pair[1], protocol)
        paths.append(relative_path)
        members.append({
            "path": relative_path,
            "artifact_fingerprint": kblib.sha256_bytes(
                kblib.canonical_json_bytes(material)),
        })
    if len(paths) != len(set(paths)):
        raise ValueError("page set must not repeat a canonical page path")
    members.sort(key=lambda member: member["path"])
    material = {
        "protocol_id": protocol["page_set_protocol_id"],
        "members": members,
    }
    return kblib.sha256_bytes(kblib.canonical_json_bytes(material))


def obligation_contract_fingerprint(plan, obligation, *, additional=None):
    """Serialize the K12/07 control state relevant to one obligation."""
    material = {
        "upstream_revision_id": plan["upstream_revision_id"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "obligation": {
            field: obligation.get(field)
            for field in _OBLIGATION_CONTRACT_FIELDS
        },
        "additional": additional or {},
    }
    return kblib.sha256_bytes(kblib.canonical_json_bytes(material))


__all__ = [
    "AUDIT_FINGERPRINT_CONTRACT_PATH", "load_contract", "validate_contract",
    "page_artifact_fingerprint_contract",
    "obligation_contract_fingerprint", "page_artifact_fingerprint",
    "page_set_artifact_fingerprint",
    "sources_sha256",
]
