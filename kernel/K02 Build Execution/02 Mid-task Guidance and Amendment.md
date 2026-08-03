## Navigation

- Parent: [[kernel/K02 Knowledge Base Build Execution Standard|K02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/K02 Build Execution/01 Contract Time and Task State|Contract Time and Task State]].
- Next: [[kernel/K02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]].

## Mid-task Guidance And Contract Amendment

During long-task execution, opinions, corrections, topics, priorities, source leads, format preferences, or stop instructions newly added by the user are collectively called `Guidance Event`s. Guidance Events MUST be preserved, classified, and dispositioned; they cannot rely solely on current context memory, nor be written directly into canonical knowledge without judgment.

An **important Guidance Event** is a message that changes objective, scope, acceptance, priority, or content judgment; the disposition obligations of both this page and [[kernel/K12 Quality Assurance/04 Guidance and Source Review|K12/04]] use this threshold. Pure status inquiries or confirmation messages get a one-line log entry, do not consume a guidance_id, and do not enter the Amendment Log.

### Cumulative Amendment Rule

The latest user instruction has the highest task authority, but by default it modifies only the contract dimensions it explicitly touches:

- Adding a topic does not automatically cancel the original scope.
- Adjusting priority does not automatically lower the original acceptance criteria.
- Expressing a personal opinion does not automatically become a knowledge fact.
- Providing a source lead does not automatically prove the claims in the source.
- Changing a diagram preference does not automatically require rewriting all historical pages.
- Constraints that do not conflict with old requirements remain in effect.

Only when new and old requirements conflict directly on the same dimension does the latest explicit instruction override the old value. When a high-impact ambiguity cannot be reliably resolved from context, mark the relevant guidance `clarification-required`, pause the affected actions, and continue unaffected Required work.

### Guidance Classification

| Guidance Type | Example | Default Route |
|---|---|---|
| Operational control | Pause, stop, run until some time, switch immediately | Update task state or time contract |
| Scope amendment | Add an indexing strategy, a session-state strategy, or a new domain | Update scope version and Coverage Ledger |
| Priority or sequence | Do topic A first, then topic B | Update queue revision |
| Acceptance or quality feedback | The core processing flow is not explained clearly | Trigger a targeted audit; register a gap once confirmed |
| Presentation preference | Change flowcharts to horizontal | Update the current batch constraint; when reusable, evaluate a Standards amendment |
| Knowledge hypothesis | Some topic is a current industry hotspot | Record as a research signal; enter evidence investigation |
| Source lead | Upstream provider A or B has a relevant article | Enter source capture and claim extraction |
| Correction | The current definition, formula, or system chain may be wrong | Assess the propagation scope; interrupt and correct immediately if necessary |
| Project or first-party context | The user describes their own system, metrics, or incidents | Preserve as bounded first-party context; do not generalize into industry fact |
| Governance candidate | From now on no flowchart may sacrifice completeness | Modify the Standards only after explicit user authorization |

The same Guidance Event MAY belong to multiple types at once. For example, "some topic is an industry hotspot and needs to be completed first" is simultaneously a scope amendment, a priority change, and a research signal.

### Intake And Impact Analysis

```text
Receive Guidance
 -> Preserve Meaning
 -> Classify Type
 -> Check Conflict And Authority
 -> Analyze Scope / Dependency / Evidence / Batch Impact
 -> Choose Disposition
 -> Amend And Version The Right Contract
 -> Map To Ledgers And Queue
 -> Acknowledge Interpretation
 -> Execute At A Safe Boundary
 -> Verify And Close
```

Impact analysis checks at least:

- Whether it changes the objective, scope, exclusions, acceptance, time, or Standards.
- Whether it affects the validity of the current batch and content already written.
- Whether it exposes new prerequisites, canonical owners, or cross-module dependencies.
- Whether it requires source intake, external verification, or evidence maturity qualification.
- Whether it changes the Required / optional / deferred disposition.
- Whether it requires re-checking already-closed pages or batches (only when the guidance is a correction and explicitly targets closed objects).
- Whether it changes the Completion Gate or the expected Terminal Audit scope.

### Disposition

Each important guidance MUST be given one explicit disposition:

