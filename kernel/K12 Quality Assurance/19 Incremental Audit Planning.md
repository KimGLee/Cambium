## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map|Cross-page and Control-plane Dimension Map]].

## Incremental Audit Planning

Each batch publishes one immutable `AuditPlan` when it enters `open`. [`audit-plan-contract.yaml`](audit-plan-contract.yaml) is the sole normative source for its fields, closed partition vocabulary, obligation shape, and serialization. The plan binds its opening control context and accepted comparison baseline, then freezes the complete definitions of all obligations applicable to that batch: owner kind and stable rule ID, target selector, applicability condition, due stage, producer route and check, evidence role and kind, optional dimension, acceptance predicate, consumer Gate, and reuse policy. Exactly one of `producer_capability` and `producer_gate_id` names the legal producer route; `consumer_gate_id` names the legal consumer.

Completeness is derived from the current Kernel registries plus registrations admitted through an existing Kernel extension point. A Profile extension MUST stay under that extension point and MUST NOT be inserted into a Kernel base closed set. A Tool may project these definitions, but it cannot invent an obligation, broaden applicability, change the acceptance predicate, or grant a new producer or consumer authority.

The complete plan may consume different registered evidence kinds. Only an `audit-receipt` obligation requires a non-null registered dimension and produces the dimension-specific receipt owned by K12/07-K12/08. A dimensionless Gate obligation, including the `page-contract` evidence consumed by `manifest_page_contract`, retains its Gate evidence kind and MUST NOT receive an invented dimension. The plan partitions are:

- mandatory full deterministic checks;
- changed-scope deterministic checks;
- initial semantic review;
- invalidated semantic review;
- overdue targeted review;
- bounded sampling;
- Profile-registered review;
- reusable evidence.

`initial-semantic-review` is a trigger-reason partition, not a new review standard. For L-tier pages it invokes the independent substantive review owned by K12/12; it never converts an M-tier page into a substantive-review obligation. M-tier pages are executed only by the M checklist inside Batch Review.

`profile-registered-review` carries only obligations already admitted through a registered Kernel extension point, including the existing K12/14 Batch Review Requirement extension. It does not add a member to any Kernel base obligation set, and its evidence kind remains the receipt schema registered by the authorized typed Profile.

Every obligation belongs to exactly one partition. The AuditPlan itself carries no actual per-obligation artifact, dependency, or contract fingerprint. When an obligation reaches `pre-merge` or `post-delta-close` and its actual target exists, the stage resolver freezes those three actual fingerprints in the evidence-time record, or binds the exact reusable receipt that already carries them. That resolution is immutable and binds the original plan ID and plan fingerprint; it MUST NOT rewrite the AuditPlan or append an obligation after `open`.

The `post-delta-close` obligations derived from the K12/09 Batch-close Closed List all resolve against one identical post-Delta after-image. Mixed snapshots cannot form a closure. The `closed` transition consumes the complete AuditPlan closure across all registered evidence kinds, explicit reconciliation of reused, superseded, and invalidated evidence, and zero unresolved required invalidations; it cannot validate only the subset represented as AuditReceipts. This semantic owner does not prescribe action order; registered capabilities own deterministic diffing, partition construction, stage resolution, and validation.

The mandatory full deterministic partition is the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]]; this module decides the plan, not the list's membership.

## Incremental By Default

The following checks cover only the changed, invalidated, overdue, or sampled scope by default (long-term assurance for P0/P1 pages is carried by freshness-expiry re-verification, with no permanent manual review scope):

- Manual review of mechanisms, why-chains, failures, and production depth;
- Item-by-item verification of source claims against body tone;
- Deep review of formula derivations and numeric context;
- host-specific rendering exceptions;
- profile-specific semantic review registered in the `Audit Dimension Registry`.
