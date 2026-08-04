# Registered Scan Registry

Interface: [Registered Scan Registry slot](../../../README.md#registered-scan-registry-slot)

## Scan Registrations

| Stable Scan ID | Activation role | Whole-corpus scope/root | Deterministic verifier command/path | Candidate predicate/boundary | Judgment Item ID reference |
|---|---|---|---|---|---|
| `agent-atlas-interview-residuals` | `K12/09 item 6 — residual-content scan` | Run from the merged in-scope vault root, passed as `.`; [the profile-owned scan configuration](../scan-configs/interview-residuals.yaml) requires the registered `Interview Preparation/` root and excludes the control plane plus the exact roots excluded by Profile Scope. | `python3 Tools/check_residual_content.py . --scan-id agent-atlas-interview-residuals --config profiles/examples/agent-atlas/scan-configs/interview-residuals.yaml --time-limit 55` | A Markdown file outside the accepted root is a candidate when it declares `type: interview-card`, uses an explicit Interview Card/answer heading, or contains at least two distinct registered answer-structure headings. The scan is candidate-only; adjudication remains with `Residual-content Disposition`. | `agent-atlas-interview-residual-disposition` |
