---
type: card
generation_mode: curated
route_id: R05
read_set_id: R05
read_set: Read Set/R05 Expression Layer Read Set.md
source_files:
  - Read Set/R05 Expression Layer Read Set.md
  - kernel/K11 Expression Layer/01 Expression Architecture and Separation.md
  - kernel/K11 Expression Layer/04 Evidence-bound Expression.md
  - kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance.md
source_hash: '1f1600ca2a11'
reviewed_source_hash: '1f1600ca2a11'
reviewed_card_hash: '536ff005b4d1'
---
# R05 Expression Layer Card

## Purpose

Create, migrate, or review a Profile-registered expression artifact while its canonical knowledge owners remain authoritative.

## Actions

- Resolve the registered artifact, scope, canonical owners, readiness binding, and applicable Profile extension before editing.
- Keep expression content traceable to canonical knowledge and avoid creating a second rule owner.
- Return to task routing when the actual work also needs an authoring, source, module, or migration route.
- Obtain `expression-layer-acceptance` before promotion or migration close.

## Stop or escalate

- Stop when no artifact is registered, its canonical binding is unresolved, or the expression would assert more than its evidence supports.
- Escalate a proposed new artifact class, readiness axis, or exception.

## Read-back hook

Resolve `R05:artifact-condition` for migration, rendering, visual, reuse, or cross-route questions; use the gate edge before acceptance.
