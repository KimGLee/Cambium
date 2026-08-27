---
type: card
generation_mode: curated
route_id: R03
read_set_id: R03
read_set: Read Set/R03 Module Build Read Set.md
source_files:
  - Read Set/R03 Module Build Read Set.md
  - kernel/K01 Scope and Architecture/05 Structural Unit Interface.md
  - kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger.md
  - kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production.md
  - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
source_hash: '673f20ea6c58'
reviewed_source_hash: '673f20ea6c58'
reviewed_card_hash: 'bfd8b3b8c502'
---
# R03 Module Build Card

## Purpose

Build or systematically expand one confirmed structural unit without changing
its governing architecture implicitly.

## Actions

- Confirm the module boundary, canonical entry, ownership, dependencies, and
  Coverage obligations.
- Return to task routing when the module contents require another work route;
  do not infer that route from this Card.
- Apply R02 to each authored page and keep Coverage synchronized with the
  accepted module boundary.
- Invoke `structure-registry` and obtain `coverage-reconciliation` before the
  module or batch review boundary.

## Stop or escalate

- Stop when the structural unit, owner, dependency, or Coverage obligation is
  ambiguous or the required work exceeds the admitted scope.
- Escalate a proposed architecture or Profile change before implementing it.

## Read-back hook

Resolve `R03:related-work` for source, expression, migration, long-running,
admission, planning, or cross-page questions; use the gate edge before review.
