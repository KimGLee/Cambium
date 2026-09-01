"""Receipt-construction mechanics shared by independent Tool producers."""

import Tools.platform.common.kblib as kblib


def make_gate_receipt(tool, tool_version, gate_id, check, target, result,
                      details, seq, *, receipt_type_id, root=None):
    """Build one ordinary producer receipt with its stable Gate identity."""
    receipt = kblib.make_receipt(
        tool, tool_version, check, target, result, details, seq,
        receipt_type_id=receipt_type_id, root=root)
    receipt["gate_id"] = gate_id
    return receipt


__all__ = ("make_gate_receipt",)
