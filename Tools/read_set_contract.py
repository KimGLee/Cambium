#!/usr/bin/env python3
"""Parse the sole machine authority carried by Cambium Read Sets.

Each ``Read Set/RNN ... Read Set.md`` owns its direct and conditional loading
edges in YAML frontmatter.  Markdown headings, prose, and Wiki Links are never
interpreted as load membership.  The body is therefore free to explain purpose
and non-deterministic trigger meaning without becoming a second declaration.

Selected-Profile supplemental Read Sets use the same edge shape with
``type: profile-read-set`` and a namespaced ``P:<profile>:<route>`` identity.
They are discovered only inside the selected Profile directory; Profile prose
and registry tables never become a second loading declaration.

This module validates and resolves declarations.  It does not select a route,
decide whether a trigger is true, deliver bytes, or record observed runtime
state.
"""

from pathlib import Path
import re

import kblib


SCHEMA_PATH = "Read Set/read-set.schema.yaml"


class ReadSetContractError(ValueError):
    """A Read Set declaration or its canonical schema is invalid."""


def _string_list(value, label, *, nonempty=False):
    if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value):
        raise ReadSetContractError("%s must be an explicit string list" % label)
    if len(value) != len(set(value)):
        raise ReadSetContractError("%s must not repeat values" % label)
    if nonempty and not value:
        raise ReadSetContractError("%s must not be empty" % label)
    return list(value)


def _nonempty_scalar(value, label):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReadSetContractError("%s must be a non-empty string" % label)
    return value


def _directory_from_prefix(value, label):
    prefix = _nonempty_scalar(value, label)
    if (not prefix.endswith("/") or prefix.endswith("//") or
            "\\" in prefix or "\x00" in prefix):
        raise ReadSetContractError("%s must end with one '/'" % label)
    directory = prefix[:-1]
    candidate = Path(directory)
    if (not directory or candidate.is_absolute() or
            ".." in candidate.parts or candidate.as_posix() != directory):
        raise ReadSetContractError(
            "%s must name a canonical repository-relative directory" % label)
    return directory


def _index_name(value, label):
    name = _nonempty_scalar(value, label)
    candidate = Path(name)
    if ("\\" in name or "\x00" in name or candidate.name != name or
            candidate.as_posix() != name or
            candidate.suffix != ".md"):
        raise ReadSetContractError(
            "%s must be one canonical Markdown filename" % label)
    return name


def _safe_relative_path(value, label, *, prefix=None, suffix=None):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReadSetContractError("%s must be a non-empty canonical path" % label)
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ReadSetContractError("%s must stay repository-relative" % label)
    normalized = candidate.as_posix()
    if normalized != value:
        raise ReadSetContractError("%s must use canonical '/' separators" % label)
    if prefix is not None and not value.startswith(prefix):
        raise ReadSetContractError("%s must start with %s" % (label, prefix))
    if suffix is not None and not value.endswith(suffix):
        raise ReadSetContractError("%s must end with %s" % (label, suffix))
    return value


