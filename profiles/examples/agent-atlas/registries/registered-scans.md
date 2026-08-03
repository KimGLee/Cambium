# Registered Scan Registry

Interface: [Registered Scan Registry slot](../../../README.md#registered-scan-registry-slot)

## Scan Registrations

| Stable Scan ID | Activation role | Whole-corpus scope/root | Deterministic verifier command/path | Candidate predicate/boundary | Judgment Item ID reference |
|---|---|---|---|---|---|
| `agent-atlas-interview-residuals` | `K12/09 item 6 — residual-content scan` | Run from the merged in-scope vault root, passed as `.`; the verifier fails if the registered `Interview Preparation/` root is absent. That expression root, the Cambium control plane, and the top-level directories excluded by Profile Scope are outside the candidate set. | `python3 profiles/examples/agent-atlas/checks/check_interview_residuals.py . --expression-root "Interview Preparation" --exclude "Archive" --exclude "Knowledge Base Standards" --exclude "Python Algorithm Agent Training" --time-limit 55` | A Markdown file outside the expression root is a candidate when it declares `type: interview-card`, uses an explicit Interview Card/answer heading, or contains a combination of registered answer-structure headings. The scan is candidate-only; adjudication remains with `Residual-content Disposition`. | `agent-atlas-interview-residual-disposition` |
