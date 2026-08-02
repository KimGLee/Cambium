## Navigation

- Parent: [[kernel/01 Scope and Architecture Standard|01 Scope and Architecture Standard]].
- Previous: [[kernel/01 Scope and Architecture/03 Foundation Preservation|Foundation Preservation]].

## Physical Folder Policy

Belonging logically to a layer does not mean existing files must be moved immediately.

A directory migration MUST satisfy:

1. The new ownership is explicit.
2. All incoming links have been inventoried.
3. The new path does not create same-name ambiguity.
4. The Overview, Roadmap, and graph group can be updated in sync.
5. The Batch-close Closed List of the batch in which the migration closes ([[kernel/12 Quality Assurance/09 Batch-close Closed List|12/09]]) covers knowledge-base-wide link verification.

Large-scale moves with no knowledge benefit, made only so directories look tidy, MUST NOT be performed.

## Shared Ownership Rule

A concept's placement is decided by the "lowest reasonable common layer":

- Serves a single domain only: place it in that domain.
- Reused across domains with a natural foundational home: place it in the `Shared Foundation Layer` registered by the selected profile.
- Generic to production systems: place it in the `Production Systems Layer` registered by the selected profile.
- Satisfies only the `Expression Layer Predicate` registered by the selected profile: place it in the `Expression Layer` registered by the selected profile.
- Describes only its usage within a case: place it in the `Case Study Layer` registered by the selected profile, but the definition still links back to the canonical note.
- Records only a single external source: place it in the `Source Note Layer` registered by the selected profile; it does not own general conclusions.
- Synthesizes multiple sources but conclusions are still forming: place it in the `Research Synthesis Layer` registered by the selected profile; it does not prematurely pose as a stable definition.

## Architecture Anti-patterns

- Creating a new top-level folder for every new term that appears.
- Copying the same concept separately into multiple domain directories.
- The Roadmap, Cheat Sheet, and topic page all storing the same explanation.
- Dumping all shared concepts into one uncategorized Glossary.
- Moving files first, then considering references and ownership.
- Using graph colors as a substitute for real knowledge-layer design.
- Deleting or over-compressing the foundation layers an application mainline depends on in order to highlight that mainline.
- Creating a canonical note from an article title without claim extraction and graph impact judgment.

## Related

- [[kernel/03 Note Types and Ownership Standard|Note Types and Ownership Standard]]
- [[kernel/05 Terminology Standard|Terminology Standard]]
- The `Expression Layer Entry` registered by the selected profile
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