def load_schema(root):
    """Load and validate the one repository-backed Read Set schema."""
    try:
        path = kblib.repository_path(
            root, SCHEMA_PATH, must_exist=True, reject_symlink=True)
        text = kblib.read_text(path)
        schema = kblib.parse_yaml_subset(text)
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        raise ReadSetContractError(
            "%s is unsafe or invalid: %s" % (SCHEMA_PATH, exc))
    if not isinstance(schema, dict):
        raise ReadSetContractError("%s must be a mapping" % SCHEMA_PATH)
    required = {
        "schema_version", "document_type", "profile_document_type",
        "path_prefix", "index_name", "route_id_pattern",
        "profile_route_id_pattern", "trigger_id_pattern", "phase_fields",
        "phases", "edge_kinds", "body_sections", "document_fields",
        "edge_fields",
    }
    if set(schema) != required:
        raise ReadSetContractError(
            "%s fields differ from the canonical closed shape; missing=%s extra=%s"
            % (SCHEMA_PATH, sorted(required - set(schema)),
               sorted(set(schema) - required)))
    if schema.get("schema_version") != 1:
        raise ReadSetContractError("unsupported Read Set schema_version")
    for field in ("document_type", "profile_document_type"):
        schema[field] = _nonempty_scalar(
            schema.get(field), "%s.%s" % (SCHEMA_PATH, field))
    if schema["document_type"] == schema["profile_document_type"]:
        raise ReadSetContractError(
            "%s document types must remain distinct" % SCHEMA_PATH)
    schema["directory"] = _directory_from_prefix(
        schema.get("path_prefix"), "%s.path_prefix" % SCHEMA_PATH)
    schema["index_name"] = _index_name(
        schema.get("index_name"), "%s.index_name" % SCHEMA_PATH)
    schema["index_path"] = schema["path_prefix"] + schema["index_name"]
    for key in ("phase_fields", "edge_kinds", "body_sections",
                "document_fields", "edge_fields"):
        schema[key] = _string_list(schema.get(key), "%s.%s" % (SCHEMA_PATH, key),
                                   nonempty=True)
    phases = schema.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ReadSetContractError("%s.phases must be a non-empty list" %
                                   SCHEMA_PATH)
    phase_ids = []
    normalized_phases = []
    expected_phase_keys = set(schema["phase_fields"])
    for index, phase in enumerate(phases):
        label = "%s.phases[%d]" % (SCHEMA_PATH, index)
        if not isinstance(phase, dict) or set(phase) != expected_phase_keys:
            actual = set(phase) if isinstance(phase, dict) else set()
            raise ReadSetContractError(
                "%s fields differ from phase_fields; missing=%s extra=%s" %
                (label, sorted(expected_phase_keys - actual),
                 sorted(actual - expected_phase_keys)))
        phase_id = phase.get("phase_id")
        trigger = phase.get("trigger")
        if not isinstance(phase_id, str) or not phase_id:
            raise ReadSetContractError("%s phase_id must be non-empty" % label)
        if phase_id in phase_ids:
            raise ReadSetContractError("%s repeats phase_id %s" %
                                       (SCHEMA_PATH, phase_id))
        if not isinstance(trigger, str) or not trigger.strip():
            raise ReadSetContractError("%s trigger must be non-empty" % label)
        for field in ("conditional", "standard"):
            if not isinstance(phase.get(field), bool):
                raise ReadSetContractError("%s %s must be boolean" %
                                           (label, field))
        phase_ids.append(phase_id)
        normalized_phases.append(dict(phase))
    schema["phases"] = normalized_phases
    schema["phase_ids"] = phase_ids
    try:
        re.compile(schema.get("route_id_pattern") + r"\Z")
        re.compile(schema.get("profile_route_id_pattern") + r"\Z")
        re.compile(schema.get("trigger_id_pattern") + r"\Z")
    except (TypeError, re.error) as exc:
        raise ReadSetContractError("Read Set schema regex is invalid: %s" % exc)
    return schema


