# Source Policy

Kernel owner: K07 Sources and Accuracy. Common slot identity is registered in the Kernel Profile interface.

## Source Authority

| Rank | Stable Source ID and exact location | Bounded canonical claim/content class | Version/release/commit, or retrieval date if unversioned |
|---:|---|---|---|
| 1 | `ATLAS-OFFICIAL` — `Knowledge Sources/Official Engineering` | Official product, API, implementation, architecture, policy, or incident claims. | Record the available release, model, API version, commit, and retrieval date. |
| 2 | `ATLAS-STANDARD` — `Knowledge Sources/Standards` | Requirements stated by a named standard or specification. | Record document identifier, edition or draft, section, and publication date. |
| 3 | `ATLAS-PAPER` — `Knowledge Sources/Papers` | Methods, experiments, results, and limitations reported by a paper. | Record DOI or archive version and publication date; pin linked code or data when relevant. |
| 4 | `ATLAS-BOOK` — `Knowledge Sources/Books` | Theory or synthesis within a named edition and chapter. | Record title, edition, chapter, and publication year. |
| 5 | `ATLAS-IMPLEMENTATION` — `Knowledge Sources/Ecosystem Implementations` | Observable behavior of a named implementation. | Record release or commit and verification date. |
| 6 | `ATLAS-COMMUNITY` — `Knowledge Sources/Community Engineering` | Bounded observations or reports that do not independently establish a general mechanism. | Record author, publication revision, and retrieval date. |

## Verification Entry Points

| Bounded claim class | Registered Source ID | Stable verifier capability, evidence source, or semantic review criterion | Version pin or freshness window |
|---|---|---|---|
| Provider or project behavior | `ATLAS-OFFICIAL` | Apply K06/03 and K07/01–K07/04 to the exact `ATLAS-OFFICIAL` source location registered by Atlas. | Exact release or retrieval date. |
| Protocol, schema, security, or measurement requirement | `ATLAS-STANDARD` | Verify the original numbered section and document status. | Exact edition, draft, or section. |
| Scientific or quantitative result | `ATLAS-PAPER` | Verify method, sample, result, and limitation in the cited version. | Published or archive version; pin code and data when used. |
| Implementation behavior | `ATLAS-IMPLEMENTATION` | Verify the pinned source or a reproducible example. | Exact release or commit. |

## Staleness Triggers

| Observable change event | Bounded affected pages or claims |
|---|---|
| A source reaches its review date, disappears, or changes without a stable version pin. | The source record and claims that depend on it. |
| A provider changes an API, model, tool contract, policy, limit, or lifecycle state. | Provider-specific behavior and comparisons using that configuration. |
| A standard, paper, code release, or dataset is corrected, withdrawn, or superseded. | Claims and conclusions bound to that version. |
| An evaluation changes its sample, model, tools, policy, environment, grader, or aggregation. | The measurement and comparisons using the previous tested-system identity. |

## Domain-specific Comparison Rules

- Registration: None

| Condition | Additional profile rule |
|---|---|

## Provenance Extensions

- Registration: None

| Applicability / trigger | Additional provenance requirement | Recording target reference (Vocabulary field ID, body heading, or evidence path) |
|---|---|---|
