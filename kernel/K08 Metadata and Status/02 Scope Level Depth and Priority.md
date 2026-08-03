## Navigation

- Parent: [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]].
- Previous: [[kernel/K08 Metadata and Status/01 Frontmatter and Core Vocabularies|Frontmatter and Core Vocabularies]].
- Next: [[kernel/K08 Metadata and Status/03 Status Axes|Status Axes]].

## Scope

- `shared`: reused by multiple top-level domains.
- `domain-specific`: belongs primarily to one domain.
- `case-specific`: belongs to only one case.
- `source-specific`: describes only one external source.

The selected profile MAY append scope values through `Vocabulary Extensions`, but MUST NOT redefine the base values above.

## Level

- `basic`: MUST be mastered before reading other core content in the current scope.
- `intermediate`: requires basic knowledge; a core capability of the target scope.
- `advanced`: deep implementation, theoretical boundaries, or production-scale problems.

Level represents prerequisite difficulty, not content priority.

## Depth

- `atomic`
- `core`
- `system`

Definitions are in the [[kernel/K04 Content Depth Standard|Content Depth Standard]].

## Priority

- `P0`: declared by the selected profile as must-master; its absence blocks dependent content or declared goals.
- `P1`: declared by the selected profile as a high-priority extension; SHOULD reach the readiness predicate specified by that profile.
- `P2`: supplementary breadth; MAY be built after the core system is complete.

P0 / P1 / P2 is a fixed three-level axis that feeds the page tier derivation and quota linkage mechanism; the selected profile MUST NOT replace, add to, remove from, or redefine this axis. The concrete granting conditions for P0 / P1 are registered by the `Priority Rubric`.
