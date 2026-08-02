## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]].
- Next: [[kernel/00 Standards Control/10 Batch Execution Checklist|Batch Execution Checklist]].

## Purpose

This module owns the standing constraint list a long-running task operates under without being told again: the snapshot form of defaults whose detailed rules are held by the domain modules. It is read once at task start, and it is the target of the Protected Defaults compression in [[kernel/00 Standards Overview|Standards Overview]]. It states what is in force; when two statements conflict, precedence is resolved by [[kernel/00 Standards Control/06 Completion Precedence and Task Contract#Standard Precedence|Standard Precedence]], not here.

## Default Constraints Snapshot

The following rules are in effect by default in all long-running tasks:

- The selected profile's `Profile Scope` registers the content mainline, the foundational knowledge layer, and the completeness predicates; the kernel requires that the mainline and the foundational knowledge be preserved together.
- The excluded scope is read from the selected profile's `Profile Scope` / `Excluded Scope` role; the kernel does not hard-code deployment paths.
- Active Standards are a protected control plane; frozen during content-building tasks, and only a governance change explicitly authorized by the user MAY modify them.
- The reader-facing language values for folders, file names, knowledge body, titles, and first-occurrence terms are provided by the selected profile's `Language Contract`.
- A knowledge object has exactly one canonical owner; other pages reuse it via wiki links.
- Proper-noun definitions, topic mechanisms, system interactions, case applications, and expression-layer content are maintained in separate layers; expression artifacts are registered by the `Expression Layer Entry`.
- External sources MUST NOT be directly equated with canonical knowledge; they MUST pass through the source-to-knowledge pipeline.
- Do not create empty-shell pages, long-lived unresolved links, or P0 / P1 core pages of only two or three sentences.
- Do not roll back, overwrite, or delete existing user modifications whose origin cannot be confirmed.
- Each batch synchronizes body links, metadata, Sources, Expression Layer mapping, and QA; hub pages such as Overview / MOC are synchronized by the integrator after batch merge ([[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]]).
- Batch, targeted audits, and the Terminal Audit reuse still-valid dimension-specific evidence via [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]; old state MUST NOT be trusted blindly, and all manual review MUST NOT be redone indiscriminately.
- `task_state`, `authoring_status`, the profile-owned expression status axis, `evidence_maturity`, and `learning_status` are maintained separately; the specific expression axis is registered by the `Expression Layer Entry`.
- Mid-task Guidance Events MUST be classified, have their disposition recorded, and be mapped to the Amendment Log, Coverage Ledger, Required Queue, or source intake.
- The user has authority over task scope and priority; user hypotheses and source leads still require evidence verification.
- Direct content extraction and structural checks run in full; static compile / parse is triggered by content; the `knowledge-host UI` bound by the selected profile, screenshots, and visual models are used only when deterministic evidence cannot eliminate a specific display uncertainty.
- Screen recording is used only for timing or interaction issues that static evidence and targeted screenshots cannot express.
- Completion MUST satisfy `missing=0`, `ambiguous=0`, Guidance / Coverage Reconciliation, the applicable QA gates, and the Terminal Proof.

## Related

- [[kernel/00 Standards Overview|Standards Overview]]
- [[kernel/00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]]
- [[kernel/00 Standards Control/05 Core Principles and Standards Map|Core Principles and Standards Map]]
