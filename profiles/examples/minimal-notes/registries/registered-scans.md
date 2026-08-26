# Registered Scan Registry

Interface: [Kernel-owned Profile interface](../../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Registered Scan Registry slot

Keep scan identity, scope, machine configuration, candidate semantics, and the Judgment Item binding in this profile; do not place persistent executable code here. This profile uses the generic matcher with [its own scan configuration](../scan-configs/residual-scan.yaml), filled from the `scan-configs/residual-scan.yaml` scaffold in `profiles/_template/`.

## Scan Registrations

| Stable Scan ID | Activation role | Whole-corpus scope/root | Verifier capability ID | Profile configuration reference or `None` | Candidate predicate/boundary | Judgment Item ID reference |
|---|---|---|---|---|---|---|
| `minimal-notes-scratch-residuals` | `K12/09 item 6 — residual-content scan` | Run from the vault root; the profile-owned configuration accepts `Notes/Daily Log` as the only root where dated-scratch structure belongs. | `residual-content-scan-v1` | `profiles/examples/minimal-notes/scan-configs/residual-scan.yaml` | A Markdown file outside `Notes/Daily Log` is a candidate when it declares `type: daily-log`, carries a `Daily Log Entry` heading, or carries at least two distinct dated-scratch sorting headings. The scan is candidate-only; adjudication belongs to `minimal-notes-scratch-residual-disposition`. | `minimal-notes-scratch-residual-disposition` |
