## Navigation

- Parent: [[kernel/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]].
- Previous: [[kernel/03 Note Types and Ownership/01 Note Type Catalog|Note Type Catalog]].
- Next: [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]].

## Ownership Rules

Every knowledge object MUST have a single canonical owner:

- Term Note owns the definition.
- Concept Note owns the mechanism.
- Process / Flow Note owns transition, branch, loop, state/effect change, and termination semantics.
- Algorithm Note owns the algorithm behavior.
- Metric Note owns the metric interpretation.
- System Component Note owns the component contract.
- System Design Note owns component interaction.
- Source Note owns faithful representation of one source.
- Research Synthesis Note owns cross-source comparison and unresolved research state.
- Case Study owns application decisions.
- The `Expression Layer Artifact` registered by the selected profile owns the expression content defined by that profile.
- Overview / MOC owns module boundary and navigation.
- Roadmap owns learning order.

## Canonical Note Rules

- One concept has only one canonical note.
- Abbreviations, full names, and multilingual names are handled via aliases and wiki link aliases.
- Other pages MAY explain the role in the current context, but MUST NOT copy the complete generic definition.
- A Process / Flow Note MAY reference component contracts, but MUST NOT copy each component's complete implementation; component pages likewise MUST NOT each claim ownership of the same end-to-end flow.
- When a canonical note moves, all path-qualified links MUST be updated.
- Concepts with the same name but different semantics are disambiguated by domain path, e.g. Protocol State vs Storage State.
- Source Note and Research Synthesis do not acquire canonical ownership of a concept by referencing it.
- The presence of a link in the `Expression Layer Artifact` registered by the selected profile, a Roadmap, a Cheat Sheet, or an Overview does not indicate that the linked canonical note has passed content review.
