## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map|Cross-page and Control-plane Dimension Map]].

## Incremental Audit Planning

Each batch produces one `AuditPlan` before close. The registered AuditPlan machine contract is the sole normative source for its fields and serialization. The plan must bind one artifact and Contract snapshot, its accepted comparison baseline, direct and dependency invalidations, and a complete partition into:

- mandatory full deterministic checks;
- changed-scope deterministic checks;
- invalidated semantic review;
- overdue targeted review;
- bounded sampling;
- reusable evidence.

Every obligation belongs to exactly one partition. Close requires current receipts for executed partitions, explicit reconciliation of reused, superseded, and invalidated evidence, and zero unresolved required invalidations. This semantic owner does not prescribe action order; registered capabilities own deterministic diffing, partition construction, and validation.

The mandatory full deterministic partition of step 4 is the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]]; this module decides the plan, not the list's membership.

## Incremental By Default

The following checks cover only the changed, invalidated, overdue, or sampled scope by default (long-term assurance for P0/P1 pages is carried by freshness-expiry re-verification, with no permanent manual review scope):

- Manual review of mechanisms, why-chains, failures, and production depth;
- Item-by-item verification of source claims against body tone;
- Deep review of formula derivations and numeric context;
- host-specific rendering exceptions;
- profile-specific semantic review registered in the `Audit Dimension Registry`.
