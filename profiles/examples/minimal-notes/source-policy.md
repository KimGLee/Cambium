# Source Policy

Interface: [Kernel-owned Profile interface](../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Source Policy slot

## Source Authority

| Rank | Stable Source ID and exact location | Bounded canonical claim/content class | Version/release/commit, or retrieval date if unversioned |
|---|---|---|---|
| 1 | `router-vendor-docs` — the router vendor's published administration manual for the installed model. | Supported settings, default values, and factory-reset behaviour of the router. | Manual revision printed on the document's cover page. |
| 2 | `device-observation` — what the maintainer observed on the device itself. | The configuration and firmware version actually running at home. | Retrieval date recorded in the note's opening paragraph. |

## Verification Entry Points

| Bounded claim class | Registered Source ID | Stable verifier capability, evidence source, or semantic review criterion | Version pin or freshness window |
|---|---|---|---|
| A claim about a router setting's default value. | `router-vendor-docs` | Open the manual revision named in the note and read the settings table for that field. | Re-check when the manual revision on the vendor site differs from the one recorded. |
| A claim about what is currently running at home. | `device-observation` | Log in to the device and read the status screen named in the note. | 180 days. |

## Staleness Triggers

| Observable change event | Bounded affected pages or claims |
|---|---|
| A firmware update is installed on any device. | Every claim on that device's page about versions, defaults, or verification screens. |
| The internet provider replaces the modem or changes the service plan. | The pages for the modem, the router, and any note whose verification step crosses the provider link. |

## Domain-specific Comparison Rules

- Registration: None

| Condition | Additional profile rule |
|---|---|

## Provenance Extensions

- Registration: None

| Applicability / trigger | Additional provenance requirement | Recording target reference (Vocabulary field ID, body heading, or evidence path) |
|---|---|---|
