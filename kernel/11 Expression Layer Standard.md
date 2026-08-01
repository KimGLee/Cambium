## Purpose

This page is the kernel entry for the Expression Layer. The kernel specifies only the separation of responsibilities, status isolation, evidence binding, linking, migration, and acceptance invariants between expression artifacts and canonical knowledge.

Concrete artifact types, display names, organization, and the readiness vocabulary are registered by the selected profile's `Expression Layer Entry`; the kernel does not duplicate these profile rules.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/11 Expression Layer/01 Expression Architecture and Separation\|Expression Architecture and Separation]] | `Purpose`, `Core Separation`, `Physical Structure` |
| [[kernel/11 Expression Layer/02 Expression Coverage and Readiness\|Expression Coverage and Readiness]] | `Expression Coverage And Readiness` |
| [[kernel/11 Expression Layer/04 Evidence-bound Expression\|Evidence-bound Expression]] | `Canonical Evidence Boundary` |
| [[kernel/11 Expression Layer/05 Expression Knowledge Binding\|Expression Knowledge Binding]] | `Resolvable Binding`, `Bidirectional Knowledge Flow`, `Evidence Maturity Boundary` |
| [[kernel/11 Expression Layer/06 Sequence and Progress Semantics\|Sequence and Progress Semantics]] | `Sequence And Progress Semantics` |
| [[kernel/11 Expression Layer/07 Expression Migration Audit and Acceptance\|Expression Migration Audit and Acceptance]] | `Migration Policy`, `Scoped Migration Audit`, `Candidate-only Automation`, `Acceptance Criteria` |

## Profile Interface

- `Expression Layer Entry` registers the current profile's expression artifacts, entry points, and single-rule owners.
- A profile MAY add artifact types, templates, classifications, and readiness values, but MUST NOT remove this domain's separation of responsibilities, canonical evidence, status independence, bidirectional binding, or create-before-remove invariants.
- The kernel references only slots and abstract roles; it does not name any profile implementation directly.

## Related Standards

- [[kernel/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
- [[kernel/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]]
- [[kernel/08 Metadata and Status Standard|08 Metadata and Status Standard]]
- [[kernel/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]]
