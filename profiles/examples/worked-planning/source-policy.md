# Source Policy

Interface: [Source Policy slot](../../README.md#source-policy-slot)

## Source Authority

| Rank | Stable Source ID and exact location | Bounded canonical claim/content class | Version/release/commit, or retrieval date if unversioned |
|---|---|---|---|
| 1 | `hub-service-manual` — the manufacturer service manual held in the workshop for each stocked hub family. | Torque figures, preload rules, and the published service sequence for that hub family. | The revision printed on the manual's cover. |
| 2 | `rim-tech-sheet` — the rim manufacturer's technical sheet for a stocked rim. | Published maximum spoke tension and the rim's effective diameter. | The sheet's publication date. |
| 3 | `bench-measurement` — a measurement retained on a completed service case. | What was actually observed on one wheel on one date. | The service date recorded on the case page. |

## Verification Entry Points

| Bounded claim class | Registered Source ID | Verifier command, path, URL, or procedure | Version pin or freshness window |
|---|---|---|---|
| A torque or preload figure quoted by a procedure page. | `hub-service-manual` | Open the manual revision named on the page and read the figure from its own table. | Re-check whenever a newer revision reaches the workshop. |
| A maximum-tension figure used to derive a working range. | `rim-tech-sheet` | Read the published maximum from the sheet for that exact rim model. | Re-check per rim model when stock changes. |
| A claim about how long a service takes. | `bench-measurement` | Read the retained bench time from the cited service case. | 24 months. |

## Staleness Triggers

| Observable change event | Bounded affected pages or claims |
|---|---|
| A newer service manual revision reaches the workshop. | Every quoted torque or preload figure whose page names the superseded revision, and every service case whose parts or tooling assumptions came from it. |
| A new rim model enters stock. | The working range on the spoke tension page and any capability whose evidence depends on it. |

## Domain-specific Comparison Rules

- Registration: Configured

| Condition | Additional profile rule |
|---|---|
| A retained bench measurement disagrees with a published figure. | The published figure stays canonical; the measurement is retained with its date and the disagreement is recorded as a gap candidate rather than silently resolved. |
| Two held document revisions give different figures for the same hub family. | The newer revision is canonical from its arrival date; pages quoting the older revision are listed for re-check before the newer figure is adopted. |

## Provenance Extensions

- Registration: None

| Applicability / trigger | Additional provenance requirement | Recording target reference (Vocabulary field ID, body heading, or evidence path) |
|---|---|---|
