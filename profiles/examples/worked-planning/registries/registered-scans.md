# Registered Scan Registry

Interface: [Registered Scan Registry slot](../../../README.md#registered-scan-registry-slot)

Keep scan identity, scope, machine configuration, candidate semantics, and the Judgment Item binding in this profile; do not place persistent executable code here. This profile uses the generic matcher with [its own scan configuration](../scan-configs/residual-scan.yaml), filled from the `scan-configs/residual-scan.yaml` scaffold in `profiles/_template/`.

## Scan Registrations

| Stable Scan ID | Activation role | Whole-corpus scope/root | Deterministic verifier command/path | Candidate predicate/boundary | Judgment Item ID reference |
|---|---|---|---|---|---|
| `worked-planning-case-residuals` | `K12/09 item 6 — residual-content scan` | Run from the vault root, passed as `.`; the profile-owned configuration accepts the case layer as the only root where service-case structure belongs and excludes the control plane. | `python3 Tools/check_residual_content.py . --scan-id worked-planning-case-residuals --config profiles/examples/worked-planning/scan-configs/residual-scan.yaml --time-limit 55` | A Markdown file outside the case layer is a candidate when it declares `type: service-case`, carries a `Service Case Log` heading, or carries at least two distinct case-only structure headings. The scan is candidate-only; adjudication belongs to `worked-planning-case-residual-disposition`. | `worked-planning-case-residual-disposition` |
