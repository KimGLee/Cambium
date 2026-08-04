# Audit Dimension Registry

Interface: [Audit Dimension Registry slot](../../../README.md#audit-dimension-registry-slot)

## Extension Dimensions

- Registration: Configured

| Dimension ID | Target list(s): `review`, `receipt`, or `review + receipt` | Meaning |
|---|---|---|
| `interview` | `review + receipt` | Fitness of Agent Systems Atlas Interview Cards for their registered spoken-answer and evaluation use, independent of authoring, evidence, and learning status. |

## Judgment Items

| Stable Judgment Item ID | Base or registered receipt Dimension ID | Exact kernel audit-layer name | Bounded audit object one run proves | Evidence role: `emits`, `consumes`, or `triggers` | Predicate owner (repo-relative path; optional `#heading`) |
|---|---|---|---|---|---|
| `agent-atlas-foundation-depth` | `content_and_depth` | `Module Review` | The profile-defined foundation pages in one bounded module satisfy their registered depth predicates. | `emits` | `profiles/examples/agent-atlas/scope-and-architecture.md#Foundation Depth Requirements` |
| `agent-atlas-interview-card-review` | `interview` | `Single Note Review` | One Interview Card satisfies every independently judgeable Card-review condition. | `emits` | `profiles/examples/agent-atlas/registries/audit-dimensions.md#Interview Card Review` |
| `agent-atlas-interview-readiness-acceptance` | `interview` | `Single Note Review` | One Interview Card and its bound canonical topics presented for `interview-ready` promotion satisfy the registered readiness predicate. | `emits` | `profiles/examples/agent-atlas/registries/audit-dimensions.md#Interview Readiness Acceptance` |
| `agent-atlas-profile-wide-interview-acceptance` | `interview` | `Specialized Audit` | The complete in-scope Agent Systems Atlas snapshot satisfies the registered profile-wide Interview-layer acceptance predicate. | `emits` | `profiles/examples/agent-atlas/registries/audit-dimensions.md#Profile-wide Interview Acceptance` |
| `agent-atlas-interview-residual-disposition` | `coverage_and_integration` | `Batch Review` | The merged in-scope snapshot's Interview-answer residual candidates outside `Interview Preparation/` all have an accepted disposition. | `emits` | `profiles/examples/agent-atlas/registries/audit-dimensions.md#Residual-content Disposition` |

## Interview Card Review

Review one Card against these independently judgeable conditions:

- the 30-second answer is direct, accurate, and bounded;
- the 90-second answer contains a connected problem, mechanism, components, tradeoff, and use case;
- required deep-dive branches reach at least three substantive levels and include answers;
- common misconceptions and Strong/Weak Answer Signals can distinguish understanding from keyword recall;
- the English and Chinese answers satisfy the [[profiles/examples/agent-atlas/language-contract#Bilingual Answer Contract|Bilingual Answer Contract]];
- every definition, mechanism, metric, and project fact resolves to its canonical owner and applicable evidence;
- emerging, contested, or unknown material keeps that qualification in the answer;
- System Design and Project Deep Dive Cards satisfy the applicable [[profiles/examples/agent-atlas/expression-layer#System Deep-dive Evidence Chain|System]] or [[profiles/examples/agent-atlas/expression-layer#Project Deep-dive Evidence Chain|Project]] evidence chain.

Each failed condition is reported separately; a general statement that the Card “looks complete” is not a pass.

## Interview Readiness Acceptance

Promotion from `mapped` to `interview-ready` requires all of the following:

1. The registered `agent-atlas-interview-card-review` judgment item passes with no unresolved condition.
2. The Card and every canonical topic it covers have reciprocal, resolvable bindings.
3. Every bound canonical knowledge page has `authoring_status: reviewed`.
4. The required Card structure and applicable category-specific sections are present.
5. Strong/Weak Answer Signals and Self-test Questions are usable for evaluation rather than decorative lists.
6. Any reported metric or outcome retains its evaluation provenance.
7. The registered pass authority approves the promotion and the gate receipt identifies this predicate owner.

This acceptance changes only `interview_status`. It does not promote `authoring_status`, learning progress, evidence maturity, or the completion state of the corpus.

## Residual-content Disposition

The registered Agent Atlas residual scan reports canonical pages that appear to retain full Interview Card material, including complete 30/90-second answers, follow-up answer trees, Strong/Weak Answer Signals, or self-test blocks. Every candidate is resolved through the disposition contract in [[kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance#Scoped Migration Audit|K11/07 Scoped Migration Audit]] and records its target Card or its bounded non-expression rationale.

The scan is candidate discovery only. A zero-candidate result proves only the registered residual predicate for the scanned snapshot; it does not prove Card quality, readiness, or profile-wide coverage.

## Profile-wide Interview Acceptance

The Agent Systems Atlas interview layer is profile-wide complete only when:

- every in-scope P0/P1 canonical topic is `interview-ready` or has an accepted `not-required` disposition naming its combined Card or bounded rationale;
- no required topic remains `missing` or merely `mapped`;
- the registered residual scan has no unresolved candidate;
- Roadmaps and Cheat Sheets resolve to current canonical owners and accepted Cards;
- the Interview Overview reflects the actual artifact set without becoming a second answer owner.

This profile-wide verdict consumes the applicable Card, link, residual-scan, source, and coverage evidence; it does not replace their individual judgments.
