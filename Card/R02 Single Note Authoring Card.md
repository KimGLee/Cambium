---
type: card
generation_mode: curated
route_id: R02
read_set_id: R02
read_set: Read Set/R02 Single Note Authoring Read Set.md
source_files:
  - Read Set/R02 Single Note Authoring Read Set.md
  - kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes.md
  - kernel/K04 Content Depth/01 Depth Model and Foundation.md
  - kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract.md
  - kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review.md
  - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
source_hash: '05a1fc2d6468'
reviewed_source_hash: '05a1fc2d6468'
reviewed_card_hash: 'b69614b05370'
---
# R02 Single Note Authoring Card

## Purpose

Create or change one canonical page within an already confirmed scope and
owner boundary.

## Actions

- Confirm the page owner, note type, intended reader, and applicable Profile
  bindings before writing.
- Write to the applicable depth and preserve claim/source distinctions.
- Invoke `page-contract`, `frontmatter-vocabulary`, and `wiki-link-integrity`
  for the changed page.
- Obtain `content-correctness` and any triggered rendering evidence before the
  applicable review boundary.

## Stop or escalate

- Stop on disputed ownership, an unresolved source conflict, or a required
  field or relation that cannot be determined safely.
- Escalate when the page would require a new rule, exception, or scope change.

## Read-back hook

Resolve the applicable `R02:semantic-condition` edge for terminology,
evidence, relationship, propagation, diagram, code, mathematics, or rendering
questions. The referenced canonical owner supplies the judgment standard.
