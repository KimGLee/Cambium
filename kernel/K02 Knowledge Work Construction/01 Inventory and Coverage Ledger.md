## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Next: [[kernel/K02 Knowledge Work Construction/02 Coverage Reconciliation|Coverage Reconciliation]].

## Phase 1: Inventory

Build an inventory of the existing knowledge base:

- File path.
- Note type.
- Domain.
- Depth class.
- Priority.
- Canonical owner.
- Authoring status.
- Profile extension status.
- Coverage disposition.
- Missing sections.
- Existing aliases and incoming links.
- Expression Layer migration target.
- Source type and evidence maturity, for source-driven pages.
- Existing Source Notes, Research Synthesis, and unsupported claims.
- Rendering mode: `source-only`, `deterministic-static`, `targeted-visual-exception`, `expanded-ui`, or `temporal-recording`; the latter three MUST be associated with an objective trigger and an unresolved question.
- Deferred reason, re-entry condition, and next batch.
- Assigned batch and the current Queue manifest projection.
- Originating guidance IDs and amendment version.
- Last audited, last reviewed, and last verified.
- The latest valid `receipt_id` for each quality dimension, artifact/dependency fingerprint, review due, and invalidation state; mark `invalidated-evidence` when an old task cannot reconstruct them.

The inventory MUST read the exclusion list from the `Excluded Scope` role of the selected `Profile Scope`; concrete instance paths MUST NOT be hard-coded in the kernel.

The inventory MUST form a persistent, queryable Coverage Ledger; it cannot exist only in transient analysis or in the executor's memory. The Coverage Ledger MAY be split by domain, but it MUST have one summary entry point and satisfy:

- Every in-scope Markdown file has exactly one record.
- Knowledge objects not yet created but belonging to Required coverage also have records.
- File system counts, the excluded scope, and Ledger summary counts can be reconciled.
- Legacy pages without metadata default to `authoring_status: unassessed` and cannot be treated as drafted merely because the file exists.
- Every unfinished Required item has an explicit `next_batch`.
- Every `deferred` and `excluded` item has a reason and a re-entry condition or scope basis.

The Coverage Ledger is the authoritative record of page/object-level coverage. Its object-side `batch` / `next_batch` projection MUST equal the frozen manifests in the canonical [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue]]; the Queue owns batch lifecycle, while the Progress Ledger owns only whole-task state and accepted Queue references.

The Ledger also carries top-level `batch_specs` as explicit Queue-compiler proposal inputs: one entry per proposed batch, with family, order hint, source route, execution mode, dependencies, confirmation requirement, and the explicit null/null or path/hash Work Spec pair defined by K13/08. These inputs do not own accepted order or lifecycle. They remain separate from page records so a historical `batch` and a different `next_batch` successor can have different configurations without rewriting closed history.

## Machine-readable Ledger

The canonical form of the Coverage Ledger is YAML; the schema is at `Tools/schemas/coverage_ledger.template.yaml`, and the runtime path is `.cambium/state/coverage_ledger.yaml`. Only the restricted subset syntax declared in the template header comment is allowed. A markdown prose view is optional, derived from the YAML, and not a basis for reconciliation; reconciliation and the Terminal Audit recognize only the YAML form. When resuming a task, load the YAML Ledger directly instead of re-reading the prose view.
