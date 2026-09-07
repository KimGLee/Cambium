"""Load the host-neutral agent interface policy and its shared transports.

This module owns only the engineering shape of
``Tools/agent-interface-policy.yaml``.  CLI argument closure remains with
``compile_cli_contract``; the transport rows here are the single machine
declaration consumed by Host rendering and navigation projections.
"""

import os
import re

import Tools.platform.common.kblib as kblib
from Tools.platform.agent_interface import agent_interface_contract


POLICY_PATH = "Tools/agent-interface-policy.yaml"
SCHEMA_VERSION = 7
ARTIFACT = "agent-interface-policy"
TOP_LEVEL_KEYS = frozenset((
    "schema_version", "artifact", "host_transports", "output_contracts",
    "consumption_defaults", "path_defaults", "path_overrides",
    "path_activation_overrides", "tools",
))
HOST_TRANSPORT_KEYS = frozenset((
    "transport_id", "protocol", "mode", "host_exposure", "module", "path",
    "server_name", "command",
))
STABLE_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
MODULE_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
SERVER_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class AgentInterfacePolicyError(ValueError):
    """The interface policy cannot be consumed without inference."""


def _nonempty_string(value):
    return isinstance(value, str) and bool(value) and value == value.strip()


def _validate_host_transports(document):
    rows = document.get("host_transports")
    if not isinstance(rows, list) or not rows:
        raise AgentInterfacePolicyError(
            "%s host_transports must be a non-empty list" % POLICY_PATH)
    found = set()
    for index, row in enumerate(rows):
        target = "host_transports[%d]" % index
        if not isinstance(row, dict) or set(row) != HOST_TRANSPORT_KEYS:
            raise AgentInterfacePolicyError(
                "%s %s must carry exactly %s" % (
                    POLICY_PATH, target,
                    ", ".join(sorted(HOST_TRANSPORT_KEYS))))
        transport_id = row.get("transport_id")
        module = row.get("module")
        if not isinstance(transport_id, str) or \
                STABLE_ID_RE.fullmatch(transport_id) is None or \
                transport_id in found:
            raise AgentInterfacePolicyError(
                "%s %s has an invalid or duplicate transport_id" % (
                    POLICY_PATH, target))
        found.add(transport_id)
        if row.get("protocol") != "mcp" or row.get("mode") != "stdio" or \
                row.get("host_exposure") != "shared-bridge":
            raise AgentInterfacePolicyError(
                "%s %s must declare the supported mcp/stdio/shared-bridge "
                "transport" % (POLICY_PATH, target))
        if not isinstance(module, str) or MODULE_RE.fullmatch(module) is None:
            raise AgentInterfacePolicyError(
                "%s %s.module must be one top-level Python module" % (
                    POLICY_PATH, target))
        if row.get("path") != "Tools/%s.py" % module:
            raise AgentInterfacePolicyError(
                "%s %s.path must be Tools/%s.py" % (
                    POLICY_PATH, target, module))
        if not isinstance(row.get("server_name"), str) or \
                SERVER_NAME_RE.fullmatch(row["server_name"]) is None:
            raise AgentInterfacePolicyError(
                "%s %s.server_name is not a stable shared Host name" % (
                    POLICY_PATH, target))
        if not _nonempty_string(row.get("command")):
            raise AgentInterfacePolicyError(
                "%s %s.command must be one non-empty string" % (
                    POLICY_PATH, target))
    if len(rows) != 1:
        raise AgentInterfacePolicyError(
            "%s must declare exactly one supported shared Host transport" %
            POLICY_PATH)


def load_policy(repo_root):
    """Return ``(document, raw_bytes)`` after validating the shared envelope."""
    root = os.path.realpath(os.path.abspath(os.fspath(repo_root)))
    path = os.path.join(root, *POLICY_PATH.split("/"))
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise AgentInterfacePolicyError(
            "cannot read %s: %s" % (POLICY_PATH, exc)) from exc
    try:
        document = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except (UnicodeError, kblib.YamlSubsetError) as exc:
        raise AgentInterfacePolicyError(
            "cannot parse %s: %s" % (POLICY_PATH, exc)) from exc
    if not isinstance(document, dict) or \
            document.get("artifact") != ARTIFACT or \
            document.get("schema_version") != SCHEMA_VERSION:
        raise AgentInterfacePolicyError(
            "%s must be %s schema_version %d" % (
                POLICY_PATH, ARTIFACT, SCHEMA_VERSION))
    if set(document) != TOP_LEVEL_KEYS:
        raise AgentInterfacePolicyError(
            "%s must carry exactly %s" % (
                POLICY_PATH, ", ".join(sorted(TOP_LEVEL_KEYS))))
    _validate_host_transports(document)
    contracts = document.get("output_contracts")
    if not isinstance(contracts, dict) or not contracts:
        raise AgentInterfacePolicyError("output_contracts must be a non-empty map")
    previous = []
    for identity, contract in contracts.items():
        if not isinstance(identity, str) or STABLE_ID_RE.fullmatch(identity) is None:
            raise AgentInterfacePolicyError("output contract ID must be stable")
        try:
            agent_interface_contract.validate_output_contract(contract)
        except ValueError as exc:
            raise AgentInterfacePolicyError("output contract %s: %s" % (identity, exc)) from exc
        if contract in previous:
            raise AgentInterfacePolicyError("duplicate output contract: %s" % identity)
        previous.append(contract)
    referenced = set()
    for row in document.get("tools") or []:
        identity = row.get("output") if isinstance(row, dict) else None
        if not isinstance(identity, str) or identity not in contracts:
            raise AgentInterfacePolicyError("each tool must reference one declared output contract")
        referenced.add(identity)
    if referenced != set(contracts):
        raise AgentInterfacePolicyError("unused output contracts: %s" % ", ".join(sorted(set(contracts) - referenced)))
    return document, raw


def host_transports(repo_root):
    """Return the validated Host transport declarations in stable order."""
    document, _raw = load_policy(repo_root)
    return tuple(
        dict(row) for row in sorted(
            document["host_transports"],
            key=lambda value: value["transport_id"]))


def shared_host_transport(repo_root, protocol="mcp"):
    """Return the sole shared Host bridge for ``protocol``."""
    matches = [
        row for row in host_transports(repo_root)
        if row["protocol"] == protocol and
        row["host_exposure"] == "shared-bridge"
    ]
    if len(matches) != 1:
        raise AgentInterfacePolicyError(
            "%s must declare exactly one shared %s Host transport" % (
                POLICY_PATH, protocol))
    return matches[0]
