## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map|Cross-page and Control-plane Dimension Map]].

## Incremental Audit Planning

Each batch generates an `AuditPlan` exactly once, before close; at batch start only the Audit Receipt Register is loaded, with no separate AuditPlan:

```text
1. Freeze current artifact and contract snapshot.
2. Diff against the latest accepted snapshot.
3. Resolve direct and dependency invalidations.
4. Partition checks into:
   - mandatory full deterministic
   - changed-scope deterministic
   - invalidated semantic review
   - overdue (freshness) targeted review
   - bounded sampling
   - reusable evidence
5. Run checks and emit new receipts.
6. Reconcile invalidated, replaced and reused receipts.
7. Close only when required invalidations are zero.
```

The mandatory full deterministic partition of step 4 is the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]]; this module decides the plan, not the list's membership.

## Incremental By Default

The following checks cover only the changed, invalidated, overdue, or sampled scope by default (long-term assurance for P0/P1 pages is carried by freshness-expiry re-verification, with no permanent manual review scope):

- Manual review of mechanisms, why-chains, failures, and production depth;
- Item-by-item verification of source claims against body tone;
- Deep review of formula derivations and numeric context;
- host-specific rendering exceptions;
- profile-specific semantic review registered in the `Audit Dimension Registry`.
