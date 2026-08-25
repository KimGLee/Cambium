---
type: runtime-card
route_id: R02
read_set: kernel/Read Sets/R02 Single Note Authoring Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R02 Single Note Authoring Read Set.md
  - kernel/K03 Note Types and Ownership/01 Note Type Catalog.md
  - kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes.md
  - kernel/K04 Content Depth/01 Depth Model and Foundation.md
  - kernel/K04 Content Depth/02 Core Concept Structure.md
  - kernel/K04 Content Depth/03 Process and Flow Structure.md
  - kernel/K04 Content Depth/04 System and Production Reasoning.md
  - kernel/K04 Content Depth/05 Source and Evaluation Depth.md
  - kernel/K08 Metadata and Status/01 Frontmatter and Core Vocabularies.md
  - kernel/K08 Metadata and Status/02 Scope Level Depth and Priority.md
  - kernel/K08 Metadata and Status/03 Status Axes.md
  - kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract.md
  - kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority.md
  - kernel/K08 Metadata and Status/08 Relationship Metadata Contract.md
  - kernel/K08 Metadata and Status/09 Page Boundary Contract.md
  - kernel/K09 Wiki Link and Navigation/01 Link Semantics and Body Links.md
  - kernel/K10 Writing and Formatting/01 Naming Language and Prose.md
  - kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review.md
  - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
  - kernel/K12 Quality Assurance/12 Substantive Correctness Review.md
readback_sources:
  - kernel/K00 Standards Control/07 Effort Tiering and Priority Quota.md
  - kernel/K04 Content Depth/06 Examples Deep Dives and Failure Analysis.md
  - kernel/K05 Terminology/01 Terminology Extraction.md
  - kernel/K05 Terminology/02 Ownership and Term Structure.md
  - kernel/K05 Terminology/03 Naming Context and Linking.md
  - kernel/K05 Terminology/04 Terminology Acceptance.md
  - kernel/K07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles.md
  - kernel/K07 Sources and Accuracy/02 Claims Sources and Classification.md
  - kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification.md
  - kernel/K07 Sources and Accuracy/04 Evaluation and Source Quality.md
  - kernel/K07 Sources and Accuracy/05 Time Formula Terminology and Uncertainty.md
  - kernel/K10 Writing and Formatting/02 Mathematics Tables and Code.md
  - kernel/K10 Writing and Formatting/03 Diagrams and Assets.md
  - kernel/K10 Writing and Formatting/04 Rendering and Formatting Review.md
  - kernel/K12 Quality Assurance/02 Rendering Verification.md
  - kernel/K12 Quality Assurance/11 Content-level Propagation.md
  - kernel/K12 Quality Assurance/13 Visual Verification Escalation.md
readback_policy: declared
source_hash: '2c1d2a7c346b'
compiled_source_hash: '2c1d2a7c346b'
---
# R02 Single Note Authoring Card

> Compiled kernel guidance. Do not hand-edit. Read the canonical sources for L-tier depth, disputed ownership, or an unlisted case.

## Use When

Create, rewrite, or target one canonical note. Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]] and the selected profile's `Language Contract` and `Vocabulary Extensions`. Combine another Card when source intake, module construction, migration, or long-running execution is involved.

## Before Start

- [ ] Confirm the note type, canonical owner, scope, depth, priority, tier, and target authoring state.
- [ ] Search for an existing synonymous owner; expand it rather than creating a competing definition.
- [ ] Choose the applicable concept, process, system, or source/evaluation structure.
- [ ] Resolve prerequisite, parent, key dependency, source, and terminology needs.
- [ ] Apply the `Language Contract` values and any `Vocabulary Extensions` field the selected profile registers, without weakening kernel ownership or quality rules.
- [ ] Fill frontmatter by the compiled applicability contract: required and met-conditional fields nonempty, no empty placeholders, no unregistered fields, and relationship fields only under their K08/08 name, direction, and shape, and any `boundary` block under its K08/09 schema with the marker-delimited projection left to `Tools/render_boundary_projection.py`. Never hand-fill a derived or projection value, and never write `learning_status` or another user-owned field to silence a check.
- [ ] Treat machine-managed frontmatter as a projection of its declared owner state. Do not hand-update `last_content_modified`, `last_reviewed`, or a Profile Gate field while editing the page.

## During

- Explain the problem or position, key mechanism or causal chain, assumptions and boundaries, an appropriate example, and applicable failure behavior.
- Keep frontmatter and independent status axes consistent with the content actually present.
- Put parent, prerequisite, dependency, and first meaningful terminology links in the body; `Related` alone is not integration.
- Support key, time-sensitive, and quantitative claims; distinguish reported claim, inference, synthesis, and recommendation.
- Treat form and evidence sufficiency as separate decisions. Translation, summarization, reordering, and list-to-prose conversion preserve only source-supported relations; when a mechanism or relation is absent, retain the neutral form and register the gap instead of inventing a connective explanation.
- If a reusable proper noun, metric, formula, table, code block, diagram, external claim, or substantive mechanism change appears, follow the matching Triggered route in R02 Read Set.
- A substantive mechanism change marks direct downstream notes for propagation review.
- A semantic content change is not a review event: the guarded writer records content-change evidence, advances `last_content_modified`, and invalidates any review or Gate evidence bound to the old semantic fingerprint. Projection-only frontmatter write-back does none of those things; only new accepted evidence can restore a current review or Gate value.

## M-tier Gate

- [ ] Type, owner, scope, depth, priority, tier, and applicable statuses are explicit and consistent.
- [ ] Frontmatter satisfies the compiled page contract for this note type, and a Core/System page carries exactly one sources-role section under a registered display title — or, for a derived expression page adding no factual claim, an explicit evidence or canonical binding. A `page-contract` advisory candidate on this page is either fixed or carries a recorded migration disposition.
- [ ] The opening states the problem or position; the body explains the mechanism or causal chain, an important boundary, and an appropriate example.
- [ ] Applicable failure behavior identifies trigger, symptom, cause, detection, and mitigation, or explicitly states why it is not applicable.
- [ ] Key, time-sensitive, and quantitative claims have role-clear evidence; claim, inference, synthesis, and recommendation are not conflated.
- [ ] Form changes preserve the admitted claim boundary; no causal, temporal, comparative, quantitative, modal, ordering, absolute, or scope relation was introduced for fluency, and any missing relation is an explicit gap.
- [ ] Parent, prerequisite, key dependency, and first meaningful terminology links are present; no missing or ambiguous link remains.
- [ ] The `Language Contract` and every triggered source, terminology, propagation, and rendering obligation have been applied.
- [ ] Applicable deterministic checks pass; visual evidence is required only after an objective exception trigger and unresolved question are recorded.

## Other Tiers And Close

- S-tier: run deterministic checks; the batch performs bounded sampling.
- L-tier: read K12/01 in full and dispatch [[kernel/K12 Quality Assurance/12 Substantive Correctness Review|Substantive Correctness Review]] to an independent execution context.
- When formatting or renderable constructs changed, run the deterministic rendering route. Escalate beyond Level 1 only for a recorded visual exception.

## Read Back When

Read R02 Read Set and the named leaf owner for complete note-type depth, terminology extraction, source authority, metric provenance, mathematics, diagrams, visual escalation, or downstream propagation.
