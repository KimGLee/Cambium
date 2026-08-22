"""Minimal stdio MCP server that measures one host's inline-result limit.

It exposes a single tool that returns a result of an exactly requested byte
size with a nonce at the very end.  A host that inlines the whole result puts
the trailing nonce in the model context; a host that truncates or externalizes
does not.  Nothing here touches a corpus: the subject under test is the host
adapter, not Cambium state.
"""

import json
import sys

PROTOCOL = "2025-11-25"
NONCE = "TAILNONCE-9f2c41d7b6e84a03"

TOOL = {
    "name": "emit_sized_payload",
    "description": (
        "Return a payload of exactly `size_bytes` UTF-8 bytes whose final "
        "field is a fixed tail nonce."),
    "inputSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "size_bytes": {"type": "integer",
                           "description": "target payload size in bytes"},
        },
        "required": ["size_bytes"],
    },
}


def build_payload(size_bytes):
    """Return text of close to size_bytes whose last token is the nonce."""
    tail = "\n<<TAIL %s>>" % NONCE
    head = "<<HEAD marker>>\n"
    filler_len = max(0, size_bytes - len(head) - len(tail))
    # Line-broken filler so a host that shows a head-and-tail summary still
    # produces readable evidence of what it dropped.
    line = "0123456789abcdef" * 4 + "\n"
    filler = (line * (filler_len // len(line) + 1))[:filler_len]
    return head + filler + tail


def respond(message_id, result):
    sys.stdout.write(json.dumps(
        {"jsonrpc": "2.0", "id": message_id, "result": result}) + "\n")
    sys.stdout.flush()


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except ValueError:
            continue
        method = message.get("method")
        message_id = message.get("id")
        if method == "initialize":
            respond(message_id, {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "inline-probe", "version": "1.0.0"},
            })
        elif method == "tools/list":
            respond(message_id, {"tools": [TOOL]})
        elif method == "tools/call":
            arguments = message.get("params", {}).get("arguments") or {}
            size = int(arguments.get("size_bytes") or 0)
            text = build_payload(size)
            respond(message_id, {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            })
        elif message_id is not None:
            respond(message_id, {})


if __name__ == "__main__":
    main()
