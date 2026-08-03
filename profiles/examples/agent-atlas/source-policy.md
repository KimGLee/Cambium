# Source Policy

Interface: [Source Policy slot](../../README.md#source-policy-slot)

Within each bounded claim class, use the highest applicable authority below. A source class never becomes canonical outside its stated claim boundary.

## Source Authority

| Rank | Stable Source ID and exact location | Bounded canonical claim/content class | Version/release/commit, or retrieval date if unversioned |
|---:|---|---|---|
| 1 | `ATLAS-OFFICIAL` — `Knowledge Sources/Official Engineering/` | A provider's, project maintainer's, or system operator's documented API, product, implementation, architecture, policy, or incident claim. | Each Source Note records `source_date`, `source_url`, `last_verified`, `review_due`, and any available release, model, API version, or commit. |
| 2 | `ATLAS-STANDARD` — `Knowledge Sources/Standards/` | Published protocol, schema, security, observability, risk, or measurement requirements within the named standard and section. | Pin the document identifier, edition/draft, section, publication date, and correction state; living standards also record `last_verified` and `review_due`. |
| 3 | `ATLAS-PAPER` — `Knowledge Sources/Papers/` | The methods, assumptions, experiments, results, and limitations actually reported by the cited paper. | Pin the publisher/DOI or archive version and publication date; pin code and data releases separately when a result depends on them. |
| 4 | `ATLAS-BOOK` — `Knowledge Sources/Books/` | Established theory or synthesis within the cited edition and chapter. | Pin title, edition, chapter, and publication year. |
| 5 | `ATLAS-IMPLEMENTATION` — `Knowledge Sources/Ecosystem Implementations/` | Observable behavior of a non-authoritative ecosystem implementation, not a general protocol guarantee. | Pin repository release or commit and the verification date. |
| 6 | `ATLAS-COMMUNITY` — `Knowledge Sources/Community Engineering/` | Bounded operational observation, reproduction, or security report from the named author; never the sole authority for a general mechanism. | Pin publication/repository revision and retrieval date; record independent corroboration or explicitly retain `single-source`. |

## Verification Entry Points

| Bounded claim class | Registered Source ID | Verifier command, path, URL, or procedure | Version pin or freshness window |
|---|---|---|---|
| Provider API, model, tool, pricing, limit, policy, or product behavior | `ATLAS-OFFICIAL` | Open the Source Note's exact `source_url`; verify the claim against the provider's current official documentation and retain the quoted section or response field in the evidence record. | The named API/model/release when exposed; otherwise the Source Note's `last_verified` date must not exceed `review_due`. |
| Open protocol, schema, security, observability, or risk requirement | `ATLAS-STANDARD` | Resolve the original standards-body URL from the Source Note and verify the exact numbered section, status, and errata/correction state. | Named RFC/specification/framework edition and section; living drafts use the recorded retrieval date and `review_due`. |
| Scientific mechanism or quantitative research result | `ATLAS-PAPER` | Resolve the DOI, publisher, or archive record in the Source Note; inspect the method, task/sample, result table, limitations, and linked code/data when the claim depends on them. | Published/archive version plus code commit and dataset release where applicable; retraction or correction checks occur at review. |
| Framework or library runtime semantics | `ATLAS-OFFICIAL` | Verify against the maintainer's official versioned documentation and, when behavior is material, the tagged source or a reproducible minimal example. | Exact package/framework release or commit; living `stable` documentation also records retrieval date. |
| Ecosystem or community operational claim | `ATLAS-IMPLEMENTATION` or `ATLAS-COMMUNITY` | Reproduce against the pinned implementation where feasible and seek an independent primary or official source before promotion beyond the bounded report. | Exact release/commit and test environment; otherwise keep the claim `single-source` until corroborated. |

## Staleness Triggers

| Observable change event | Bounded affected pages or claims |
|---|---|
| A Source Note reaches `review_due`, its `source_url` becomes unavailable, or the upstream page changes without a stable version pin. | That Source Note and every canonical, synthesis, case, or interview claim whose evidence path cites it. |
| A provider changes a model snapshot, API/schema, tool contract, rate/price limit, policy, safety control, or product lifecycle state. | Provider-specific behavior and comparisons using that exact configuration; unrelated framework-neutral mechanisms remain valid. |
| A standard publishes a new edition, draft status, erratum, correction, or withdrawal. | Claims bound to the changed document and section, plus implementations whose conformance conclusion used it. |
| A paper is corrected, retracted, superseded, or its code/data cannot reproduce the cited result. | The paper-specific result, downstream synthesis, numerical assertion, and any decision that relied on it. |
| An evaluation changes task/sample, split, model, Harness, tools, policy, budget, environment, grader, aggregation, or validity checks. | That measurement, its comparisons, and any promoted conclusion using the old tested-system identity. |

## Domain-specific Comparison Rules

- Registration: Configured

| Condition | Additional profile rule |
|---|---|
| A P0/P1 Agent, Harness, LLM-interface, tool-use, context/cache, evaluation, or safety claim has directly relevant first-party material from both OpenAI and Anthropic. | Capture and compare both `ATLAS-OFFICIAL` sources against the same bounded question; record configuration, date, agreement, disagreement, and non-claims. If only one provider has a directly relevant source, record the other search and absence instead of inventing symmetry. |
| A vendor benchmark or product result is used to support a framework-neutral conclusion. | Add an independent paper, standard, reproducible implementation result, or clearly mark the conclusion provider-specific; vendor attribution alone cannot promote it to a universal mechanism. |

## Provenance Extensions

- Registration: Configured

| Applicability / trigger | Additional provenance requirement | Recording target reference (Vocabulary field ID, body heading, or evidence path) |
|---|---|---|
| Any quantitative evaluation, benchmark, A/B result, model comparison, or production metric used as evidence | Record the supported claim; task distribution and sample/split; model and Harness versions; tools, policy, memory, retrieval, and safeguards; trial count/seeds and budgets; environment/runtime; grader; aggregation; uncertainty and failure distribution; timestamp; and validity checks. | `AI Systems Engineering/Evaluation/Evaluation Provenance.md#Core Records` or the equivalent immutable evaluation evidence record. |
| Any Agent evaluation with tool use, state change, or external side effects | Preserve the transcript or auditable trace, trajectory and artifacts, authoritative final environment outcome, side-effect receipts, and failure taxonomy; a final answer or aggregate score alone is insufficient. | `AI Systems Engineering/Evaluation/Evaluation Provenance.md#Trial And Evidence Record` |
