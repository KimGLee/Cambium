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


def validate_host_handoff(payload):
    """Validate the existing observation handoff without asserting write outcome."""
    required = {"status", "host_environment", "host_preparation"}
    if (not isinstance(payload, dict) or not required <= set(payload) or
            set(payload) - required - {"prior_output"} or
            payload.get("status") != "await-host"):
        raise ValueError("Host handoff requires its exact observation and preparation fields")
    diagnostic = payload["host_environment"]
    fields = {"code", "capability_id", "resource", "constructs", "remedy", "message"}
    if not isinstance(diagnostic, dict) or set(diagnostic) != fields:
        raise ValueError("Host handoff diagnostic has an invalid field set")
    for field in ("code", "capability_id", "remedy", "message"):
        if not isinstance(diagnostic[field], str) or not diagnostic[field]:
            raise ValueError("Host handoff diagnostic %s must be nonempty text" % field)
    resource = diagnostic["resource"]
    if resource is not None and not isinstance(resource, str):
        raise ValueError("Host handoff resource must be text or null")
    constructs = diagnostic["constructs"]
    if (not isinstance(constructs, list) or
            any(not isinstance(item, str) or not item for item in constructs) or
            constructs != sorted(set(constructs))):
        raise ValueError("Host handoff constructs must be sorted unique strings")
    if payload["host_preparation"] != preparation_request([diagnostic]):
        raise ValueError("Host preparation request differs from its diagnostic projection")
    if "prior_output" in payload and not isinstance(payload["prior_output"], str):
        raise ValueError("Host handoff prior output must retain its original text")
    return payload


def host_handoff(diagnostic, *, prior_output=None):
    """Project one failed observation; do not guess whether earlier steps wrote."""
    payload = {"status": "await-host", "host_environment": diagnostic,
               "host_preparation": preparation_request([diagnostic])}
    if prior_output is not None:
        payload["prior_output"] = prior_output
    return validate_host_handoff(payload)


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


__all__ = ["PREPARATION_CAPABILITY_ID", "HostEnvironmentUnavailable", "preparation_failure",
           "preparation_request", "host_handoff", "validate_host_handoff"]
