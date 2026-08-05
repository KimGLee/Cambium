---
type: read-set
route_id: R12
---

## Purpose

Used for a targeted review of changed, invalidated, overdue, or sampled objects, or for a specialized audit with one declared cross-batch invariant. It does not perform task completion acceptance or produce a Terminal Proof.

## Start

First load [[kernel/Read Sets/R01 Core Bootstrap Read Set|R01 Core Bootstrap]] and the route relevant to the finding, then read:

- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]]

Declare the acceptance predicate, audit object, receipt dimension, affected scope, evidence eligible for reuse, and either the changed / invalidated / overdue / sampled partition or the specialized invariant before review begins.

## Triggered

- Note or module content review: load the applicable Gate modules of R02 or R03.
- Source or guidance review: read [[kernel/K12 Quality Assurance/04 Guidance and Source Review|Guidance and Source Review]].
- Expression-layer review: combine [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]] and the artifact's supplemental profile gate.
- Migration review: combine the Gate modules of [[kernel/Read Sets/R06 Migration and Refactor Read Set|R06 Migration and Refactor]].
- Rendering question: read [[kernel/K12 Quality Assurance/02 Rendering Verification|Rendering Verification]]; visual evidence additionally requires [[kernel/K12 Quality Assurance/13 Visual Verification Escalation|Visual Verification Escalation]].
- A whole-task completion candidate: combine [[kernel/Read Sets/R08 Audit and Completion Read Set|R08 Audit and Completion]].
- When `Corpus Planning` is configured, read [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]], [[kernel/K02 Knowledge Work Construction/05 Global Map Contract|Global Map Contract]], [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract|Capability Matrix Contract]], and [[kernel/K02 Knowledge Work Construction/07 Gap Register Contract|Gap Register Contract]], then use explicit Global Map downstream relations, Capability Matrix owner/gap references, and Gap Register links to form the initial affected set. The audit still verifies that set against the changed predicate and expands only by this route's bounded rule; the planning artifacts do not decide the audit result.
- An audit finding creates or changes a semantic-gap candidate or planning relation: combine [[kernel/Read Sets/R13 Corpus Planning Read Set|R13 Corpus Planning]] after recording the audit finding. R12 owns evidence; R13 owns the planning write-back.

## Gate

- Reuse only receipts whose predicate and fingerprints remain compatible.
- Review only the changed, invalidated, overdue, sampled, or declared specialized-invariant scope, plus required global invariants.
- A suspected systemic problem expands first to a bounded sample; only recurrence invalidates the whole affected family.
- Re-run only invalidated dimensions and their necessary global invariants after a fix.
- Unresolved failures become explicit repair items; a targeted or specialized audit MUST NOT claim task completion or substitute for Terminal Proof.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance]]
- [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence|Terminal Audit and Convergence]]