def _parse_declaration(text, relative, schema, *, document_type,
                       route_id_pattern, dependency_patterns,
                       require_filename_identity):
    """Validate the shared machine declaration shape for one Read Set."""
    body_headings = []
    for _line_number, line in kblib.markdown_authority_lines(text or ""):
        heading = kblib.markdown_atx_heading(line)
        if heading is not None and heading[0] == 2:
            body_headings.append(heading[1])
    if body_headings != schema["body_sections"]:
        raise ReadSetContractError(
            "%s body sections must be exactly %s" %
            (relative, schema["body_sections"]))
    raw = kblib.extract_frontmatter(text or "")
    if raw is None:
        raise ReadSetContractError("%s has no YAML frontmatter" % relative)
    try:
        value = kblib.parse_yaml_subset(raw)
    except (ValueError, kblib.YamlSubsetError) as exc:
        raise ReadSetContractError("%s frontmatter is invalid: %s" %
                                   (relative, exc))
    if not isinstance(value, dict):
        raise ReadSetContractError("%s frontmatter must be a mapping" % relative)
    expected_fields = set(schema["document_fields"])
    if set(value) != expected_fields:
        raise ReadSetContractError(
            "%s declaration fields differ from the schema; missing=%s extra=%s"
            % (relative, sorted(expected_fields - set(value)),
               sorted(set(value) - expected_fields)))
    if value.get("type") != document_type:
        raise ReadSetContractError("%s must declare type: %s" %
                                   (relative, document_type))
    if value.get("schema_version") != schema["schema_version"]:
        raise ReadSetContractError("%s uses an unsupported schema_version" % relative)
    route_id = value.get("route_id")
    if not isinstance(route_id, str) or not re.fullmatch(
            route_id_pattern, route_id):
        raise ReadSetContractError("%s has invalid route_id %r" %
                                   (relative, route_id))
    if (require_filename_identity and
            not Path(relative).name.startswith(route_id + " ")):
        raise ReadSetContractError(
            "%s filename must start with route_id %s" % (relative, route_id))
    activation_phase = value.get("activation_phase")
    if activation_phase not in schema["phase_ids"]:
        raise ReadSetContractError("%s has invalid activation_phase %r" %
                                   (relative, activation_phase))
    if not isinstance(value.get("narrowable"), bool):
        raise ReadSetContractError("%s narrowable must be boolean" % relative)

    edges = value.get("load_edges")
    if not isinstance(edges, list) or not edges:
        raise ReadSetContractError("%s load_edges must be a non-empty list" % relative)
    expected_edge_fields = set(schema["edge_fields"])
    edge_ids = set()
    normalized_edges = []
    for index, edge in enumerate(edges):
        label = "%s load_edges[%d]" % (relative, index)
        if not isinstance(edge, dict) or set(edge) != expected_edge_fields:
            actual = set(edge) if isinstance(edge, dict) else set()
            raise ReadSetContractError(
                "%s fields differ from the schema; missing=%s extra=%s" %
                (label, sorted(expected_edge_fields - actual),
                 sorted(actual - expected_edge_fields)))
        edge_id = edge.get("edge_id")
        trigger_id = edge.get("trigger_id")
        for field, identifier in (("edge_id", edge_id),
                                  ("trigger_id", trigger_id)):
            if not isinstance(identifier, str) or not re.fullmatch(
                    schema["trigger_id_pattern"], identifier):
                raise ReadSetContractError("%s %s is invalid: %r" %
                                           (label, field, identifier))
        if edge_id in edge_ids:
            raise ReadSetContractError("%s repeats edge_id %s" %
                                       (relative, edge_id))
        edge_ids.add(edge_id)
        kind = edge.get("kind")
        phase_id = edge.get("phase_id")
        if kind not in schema["edge_kinds"]:
            raise ReadSetContractError("%s has invalid kind %r" % (label, kind))
        if phase_id not in schema["phase_ids"]:
            raise ReadSetContractError("%s has invalid phase_id %r" %
                                       (label, phase_id))
        targets = _string_list(edge.get("targets"), "%s targets" % label)
        for target in targets:
            _safe_relative_path(target, "%s target" % label)
            if Path(target).suffix not in (".md", ".yaml", ".json"):
                raise ReadSetContractError(
                    "%s target %r must be Markdown or a machine contract" %
                    (label, target))
        read_sets = _string_list(edge.get("read_sets"),
                                 "%s read_sets" % label)
        for dependency in read_sets:
            if not any(re.fullmatch(pattern, dependency)
                       for pattern in dependency_patterns):
                raise ReadSetContractError(
                    "%s dependency %r is not a route identity" %
                    (label, dependency))
            if dependency == route_id:
                raise ReadSetContractError("%s must not depend on itself" % label)
        if not targets and not read_sets:
            raise ReadSetContractError(
                "%s must declare at least one target or Read Set edge" % label)
        normalized_edges.append({
            "edge_id": edge_id,
            "kind": kind,
            "phase_id": phase_id,
            "trigger_id": trigger_id,
            "targets": targets,
            "read_sets": read_sets,
        })
    if not any(edge["kind"] == "required" and
               edge["phase_id"] == activation_phase
               for edge in normalized_edges):
        raise ReadSetContractError(
            "%s activation_phase %s has no required load edge" %
            (relative, activation_phase))
    return {
        "type": value["type"],
        "schema_version": value["schema_version"],
        "route_id": route_id,
        "activation_phase": activation_phase,
        "narrowable": value["narrowable"],
        "load_edges": normalized_edges,
    }


def parse_declaration(text, relative, schema):
    """Return one validated top-level Read Set declaration."""
    prefix = schema["path_prefix"]
    _safe_relative_path(relative, "Read Set path", prefix=prefix, suffix=".md")
    if Path(relative).name == schema["index_name"]:
        raise ReadSetContractError("the generated Read Set Index is not a Read Set")
    return _parse_declaration(
        text, relative, schema,
        document_type=schema["document_type"],
        route_id_pattern=schema["route_id_pattern"],
        dependency_patterns=(schema["route_id_pattern"],),
        require_filename_identity=True,
    )


def parse_profile_declaration(text, relative, schema, profile_directory,
                              *, profile_id=None):
    """Return one selected-Profile supplemental Read Set declaration."""
    _safe_relative_path(profile_directory, "selected Profile directory")
    prefix = profile_directory.rstrip("/") + "/"
    _safe_relative_path(
        relative, "Profile Read Set path", prefix=prefix, suffix=".md")
    declaration = _parse_declaration(
        text, relative, schema,
        document_type=schema["profile_document_type"],
        route_id_pattern=schema["profile_route_id_pattern"],
        dependency_patterns=(schema["route_id_pattern"],
                             schema["profile_route_id_pattern"]),
        require_filename_identity=False,
    )
    if (profile_id is not None and
            not declaration["route_id"].startswith("P:%s:" % profile_id)):
        raise ReadSetContractError(
            "%s route_id %s does not belong to selected Profile %s" %
            (relative, declaration["route_id"], profile_id))
    return declaration


