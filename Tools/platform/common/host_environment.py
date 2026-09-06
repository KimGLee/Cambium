"""Mechanical Host observation failures, not governance verdicts or state.

Deliberately not a ValueError/OSError/RuntimeError: an unavailable observation must travel
through evidence validators without being classified as stale or corrupt.
Only an operation/transport boundary may turn it into a Host handoff.
"""

PREPARATION_CAPABILITY_ID = "host-environment-preparation-v1"


def preparation_request(diagnostics):
    """Project known environment failures to the single preparation capability.

    These are references to existing capabilities, not version/acceptance rules.
    An unknown capability is an inspection boundary, never a guessed install.
    """
    rendering = {"static-markdown-render-v1", "rendering-runtime-preparation-v1"}
    capabilities = {row.get("capability_id") for row in diagnostics}
    constructs = sorted({item for row in diagnostics for item in row.get("constructs", ())})
    known = bool(capabilities) and capabilities <= rendering | {PREPARATION_CAPABILITY_ID}
    return {"capability_id": PREPARATION_CAPABILITY_ID,
            "arguments": {"construct": constructs, "rendering": bool(capabilities & rendering),
                          "json": True} if known else None,
            "diagnostics": diagnostics}


class HostEnvironmentUnavailable(Exception):
    """A required observation could not execute; no verdict was obtained."""

    def __init__(self, message, *, capability_id, code, resource=None,
                 constructs=(), remedy="prepare"):
        super().__init__(message)
        self.capability_id = capability_id
        self.code = code
        self.resource = None if resource is None else str(resource)
        self.constructs = tuple(sorted(set(constructs)))
        self.remedy = remedy

    def diagnostic(self):
        return {"code": self.code, "capability_id": self.capability_id,
                "resource": self.resource, "constructs": list(self.constructs),
                "remedy": self.remedy, "message": str(self)}


def preparation_failure(report, error, *, capability_id):
    """Preserve completed steps while reporting the failed preparation boundary."""
    diagnostic = error.diagnostic() if isinstance(error, HostEnvironmentUnavailable) else {
        "code": "host-preparation-failed", "capability_id": capability_id,
        "resource": None, "remedy": "inspect", "message": str(error)}
    status = "invalid" if isinstance(error, (ValueError, TypeError, KeyError)) else "needs-preparation"
    report.update(result=status, findings=[str(error)], diagnostics=[diagnostic])
    return report


__all__ = ["PREPARATION_CAPABILITY_ID", "HostEnvironmentUnavailable", "preparation_failure", "preparation_request"]
