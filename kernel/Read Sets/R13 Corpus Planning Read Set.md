---
type: read-set
route_id: R13
---

## Purpose

Used to create or reconcile the selected profile's Global Map, Capability
Matrix, and Gap Register, and to hand an accepted semantic gap into Coverage.
It does not author corpus pages, schedule or execute batches, or perform an
audit.

## Start

First load [[kernel/Read Sets/R01 Core Bootstrap Read Set|R01 Core Bootstrap]],
then read:

- the selected profile's `Corpus Planning` binding;
- [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|Corpus Planning Applicability and Lifecycle]];
- [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]];
- [[kernel/K02 Knowledge Work Construction/05 Global Map Contract|Global Map Contract]];
- [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract|Capability Matrix Contract]];
- [[kernel/K02 Knowledge Work Construction/07 Gap Register Contract|Gap Register Contract]];
- [[kernel/K01 Scope and Architecture/02 Logical Architecture and Knowledge Spine|Logical Architecture and Knowledge Spine]].

Resolve `Applicability` before editing a planning artifact. `Configured`
requires all three bound paths, the declared capability scale, and a pass
authority. `applicability.state: not-applicable` with a nonempty `reason` is valid only within the bounded case
defined by K02/03 through K02/07 and authorizes no artifact invention.

## Triggered

- Creating or changing corpus architecture: read [[kernel/K02 Knowledge Work Construction/08 Architecture Samples and Dependency Planning|Architecture Samples and Dependency Planning]].
- Promoting a confirmed semantic gap: read [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]] and [[kernel/K02 Knowledge Work Construction/02 Coverage Reconciliation|Coverage Reconciliation]], then create or amend the canonical Coverage object. R13 stops at that handoff; Queue planning and execution use R07 and the route for the actual work.
- Moving or renaming a bound planning artifact or mapped canonical owner: combine [[kernel/Read Sets/R06 Migration and Refactor Read Set|R06 Migration and Refactor]].
- Building or revising the knowledge objects that close a gap: combine R02, R03, or the other route for the actual content work.
- Using the explicit map, capability, and gap relations to select an audit scope: combine [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|R12 Targeted and Specialized Audit]]. R12 owns the audit predicate, evidence, expansion, and result.
- The selected profile's Structure Registry is `configured` and the operation touches a registered entry or its Global Map binding: read [[kernel/K01 Scope and Architecture/05 Structural Unit Interface|Structural Unit Interface]] and reconcile the registry against the Global Map with `Tools/check_structure.py`. R13 reconciles the bindings; it does not own structure rules or take over the structural work route.

## Gate

- The three configured paths exist inside the repository and retain distinct role ownership.
- Global Map entries, Capability Matrix records, and Gap Register records have stable unique identities and valid explicit cross-references.
- A promoted gap has one matching canonical Coverage object; any later Queue projection is owned and validated by the Required Queue rather than copied into the Gap Register.
- Planning artifacts do not copy task state, batch lifecycle, Queue order, holds, revisions, fingerprints, or receipts.
- `python3 Tools/check_corpus_plan.py . --json` reports `structural_reconciliation_valid: true` against the selected Profile and current runtime state.
- When the operation accepts Matrix capabilities, a closed decision plan under `.cambium/deltas/corpus-plan-acceptances/` names every current Capability ID exactly once and `python3 Tools/record_corpus_acceptance.py . --plan <plan> --actor-role <Profile-bound-role> --apply` records a current `corpus-plan-semantic-acceptance` receipt.
- The structural and semantic Gate IDs remain distinct; neither receipt substitutes for the other.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K02 Knowledge Work Construction Standard|Knowledge Work Construction]]
- [[kernel/Read Sets/R03 Module Build Read Set|Module Build]]
- [[kernel/Read Sets/R07 Long-running Execution Read Set|Long-running Execution]]
- [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|Targeted and Specialized Audit]]