def load_declaration(root, relative, schema=None):
    """Load one safe UTF-8 Read Set and return its declaration and bytes."""
    schema = schema or load_schema(root)
    try:
        path = kblib.repository_path(
            root, relative, must_exist=True, reject_symlink=True)
        text = kblib.read_text(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReadSetContractError("%s is unsafe or unreadable: %s" %
                                   (relative, exc))
    return parse_declaration(text, relative, schema), text


def discover_profile(root, selected_profile_manifest):
    """Return machine supplemental declarations inside one selected Profile.

    The manifest supplies the Profile identity and directory boundary.  Only
    files whose own frontmatter declares ``type: profile-read-set`` enter the
    registry; tables, headings, Wiki Links, and other prose are ignored.
    """
    schema = load_schema(root)
    _safe_relative_path(
        selected_profile_manifest, "selected Profile manifest", suffix=".md")
    try:
        manifest_path = kblib.repository_path(
            root, selected_profile_manifest, must_exist=True,
            reject_symlink=True)
        manifest_text = kblib.read_text(manifest_path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReadSetContractError(
            "selected Profile manifest is unsafe or unreadable: %s" % exc)
    profile_directory = Path(selected_profile_manifest).parent.as_posix()
    directory_name = Path(profile_directory).name
    profile_id, identity_errors = kblib.profile_identity(
        manifest_text, directory_name)
    if identity_errors or not profile_id:
        details = "; ".join(error[1] for error in identity_errors)
        raise ReadSetContractError(
            "selected Profile identity is invalid: %s" %
            (details or "missing profile_id"))
    directory = Path(root).resolve() / profile_directory
    if not directory.is_dir() or directory.is_symlink():
        raise ReadSetContractError(
            "selected Profile directory is missing or unsafe")
    result = {}
    for path in sorted(directory.rglob("*.md")):
        relative = path.relative_to(Path(root).resolve()).as_posix()
        try:
            safe_path = kblib.repository_path(
                root, relative, must_exist=True, reject_symlink=True)
            text = kblib.read_text(safe_path)
        except (OSError, UnicodeError, ValueError):
            continue
        if kblib.read_set_document_type(text) != schema["profile_document_type"]:
            continue
        declaration = parse_profile_declaration(
            text, relative, schema, profile_directory,
            profile_id=profile_id)
        route_id = declaration["route_id"]
        if route_id in result:
            raise ReadSetContractError(
                "more than one Profile Read Set declares %s" % route_id)
        result[route_id] = {
            "route_id": route_id,
            "path": relative,
            "text": text,
            "declaration": declaration,
        }
    return result


def discover(root, schema=None):
    """Return ``route_id -> record`` from declarations, never from an Index."""
    schema = schema or load_schema(root)
    directory = Path(root).resolve() / schema["directory"]
    if not directory.is_dir() or directory.is_symlink():
        raise ReadSetContractError("canonical Read Set directory is missing or unsafe")
    result = {}
    paths = sorted(path for path in directory.glob("*.md")
                   if path.name != schema["index_name"])
    if not paths:
        raise ReadSetContractError("canonical Read Set directory has no declarations")
    for path in paths:
        relative = path.relative_to(Path(root).resolve()).as_posix()
        try:
            text = kblib.read_text(path)
        except (OSError, UnicodeError) as exc:
            raise ReadSetContractError("%s is unreadable: %s" % (relative, exc))
        declaration = parse_declaration(text, relative, schema)
        route_id = declaration["route_id"]
        if route_id in result:
            raise ReadSetContractError("more than one Read Set declares %s" % route_id)
        result[route_id] = {
            "route_id": route_id,
            "path": relative,
            "text": text,
            "declaration": declaration,
        }
    for route_id, record in result.items():
        for target in targets(record["declaration"]):
            try:
                kblib.repository_path(
                    root, target, must_exist=True, reject_symlink=True)
            except (OSError, ValueError) as exc:
                raise ReadSetContractError(
                    "%s declares unsafe or missing target %s: %s" %
                    (record["path"], target, exc))
        for edge in record["declaration"]["load_edges"]:
            missing = sorted(set(edge["read_sets"]) - set(result))
            if missing:
                raise ReadSetContractError(
                    "%s edge %s references unknown Read Set(s): %s" %
                    (record["path"], edge["edge_id"], ", ".join(missing)))
    return result


def targets(declaration, *, kinds=None):
    """Return unique declared target paths for the requested edge kinds."""
    allowed = set(kinds) if kinds is not None else None
    values = set()
    for edge in declaration.get("load_edges", []):
        if allowed is None or edge.get("kind") in allowed:
            values.update(edge.get("targets", []))
    return sorted(values)


def dependencies(declaration, *, kinds=None):
    """Return unique direct Read Set IDs for the requested edge kinds."""
    allowed = set(kinds) if kinds is not None else None
    values = set()
    for edge in declaration.get("load_edges", []):
        if allowed is None or edge.get("kind") in allowed:
            values.update(edge.get("read_sets", []))
    return sorted(values)


def readback_edges(declaration):
    """Return the declared conditional read-back edges in declaration order."""
    return [dict(edge) for edge in declaration.get("load_edges", [])
            if edge.get("kind") == "read-back"]
