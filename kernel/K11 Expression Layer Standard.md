## Purpose

This page is the kernel entry for the Expression Layer. The kernel specifies only the separation of responsibilities, status isolation, evidence binding, linking, migration, and acceptance invariants between expression artifacts and canonical knowledge.

Concrete artifact types, display names, organization, and the readiness vocabulary are registered by the selected profile's `Expression Layer Entry`; the kernel does not duplicate these profile rules.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/K11 Expression Layer/01 Expression Architecture and Separation\|Expression Architecture and Separation]] | `Purpose`, `Core Separation`, `Physical Structure` |
| [[kernel/K11 Expression Layer/02 Expression Coverage and Readiness\|Expression Coverage and Readiness]] | `Expression Coverage And Readiness` |
| [[kernel/K11 Expression Layer/04 Evidence-bound Expression\|Evidence-bound Expression]] | `Canonical Evidence Boundary` |
| [[kernel/K11 Expression Layer/05 Expression Knowledge Binding\|Expression Knowledge Binding]] | `Resolvable Binding`, `Bidirectional Knowledge Flow`, `Evidence Maturity Boundary` |
| [[kernel/K11 Expression Layer/06 Sequence and Progress Semantics\|Sequence and Progress Semantics]] | `Sequence And Progress Semantics` |
| [[kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance\|Expression Migration Audit and Acceptance]] | `Migration Policy`, `Scoped Migration Audit`, `Candidate-only Automation`, `Acceptance Criteria` |

## Profile Interface

- `Expression Layer Entry` registers the current profile's expression artifacts, entry points, and single-rule owners.
- Its `Registered Artifacts` configured table is the sole machine-readable registration: each row binds one stable artifact identity and type to its reader-facing label, entry point, canonical dependency map and/or Metadata Contract binding, revalidation trigger, Profile-owned contract, and optional readiness field. `Registration: None` uses the same empty table shape.
- A readiness field is optional. Registering an expression artifact does not create a readiness axis; when a row names one, that field must already be registered through the Profile's Vocabulary Extensions, Metadata Contract, and Gate contract.
- A profile MAY add artifact types, templates, classifications, and readiness values, but MUST NOT remove this domain's separation of responsibilities, canonical evidence, status independence, bidirectional binding, or create-before-remove invariants.
- The kernel references only slots and abstract roles; it does not name any profile implementation directly.
- A profile that registers no expression artifact creates no R05 task target; the agent stops rather than inventing one. Once an artifact is registered and enters scope, the R05 separation, evidence, binding, migration, and acceptance floor is applicable and cannot be disabled by the profile. The rule is owned by [[kernel/K11 Expression Layer/01 Expression Architecture and Separation#Core Separation|Core Separation]].

## Related Standards

- [[kernel/K03 Note Types and Ownership Standard|K03 Note Types and Ownership Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]]
- [[kernel/K07 Sources and Accuracy Standard|K07 Sources and Accuracy Standard]]
- [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]]
- [[kernel/K09 Wiki Link and Navigation Standard|K09 Wiki Link and Navigation Standard]]
