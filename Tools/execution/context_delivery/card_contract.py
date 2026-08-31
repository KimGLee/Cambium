#!/usr/bin/env python3
"""Load and project the repository's serialized-Card engineering contract.

``Tools/schemas/card.schema.yaml`` is the single machine source for the Card
directory, generated-index location, document discriminator, generation mode,
field lists, and identifier shapes used by repository tooling.  It describes
the serialized form; it does not own Card governance semantics or checklist
meaning.  This module validates the closed machine shape and derives safe
repository-relative layout paths.  It does not discover Cards, judge curated
content, calculate review hashes, generate navigation, or expose a command-line
interface.
"""

from pathlib import Path
import re

import Tools.platform.common.kblib as kblib


SCHEMA_PATH = "Tools/schemas/card.schema.yaml"


class CardContractError(ValueError):
    """The Card schema or a Card consumer input is structurally invalid."""


def string_list(value, label, *, nonempty=False):
    """Validate a unique explicit string list under the Card contract."""
    if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value):
        raise CardContractError("%s must be an explicit string list" % label)
    if len(value) != len(set(value)):
        raise CardContractError("%s must not repeat values" % label)
    if nonempty and not value:
        raise CardContractError("%s must not be empty" % label)
    return list(value)


def _nonempty_scalar(value, label):
    if not isinstance(value, str) or not value or value != value.strip():
        raise CardContractError("%s must be a non-empty string" % label)
    return value


def _directory_from_prefix(value, label):
    prefix = _nonempty_scalar(value, label)
    if (not prefix.endswith("/") or prefix.endswith("//") or
            "\\" in prefix or "\x00" in prefix):
        raise CardContractError("%s must end with one '/'" % label)
    directory = prefix[:-1]
    candidate = Path(directory)
    if (not directory or candidate.is_absolute() or
            ".." in candidate.parts or candidate.as_posix() != directory):
        raise CardContractError(
            "%s must name a canonical repository-relative directory" % label)
    return directory


def _index_name(value, label):
    name = _nonempty_scalar(value, label)
    candidate = Path(name)
    if ("\\" in name or "\x00" in name or candidate.name != name or
            candidate.as_posix() != name or
            candidate.suffix != ".md"):
        raise CardContractError(
            "%s must be one canonical Markdown filename" % label)
    return name


def load_schema(root):
    """Return the validated Card schema plus its derived layout projection."""
    try:
        path = kblib.repository_path(
            root, SCHEMA_PATH, must_exist=True, reject_symlink=True)
        value = kblib.parse_yaml_subset(kblib.read_text(path))
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        raise CardContractError("%s is unsafe or invalid: %s" %
                                (SCHEMA_PATH, exc))
    expected = {
        "schema_version", "document_type", "generation_mode", "path_prefix",
        "index_name", "route_id_pattern", "hash_pattern", "document_fields",
        "body_sections",
    }
    if not isinstance(value, dict) or set(value) != expected:
        actual = set(value) if isinstance(value, dict) else set()
        raise CardContractError(
            "%s fields differ from the canonical closed shape; missing=%s extra=%s"
            % (SCHEMA_PATH, sorted(expected - actual),
               sorted(actual - expected)))
    if value.get("schema_version") != 1:
        raise CardContractError("unsupported Card schema_version")

    for field in ("document_type", "generation_mode"):
        value[field] = _nonempty_scalar(
            value.get(field), "%s.%s" % (SCHEMA_PATH, field))
    value["directory"] = _directory_from_prefix(
        value.get("path_prefix"), "%s.path_prefix" % SCHEMA_PATH)
    value["index_name"] = _index_name(
        value.get("index_name"), "%s.index_name" % SCHEMA_PATH)
    value["index_path"] = value["path_prefix"] + value["index_name"]

    for field in ("document_fields", "body_sections"):
        value[field] = string_list(
            value.get(field), "%s.%s" % (SCHEMA_PATH, field),
            nonempty=True)
    try:
        value["route_id_re"] = re.compile(
            _nonempty_scalar(value.get("route_id_pattern"),
                             "%s.route_id_pattern" % SCHEMA_PATH) + r"\Z")
        value["hash_re"] = re.compile(
            _nonempty_scalar(value.get("hash_pattern"),
                             "%s.hash_pattern" % SCHEMA_PATH) + r"\Z")
    except re.error as exc:
        raise CardContractError("Card schema regex is invalid: %s" % exc)
    return value
