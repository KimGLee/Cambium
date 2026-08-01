## Navigation

- Parent: [[kernel/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]].
- Next: [[kernel/09 Wiki Link and Navigation/02 Structural and Bidirectional Links|Structural and Bidirectional Links]].

## Purpose

This standard specifies how wiki links express real knowledge relationships, and guarantees bidirectional navigation among Overview, sequence views, topic pages, term pages, Source Notes, Research Synthesis, cases, and `Expression Layer Artifact`.

## Link Meaning

A wiki link SHOULD express at least one of the following relationships:

- Prerequisite: the current content depends on it.
- Parent: the current content belongs to it.
- Component: it is a part of the current system.
- Alternative: it is an alternative approach.
- Comparison: comparison on unified dimensions is needed.
- Application: the current concept is used in that system.
- Failure / Control: it explains a failure cause or a mitigation.
- Source / Evidence: a source or synthesis supports, limits, or refutes the current claim.
- Supersession: new evidence or a new page supersedes an old conclusion.
- Derived Expression: the relationship between canonical knowledge and an `Expression Layer Artifact`; the concrete binding is provided by the `Expression Layer Entry`.

Ordinary words or semantically weakly related pages MUST NOT be linked for the sake of graph density.

## In-body Links

- Create the link at the first meaningful occurrence of a proper term.
- A link MUST have surrounding context in the current text; writing only "see this page" is not allowed.
- Later repeated occurrences on the same page are usually not linked again.
- Important dependencies MUST NOT be placed only in the end-of-page `Related`.
- Link text SHOULD fit the language of the current sentence rather than forcibly displaying the full path.
