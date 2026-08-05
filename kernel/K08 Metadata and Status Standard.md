## Purpose

This page is the stable entry point for the Metadata and Status standard. The detailed rules have been split by responsibility into the modules below; the original content has not been reduced.

## Reading Rule

- Use this MOC to locate the rule owner first, then read the modules required by the current task, event, or quality gate.
- Entering this domain does not require reading all modules at once.
- Each module returns to its parent via `Navigation` and links to its adjacent previous and next modules.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/K08 Metadata and Status/01 Frontmatter and Core Vocabularies\|Frontmatter and Core Vocabularies]] + `Vocabulary Extensions` | `Purpose`, `Frontmatter Schema`, `Type Vocabulary`, `Domain Vocabulary`, `Freshness And Lifecycle Vocabulary` |
| [[kernel/K08 Metadata and Status/02 Scope Level Depth and Priority\|Scope Level Depth and Priority]] + `Priority Rubric` + `Vocabulary Extensions` | `Scope`, `Level`, `Depth`, `Priority` |
| [[kernel/K08 Metadata and Status/03 Status Axes\|Status Axes]] + `Vocabulary Extensions` | `Status Axes` |
| [[kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata\|Evidence and Relationship Metadata]] + `Language Contract` | `Evidence Maturity`, `Prerequisites`, `Aliases` |
| [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata\|Review Source and Migration Metadata]] + `Vocabulary Extensions` | `Review Dates`, `Freshness And Review Due`, `Conditional Source Metadata`, `Migration Rules`, `Related` |

Machine-readable base values are registered in `kernel/K08 Metadata and Status/vocabulary-base.yaml`; the selected profile appends values only through `Vocabulary Extensions`. Markdown prose remains the single canonical owner of field semantics and behavior rules; machine registries do not duplicate upgrade gates.

## Applicable Read Sets

- [[kernel/Read Sets/R02 Single Note Authoring Read Set|Single Note Authoring]]
- [[kernel/Read Sets/R03 Module Build Read Set|Module Build]]
- [[kernel/Read Sets/R04 Source-driven Expansion Read Set|Source-driven Expansion]]
- [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]]
- [[kernel/Read Sets/R06 Migration and Refactor Read Set|Migration and Refactor]]

## Related Standards

- [[kernel/K03 Note Types and Ownership Standard|K03 Note Types and Ownership Standard]]
- [[kernel/K04 Content Depth Standard|K04 Content Depth Standard]]
- `Expression Layer Entry` (the selected profile's expression layer standard)
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]]
- [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]]
- [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]]
