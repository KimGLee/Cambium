## Navigation

- Parent: [[kernel/08 Metadata and Status Standard|08 Metadata and Status Standard]].
- Previous: [[kernel/08 Metadata and Status/02 Scope Level Depth and Priority|Scope Level Depth and Priority]].
- Next: [[kernel/08 Metadata and Status/04 Evidence and Relationship Metadata|Evidence and Relationship Metadata]].

## Status Axes

`authoring_status`, the profile-registered expression readiness status, `evidence_maturity`, and `learning_status` are four independent dimensions and MUST NOT be merged into a single status chain.

For example, a page MAY simultaneously satisfy:

```yaml
authoring_status: reviewed
# profile readiness status: missing
evidence_maturity: single-source
learning_status:
```

This means the knowledge page has completed authoring review, but the profile-registered expression-layer material has not yet been built, the empirical conclusion is still supported by only a single source, and the user's learning status is unknown.

File existence, a resolvable wiki link, the existence of an external checklist item, or a large page word count MUST NOT automatically change any status.

### Authoring Status

`authoring_status` represents only the authoring and quality-review progress of a knowledge file:

- `unassessed`: an old page, or a page newly brought into scope, not yet reviewed against the current Standards. Existing pages without metadata default to this status in the Coverage Ledger.
- `outline`: only headings, structure, or scattered points; does not count as completed content.
- `drafted`: the main content has been written, but facts, formulas, links, sources, profile expression artifact migration, or rendering have not been fully checked.
- `reviewed`: has passed the content, source, formula, link, duplication, formatting, and required rendering checks for the corresponding note type.

The status transitions are:

```text
unassessed
 -> outline
 -> drafted
 -> reviewed
```

When a regression, source invalidation, or major structural gap is found, `reviewed` MAY be downgraded back to `drafted`. A status MUST NOT be upgraded directly because the file exists, its length reaches a threshold, or automated checks pass.

### Profile Readiness Status

The field, allowed values, and upgrade rules of the fourth status axis are registered by the selected profile's `Vocabulary Extensions` and point to a single prose owner. This status MUST NOT be inferred automatically from file existence, link resolvability, or the other status axes.

### Learning Status

`learning_status` belongs to the user's personal learning progress and is not written automatically by bulk knowledge-base building:

- `not-started`
- `learning`
- `self-tested`
- `mastered`

`mastered` requires oral recall, self-testing, practice, or explicit user confirmation. External progress lists and `learning_status` MUST NOT be used to prove that page authoring is complete.

### Coverage Disposition

`coverage_disposition` represents how a page is handled within the current build scope:

- `required`: MUST be completed within the current scope; blocks task completion until the target status is reached.
- `optional`: valuable but does not block the current task.
- `deferred`: postponed for now; `deferred_reason`, the re-entry condition, or the target batch MUST be filled in.
- `excluded`: explicitly not part of the current task; MUST be traceable back to the scope contract.

`next_batch` maps unfinished pages to an explicit batch; a vague "fill in later" MUST NOT be the only record. The authoritative summary of coverage disposition is kept in the Coverage Ledger; Frontmatter is only the page-local projection.
