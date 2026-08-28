## Navigation

- Parent: [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]].
- Previous: [[kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata|Evidence and Relationship Metadata]].
- Next: [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract|Frontmatter Applicability Contract]].

## Review Dates

- `last_content_modified`: the most recent substantive page-content change
  accepted by the Integrator. It is an event projection, not filesystem mtime.
- `last_reviewed`: the most recent content quality review.
- `last_verified`: the most recent verification of time-sensitive external facts.

Stable mathematical concepts do not need frequent `last_verified` updates; protocols, prices, products, and security requirements do.

`last_reviewed` and `last_verified` record completed evidence-backed events. At the run's causal boundary `as_of`, each explicit non-empty value MUST be a valid `YYYY-MM-DD` no later than `as_of` (equality is valid); otherwise the page is a candidate. Validate both fields before baseline or volatility: invalid `last_verified` cannot fall back to `last_reviewed`, an invalid/future unselected field cannot be hidden by the selected one, and `stable` cannot exempt invalid/future evidence. `last_content_modified` records the guarded content-change event described below; it is compared with review evidence but is not a substitute freshness baseline.

`first_seen` records the date an emerging topic or source signal first entered the knowledge base; it is not the same as the source's publication date.

`last_content_modified` is the intermediate state between intake and review. When the semantic content fingerprint changes, the guarded content-change event advances this date and invalidates review evidence bound to the prior fingerprint. Changes confined to machine-controlled projections do neither. Until new review evidence binds the current fingerprint, the old `last_reviewed` value has no current authority and the page is a re-review candidate; the tool must not manufacture a replacement date from mtime or the day it happened to run.

## Freshness And Review Due

`volatility` uses a controlled vocabulary and describes how fast a page's conclusions decay in freshness:

- `fast`: conclusions that change rapidly, such as current external interfaces,
  comparisons, and performance measurements.
- `slow`: conclusions that change more slowly, such as methodology and system
  design patterns.
- `stable`: stable conclusions such as mathematics and classical foundations.

The registered vocabulary base is the sole normative source for closed values and default review intervals. This page owns their meanings and the freshness calculation boundary.

An absent/blank page value uses its domain default from the selected Profile's `Vocabulary Extensions`; a page MAY validly override it. A non-empty value outside the vocabulary is a candidate, not a reason to use that default.

`review_by` is derived, never written by hand: for non-stable policy, the registered freshness capability adds the resolved interval to the first available valid event (`last_verified`, then `last_reviewed`). Only absence/blankness permits fallback. If both events are absent, creation or substantive-modification time is diagnostic only and the page awaits first verification, including under `stable`.

Every active in-scope page MUST have one closed outcome. The candidate set is exactly: content modified after its current review; overdue; awaiting first verification; invalid or post-`as_of` explicit event; invalid explicit or unresolved fallback `volatility`; and unparseable frontmatter. Treat the last conservatively because lifecycle and facts are unprovable. Explicit exclusions and provably retired/merged pages are accounted outside the active set; no fallback, exemption, or skip may turn a candidate into a pass. A pass requires a completed scan, at least one discovered Markdown file, every active page classified, and this set empty. Zero discovery is a scan-level candidate. Candidates feed Maintenance without changing page status; [[kernel/K00 Standards Control/08 Maintenance Run Envelope|K00/08]] owns fusion, ordering, and budget truncation.

Re-verification MUST answer: does this topic still deserve its current priority today? Upgrades and downgrades are recorded in the Coverage Ledger with the reason stated.

## Conditional Source Metadata

The registered applicability and relationship bases are the sole normative source for conditional source-field membership, shape, and conditions. The semantic responsibilities are:

- `source_type` uses a controlled vocabulary, distinguishing paper, official article, documentation, benchmark, postmortem, community discussion, and independent reproduction.
- `evidence_roles` describes the evidence role the source plays, rather than simply repeating the source's authority level.
- `claim_scope` states which component, execution / control setup, task, organization, or time range the conclusion applies to.
- `supersedes` / `superseded_by` preserve the evolution relationship between conclusions.
- `source_valid_until` records a real external validity boundary (a legal, contract, standard, or version expiry), per the split owned by [[kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority|Frontmatter Writer and Projection Authority]]; ordinary freshness uses the valid baseline cascade and resolved volatility defined above. Legacy `review_due` migrates under [[kernel/K08 Metadata and Status/08 Relationship Metadata Contract|Relationship Metadata Contract]] — derived freshness is dropped; a genuine external validity date moves here. Stable knowledge needs no recurring re-review.

## Migration Rules

A metadata migration is valid only when the machine contract has already been adopted, Coverage remains authoritative for current state, body semantics are unchanged, and every projected value is supported by its canonical owner or required evidence. Legacy values cannot be used to infer a different status axis, and absence cannot be upgraded to reviewed. Aliases, prerequisites, deferral, and exclusion require their ordinary semantic review and rationale. This semantic owner does not prescribe a migration action sequence. Registered capabilities own deterministic transformation and verification.

## Related

- [[kernel/K04 Content Depth Standard|Content Depth Standard]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- [[kernel/K02 Knowledge Work Construction Standard|Knowledge Work Construction Standard]]
