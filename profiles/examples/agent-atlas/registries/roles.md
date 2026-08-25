# Role Registry

Interface: [Role Registry slot](../../../README.md#role-registry-slot)

## Process Roles

| Kernel role | Bound actor or system ID/name |
|---|---|
| `proposer` | Model-proposal actor |
| `gatekeeper` | Harness-control system |
| `executor` | External-executor actor |
| `stopper` | Human authority |

## Knowledge Host

| Kernel role | Binding |
|---|---|
| `knowledge-host` | Agent Systems Atlas Obsidian vault |
| `knowledge-host UI` | Obsidian desktop UI |

## Metric Traceability Roles

- Applicability: Configured

| Kernel role | Profile field or identifier |
|---|---|
| `task` | `task_id` |
| `dataset` | Immutable Dataset And Sample Manifest identifier |
| `trial` | `trial_id`; at evidence-record level, `run_id` plus `trial_index` |
| `execution runtime` | `system_id` plus the immutable Environment Manifest identifier |
| `grader` | `grader_id` or the Grader Record's pinned implementation/version |
| `aggregation` | Immutable Aggregation Record identifier plus implementation digest |

These bindings apply when Atlas reports evaluated metrics, whether the measurement was produced locally or summarized from an external source. Their target-corpus semantics are owned by `AI Systems Engineering/Evaluation/Evaluation Provenance.md#Core Records`; the profile's Source Policy governs the evidence required for external results.

## Extension Roles

- Registration: Configured

| Role ID | Bound actor or system ID/name | Responsibility |
|---|---|---|
| `interview-reviewer` | Human authority or explicitly delegated qualified reviewer | Judge Interview Card acceptance and authorize promotion to `interview-ready`. |
| `content-reviewer` | Human authority or explicitly delegated qualified reviewer | Judge each manifest page's two-axis content-form and rewrite-disposition evidence before `merge-ready`, including any source-gap disposition. |
