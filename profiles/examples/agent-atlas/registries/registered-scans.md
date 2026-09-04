# Registered Scan Registry

Kernel owner: K12 Quality Assurance. Common slot identity and table contract are registered in the Kernel Profile interface.

## Scan Registrations

| Stable Scan ID | Activation role | Whole-corpus scope/root | Verifier capability ID | Profile configuration reference or `None` | Candidate predicate/boundary | Judgment Item ID reference |
|---|---|---|---|---|---|---|
| `agent-atlas-residual-content` | `K12/09 item 6 — residual-content scan` | Repository root, excluding control-plane and Profile Scope exclusions | `residual-content-scan-v1` | `profiles/examples/agent-atlas/scan-configs/residual-scan.yaml` | Markdown outside `Interview Preparation` containing registered interview-answer markers is a candidate only. | `agent-atlas-residual-disposition` |
