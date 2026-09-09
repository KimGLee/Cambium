"""Pure argv rendering from the compiled CLI invocation shape.

This module owns no operation registry and performs no IO.  It translates one
already-selected tool schema plus explicit argument values into argv tokens.
Callers remain responsible for selecting and loading the compiled contract,
choosing an interpreter and entrypoint, and adapting ``ArgvRenderError`` to
their own public error vocabulary.
"""

from Tools.platform.agent_interface import agent_interface_contract


CLI_EXTENSION_KEY = "x-cambium-cli"
STRUCTURED_OUTPUT_ARGUMENT = "json"
STRUCTURED_OUTPUT_FLAG = "--json"


class ArgvRenderError(ValueError):
    """The supplied values cannot be represented by the declared CLI."""

    def __init__(self, message, data=None):
        super().__init__(message)
        self.message = message
        self.data = data


def cli_metadata(property_schema):
    """Return the compiled CLI metadata carried by one property schema."""
    meta = property_schema.get(CLI_EXTENSION_KEY)
    return meta if isinstance(meta, dict) else {}


def option_flag(option_strings):
    """Choose the declared long option spelling when one exists."""
    for candidate in option_strings:
        if candidate.startswith("--"):
            return candidate
    return option_strings[0]


def positional_order(schema):
    """Return positional destinations in their compiled declaration order."""
    properties = schema["properties"]
    positionals = [
        key for key in sorted(properties)
        if not cli_metadata(properties[key]).get("option_strings")
    ]
    required = [
        key for key in schema.get("required", [])
        if key in positionals
    ]
    return required + [key for key in positionals if key not in required]


def render_value(name, declared_type, value):
    """Render one typed value as one argv token."""
    try:
        agent_interface_contract.validate_input({"type": declared_type}, value, field=name)
    except ValueError as exc:
        raise ArgvRenderError(str(exc), {"field": name, "reason": "invalid-type",
                                        "expected": declared_type}) from exc
    if declared_type == "integer":
        return str(value)
    if declared_type == "number":
        return str(value)
    return value


def _option_value(flag, value):
    # Option-looking strings are values, not a second option. No shell or
    # sentinel escaping is involved; this is argparse's own value spelling.
    return [flag + "=" + value] if value.startswith("-") else [flag, value]


def schema_from_compiled_tool(tool_record):
    """Project one complete invocation schema from a compiled CLI tool record.

    It shares mechanical expression, choices and cardinality with MCP and
    Runner, including effective defaults and declared path admission metadata.
    It does not define path capabilities or domain acceptance policy.
    """
    properties = {}
    required = []
    path_capabilities = {item["argument"]: item
                         for item in (tool_record.get("agent_interface") or {}).get(
                             "path_arguments", [])}
    for argument in tool_record.get("arguments") or []:
        name = argument["dest"]
        properties[name] = agent_interface_contract.argument_schema(
            argument, path_capability=path_capabilities.get(name))
        if argument.get("required"):
            required.append(name)
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def build_argv(tool_name, schema, arguments, *,
               transport_owned_argument=None, transport_owned_flag=None):
    """Return ``(argv_tail, ignored_transport_arguments)``.

    Positionals follow the compiled declaration order; options use a stable
    destination order.  When a transport owns an argument such as ``json``,
    a caller-supplied value is ignored and reported, while the transport flag
    is appended whenever the selected tool declares that argument.
    """
    properties = schema["properties"]
    undeclared = [key for key in sorted(arguments) if key not in properties]
    if undeclared:
        raise ArgvRenderError(
            "%s does not declare %s" %
            (tool_name, ", ".join(undeclared)),
            {"tool": tool_name, "undeclared": undeclared})

    missing = sorted(set(schema.get("required", [])) - set(arguments))
    if missing:
        raise ArgvRenderError("%s misses required arguments: %s" %
                              (tool_name, ", ".join(missing)),
                              {"tool": tool_name, "reason": "missing-required", "fields": missing})
    for key, value in arguments.items():
        if key == transport_owned_argument:
            continue
        try:
            agent_interface_contract.validate_input(properties[key], value, field=key)
        except ValueError as exc:
            raise ArgvRenderError(str(exc), {"tool": tool_name, "field": key,
                                  "reason": "unrepresentable-input",
                                  "expected": properties[key]}) from exc

    ignored = []
    positional_tokens = []
    missing_before_supplied = None
    for key in positional_order(schema):
        if key not in arguments:
            if missing_before_supplied is None:
                missing_before_supplied = key
            continue
        if missing_before_supplied is not None:
            raise ArgvRenderError(
                "%s takes %s before %s; %s was supplied without it, and no "
                "argv can carry that" %
                (tool_name, missing_before_supplied, key, key),
                {"tool": tool_name,
                 "missing": missing_before_supplied,
                 "supplied": key})
        positional_tokens.append(
            render_value(key, properties[key].get("type"), arguments[key]))

    option_tokens = []
    for key in sorted(arguments):
        meta = cli_metadata(properties[key])
        option_strings = meta.get("option_strings") or []
        if not option_strings:
            continue
        if key == transport_owned_argument:
            ignored.append(key)
            continue
        flag = option_flag(option_strings)
        value = arguments[key]
        declared_type = properties[key].get("type")
        if value is None:
            if meta.get("null_encoding") != "omit":
                raise ArgvRenderError("%s has no null encoding" % key,
                                      {"field": key, "reason": "null-not-expressible"})
            continue
        if isinstance(declared_type, list):
            declared_type = next(item for item in declared_type if item != "null")
        if meta.get("action") == "count":
            option_tokens.extend([flag] * value)
            continue
        if meta.get("action") == "store_true" or declared_type == "boolean":
            if value:
                option_tokens.append(flag)
            continue
        if meta.get("action") == "append" or declared_type == "array":
            item_type = (properties[key].get("items") or {}).get("type")
            nargs = meta.get("nargs")
            if not value:
                if nargs == "*":
                    option_tokens.append(flag)
                elif meta.get("empty_encoding") != "omit":
                    raise ArgvRenderError("%s has no empty-list encoding" % key,
                                          {"field": key, "reason": "empty-not-expressible"})
                continue
            if meta.get("action") == "extend" and nargs in ("*", "+"):
                for item in value:
                    option_tokens.extend(_option_value(flag, render_value(key, item_type, item)))
                continue
            if (meta.get("action") != "append" and nargs in ("*", "+")) or (type(nargs) is int and nargs > 0):
                option_tokens.append(flag)
                option_tokens.extend(render_value(key, item_type, item) for item in value)
                continue
            for item in value:
                option_tokens.extend(_option_value(flag, render_value(key, item_type, item)))
            continue
        option_tokens.extend(_option_value(flag, render_value(key, declared_type, value)))

    tail = positional_tokens + option_tokens
    if transport_owned_argument in properties:
        if not isinstance(transport_owned_flag, str) or not \
                transport_owned_flag:
            raise ArgvRenderError(
                "transport-owned argument %s has no argv flag" %
                transport_owned_argument)
        tail.append(transport_owned_flag)
    return tail, ignored
