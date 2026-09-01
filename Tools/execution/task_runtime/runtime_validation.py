"""Compose Queue runtime validation with persisted Gate evidence validation.

The Queue runtime owns state validation and the metadata Gate runtime owns its
typed evidence predicate.  Neither owner may import the other without forming
a dependency cycle, so this application boundary supplies the predicate
explicitly.  It owns no validation rule of its own.
"""

import Tools.execution.evidence.metadata_gate_runtime as metadata_gate_runtime
from Tools.execution.task_runtime import queue_runtime


def validate_runtime(*args, **kwargs):
    """Run the complete repository consistency pass.

    The metadata Gate predicate has one machine owner.  It is deliberately
    not an injection point on this public composition boundary: accepting a
    caller-supplied predicate would let an ordinary consumer create a second
    interpretation of persisted Gate evidence.
    """
    if "gate_evidence_errors" in kwargs:
        raise TypeError(
            "gate_evidence_errors is owned by metadata_gate_runtime and "
            "cannot be overridden")
    return queue_runtime.runtime.validate_runtime(
        *args,
        gate_evidence_errors=
            metadata_gate_runtime.persisted_property_gate_errors,
        **kwargs,
    )


def require_gate_context_current(context, phase, *, runtime=None):
    """Prove runtime authority and its derived metadata Gate view current."""
    queue_runtime.require_runtime_authority_current(
        context.root, context.authority, phase)
    metadata_gate_runtime.require_context_current(
        context, phase, runtime=runtime)


__all__ = [
    "require_gate_context_current",
    "validate_runtime",
]
