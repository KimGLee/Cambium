## Purpose

This page is the stable entry point for the Metadata and Status standard.
Detailed rules are maintained by the responsibility-specific modules below.

## Reading Rule

- Use this MOC only to locate the canonical semantic owner. Loading decisions
  are owned outside Kernel; opening this index is not evidence that any leaf was
  loaded.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/K08 Metadata and Status/01 Frontmatter and Core Vocabularies\|Frontmatter and Core Vocabularies]] + `Vocabulary Extensions` | `Purpose`, `Frontmatter Schema`, `Type Vocabulary`, `Domain Vocabulary`, `Freshness And Lifecycle Vocabulary` |
| [[kernel/K08 Metadata and Status/02 Scope Level Depth and Priority\|Scope Level Depth and Priority]] + `Priority Rubric` + `Vocabulary Extensions` | `Scope`, `Level`, `Depth`, `Priority` |
| [[kernel/K08 Metadata and Status/03 Status Axes\|Status Axes]] + `Vocabulary Extensions` | `Status Axes` |
| [[kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata\|Evidence and Relationship Metadata]] + `Language Contract` | `Evidence Maturity`, `Prerequisites`, `Aliases` |
| [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata\|Review Source and Migration Metadata]] + `Vocabulary Extensions` | `Review Dates`, `Freshness And Review Due`, `Conditional Source Metadata`, `Migration Rules`, `Related` |
| [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract\|Frontmatter Applicability Contract]] + `Metadata Contract` | `Frontmatter Applicability Contract`, `Two-layer Composition`, `Missingness Has One Owner`, `Enablement` |
| [[kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority\|Frontmatter Writer and Projection Authority]] | `Frontmatter Writer and Projection Authority`, `Writer Rules` |
| [[kernel/K08 Metadata and Status/08 Relationship Metadata Contract\|Relationship Metadata Contract]] + `Metadata Contract` | `Relationship Metadata Contract`, `Closure And Extension` |
| [[kernel/K08 Metadata and Status/09 Page Boundary Contract\|Page Boundary Contract]] + `Metadata Contract` | `Page Boundary Contract`, `Cross-page Rules`, `Projection`, `Enablement` |

Machine-readable base values are registered in `kernel/K08 Metadata and Status/vocabulary-base.yaml`; the selected profile appends values only through `Vocabulary Extensions`. Field applicability and relationship bases are registered in `applicability-base.yaml` and `relationship-base.yaml` of the same directory; the selected profile declares only differences through its `Metadata Contract` slot. Markdown prose remains the single canonical owner of field semantics and behavior rules; machine registries do not duplicate upgrade gates.

## Related Standards

- [[kernel/K03 Note Types and Ownership Standard|K03 Note Types and Ownership Standard]]
- [[kernel/K04 Content Depth Standard|K04 Content Depth Standard]]
- `Expression Layer Entry` (the selected profile's expression layer standard)
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]]
- [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]]
- [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]]
