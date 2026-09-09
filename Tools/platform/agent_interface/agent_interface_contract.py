"""Stable machine identity shared by agent-interface producers and consumers.

This is the single machine owner for the generated interface-projection
envelope and for the environment names that bind a Host, the MCP transport,
and child Tool processes.  It contains no IO, generation, transport, or
governance judgment; those responsibilities remain with its consumers.
"""

PROJECTION_ARTIFACT_KIND = "agent-interface-projection"
PROJECTION_SCHEMA_VERSION = 6
CLI_CONTRACT_SCHEMA_VERSION = 11
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

# Process observations, not evidence acceptance or publication facts.
PROCESS_VERDICTS = {0: "clean", 1: "failed_or_unreliable", 2: "hold"}
UNREADABLE_VERDICT = "unreadable"


def nullable_argument(action):
    """Declare null as the existing omitted-argument None, never a new value.

    Call next to the actual argparse declaration. Optional/default None alone
    does not opt a parameter into this representation.
    """
    if (not action.option_strings or action.required or
            action.default is not None or action.nargs == 0):
        raise ValueError("nullable argument requires an optional None default")
    action.cambium_null_encoding = "omit"
    return action


def argument_expression(action):
    """Capture and validate only explicitly declared expression metadata."""
    encoding = getattr(action, "cambium_null_encoding", None)
    if encoding is None:
        return {}
    if encoding != "omit":
        raise ValueError("unknown argument null encoding")
    nullable_argument(action)
    return {"null_encoding": encoding}


def argument_schema(argument, path_capability=None):
    """One mechanical projection for CLI encoding, MCP and Runner bindings."""
    scalar_type = {"bool": "boolean", "float": "number", "int": "integer",
                   "str": "string"}.get(argument.get("type"), "string")
    scalar = {"type": scalar_type}
    if argument.get("choices"):
        scalar["enum"] = list(argument["choices"])
    action, nargs = argument.get("action"), argument.get("nargs")
    sequence = (action in ("append", "append_const", "extend") or
                nargs in ("*", "+") or type(nargs) is int and nargs >= 1)
    if action == "count":
        schema = {"type": "integer", "minimum": 0}
    elif nargs == 0:
        schema = {"type": "boolean"}
    elif sequence:
        schema = {"type": "array", "items": scalar}
        if nargs == "+" or (nargs != "*" and
                            (argument.get("required") or
                             argument.get("default") != [])):
            schema["minItems"] = 1
        if type(nargs) is int and action not in ("append", "extend"):
            schema.update(minItems=nargs, maxItems=nargs)
    else:
        schema = scalar
    meta = {"action": action,
            "option_strings": list(argument.get("option_strings") or [])}
    if nargs is not None:
        meta["nargs"] = nargs
    if argument.get("type") is not None:
        meta["type"] = argument["type"]
    expression = argument.get("expression") or {}
    if expression:
        if (expression != {"null_encoding": "omit"} or
                argument.get("required") or argument.get("default") is not None or
                not meta["option_strings"] or nargs == 0):
            raise ValueError("invalid compiled argument expression")
        meta.update(expression)
        schema["type"] = [schema["type"], "null"]
        if "enum" in schema:
            schema["enum"].append(None)
    if sequence and argument.get("default") == []:
        meta["empty_encoding"] = "omit"
    schema["x-cambium-cli"] = meta
    if argument.get("help"):
        schema["description"] = argument["help"]
    if (argument.get("default") is not None and
            argument.get("default_type") != "argparse.SUPPRESS"):
        schema["default"] = argument["default"]
    if path_capability is not None:
        schema[PATH_EXTENSION_KEY] = {
            "access": path_capability["access"],
            "consumption": path_capability["consumption"],
            "constraint": path_capability["constraint"],
            "value": path_capability["value"],
            "suffixes": list(path_capability["suffixes"]),
            "active_when_any": list(path_capability["active_when_any"]),
            "inactive_when_any": list(path_capability["inactive_when_any"]),
        }
    return schema


