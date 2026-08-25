## Navigation

- Parent: [[kernel/K07 Sources and Accuracy Standard|K07 Sources and Accuracy Standard]].
- Previous: [[kernel/K07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles|Source Hierarchy and Evidence Roles]].
- Next: [[kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification|Official and Cross-source Verification]].

## Claims Requiring Sources

The following content MUST have sources:

- Mathematical definitions and important formulas.
- Original algorithm mechanisms, complexity, and theoretical properties.
- Protocol roles, lifecycles, and security requirements.
- Current capabilities and limitations of frameworks, libraries, and models.
- Benchmark, performance, pricing, and version data.
- Security attacks, risk classifications, and mitigation recommendations.
- Contested or condition-dependent engineering conclusions.
- Architecture, metrics, user scale, cost, and effectiveness data in industry cases.
- New system / operational-control patterns synthesized from official articles or community discussions.

Common-sense connective sentences do not require per-sentence citation, but "common practice" MUST NOT be used to mask unverified facts. Citation-free does not mean claim-free: a connective or restructuring edit MUST NOT add a causal, mechanistic, temporal, comparative, quantitative, ordering, modal, absolute, or scope relation that the page's admitted evidence does not support.

## Claim-preserving Transformation

Translation, summarization, list-to-prose conversion, reordering, and other form changes may reorganize supported claims; they do not create authority to complete a missing explanation. Before a transformation, the author or reviewer distinguishes the content's natural form from whether the current evidence is sufficient for the proposed rewrite. A list is a compressed causal narrative only when its existing items themselves state the relevant causal, mechanistic, or failure relations. List density, short item length, or a page-depth requirement is not evidence that those relations exist.

When the target form requires a relation or mechanism that the admitted content and sources do not supply, the transformation is blocked: preserve the neutral source form, record the exact evidence or knowledge gap and its owner, and let the applicable depth/acceptance rule decide whether that gap blocks the page. Filling the gap with an inferred transition, ordering, quantity, strengthening, or universal statement in order to satisfy a prose rule is a new unsupported claim.

## Source Placement

Every Core / System page satisfies the `sources` section role: a section whose responsibility is aggregating the page's evidence entries. The kernel owns the role, not an English string: the default display title is `Sources`, and the selected profile's `Language Contract` binds the reader-facing display title and MAY register bounded migration-period aliases; checkers verify the role through those registered titles and MUST NOT hardcode one language's heading. One page carries at most one sources-role section — near-synonym duplicate headings are a defect.

A derived expression page that adds no factual claim of its own MAY satisfy the role through an explicit canonical or evidence binding (a nonempty `evidence_sources` list or a profile-registered expression-to-canonical relation) instead of a heading; the moment it adds a fact, number, or empirical conclusion it keeps its own direct evidence.

Recommended format under the registered display title:

```markdown

## Sources

- [Descriptive source title](https://example.com)
- Paper title, authors, year.
```

Whether the role's section exists, resolves, and matches a registered title is deterministic and belongs to the `page-contract` gate of [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract|K08/06]]; whether the cited sources genuinely support the claims stays with this standard's substantive review and [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|K12/05]]. No second sources checker is created.

Conclusions that are time-sensitive, easily misunderstood, or directly cite official behavior SHOULD have links placed near the relevant paragraph, while also being aggregated in Sources.

Only sources that will be reused, compared, or continuously tracked get a Source Note. An ordinary supporting citation simply stays in the relevant paragraph of the canonical note or in Sources.

## Claim Classification

Source-driven content SHOULD distinguish:

- `Reported Claim`: directly reported by the source.
- `Reasoned Inference`: inferred from the source.
- `Cross-source Synthesis`: a judgment formed after comparing multiple sources.
- `Engineering Recommendation`: a recommendation combining evidence and constraints.

Body tone MUST be consistent with the claim type and `evidence_maturity`. A single community discussion MUST NOT be written as "the industry has proven", and a single vendor case MUST NOT be written as "all systems should".