- `interrupt-now`: immediately save a consistent checkpoint and switch.
- `apply-to-current-batch`: consistent with the current owner and acceptance; can be integrated without expanding the batch boundary.
- `queue-next`: execute immediately after the current smallest acceptable unit completes.
- `queue-by-dependency`: add to the Required Queue; position determined by prerequisite order.
- `research-first`: do source inventory, claim extraction, and gap analysis first.
- `deferred`: postponed; the reason, re-entry condition, and authority MUST be recorded.
- `clarification-required`: high-impact semantics cannot be reliably judged; await user clarification.
- `superseded`: replaced by later explicit guidance, with the replacement relationship preserved.
- `not-applicable`: unrelated to the current contract or already fully covered by existing work; the basis MUST be stated.

`deferred` or `not-applicable` MUST NOT be used to silently drop requirements newly added by the user.

### Safe Switching Policy

By default, switch at the smallest safe boundary rather than leaving inconsistent state in the middle of a file or a verification. Usually first complete the current atomic edit, save the file, and run the necessary local checks, then checkpoint and re-order the queue. Under concurrent execution, interruption and switching are performed by the integrator: locate the affected batches per the Amendment Record's `affected_batches`; unaffected batches are not interrupted.

The following cases MUST interrupt immediately:

- The user explicitly requests an immediate stop, pause, or switch.
- A new constraint forbids continuing the current action.
- The current work contains a safety, data-integrity, or serious factual error.
- New information invalidates the current batch's underlying assumptions.
- Continuing would enlarge an error, overwrite user modifications, or produce irreversible side effects.

The following cases usually do not interrupt immediately:

- Adding a cross-domain topic with no direct dependency on the current batch.
- Only changing subsequent priorities.
- A user hypothesis that requires source research before confirmation.
- Formatting or navigation requirements that can be handled safely after the current atomic operation.

Small additions with the same owner and the same acceptance MAY enter the current batch; new topics that cross owners or systems MUST form an independent vertical slice. Continuously arriving guidance MUST NOT all be stuffed into the current batch, causing unbounded batch expansion.

### Amendment Record

Important Guidance Events MUST enter the Amendment Log of the Progress Ledger. The record includes at least:

```text
guidance_id
received_at
message_reference
raw_guidance_summary
normalized_intent
guidance_types
authority_scope
evidence_role
affected_scope
affected_pages
affected_batches
dependency_impact
conflict_analysis
disposition
contract_version_before / after
scope_version_before / after
queue_revision_before / after
batch_revision_before / after
standards_version_before / after
completion_gate_impact
status
verification_evidence
```

`raw_guidance_summary` SHOULD preserve the original meaning but not copy irrelevant conversation or sensitive information. `normalized_intent` states how the executor understood the requirement. `evidence_role` distinguishes user authority, research signal, source lead, first-party context, and externally verified claim.

`guidance_id` uses a task-local, monotonically increasing, never-reused identifier, e.g. `G-001`, `G-002`. Only then can checkpoints and the Terminal Audit use `last_reconciled_guidance_id` and `guidance_cutoff_id` to establish explicit boundaries.

Recommended guidance status values:

```text
received
 -> classified
 -> mapped
 -> in-progress
 -> verified

classified -> clarification-required
classified / mapped -> deferred
received / classified / mapped -> superseded
```

### Versioning Rules

- `contract_version`: bump when the objective, constraints, acceptance, time, exclusions, or pause policy changes.
- `scope_version`: bump when in-scope domains, Required objects, or coverage disposition change.
- `queue_revision`: bump when only priority and dependency order change.
- `batch_revision`: bump when the current batch's pages, acceptance, or verification plan changes.
- `standards_version`: bump only for a reusable governance rule with explicit user authorization to modify the Standards.

One guidance MAY bump multiple versions. When only a research lead is added and it has not yet been accepted into scope, do not bump the scope version early.

### User-facing Acknowledgement

After receiving important guidance that affects the task, a brief progress update SHOULD state:

- What type it was understood as.
- Which scope, batches, or evidence work it affects.
- Whether it will be applied immediately, switched to after a safe boundary, queued by dependency, or researched first.
- Whether it changes the contract, scope, queue, or Standards version.

When there is no substantive ambiguity, repeated confirmation requests are not needed; but the user must not discover only in the final report that their guidance was deferred or ignored.
