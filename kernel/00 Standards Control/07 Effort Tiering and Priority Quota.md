## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]].
- Next: [[kernel/00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]].

## Purpose

This module owns how much acceptance ceremony a page receives, and the priority distribution that keeps that decision honest. It is read when a page is given a tier in the Coverage Ledger, and again by whichever gate is about to accept it. It decides the intensity of the acceptance; what that acceptance actually checks is decided by [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|12/01]], [[kernel/12 Quality Assurance/03 Module and Coverage Review|12/03]], and [[kernel/12 Quality Assurance/14 Batch Review|12/14]].

## Effort Tiering

Page-level acceptance intensity is executed by S/M/L tiering. This section is the canonical owner of the tiering rules; the Tiering tables in the Runtime Cards are compiled from this section.

| Tier | Determination | Ceremony |
|---|---|---|
| S | priority=P2, or terminology stub / placeholder / link-aggregation pages | script checks only; no note gate; spot check at batch close per [[kernel/12 Quality Assurance/14 Batch Review\|12/14]] |
| M | regular priority=P1 pages | script checks + the corresponding Card's Gate list; the note gate is folded into the batch gate |
| L | priority=P0, or core concept / process-flow / system / risk-control mainline pages, plus the additional L-tier triggers registered in the selected profile's `Routing And Gate Registry` | full procedure: complete [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review\|12/01]] review + a standalone note gate + applicable expression migration checks |

- The specific grant conditions for P0 / P1 are registered by the selected profile's `Priority Rubric`.
- Escalate one tier when tiering is disputed.
- Each page's tier is recorded in the Coverage Ledger's `tier` field (schema: `Tools/schemas/coverage_ledger.template.yaml`).
- Tiering only adjusts the intensity of the acceptance ceremony; it does not change any content quality standard itself.

### Priority Quota

tier is derived from priority; priority inflation defeats tiering. Kernel default corpus-wide quotas:

- `P0` share target ≤15%; the specific grant targets are registered by the selected profile's `Priority Rubric`.
- `P1` share target ≤35%; the specific grant targets are registered by the selected profile's `Priority Rubric`.
- All remaining pages are `P2` (including all terminology stubs, placeholder pages, and the vast majority of Source Notes).

P0/P1 pages exceeding quota MUST be demoted, or an explicit exemption rationale MUST be recorded in the Coverage Ledger; over-allocation without an exemption record is handled as a coverage reconciliation gap. Coverage reconciliation for REBASE and Maintenance Runs MUST check the priority and tier distributions (`Tools/check_vocab.py` outputs distribution statistics and over-allocation candidates). The selected profile MAY override the 15% / 35% defaults, but MUST register the override explicitly.

## Related

- [[kernel/00 Standards Overview|Standards Overview]]
- [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/12 Quality Assurance/14 Batch Review|Batch Review]]
