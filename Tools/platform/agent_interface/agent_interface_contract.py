"""Stable machine identity shared by agent-interface producers and consumers.

This is the single machine owner for the generated interface-projection
envelope and for the environment names that bind a Host, the MCP transport,
and child Tool processes.  It contains no IO, generation, transport, or
governance judgment; those responsibilities remain with its consumers.
"""

PROJECTION_ARTIFACT_KIND = "agent-interface-projection"
PROJECTION_SCHEMA_VERSION = 5
MCP_FORM = "mcp"

PATH_EXTENSION_KEY = "x-cambium-path"
WORKSPACE_EXTENSION_KEY = "x-cambium-workspace"
OUTPUT_EXTENSION_KEY = "x-cambium-output"
HOST_BOUNDARY_EXTENSION_KEY = "x-cambium-host-environment-boundary"

SOURCE_DISTRIBUTION_TARGET = "source-distribution"
CARRIED_RUNTIME_TARGET = "carried-runtime"

WORKSPACE_ENV = "CAMBIUM_WORKSPACE_ROOT"
EXECUTION_CONTEXT_ENV = "CAMBIUM_EXECUTION_CONTEXT_ID"
INTERFACE_SOURCE_HASH_ENV = "CAMBIUM_INTERFACE_SOURCE_HASH"
INTERFACE_PROJECTION_ENV = "CAMBIUM_INTERFACE_PROJECTION"
PATH_CAPABILITIES_ENV = "CAMBIUM_PATH_CAPABILITIES"
PATH_CAPABILITIES_ACK_ENV = "CAMBIUM_PATH_CAPABILITIES_ACK_FD"
WORKSPACE_FD_ENV = "CAMBIUM_WORKSPACE_FD"


def validate_output_contract(contract):
    """Validate one transport output declaration, without business judgment."""
    keys = {
        "mode", "result_contract", "json_argument", "json_value",
        "json_inactive_when_any", "json_types", "required_keys",
        "empty_exit_codes", "empty_success_disabled_by",
    }
    if not isinstance(contract, dict) or set(contract) != keys:
        raise ValueError(
            "output contract must carry exactly " + ", ".join(sorted(keys)))
    mode = contract["mode"]
    if contract["result_contract"] not in ("tool-payload", "receipt-publication"):
        raise ValueError("output result_contract is not declared")
    if contract["result_contract"] == "receipt-publication" and mode not in ("always-json", "json-option"):
        raise ValueError("receipt-publication results require JSON output")
    if mode not in ("always-json", "json-option", "text"):
        raise ValueError("output mode is not declared")
    if mode == "json-option":
        if not isinstance(contract["json_argument"], str) or not contract["json_argument"]:
            raise ValueError("json-option output requires a named argument")
        if not isinstance(contract["json_value"], (str, bool)):
            raise ValueError("json-option output requires a scalar selector value")
    elif contract["json_argument"] is not None or contract["json_value"] is not None:
        raise ValueError("only json-option output may select an argument")
    inactive = contract["json_inactive_when_any"]
    if (not isinstance(inactive, list) or
            any(not isinstance(value, str) or not value for value in inactive) or
            len(inactive) != len(set(inactive)) or
            (inactive and mode != "json-option")):
        raise ValueError(
            "JSON inactive modes must be unique boolean arguments of json-option output")
    types = contract["json_types"]
    required = contract["required_keys"]
    empty = contract["empty_exit_codes"]
    if (not isinstance(types, list) or
            any(value not in ("object", "array") for value in types) or
            len(types) != len(set(types))):
        raise ValueError("output json_types must be unique object/array shapes")
    if (mode == "text") != (not types):
        raise ValueError("JSON output requires a shape; text must not declare one")
    if (not isinstance(required, list) or
            any(not isinstance(value, str) or not value for value in required) or
            len(required) != len(set(required))):
        raise ValueError("output required_keys must be unique non-empty strings")
    if required and "object" not in types:
        raise ValueError("output required_keys requires the object shape")
    if (not isinstance(empty, list) or
            any(type(value) is not int or value not in (0, 1, 2) for value in empty) or
            len(empty) != len(set(empty))):
        raise ValueError("output empty_exit_codes must be unique declared process codes")
    disabled = contract["empty_success_disabled_by"]
    if (not isinstance(disabled, list) or
            any(not isinstance(value, str) or not value for value in disabled) or
            len(disabled) != len(set(disabled)) or
            (disabled and (mode == "text" or 0 not in empty))):
        raise ValueError(
            "empty success conditions must name unique boolean arguments "
            "of an output contract that permits empty exit 0")
    return contract


def decode_output(contract, stdout, exit_code, arguments):
    """Observe declared stdout shape; preserve payload and raw process code.

    This validates only transport readability. Receipt schemas, publication
    facts, business verdicts and evidence acceptance remain with their owners.
    """
    import json

    validate_output_contract(contract)
    selected = contract["mode"] == "always-json" or (
        contract["mode"] == "json-option" and
        arguments.get(contract["json_argument"]) == contract["json_value"] and
        not any(arguments.get(flag) is True
                for flag in contract["json_inactive_when_any"]))
    result = {"stdout_parse": "not_requested", "output_reliable": True}
    if not selected:
        return result
    try:
        text = stdout.decode("utf-8")
        if not text.strip():
            result["stdout_parse"] = "empty"
            if exit_code not in contract["empty_exit_codes"]:
                raise ValueError(
                    "declared JSON output is empty for exit code %s" % exit_code)
            if exit_code == 0 and any(
                    arguments.get(flag) is True
                    for flag in contract["empty_success_disabled_by"]):
                raise ValueError(
                    "successful write mode requires declared JSON output")
            return result
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise ValueError("stdout is not JSON: %s" % exc) from exc
        shape = ("object" if isinstance(payload, dict)
                 else "array" if isinstance(payload, list) else None)
        if shape not in contract["json_types"]:
            raise ValueError(
                "JSON output shape is not one of %s" % contract["json_types"])
        if isinstance(payload, dict):
            missing = set(contract["required_keys"]) - set(payload)
            if missing:
                raise ValueError(
                    "JSON output lacks required keys: %s" %
                    ", ".join(sorted(missing)))
    except (UnicodeError, ValueError) as exc:
        result.update(stdout_parse="unparseable", output_reliable=False,
                      stdout_parse_error=str(exc))
        return result
    result.update(stdout_parse="parsed", stdout_json=payload)
    return result