def validate_input(schema, value, *, field="input"):
    """Validate the small structural vocabulary emitted by these bindings.

    Domain predicates and authorization remain in their existing owners. No
    coercion, defaults, filesystem access or caller values in error messages.
    """
    declared = schema.get("type")
    types = declared if isinstance(declared, list) else [declared]
    actual = ("null" if value is None else "boolean" if type(value) is bool else
              "integer" if type(value) is int else "number" if type(value) is float else
              "string" if isinstance(value, str) else "array" if isinstance(value, list) else
              "object" if isinstance(value, dict) else "unsupported")
    if actual not in types and not (actual == "integer" and "number" in types):
        raise ValueError("%s requires %s" % (field, "/".join(types)))
    if "enum" in schema and not any(type(value) is type(item) and value == item
                                    for item in schema["enum"]):
        raise ValueError("%s is outside the declared choices" % field)
    if actual == "object":
        properties = schema.get("properties", {})
        missing = sorted(set(schema.get("required", [])) - set(value))
        if missing:
            raise ValueError("%s misses required fields: %s" % (field, ", ".join(missing)))
        for key, item in value.items():
            child = properties.get(key, schema.get("additionalProperties", False))
            if not isinstance(key, str) or child is False:
                raise ValueError("%s has an unsupported field" % field)
            if isinstance(child, dict):
                validate_input(child, item, field=field + "." + key)
    elif actual == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise ValueError("%s violates declared list cardinality" % field)
        for item in value:
            validate_input(schema["items"], item, field=field + "[]")
    elif actual == "string" and len(value) < schema.get("minLength", 0):
        raise ValueError("%s is shorter than its declared minimum" % field)
    elif actual in ("number", "integer"):
        import math
        if (actual == "number" and not math.isfinite(value)) or value < schema.get("minimum", -float("inf")):
            raise ValueError("%s is outside its numeric bounds" % field)
    return value


def input_binding(tool_record, parameters, *, required=(), shapes=None,
                  encodings=None, arguments=None, conditions=None):
    """Project an existing route's source-to-parameter binding, not a registry."""
    import hashlib
    import json
    by_name = {row["dest"]: row for row in tool_record["arguments"]}
    properties = {}
    encodings = dict(encodings or {})
    bound = dict(arguments or {})
    required = set(required)
    for source, destination in parameters.items():
        if destination not in by_name or destination in bound:
            raise ValueError("input binding has an absent or machine-owned destination")
        argument = by_name[destination]
        schema = argument_schema(argument)
        if argument.get("help"):
            schema["description"] = argument["help"]
        if source in (shapes or {}):
            schema.update(shapes[source])
        if argument.get("required"):
            required.add(source)
        properties[source] = schema
    if not required.issubset(parameters) or not set(encodings).issubset(parameters):
        raise ValueError("input binding refers to an undeclared source")
    if len(set(parameters.values())) != len(parameters):
        raise ValueError("input binding repeats a destination")
    if any(value not in ("json-items", "key-value-items") for value in encodings.values()):
        raise ValueError("input binding has an undeclared structural encoding")
    result = {"type": "object", "properties": properties,
              "required": sorted(required), "additionalProperties": False,
              "x-cambium-binding": {"tool": tool_record["tool"],
                  "parameters": dict(parameters), "encodings": encodings,
                  "arguments": bound,
                  "source_fingerprint": "sha256:" + hashlib.sha256(json.dumps(
                      tool_record, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()}}
    if conditions:
        result["x-cambium-owner-conditions"] = conditions
    return result


def bind_input(schema, supplied):
    """Admit exposed source fields and encode them without identity overrides."""
    import json
    validate_input(schema, supplied)
    binding = schema["x-cambium-binding"]
    result = dict(binding["arguments"])
    for source, value in supplied.items():
        encoding = binding["encodings"].get(source)
        if encoding == "json-items":
            value = [json.dumps(item, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) for item in value]
        elif encoding == "key-value-items":
            value = [key + "=" + item for key, item in sorted(value.items())]
        result[binding["parameters"][source]] = value
    return result


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
