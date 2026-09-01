"""Pure K12/07 fingerprint projections shared by producers and consumers."""

import Tools.execution.audit.audit_receipt_contract as audit_receipt_contract
import Tools.platform.common.kblib as kblib
from Tools.platform.repository.path_contract import \
    canonical_repository_relative_path


_OBLIGATION_CONTRACT_FIELDS = (
    "owner_kind", "owner_rule_id", "kernel_extension_point", "partition",
    "due_stage", "target", "applicability", "evidence_role",
    "evidence_kind", "dimension", "acceptance_predicate",
    "producer_check", "producer_capability", "producer_gate_id",
    "consumer_gate_id", "fingerprint_binding",
)


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
    protocol = audit_receipt_contract.page_artifact_fingerprint_contract(
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
    protocol = audit_receipt_contract.page_artifact_fingerprint_contract(
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
    "obligation_contract_fingerprint", "page_artifact_fingerprint",
    "page_set_artifact_fingerprint",
]
