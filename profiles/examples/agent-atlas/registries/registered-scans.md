# Registered Scan Registry

Interface: [Kernel-owned Profile interface](../../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Registered Scan Registry slot

## Scan Registrations

| Stable Scan ID | Activation role | Whole-corpus scope/root | Verifier capability ID | Profile configuration reference or `None` | Candidate predicate/boundary | Judgment Item ID reference |
|---|---|---|---|---|---|---|
| `agent-atlas-interview-residuals` | `K12/09 item 6 — residual-content scan` | Run from the merged in-scope vault root; [the profile-owned scan configuration](../scan-configs/interview-residuals.yaml) requires the registered `Interview Preparation/` root and excludes the control plane plus the exact roots excluded by Profile Scope. | `residual-content-scan-v1` | `profiles/examples/agent-atlas/scan-configs/interview-residuals.yaml` | A Markdown file outside the accepted root is a candidate when it declares `type: interview-card`, uses an explicit Interview Card/answer heading, or contains at least two distinct registered answer-structure headings. The scan is candidate-only; adjudication remains with `Residual-content Disposition`. | `agent-atlas-interview-residual-disposition` |
