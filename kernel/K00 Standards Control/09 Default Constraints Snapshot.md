## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]].
- Next: [[kernel/K00 Standards Control/10 Batch Execution Checklist|Batch Execution Checklist]].

## Purpose

This module owns the standing constraint list a long-running task operates under without being told again: the snapshot form of defaults whose detailed rules are held by the domain modules. It is read once at task start, and it is the target of the Protected Defaults compression in [[kernel/K00 Standards Overview|Standards Overview]]. It states what is in force; when two statements conflict, precedence is resolved by [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Standard Precedence|Standard Precedence]], not here.

## Default Constraints Snapshot

The following rules are in effect by default in all long-running tasks:

- The selected profile's `Profile Scope` registers the content mainline, the foundational knowledge layer, and the completeness predicates; the kernel requires that the mainline and the foundational knowledge be preserved together ([[kernel/K01 Scope and Architecture/03 Foundation Preservation|K01/03]]).
- The excluded scope is read from the selected profile's `Profile Scope` / `Excluded Scope` role; the kernel does not hard-code deployment paths ([[kernel/K01 Scope and Architecture/01 Scope Boundaries|K01/01]]).
- Active Standards are a protected control plane; frozen during content-building tasks, and only a governance change explicitly authorized by the user MAY modify them ([[kernel/K00 Standards Control/04 Control State and Scope|K00/04]]).
- The reader-facing language values for folders, file names, knowledge body, titles, and first-occurrence terms are provided by the selected profile's `Language Contract`.
- A knowledge object has exactly one canonical owner; other pages reuse it via wiki links ([[kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes|K03/02]]).
- Proper-noun definitions, topic mechanisms, system interactions, case applications, and expression-layer content are maintained in separate layers ([[kernel/K03 Note Types and Ownership/01 Note Type Catalog|K03/01]]); expression artifacts are registered by the `Expression Layer Entry` ([[kernel/K11 Expression Layer/01 Expression Architecture and Separation|K11/01]]).
- External sources MUST NOT be directly equated with canonical knowledge; they MUST pass through the source-to-knowledge pipeline ([[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|K06/03]]).
- Do not create empty-shell pages, long-lived unresolved links ([[kernel/K09 Wiki Link and Navigation/04 MOC Related and Link Creation|K09/04]]), or P0 / P1 core pages of only two or three sentences ([[kernel/K04 Content Depth/01 Depth Model and Foundation|K04/01]]).
- Do not roll back, overwrite, or delete existing user modifications whose origin cannot be confirmed ([[kernel/K02 Knowledge Work Construction/10 Existing Changes and Migration Safety|K02/10]]).
- Each batch synchronizes body links, metadata, Sources, Expression Layer mapping, and QA; hub pages such as Overview / MOC are synchronized by the integrator after batch merge ([[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|K13/10]]).
- Batch, targeted audits, and the Terminal Audit reuse still-valid dimension-specific evidence via [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]; old state MUST NOT be trusted blindly, and all manual review MUST NOT be redone indiscriminately.
- `task_state`, `authoring_status`, the profile-owned expression status axis, `evidence_maturity`, and `learning_status` are maintained separately ([[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|K13/03]], [[kernel/K08 Metadata and Status/03 Status Axes|K08/03]], [[kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata|K08/04]]); the specific expression axis is registered by the `Expression Layer Entry`.
- Mid-task Guidance Events MUST be classified, have their disposition recorded, and be mapped to the Amendment Log, Coverage Ledger, Required Queue, or source intake ([[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis|K13/04]], [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching|K13/05]], [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|K13/06]]).
- The user has authority over task scope and priority; user hypotheses and source leads still require evidence verification ([[kernel/K06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads|K06/02]]).
- Direct content extraction and structural checks run in full; static compile / parse is triggered by content; the `knowledge-host UI` bound by the selected profile, screenshots, and visual models are used only when deterministic evidence cannot eliminate a specific display uncertainty ([[kernel/K12 Quality Assurance/02 Rendering Verification|K12/02]], [[kernel/K12 Quality Assurance/13 Visual Verification Escalation|K12/13]]).
- Screen recording is used only for timing or interaction issues that static evidence and targeted screenshots cannot express.
- Completion MUST satisfy `missing=0`, `ambiguous=0`, Guidance / Coverage
  Reconciliation, the applicable QA gates, and the closure selected by the Task
  Contract: Terminal Proof for `completion_semantics: build`, or the bounded
  maintenance completion gate for `completion_semantics: maintenance`
  ([[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|K12/06]],
  [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy|K13/11]]).

## Related

- [[kernel/K00 Standards Overview|Standards Overview]]
- [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]]
- [[kernel/K00 Standards Control/05 Core Principles|Core Principles]]
