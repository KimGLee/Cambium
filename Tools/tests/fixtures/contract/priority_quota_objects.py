"""Minimal typed inputs to the Kernel-owned optional quota policy."""

NONE_PRIORITY_QUOTA_RUBRIC = {
    "priority_quota": {"mode": "none", "items": []},
}

CONFIGURED_PRIORITY_QUOTA_RUBRIC = {
    "priority_quota": {"mode": "configured", "items": [
        {"priority": "P0", "maximum_share": 0.2,
         "rationale": "instance-specific core ceiling"},
        {"priority": "P1", "maximum_share": 0.3,
         "rationale": "instance-specific supporting ceiling"},
    ]},
}

__all__ = [
    "CONFIGURED_PRIORITY_QUOTA_RUBRIC",
    "NONE_PRIORITY_QUOTA_RUBRIC",
]
