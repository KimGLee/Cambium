"""Deterministic CUE projections of existing domain-owned Profile contracts.

These shared contracts also have non-Profile consumers. Their YAML owner remains
authoritative; the generated CUE is a checked projection, never a second
handwritten schema. Source bytes and resulting CUE travel in the same snapshot.
Cross-document identity, filesystem, tightening, and evidence checks remain
with the existing owner evaluator; passing this projection does not prove them.
"""

import argparse
from collections.abc import Mapping
import hashlib
import itertools
import json
import re
from pathlib import Path, PurePosixPath
import sys

from Tools.platform.common import kblib

PROFILE_INTERFACE_SOURCE = "kernel/K00 Standards Control/profile-interface.yaml"
PROFILE_ENCODING_SOURCE = "Tools/governance/profile/profile-encoding.yaml"


def _q(value):
    return json.dumps(value, ensure_ascii=False)


def _enum(values):
    return " | ".join(_q(value) for value in values)


def _record(fields, types=None, optional=()):
    types = types or {}
    return "{" + ", ".join(
        (field if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", field) and field not in {"in", "if", "for", "let"} else _q(field)) + ("?" if field in optional else "") + ": " + types.get(field, "#Text")
        for field in fields
    ) + "}"


def _with_conditions(record, conditions):
    return record[:-1] + "\n" + conditions + "\n}"


def _corpus(contract):
    shape = contract["slot_envelope"]
    inactive = shape["applicability_branches"]["inactive"]
    configured = shape["applicability_branches"]["configured"]
    bindings = _record(shape["artifact_binding_fields"])
    scale = _record(shape["capability_scale_fields"], {
        "rank": "int & >=0", "target_eligible": "bool",
    })
    authority = _record(shape["pass_authority_fields"])
    return """#CorpusPlanning: {
    schema_version: %s
    applicability: {state: %s, reason?: #Text} | {state: %s, reason: #Text}
    artifact_bindings: {...}
    capability_scale: [...%s]
    pass_authority: {...}
    if applicability.state == %s {
        artifact_bindings: %s
        capability_scale: [_, ..._]
        pass_authority: %s
    }
    if applicability.state == %s {
        artifact_bindings: close({})
        capability_scale: []
        pass_authority: close({})
    }
}
""" % (shape["schema_version"], _q(configured), _q(inactive), scale,
         _q(configured), bindings, authority, _q(inactive))


def _structure(contract):
    modes = []
    for mode, spec in contract["role_modes"].items():
        if not isinstance(spec, dict) or "required_fields" not in spec:
            continue
        fields = spec["required_fields"] + spec["optional_fields"]
        types = {"mode": _q(mode)}
        if "generator_capability" in fields:
            types["generator_capability"] = "#Text & =~" + _q("^" + contract["role_modes"]["stable_capability_id_pattern"] + "$")
        modes.append(_record(fields, types, spec["optional_fields"]))
    unit = contract["unit"]
    support = contract["support_layer"]
    entry = _record(unit["entry_fields"], optional=("expected_type",))
    role = "(" + " | ".join(modes) + ")"
    role_fields = _record(unit["role_fields"], {name: "#StructureRole" for name in unit["role_fields"]})
    taxonomy = _record(support["taxonomy"]["fields"], {
        "classes": "[" + _record(support["taxonomy"]["class_fields"]) + ", ..." + _record(support["taxonomy"]["class_fields"]) + "]",
    })
    unit_shape = _record(unit["fields"], {
        "kind": _enum(unit["kinds"]), "entry": entry, "roles": role_fields,
    }, optional=("parent", "global_map_entry"))
    support_shape = _record(support["fields"], {
        "role": _enum(support["roles"]), "layout": _enum(support["layouts"]),
        "entry": entry, "taxonomy": taxonomy, "coverage": "#StructureRole", "bindings": "{...}",
    }, optional=("global_map_entry", "taxonomy"))
    binding_conditions = []
    for name, fields in support["binding_fields_by_role"].items():
        types = {}
        if "index_mode" in fields: types["index_mode"] = _enum(support["source_index_modes"])
        if "readiness_projection" in fields: types["readiness_projection"] = "#StructureRole"
        binding_conditions.append("if role == %s { bindings: %s }" % (_q(name), _record(fields, types)))
    unit_shape = _with_conditions(unit_shape, 'if kind == "domain" {parent?: _|_}\nif kind == "module" {parent: #Text}')
    support_shape = _with_conditions(support_shape, 'if layout == "flat" {taxonomy?: _|_}\nif layout == "grouped" {taxonomy: %s}\n%s' % (taxonomy, "\n".join(binding_conditions)))
    return """#StructureRole: %s
#StructureUnit: %s
#StructureSupport: %s
#StructureRegistry: {
    schema_version: %s
    applicability: {state: "configured"} | {state: "not-applicable", reason: #Text}
    units: [...#StructureUnit]
    support_layers: [...#StructureSupport]
    if applicability.state == "configured" { units: [_, ..._] }
    if applicability.state == "not-applicable" { units: [], support_layers: [] }
}
""" % (role, unit_shape, support_shape, contract["document"]["schema_version"])


def _metadata(contract):
    condition = contract["condition"]
    choices = condition["clause_choice_fields"]
    clause = " | ".join(_record(condition["clause_required_fields"] + [choice], {
        # K08 declares nonempty-list, not string-list. Its evaluator owns
        # condition meaning; this projection must not invent a member type.
        choice: "true" if choice == "absent" else "[_, ..._]",
    }) for choice in choices)
    groups = condition["allowed_group_fields"]
    condition_shape = _record(groups, {name: "[#MetadataClause, ...#MetadataClause]" for name in groups}, optional=groups)
    condition_shape += " & struct.MinFields(%d)" % condition["minimum_groups"]
    definitions = ['import "struct"', "#MetadataClause: " + clause, "#MetadataCondition: " + condition_shape]
    collection_definitions = {}
    for kind, spec in contract["entry_types"].items():
        fields = spec["required_fields"] + spec["optional_fields"]
        types = {"condition": "#MetadataCondition"}
        if "mode" in fields: types["mode"] = _enum(spec.get("allowed_modes", contract["mode_values"]))
        if "shape" in fields: types["shape"] = _enum(contract["shape_values"])
        if "target" in fields: types["target"] = "#Text | [#Text, ...#Text]"
        if "role" in fields: types["role"] = _enum(spec["roles"])
        if "titles" in fields: types["titles"] = "[#Text, ...#Text]"
        if "aliases" in fields: types["aliases"] = "[...#Text]"
        definition = "#Metadata" + "".join(part.title() for part in kind.split("_"))
        shape = _record(fields, types, spec["optional_fields"])
        if "mode" in fields and contract["entry_rules"]["conditional_mode_requires_condition"]:
            shape = _with_conditions(shape, 'if mode == "conditional" {condition: #MetadataCondition}')
        definitions.append(definition + ": " + shape)
        collection_definitions[kind] = definition
    labels = _record(contract["boundary_projection"]["label_keys"], optional=contract["boundary_projection"]["label_keys"])
    metadata_shape = _record(
        contract["document"]["required_fields"] + contract["document"]["optional_fields"], {
            "schema_version": str(contract["document"]["schema_version"]),
            "applicability": "{state: " + _enum(contract["applicability"]["states"]) + "}",
            "applicability_differences": "[..." + collection_definitions["applicability_difference"] + "]",
            "extension_fields": "[..." + collection_definitions["extension_field"] + "]",
            "relationship_extensions": "[..." + collection_definitions["relationship_extension"] + "]",
            "section_roles": "[..." + collection_definitions["section_role"] + "]",
            "boundary_projection": "{labels: " + labels + "}",
        }, contract["document"]["optional_fields"]
    )
    definitions.append("#MetadataContract: " + _with_conditions(metadata_shape, 'if applicability.state == "kernel-defaults" {applicability_differences: [], extension_fields: [], relationship_extensions: [], section_roles: [], boundary_projection?: _|_}'))
    return "\n".join(definitions) + "\n"


def _vocabulary(contract):
    field = contract["vocabulary_field"]
    field_shape = _record(field["required_fields"] + field["optional_fields"], {"values": "[...#Text]"}, field["optional_fields"])
    return """#VocabularyExtensions: {
    schema_version: %s
    frontmatter_extensions: {fields: [...#Text]}
    fields: {[=~%s]: %s}
    volatility_defaults: {[string]: #Text}
}
""" % (contract["document"]["schema_version"], _q("^" + field["field_id_pattern"] + "$"), field_shape)


def _rendering(contract):
    shape = contract["profile_shape"]
    rule = _record(shape["rule_fields"], {"rule_id": "#Text & =~" + _q("^" + shape["identifier_pattern"] + "$")})
    return """#RenderingContract: {
    schema_version: %s
    registration: %s
    rules: [...%s]
    if registration == %s {rules: []}
    if registration == %s {rules: [_, ..._]}
}
""" % (shape["schema_version"], _enum(shape["registration_values"]), rule,
         _q(shape["inactive_registration"]), _q(shape["configured_registration"]))


def _audit_base(contract):
    # Targets are an unordered set in the structured interface. Every accepted
    # combination still comes from one existing owner declaration; duplicates
    # are never an additional combination.
    targets = sorted({
        tuple(order)
        for row in contract["extension_target_mappings"]
        for order in itertools.permutations(row["outputs"])
    })
    return "#AuditEvidenceRole: %s\n#AuditTargets: %s\n" % (
        _enum(contract["evidence_roles"]),
        " | ".join("[" + ", ".join(_q(item) for item in order) + "]" for order in targets),
    )


_PROJECTORS = {
    "cambium-corpus-planning-contract": _corpus,
    "structure-registry-shape-v2": _structure,
    "metadata-contract-shape-v1": _metadata,
    "vocabulary-extensions-shape-v1": _vocabulary,
    "cambium-profile-rendering-contract": _rendering,
    "cambium-audit-dimension-base": _audit_base,
}


def project_profile_schema(source_path, source_bytes):
    """Return exact generated bytes from a bound owner's bytes, without I/O."""
    raw = source_bytes.encode("utf-8") if isinstance(source_bytes, str) else source_bytes
    contract = kblib.parse_yaml_subset(raw.decode("utf-8", errors="strict"))
    if not isinstance(contract, Mapping):
        raise ValueError("Profile shape owner must be an object")
    projector = _PROJECTORS.get(contract.get("contract_id", contract.get("registry_id")))
    if projector is None:
        raise ValueError("unsupported Profile shape owner: %s" % source_path)
    prefix = (
        "package profile\n\n// GENERATED: do not edit this projection.\n"
        "// Semantic owner: %s\n// Source: %s\n// Source SHA256: %s\n"
        "// Projected checks: object fields, scalar/list types, declared enums and applicability shapes.\n"
        "// Owner evaluator still checks identities, graph/reference closure, tightening,\n"
        "// conditional nonempty configuration, external vocabularies and evidence.\n"
        % (contract["semantic_owner"], source_path, hashlib.sha256(raw).hexdigest())
    )
    return (prefix + projector(contract)).encode("utf-8")


def project_profile_document(encoding_bytes, interface_bytes):
    """Project the Tool encoding envelope, referencing Kernel semantic objects."""
    encoding_raw = encoding_bytes.encode("utf-8") if isinstance(encoding_bytes, str) else encoding_bytes
    interface_raw = interface_bytes.encode("utf-8") if isinstance(interface_bytes, str) else interface_bytes
    encoding = kblib.parse_yaml_subset(encoding_raw.decode("utf-8", errors="strict"))
    interface = kblib.parse_yaml_subset(interface_raw.decode("utf-8", errors="strict"))
    definitions = encoding["cue_definitions"]
    complete, draft = definitions["profile"], definitions["draft"]
    semantic = interface["semantic_definition"]
    if any(not isinstance(value, str) or not re.fullmatch(r"#[A-Za-z][A-Za-z0-9_]*", value)
           for value in (complete, draft, semantic)):
        raise ValueError("Profile projection requires safe named CUE definitions")
    version, container = encoding["document_schema_version"], encoding["slot_container"]
    if type(version) is not int or version < 1 or not isinstance(container, str) or not container:
        raise ValueError("Profile encoding requires a positive version and a named slot container")
    return ("""package profile

// GENERATED Tool encoding projection: do not edit this file.
// Encoding owner: %s
// Encoding SHA256: %s
// Semantic interface: %s
// Semantic interface SHA256: %s
// Kernel slot/value domains remain unchanged by this document wrapper.
// Draft input does not supply defaults, confirmation, selection, or adoption.
// Directory identity spelling/equality remain with profile_layout_contract.
#OverrideValue: string | bool | number
%s: {
    schema_version?: %d
    profile_id?: #Text
    execution_default_overrides?: {[string]: #OverrideValue}
    %s?: #SlotFields
}
%s: %s & {
    schema_version: %d
    profile_id: #Text
    %s: %s
}
""" % (PROFILE_ENCODING_SOURCE, hashlib.sha256(encoding_raw).hexdigest(),
         PROFILE_INTERFACE_SOURCE, hashlib.sha256(interface_raw).hexdigest(),
         draft, version, _q(container), complete, draft, version, _q(container), semantic)).encode("utf-8")


def check_profile_schema_projections(encoding, snapshot_sources):
    """Reject stale/edited generated CUE using only the same input snapshot."""
    encoding_raw = snapshot_sources[PROFILE_ENCODING_SOURCE]
    encoding_text = encoding_raw if isinstance(encoding_raw, str) else encoding_raw.decode("utf-8")
    if encoding != kblib.parse_yaml_subset(encoding_text):
        raise ValueError("Profile encoding mapping differs from its bound source")
    for entry in encoding["cue_sources"]:
        source_path = entry.get("projection_of")
        if source_path is None:
            continue
        expected = project_profile_schema(source_path, snapshot_sources[source_path])
        actual = snapshot_sources[entry["path"]]
        actual = actual.encode("utf-8") if isinstance(actual, str) else actual
        if actual != expected:
            raise ValueError("stale Profile schema projection: %s" % entry["path"])
    expected_document = project_profile_document(
        snapshot_sources[PROFILE_ENCODING_SOURCE], snapshot_sources[PROFILE_INTERFACE_SOURCE])
    for path in encoding["encoding_cue_sources"]:
        actual = snapshot_sources[path]
        actual = actual.encode("utf-8") if isinstance(actual, str) else actual
        if actual != expected_document:
            raise ValueError("stale Profile encoding projection: %s" % path)


def _local_projection_path(root, relative):
    """Resolve only declared repository files, never an external/symlink target."""
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or str(path) != relative:
        raise ValueError("non-canonical projection path: %s" % relative)
    target = root
    for part in path.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError("symlink in projection path: %s" % relative)
    return target


def main(argv=None):
    """Check or regenerate only Tool-declared projections of existing owners."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify exact generated bytes without writing")
    mode.add_argument("--write", action="store_true", help="regenerate only declared owner projections")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        encoding_path = _local_projection_path(root, PROFILE_ENCODING_SOURCE)
        encoding_bytes = encoding_path.read_bytes()
        encoding = kblib.parse_yaml_subset(encoding_bytes.decode("utf-8"))
        outputs = {}
        for entry in encoding["cue_sources"]:
            source = entry.get("projection_of")
            if source is None:
                continue
            relative = entry["path"]
            if not relative.startswith("kernel/") or not relative.endswith(".profile-projection.cue"):
                raise ValueError("not a generated Profile projection: %s" % relative)
            if relative in outputs:
                raise ValueError("duplicate Profile projection: %s" % relative)
            target = _local_projection_path(root, relative)
            source_path = _local_projection_path(root, source)
            outputs[relative] = (target, project_profile_schema(source, source_path.read_bytes()))
        interface_bytes = _local_projection_path(root, PROFILE_INTERFACE_SOURCE).read_bytes()
        encoded_document = project_profile_document(encoding_bytes, interface_bytes)
        for relative in encoding["encoding_cue_sources"]:
            if not relative.startswith("Tools/") or not relative.endswith(".cue") or relative in outputs:
                raise ValueError("not a Tool encoding projection: %s" % relative)
            outputs[relative] = (_local_projection_path(root, relative), encoded_document)
        if not outputs:
            raise ValueError("no Profile schema projections declared")
        stale = [name for name, (path, data) in outputs.items() if not path.is_file() or path.read_bytes() != data]
        if args.check and stale:
            raise ValueError("stale Profile schema projections: " + ", ".join(stale))
        if args.write:
            for name in stale:
                path, data = outputs[name]
                path.write_bytes(data)
        print("Profile schema projections: %d checked%s" % (len(outputs), "; %d regenerated" % len(stale) if args.write else ""))
        return 0
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print("Profile schema projection error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
