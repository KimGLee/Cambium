"""Current-contract Task Progress objects used at contract boundaries."""

from Tools.execution.task_runtime.queue_runtime.task_progress import (
    MAINTENANCE_COMPLETION_FIELDS,
)


def maintenance_completion(*, state="pending", **receipt_bindings):
    """Build one closed ``maintenance_completion`` mapping.

    The production contract supplies the closed field set.  The fixture only
    chooses values for a test and therefore cannot drift into a second field
    registry.
    """
    unknown = set(receipt_bindings) - (
        MAINTENANCE_COMPLETION_FIELDS - {"state"}
    )
    if unknown:
        raise ValueError(
            "unknown maintenance completion field(s): %s" %
            ", ".join(sorted(unknown))
        )
    result = {
        field: None for field in MAINTENANCE_COMPLETION_FIELDS
    }
    result["state"] = state
    result.update(receipt_bindings)
    return result
