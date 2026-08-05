## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|Task State and Transition Rules]].
- Next: [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching|Guidance Disposition and Safe Switching]].

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
| Priority or sequence | Do topic A first, then topic B | Update approved ordering and Queue structure |
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
