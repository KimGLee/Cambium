## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]].
- Next: [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]].

## Purpose

This module owns how much acceptance ceremony a page receives and the optional numeric guardrail a Profile may place on priority distribution. It is read when a page is given a tier in the Coverage Ledger, and again by whichever gate is about to accept it. It decides the intensity of the acceptance; what that acceptance actually checks is decided by [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|K12/01]], [[kernel/K12 Quality Assurance/03 Module and Coverage Review|K12/03]], and [[kernel/K12 Quality Assurance/14 Batch Review|K12/14]].

## Effort Tiering

Page-level acceptance intensity is executed by S/M/L tiering. This section is the canonical owner of the tiering rules. Non-authoritative action projections may reference or summarize these rules but do not redefine them.

| Tier | Determination | Ceremony |
|---|---|---|
| S | priority=P2, or terminology stub / placeholder / link-aggregation pages | script checks only; no note gate; spot check at batch close per [[kernel/K12 Quality Assurance/14 Batch Review\|K12/14]] |
| M | regular priority=P1 pages | deterministic checks + the [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review#M-tier Gate Checklist\|M-tier Gate Checklist]]; the note gate is folded into the batch gate |
| L | priority=P0, or core concept / process-flow / system / risk-control mainline pages, plus the additional L-tier triggers registered in the selected profile's `Routing And Gate Registry` | full procedure: complete [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review\|K12/01]] review + a standalone note gate + applicable expression migration checks |

- The specific grant conditions for P0 / P1 are registered by the selected profile's `Priority Rubric`.
- A page that satisfies neither grant condition is P2; a quota does not grant or revoke priority.
- Escalate one tier when tiering is disputed.
- Each page's tier is recorded in the Coverage Ledger under the
  `coverage-ledger` schema contract.
- Tiering only adjusts the intensity of the acceptance ceremony; it does not change any content quality standard itself.

### Priority Quota

Tier is derived from priority, so a knowledge repository may choose a numeric guardrail against priority inflation. Such a guardrail is optional and belongs to the selected Profile. The [`contract-exception-policy-base.yaml`](contract-exception-policy-base.yaml) machine registry is the unique authority for the P0/P1 policy IDs, limit domain, Profile registration states, and effective-policy fingerprint protocol. This page owns what an active quota means; it defines no universal numeric ceiling.

- `Registration: None` means that no numeric corpus-share ceiling is active. It produces no quota excess, authorizes no quota exception, and cannot block a Gate or batch close. The Profile's P0/P1 grant predicates still apply in full.
- `Registration: Configured` activates one standing pair of P0/P1 ceilings supplied by the selected Profile. Both classes and a non-empty rationale for each are required; a Profile cannot inherit unstated Kernel numbers.

When a configured quota is exceeded, the excess MUST be resolved through exactly one of three instruments, chosen by the lifetime of the decision. Demote pages whose priority grant is not justified, and the excess ends now. Revise and re-adopt the Profile registration when the corpus needs different long-lived ceilings. Register a bounded policy exception in the Task Contract when the excess is accepted temporarily -- the exception names its class, maximum share, and the fingerprint of the active Profile registration it was judged against, and it dies with its task or named snapshot. Batch close consumes the excess only through a currently valid exception; generic candidate-acceptance flags cannot disposition a quota candidate, so the same excess is never re-accepted ad hoc close after close.

The `priority-quota-distribution` Gate applies only when the selected Profile configures a quota. Its receipt carries per-class structured shares, the active ceilings, exceeded classes, and the effective-policy fingerprint. With `Registration: None`, this Gate is not applicable and produces neither a receipt nor an excess candidate. Any consumer that requires quota-distribution evidence must consume this configured-policy receipt rather than deriving shares or activation state from display text. The Coverage Ledger records page priorities and dispositions; it carries no quota policy and no exemptions.

An active ceiling pair applies to the same corpus partitioned by the three priority classes, so it is admissible only where it leaves that partition intact. Each value is non-negative and below the whole corpus, and the combined ceilings must leave a non-empty remainder for P2. A pair that consumes the whole corpus is not a meaningful priority-distribution guardrail and cannot be registered or granted as an exception.

## Related

- [[kernel/K00 Standards Overview|Standards Overview]]
- [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
