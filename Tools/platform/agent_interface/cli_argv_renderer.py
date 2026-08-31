"""Pure argv rendering from the compiled CLI invocation shape.

This module owns no operation registry and performs no IO.  It translates one
already-selected tool schema plus explicit argument values into argv tokens.
Callers remain responsible for selecting and loading the compiled contract,
choosing an interpreter and entrypoint, and adapting ``ArgvRenderError`` to
their own public error vocabulary.
"""


CLI_EXTENSION_KEY = "x-cambium-cli"
STRUCTURED_OUTPUT_ARGUMENT = "json"
STRUCTURED_OUTPUT_FLAG = "--json"
DEFAULT_SCALAR_TYPE = "string"
JSON_SCALAR_TYPES = {
    "bool": "boolean",
    "float": "number",
    "int": "integer",
    "str": "string",
}
LIST_ACTIONS = frozenset(("append", "append_const", "extend"))
COUNT_ACTIONS = frozenset(("count",))


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
    if declared_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ArgvRenderError(
                "%s is declared integer; %r cannot be rendered onto argv" %
                (name, value))
        return str(value)
    if declared_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ArgvRenderError(
                "%s is declared number; %r cannot be rendered onto argv" %
                (name, value))
        return str(value)
    if not isinstance(value, str):
        raise ArgvRenderError(
            "%s is declared string; %r cannot be rendered onto argv" %
            (name, value))
    return value


def _scalar_type(argument):
    declared = argument.get("type")
    if declared is None:
        return DEFAULT_SCALAR_TYPE
    return JSON_SCALAR_TYPES.get(declared, DEFAULT_SCALAR_TYPE)


def _is_list_valued(argument):
    nargs = argument.get("nargs")
    if argument.get("action") in LIST_ACTIONS:
        return True
    if nargs in ("*", "+"):
        return True
    return isinstance(nargs, int) and not isinstance(nargs, bool) and nargs >= 1


def schema_from_compiled_tool(tool_record):
    """Project the argv-relevant schema from one compiled CLI tool record.

    The projection deliberately contains only fields consumed by
    ``build_argv``.  It does not reproduce MCP descriptions, path
    capabilities, choices, defaults, or any other interface policy.
    """
    properties = {}
    required = []
    for argument in tool_record.get("arguments") or []:
        name = argument["dest"]
        action = argument.get("action")
        nargs = argument.get("nargs")
        if action in COUNT_ACTIONS:
            property_schema = {"type": "integer"}
        elif nargs == 0:
            property_schema = {"type": "boolean"}
        elif _is_list_valued(argument):
            property_schema = {
                "type": "array",
                "items": {"type": _scalar_type(argument)},
            }
        else:
            property_schema = {"type": _scalar_type(argument)}
        meta = {
            "action": action,
            "option_strings": list(argument.get("option_strings") or []),
        }
        if nargs is not None:
            meta["nargs"] = nargs
        if argument.get("type") is not None:
            meta["type"] = argument["type"]
        property_schema[CLI_EXTENSION_KEY] = meta
        properties[name] = property_schema
        if argument.get("required"):
            required.append(name)
    schema = {"properties": properties}
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
        if meta.get("action") == "store_true" or declared_type == "boolean":
            if not isinstance(value, bool):
                raise ArgvRenderError(
                    "%s is a flag; %r cannot be rendered onto argv" %
                    (key, value))
            if value:
                option_tokens.append(flag)
            continue
        if meta.get("action") == "append" or declared_type == "array":
            if not isinstance(value, list):
                raise ArgvRenderError(
                    "%s is a repeatable option; %r cannot be rendered onto "
                    "argv" % (key, value))
            item_type = (properties[key].get("items") or {}).get("type")
            for item in value:
                option_tokens.append(flag)
                option_tokens.append(render_value(key, item_type, item))
            continue
        option_tokens.append(flag)
        option_tokens.append(render_value(key, declared_type, value))

    tail = positional_tokens + option_tokens
    if transport_owned_argument in properties:
        if not isinstance(transport_owned_flag, str) or not \
                transport_owned_flag:
            raise ArgvRenderError(
                "transport-owned argument %s has no argv flag" %
                transport_owned_argument)
        tail.append(transport_owned_flag)
    return tail, ignored
