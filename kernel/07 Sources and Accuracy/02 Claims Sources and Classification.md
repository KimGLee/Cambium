## Navigation

- Parent: [[kernel/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]].
- Previous: [[kernel/07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles|Source Hierarchy and Evidence Roles]].
- Next: [[kernel/07 Sources and Accuracy/03 Official and Cross-source Verification|Official and Cross-source Verification]].

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

Common-sense connective sentences do not require per-sentence citation, but "common practice" MUST NOT be used to mask unverified facts.

## Source Placement

Every Core / System page contains at least `## Sources`.

Recommended format:

```markdown

## Sources

- [Descriptive source title](https://example.com)
- Paper title, authors, year.
```

Conclusions that are time-sensitive, easily misunderstood, or directly cite official behavior SHOULD have links placed near the relevant paragraph, while also being aggregated in Sources.

Only sources that will be reused, compared, or continuously tracked get a Source Note. An ordinary supporting citation simply stays in the relevant paragraph of the canonical note or in Sources.

## Claim Classification

Source-driven content SHOULD distinguish:

- `Reported Claim`: directly reported by the source.
- `Reasoned Inference`: inferred from the source.
- `Cross-source Synthesis`: a judgment formed after comparing multiple sources.
- `Engineering Recommendation`: a recommendation combining evidence and constraints.

Body tone MUST be consistent with the claim type and `evidence_maturity`. A single community discussion MUST NOT be written as "the industry has proven", and a single vendor case MUST NOT be written as "all systems should".
