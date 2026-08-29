# Contributing to Cambium

## One public owner before implementation

Repository work starts from a GitHub Issue. A confirmed defect, enhancement, or governance change may originate in private notes, adopter evidence, or an exploratory report, but those materials are not its lifecycle owner. Promote the accepted problem into an Issue before opening an implementation pull request.

For defects, use the Bug report form and keep four things distinct:

- the observable problem;
- direct evidence and the exact revision tested;
- affected and excluded scope;
- the system invariant or ownership boundary a durable fix must restore.

Implementation PRs must contain `Closes #<issue>` (or the equivalent `Fixes` or `Resolves` form) for at least one real, open Issue in this repository. CI checks the referenced object and refuses a missing Issue, a PR number used as an Issue, or a closed owner. Related work that the PR does not close can use a non-closing reference separately.

Local `docs/` records remain intentionally ignored. They are useful as an investigation inbox and may preserve wider evidence, rejected hypotheses, and unresolved questions. They do not replace the canonical Issue, and CI neither reads nor uploads them.

## Markdown source format

Write each prose paragraph as one physical line; do not hard-wrap prose to a fixed column width. Keep separate lines where Markdown structure requires them, including headings, lists, block quotes, tables, code blocks, frontmatter, link definitions, and explicit hard breaks. Generated or byte-preserving historical artifacts follow their producer or archival contract.

## Pull request scope

Keep the PR within the owner Issue's accepted scope. State the system boundary restored, describe material compatibility decisions, and list exact tests and negative cases. If investigation changes the diagnosis materially, correct the Issue before asking reviewers to evaluate the implementation.
