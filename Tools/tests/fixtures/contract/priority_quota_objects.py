"""Minimal current Profile forms for the optional priority-quota contract."""


NONE_PRIORITY_QUOTA_RUBRIC = """## Priority Quota

- Registration: None
"""

CONFIGURED_PRIORITY_QUOTA_RUBRIC = """## Priority Quota

- Registration: Configured

| Class | Maximum corpus share | Rationale |
|---|---|---|
| `P0` | `20%` | instance-specific core ceiling |
| `P1` | `30%` | instance-specific supporting ceiling |
"""


__all__ = [
    "CONFIGURED_PRIORITY_QUOTA_RUBRIC",
    "NONE_PRIORITY_QUOTA_RUBRIC",
]
