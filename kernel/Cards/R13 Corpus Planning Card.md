---
type: runtime-card
route_id: R13
read_set: kernel/Read Sets/R13 Corpus Planning Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R13 Corpus Planning Read Set.md
  - kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md
  - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
  - kernel/K02 Knowledge Work Construction/05 Global Map Contract.md
  - kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract.md
  - kernel/K02 Knowledge Work Construction/07 Gap Register Contract.md
  - kernel/K01 Scope and Architecture/02 Logical Architecture and Knowledge Spine.md
  - kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger.md
  - kernel/K02 Knowledge Work Construction/02 Coverage Reconciliation.md
source_hash: 'e5a0302b69fa'
---
# R13 Corpus Planning Card

> Compiled kernel guidance. Read the R13 Read Set and K02/03 through K02/07 for
> disputed role, promotion, applicability, or semantic-acceptance decisions.

## Use When

Create or reconcile the Global Map, Capability Matrix, or Gap Register, or
promote one accepted semantic gap into Coverage. Load R01 and the selected
profile's `Corpus Planning` binding first.

Do not use R13 to author the knowledge that closes a gap, schedule or execute a
batch, maintain task state, or claim audit completion. Combine the route that
owns that work.

## Before Start

- [ ] Resolve `applicability.state`; `configured` binds all three artifact paths, one capability scale, and a pass authority, while `not-applicable` carries a nonempty reason and no active bindings.
- [ ] Read the current Global Map, Capability Matrix, and Gap Register together so one edit does not create a second owner or stale cross-reference.
- [ ] Identify whether this operation is planning, Coverage promotion, content work, migration, or audit; route every non-planning operation to its owner.

## During

- Keep the Global Map to stable corpus topology, entry paths, responsibilities, owners, and explicit upstream/downstream relations.
- Keep the Capability Matrix to testable reader outcomes, current/target scale values, canonical owners, evidence, and linked gaps.
- Keep the Gap Register to semantic candidates and their admission handoff. Do not copy mutable Coverage, Queue, Progress, or receipt state.
- Promote only an accepted gap with a stable owner, path, and disposition. Create or amend its canonical Coverage record; Queue projection happens later under R07 and the actual work route.
- Preserve stable IDs across path renames and update every explicit Profile, Map, Matrix, Gap, Coverage, Queue, and Work Spec reference in one controlled migration.

## Gate

- [ ] `Tools/check_corpus_plan.py --json` reports `structural_reconciliation_valid: true` for a configured plan and records Gate ID `corpus-plan-structure` when receipts are requested.
- [ ] Every promoted gap resolves to exactly one current Coverage object.
- [ ] No planning artifact contains a competing task state, batch lifecycle, Queue order, hold, revision, fingerprint, or receipt ledger.
- [ ] When capabilities are accepted, `record_corpus_acceptance.py --apply` consumes the closed YAML decision plan and records a current Gate ID `corpus-plan-semantic-acceptance` receipt from the Profile-bound authority role; it remains distinct from the structural receipt.

## Read Back When

Read [[kernel/Read Sets/R13 Corpus Planning Read Set|R13 Read Set]] and
[[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|K02/03]],
[[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|K02/04]],
[[kernel/K02 Knowledge Work Construction/05 Global Map Contract|K02/05]],
[[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract|K02/06]],
and [[kernel/K02 Knowledge Work Construction/07 Gap Register Contract|K02/07]]
for the lifecycle, complete artifact contracts, Gap-to-Coverage boundary, applicability
rule, or reconciliation lifecycle. Combine R06 for path migration, R12 for an
audit, and R02/R03/R07 for content and batch execution.
