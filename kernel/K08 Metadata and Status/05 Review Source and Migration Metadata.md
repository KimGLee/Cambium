## Navigation

- Parent: [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]].
- Previous: [[kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata|Evidence and Relationship Metadata]].
- Next: [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract|Frontmatter Applicability Contract]].

## Review Dates

- `last_reviewed`: the most recent content quality review.
- `last_verified`: the most recent verification of time-sensitive external facts.

Stable mathematical concepts do not need frequent `last_verified` updates; protocols, prices, products, and security requirements do.

`first_seen` records the date an emerging topic or source signal first entered the knowledge base; it is not the same as the source's publication date.

## Freshness And Review Due

`volatility` uses a controlled vocabulary and describes how fast a page's conclusions decay in freshness:

- `fast`: fast-changing content, such as the current state of external services and interfaces, component comparisons, and performance numbers; re-verification interval 120 days.
- `slow`: slow-changing content, such as methodology and system design patterns; re-verification interval 365 days.
- `stable`: stable content, such as mathematics and classical foundational principles; no re-verification deadline.

When not explicitly declared, the default value is taken from the domain dispatch table registered by the selected profile's `Vocabulary Extensions`; a single page MAY override it explicitly.

`review_by` is not filled in by hand; `Tools/check_freshness.py` computes it as `last_verified + corresponding interval`. When a page has no `last_verified`, the creation date or the date of the most recent substantive modification is used instead, and the page is marked as awaiting first verification.

Overdue semantics: a past `review_by` means the page enters the maintenance-run candidate list (sorted by priority); it does not automatically change any of the page's status axes.

Re-verification MUST answer: does this topic still deserve its current priority today? Upgrades and downgrades are recorded in the Coverage Ledger with the reason stated.

## Conditional Source Metadata

Source Notes and Research Synthesis MAY add:

```yaml
source_type: official-engineering-article
source_organization: Example Organization
source_date:
source_url:
evidence_roles:
  - implementation-evidence
claim_scope:
supersedes:
superseded_by:
source_valid_until:
```

- `source_type` uses a controlled vocabulary, distinguishing paper, official article, documentation, benchmark, postmortem, community discussion, and independent reproduction.
- `evidence_roles` describes the evidence role the source plays, rather than simply repeating the source's authority level.
- `claim_scope` states which component, execution / control setup, task, organization, or time range the conclusion applies to.
- `supersedes` / `superseded_by` preserve the evolution relationship between conclusions.
- `source_valid_until` records a real external validity boundary (a legal, contract, standard, or version expiry), per the split owned by [[kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority|Frontmatter Writer and Projection Authority]]; ordinary freshness stays derived from `last_verified` and `volatility`, and the legacy `review_due` field migrates under [[kernel/K08 Metadata and Status/08 Relationship Metadata Contract|Relationship Metadata Contract]] — a value synonymous with derived freshness is dropped, a genuine external validity date moves here. Stable foundational knowledge is not required to be re-reviewed frequently.

## Migration Rules

- Approve the schema first, then add frontmatter in bulk.
- Establish the authoritative state in the Coverage Ledger first, then decide whether to write back to Frontmatter in bulk.
- Migration MUST NOT change body semantics.
- Old `status` migrates only to `authoring_status`; the profile-registered expression readiness status, `learning_status`, or `evidence_maturity` MUST NOT be inferred from it.
- Existing pages without Frontmatter default to `unassessed`, not `drafted` or `reviewed`.
- aliases and prerequisites require manual or semi-automated review.
- MUST NOT mark all pages as reviewed in one pass.
- `deferred` and `excluded` MUST have explicit reasons and MUST NOT serve as default values that hide gaps.
- After completion, verify that the selected knowledge host's plugins and relationship graph are unaffected.

## Related

- [[kernel/K04 Content Depth Standard|Content Depth Standard]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- [[kernel/K02 Knowledge Work Construction Standard|Knowledge Work Construction Standard]]
