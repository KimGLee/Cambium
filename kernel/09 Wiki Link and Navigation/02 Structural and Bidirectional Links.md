## Navigation

- Parent: [[kernel/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]].
- Previous: [[kernel/09 Wiki Link and Navigation/01 Link Semantics and Body Links|Link Semantics and Body Links]].
- Next: [[kernel/09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]].

## Structural Links

A core note SHOULD at minimum be able to navigate to:

- One Parent / Overview.
- The necessary Prerequisites.
- Key Components or sub-concepts.
- At least one Application, Alternative, or Failure link.
- Where applicable, at least one `Expression Layer Artifact` registered by the `Expression Layer Entry`.

A Source Note SHOULD also link the affected knowledge notes; a Research Synthesis SHOULD link the source set, the existing owners, and the graph nodes it proposes to change. A canonical note is not required to list all Source Notes, but key time-sensitive claims MUST retain a traceable evidence link.

A fixed link count MUST NOT be required mechanically; relationship authenticity comes first.

## Bidirectional Knowledge Flow

Recommended relationships:

```text
Overview -> Topic
Topic -> Prerequisite / Component / Alternative
Source Note -> Affected Knowledge Notes
Research Synthesis -> Source Notes + Canonical Topics
Canonical Topic -> Key Evidence / Research Synthesis
Case Study -> Canonical Topic
Canonical Note <-> Expression Layer Artifact
Cheat Sheet -> Canonical Note
```

The selected knowledge host's backlinks capability MAY provide reverse discovery, but key navigation SHOULD still exist explicitly in the body.
