## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]].
- Next: [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]].

## Purpose

This module owns how much acceptance ceremony a page receives, and the priority distribution that keeps that decision honest. It is read when a page is given a tier in the Coverage Ledger, and again by whichever gate is about to accept it. It decides the intensity of the acceptance; what that acceptance actually checks is decided by [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|K12/01]], [[kernel/K12 Quality Assurance/03 Module and Coverage Review|K12/03]], and [[kernel/K12 Quality Assurance/14 Batch Review|K12/14]].

## Effort Tiering

Page-level acceptance intensity is executed by S/M/L tiering. This section is the canonical owner of the tiering rules; the shared Tiering table in the kernel Core Bootstrap Card is compiled from this section and task cards do not redefine it.

| Tier | Determination | Ceremony |
|---|---|---|
| S | priority=P2, or terminology stub / placeholder / link-aggregation pages | script checks only; no note gate; spot check at batch close per [[kernel/K12 Quality Assurance/14 Batch Review\|K12/14]] |
| M | regular priority=P1 pages | script checks + the [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review#M-tier Gate Checklist\|M-tier Gate Checklist]] compiled into the Single Note Authoring Card; the note gate is folded into the batch gate |
| L | priority=P0, or core concept / process-flow / system / risk-control mainline pages, plus the additional L-tier triggers registered in the selected profile's `Routing And Gate Registry` | full procedure: complete [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review\|K12/01]] review + a standalone note gate + applicable expression migration checks |

- The specific grant conditions for P0 / P1 are registered by the selected profile's `Priority Rubric`.
- Escalate one tier when tiering is disputed.
- Each page's tier is recorded in the Coverage Ledger's `tier` field (schema: `Tools/schemas/coverage_ledger.template.yaml`).
- Tiering only adjusts the intensity of the acceptance ceremony; it does not change any content quality standard itself.

### Priority Quota

tier is derived from priority; priority inflation defeats tiering. Kernel default corpus-wide quotas:

- `P0` share target ≤15%; the specific grant targets are registered by the selected profile's `Priority Rubric`.
- `P1` share target ≤35%; the specific grant targets are registered by the selected profile's `Priority Rubric`.
- All remaining pages are `P2` (including all terminology stubs, placeholder pages, and the vast majority of Source Notes).

P0/P1 pages exceeding quota MUST be resolved through exactly one of three instruments, chosen by the lifetime of the decision. Demote the pages, and the excess ends now. Register standing targets in the selected profile's `Priority Rubric` `Priority Quota` block when this corpus's own structure justifies different long-lived shares -- the registration carries both classes, a required rationale per class, and the joint bound below, and `profile-load` validates it. Register a bounded policy exception in the Task Contract (`Tools/apply_contract_amendment.py`, K13/06) when the excess is accepted temporarily -- the exception names its class, its maximum share, and the fingerprint of the quota registration it was judged against, and it dies with its task or its named snapshot. Batch close consumes the excess only through a currently valid exception; the generic candidate-acceptance flags cannot disposition a quota candidate, so the same excess is never re-accepted ad hoc close after close. Coverage reconciliation for REBASE and Maintenance Runs MUST check the priority and tier distributions (`Tools/check_vocab.py` outputs distribution statistics and per-class over-allocation candidates). The Coverage Ledger records page priorities and dispositions; it carries no quota policy and no exemptions.

An overriding share is a share of the same corpus the three classes partition, so it is admissible only where it leaves that partition intact. Each of the two overriding values is therefore at least 0% and strictly below 100%, and the two together stay strictly below 100%: the remainder class above is `P2` and it carries all terminology stubs and placeholder pages, so a quota that consumes the whole corpus states that a page class the section requires to be non-empty is empty. A quota at or above the whole corpus also silences this section's own demotion rule, because no page can then exceed it — the override registers a quota, and a value that no page can exceed is not one.

## Related

- [[kernel/K00 Standards Overview|Standards Overview]]
- [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
