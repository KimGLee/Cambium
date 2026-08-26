## Purpose

This page is the stable entry point of the Knowledge Work Construction
standard. Detailed rules are maintained by the responsibility-specific modules
below; task-runtime semantics are indexed separately by
[[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control]].

## Reading Rule

- Use this MOC only to locate the canonical semantic owner. Loading decisions
  are owned outside Kernel; opening this index is not evidence that any leaf was
  loaded.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger\|Inventory and Coverage Ledger]] | `Coverage Inventory Boundary`, `Machine-readable Ledger` |
| [[kernel/K02 Knowledge Work Construction/02 Coverage Reconciliation\|Coverage Reconciliation]] | `Coverage Reconciliation` |
| [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle\|Corpus Planning Applicability and Lifecycle]] | `Purpose And Ownership`, `Planning Result`, `Lifecycle And Reconciliation` |
| [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries\|Corpus Planning Runtime Audit and Gate Boundaries]] | `Purpose And Ownership`, `Runtime And Audit Boundaries`, `Explicit Affected-path Projection`, `Machine Gates And Agent Query` |
| [[kernel/K02 Knowledge Work Construction/05 Global Map Contract\|Global Map Contract]] | `Purpose And Ownership`, `Global Map Contract`, `Related` |
| [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract\|Capability Matrix Contract]] | `Purpose And Ownership`, `Capability Matrix Contract`, `Related` |
| [[kernel/K02 Knowledge Work Construction/07 Gap Register Contract\|Gap Register Contract]] | `Purpose And Ownership`, `Gap Register Contract`, `Related` |
| [[kernel/K02 Knowledge Work Construction/08 Architecture Samples and Dependency Planning\|Architecture Samples and Dependency Planning]] | `Phase 3: Representative Samples`, `Phase 4: Dependency-ordered Build` |
| [[kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production\|Knowledge Batch Production]] | `Batch Policy`, `Source-driven Expansion Batch` |
| [[kernel/K02 Knowledge Work Construction/10 Existing Changes and Migration Safety\|Existing Changes and Migration Safety]] | `Existing Changes`, `Migration Safety` |

The closed machine projection shared by K02/03 and K02/04 is
[`corpus-planning-contract.yaml`](<K02 Knowledge Work Construction/corpus-planning-contract.yaml>).
It carries the existing Profile-slot envelope, applicability branches,
receipt freshness binding, and close-trigger identities; it adds no separate
semantic owner.

## Related Standards

- [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]]
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
- [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]]
- [[kernel/K00 Standards Overview|K00 Standards Overview]]
- [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]]
