## Navigation

- Parent: [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]].
- Next: [[kernel/K08 Metadata and Status/02 Scope Level Depth and Priority|Scope Level Depth and Priority]].

## Purpose

This standard defines machine-readable metadata, priority, and maturity for knowledge files, so that very long tasks can track coverage instead of relying on whether a file exists.

## Frontmatter Schema

The registered frontmatter applicability and relationship bases are the sole machine owners of the Kernel field set, shapes, modes, and conditions. The registered vocabulary base is the sole machine owner of closed values. This page defines their meanings and extension boundary; it does not repeat a second field schema in prose.

The selected Profile MAY register extension fields and values through its Vocabulary Extensions and Metadata Contract, within the extension rules in K08/06. Newly created or substantially rewritten pages use the applicable fields. Before any bulk migration, the Coverage Ledger remains authoritative for current corpus state.

## Type Vocabulary

The registered vocabulary base is the sole normative source for Kernel type membership. A type denotes the semantic role of a page; it does not grant authority, choose a task route, or prove completion.

The selected profile MAY append registered type values through `Vocabulary Extensions`, but MUST NOT delete, rename, or redefine kernel base values.

Type responsibilities are defined in the [[kernel/K03 Note Types and Ownership Standard|Note Types and Ownership Standard]].

## Domain Vocabulary

Concrete domain values are registered by the selected profile's `Vocabulary Extensions`.

Domain uses a controlled vocabulary; case or synonym variants MUST NOT be created at will.

## Freshness And Lifecycle Vocabulary

- `volatility`: allowed values `fast` / `slow` / `stable`. The canonical owner of the three-tier definitions, domain default dispatch, and re-verification intervals is [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]].
- `review_by`: the derived re-verification due date produced by the registered
  freshness capability; it is read-only and MUST NOT be filled in by hand.
- `lifecycle`: the content lifecycle axis. Its closed values are in the
  registered vocabulary base; retirement and merge semantics are owned by
  [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]].
