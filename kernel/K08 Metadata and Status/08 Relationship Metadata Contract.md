## Navigation

- Parent: [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]].
- Previous: [[kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority|Frontmatter Writer and Projection Authority]].
- Next: [[kernel/K08 Metadata and Status/09 Page Boundary Contract|Page Boundary Contract]].

## Relationship Metadata Contract

Near-synonym relationship fields MUST NOT coexist ownerless, and relationships are not compressed into one undirected list. Each kernel relationship field has one name, one direction, one target type, and one value shape, registered in `kernel/K08 Metadata and Status/relationship-base.yaml` with this leaf as its semantic owner:

- `source_url`: the entry from a Source Note to its **external** original — document, artifact, DOI, standard section, release, or commit. It never points at an internal page, and an internal Source Note is never presented as the external original.
- `evidence_sources`: internal evidence **inputs**, always list-shaped; each item resolves to a `source-note` page, or to a `research-synthesis` page where the compiled contract admits it. Canonical output relations are never written here.
- `supersedes` / `superseded_by`: version evolution between conclusions, one target each, mutually inverse in direction.
- `source_valid_until`: a real external validity date, per the [[kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority|K08/07]] split from derived freshness.

Canonical expression bindings (a profile's `canonical_bindings` or equivalent) are Profile-owned extension relations: they stay out of `evidence_sources` and out of this kernel base. `canonical_targets` or `promoted_to` style output relations enter the kernel only when a real machine consumer exists — never for field symmetry. One-shot source probe or access results belong in receipts, not in long-lived page frontmatter.

## Closure And Extension

An unregistered relationship-like field is a violation under the [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract|K08/06]] unknown-field closure — legacy spellings such as `sources`, `source_note`, `source_notes`, or `source_set` do not coexist with the canonical names on any long-term basis. A profile registers additional relations only as namespaced `Metadata Contract` extensions with an explicit direction, target type, and value shape; a spelling variant or alias of a kernel field is not registrable. Migration from legacy fields judges semantic equivalence per page and records an old-field to new-field manifest; names are never merged mechanically.

`Tools/check_page_contract.py` validates shape, direction plausibility (field present on an admissible page type), and target resolvability under the same advisory contract as K08/06. Whether a source is credible, independent, or actually supports a claim stays with [[kernel/K07 Sources and Accuracy Standard|K07]] and [[kernel/K12 Quality Assurance Standard|K12]] substantive review; Global Map typed edges stay with [[kernel/K02 Knowledge Work Construction/05 Global Map Contract|K02/05]] and are not duplicated as page fields.
