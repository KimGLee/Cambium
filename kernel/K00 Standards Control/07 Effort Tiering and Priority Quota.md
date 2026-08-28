## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]].
- Next: [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]].

## Purpose

This module owns how much acceptance ceremony a page receives, and the priority distribution that keeps that decision honest. It is read when a page is given a tier in the Coverage Ledger, and again by whichever gate is about to accept it. It decides the intensity of the acceptance; what that acceptance actually checks is decided by [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|K12/01]], [[kernel/K12 Quality Assurance/03 Module and Coverage Review|K12/03]], and [[kernel/K12 Quality Assurance/14 Batch Review|K12/14]].

## Effort Tiering

Page-level acceptance intensity is executed by S/M/L tiering. This section is the canonical owner of the tiering rules. Non-authoritative action projections may reference or summarize these rules but do not redefine them.

| Tier | Determination | Ceremony |
|---|---|---|
| S | priority=P2, or terminology stub / placeholder / link-aggregation pages | script checks only; no note gate; spot check at batch close per [[kernel/K12 Quality Assurance/14 Batch Review\|K12/14]] |
| M | regular priority=P1 pages | deterministic checks + the [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review#M-tier Gate Checklist\|M-tier Gate Checklist]]; the note gate is folded into the batch gate |
| L | priority=P0, or core concept / process-flow / system / risk-control mainline pages, plus the additional L-tier triggers registered in the selected profile's `Routing And Gate Registry` | full procedure: complete [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review\|K12/01]] review + a standalone note gate + applicable expression migration checks |

- The specific grant conditions for P0 / P1 are registered by the selected profile's `Priority Rubric`.
- Escalate one tier when tiering is disputed.
- Each page's tier is recorded in the Coverage Ledger under the
  `coverage-ledger` schema contract.
- Tiering only adjusts the intensity of the acceptance ceremony; it does not change any content quality standard itself.

### Priority Quota

Tier is derived from priority; priority inflation defeats tiering. The [`contract-exception-policy-base.yaml`](contract-exception-policy-base.yaml) machine registry is the unique authority for the P0/P1 policy IDs, their Kernel-default ceilings, limit domain, and effective-policy fingerprint protocol. This page owns why those constraints exist and how they govern priority assignment; it does not restate the machine values.

- `P0` and `P1` each resolve to the registry default unless the selected
  Profile's `Priority Rubric` supplies a valid standing registration.
- All remaining pages are `P2` (including all terminology stubs, placeholder pages, and the vast majority of Source Notes).

P0/P1 pages exceeding quota MUST be resolved through exactly one of three instruments, chosen by the lifetime of the decision. Demote the pages, and the excess ends now. Register standing targets in the selected profile's `Priority Rubric` `Priority Quota` block when this corpus's own structure justifies different long-lived shares -- the registration carries both classes, a required rationale per class, and the joint bound defined by the machine registry, and `profile-load` validates it. Register a bounded policy exception in the Task Contract when the excess is accepted temporarily -- the exception names its class, its maximum share, and the fingerprint of the quota registration it was judged against, and it dies with its task or its named snapshot. Batch close consumes the excess only through a currently valid exception; the generic candidate-acceptance flags cannot disposition a quota candidate, so the same excess is never re-accepted ad hoc close after close. Coverage reconciliation for REBASE and Maintenance Runs MUST consume the `priority-quota-distribution` Gate receipt, which carries per-class structured shares, the exceeded classes, and the effective-policy fingerprint they were measured under -- never a share re-derived from display text. The Coverage Ledger records page priorities and dispositions; it carries no quota policy and no exemptions.

An overriding share is a share of the same corpus the three classes partition, so it is admissible only where it leaves that partition intact. Each value is non-negative and below the whole corpus, and the combined ceilings must leave a non-empty remainder for `P2`. A ceiling that consumes the whole corpus would both contradict that required remainder and silence this section's demotion rule; it is therefore not a quota override at all.

## Related

- [[kernel/K00 Standards Overview|Standards Overview]]
- [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
