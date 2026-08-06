# Registered Scan Registry

Interface: [Registered Scan Registry slot](../../README.md#registered-scan-registry-slot)

Keep scan identity, scope, machine configuration, candidate semantics, and the Judgment Item binding in this profile; do not place persistent executable code here. If the generic matcher is sufficient, fill [the profile-owned scan configuration](../scan-configs/residual-scan.yaml) — already copied into this template from [the residual scan config template](../../../Tools/schemas/residual_scan_config.template.yaml) — and bind `Tools/check_residual_content.py` below with the same Stable Scan ID passed through `--scan-id`. Keep that file at `scan-configs/<scan-name>.yaml` inside this profile; a `--config` path outside the filled profile folder configures someone else's scan.

## Scan Registrations

| Stable Scan ID | Activation role | Whole-corpus scope/root | Deterministic verifier command/path | Candidate predicate/boundary | Judgment Item ID reference |
|---|---|---|---|---|---|
| TODO(profile) | `K12/09 item 6 — residual-content scan` | TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) |

Copy the row for an additional scan and replace its activation role.
