---
type: runtime-card
route_id: R04
read_set: kernel/Read Sets/R04 Source-driven Expansion Read Set.md
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/R04 Source-driven Expansion Read Set.md
  - kernel/K06 Knowledge Intake and Evolution/01 Intake Scope and Knowledge Model.md
  - kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline.md
  - kernel/K06 Knowledge Intake and Evolution/04 Intake Note Types and Source Roles.md
  - kernel/K06 Knowledge Intake and Evolution/05 Evidence Maturity and Batch Policy.md
  - kernel/K06 Knowledge Intake and Evolution/06 Intake Anti-patterns and Acceptance.md
  - kernel/K06 Knowledge Intake and Evolution/07 Environmental Scanning and Watermark.md
  - kernel/K06 Knowledge Intake and Evolution/08 Canonical Promotion Gate.md
  - kernel/K07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles.md
  - kernel/K07 Sources and Accuracy/02 Claims Sources and Classification.md
  - kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification.md
  - kernel/K07 Sources and Accuracy/06 Source Maintenance and Acceptance.md
  - kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata.md
  - kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes.md
  - kernel/K12 Quality Assurance/04 Guidance and Source Review.md
source_hash: a19141576015
---
# R04 Source-driven Expansion Card

> Compiled kernel guidance. Do not hand-edit. Authority, comparability, metric, conflict, and uncertainty judgments require source read-back.

## Use When

Turn documentation, papers, code, benchmarks, cases, postmortems, community signals, or user source leads into traceable corpus updates. Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]], the selected profile's `Source Policy` and `Language Contract`, and `R02` whenever a canonical note is created or changed.

## Before Start

- [ ] Declare the source scope, scan boundary or source lead, target questions, and affected canonical objects.
- [ ] Create a source inventory and claim-extraction plan; preserve original identity text while writing claims in the profile's body language.
- [ ] Assign source and evidence roles before drawing conclusions.
- [ ] Identify the current canonical owner and whether the likely disposition is update, new owner, split, merge, synthesis, case, signal, defer, or supersede.

## During

Run the pipeline in order: Environmental Scanning → Source Capture → Claim Extraction → Evidence Classification → Cross-source Synthesis → Knowledge Gap Analysis → Graph Impact Decision → Note Creation And Integration → Verification And Promotion → Maintenance And Supersession.

- Separate reported facts, inference, cross-source synthesis, and recommendation.
- State applicability, source-specific conditions, disagreement, comparability limits, and uncertainty.
- Express a gap as a missing question, mechanism, boundary, or owner, not merely as a missing article.
- Update evidence maturity, provenance, relationships, affected notes, and source dates as the evidence warrants.
- Do not promote a source summary directly into stable canonical knowledge.

## Canonical Promotion Gate

- [ ] The knowledge object has a clear problem, boundary, and owner.
- [ ] Key claims trace to specific sources.
- [ ] Facts, inferences, syntheses, and recommendations are distinguished.
- [ ] Applicability and source-specific conditions are stated.
- [ ] Synonymous pages and duplicate definitions were checked.
- [ ] Evidence maturity matches body tone.
- [ ] The page reaches its depth class and is not a source summary or empty shell.
- [ ] Wiki links, Sources, metadata, and rendering were verified.

Unpromoted content may remain a Source Note or Research Synthesis.

## Read Back When

Read R04 Read Set and the relevant owner for user hypotheses, source authority, cross-source independence, benchmark provenance, formula or time sensitivity, source conflict, terminology extraction, or any uncertain promotion decision.
