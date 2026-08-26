# Scope And Architecture

Interface: [Kernel-owned Profile interface](../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Profile Scope slot

## Goal

| Knowledge-base goal (one sentence) | Intended reader role(s) |
|---|---|
| Keep one maintainer's working notes on home-network operation findable, current, and safe to act on a year later. | The single maintainer who owns the network. |

## Content Priority Factors

| Rank | Ranked content-priority factor |
|---:|---|
| 1 | The note is needed while something is broken. |
| 2 | The note records a decision whose reason is otherwise unrecoverable. |
| 3 | Everything else in scope. |

## Excluded Scope

| Bounded excluded content (`None — no exclusions` allowed) | Destination or handling (`Not applicable` when none) |
|---|---|
| None — no exclusions | Not applicable |

## Logical Architecture

Use exact repository-relative directory paths without trailing slashes. Separate multiple directories in one layer with semicolons.

| Stable Layer ID | Repository-relative directories | Single layer responsibility |
|---|---|---|
| L-NOTES | Notes | Own every canonical note, including the dated scratch entries under `Notes/Daily Log`. |

## Knowledge Spine

| Page-to-page organizing logic / Knowledge Spine | Field or statement locating each page on that spine |
|---|---|
| One page per device, service, or recurring procedure; each page names the device or service it depends on. | The `depends_on` sentence in the page's opening paragraph. |

## Placement Layer Registrations

Layer roles bind a registered Layer ID; an unused role uses `None` plus its fallback Layer ID. The expression role uses a testable predicate, or `always false` when unused.

| Kernel role | Binding type | Registered binding or inactive form |
|---|---|---|
| `Shared Foundation Layer` | Layer ID | L-NOTES |
| `Production Systems Layer` | Layer ID | None — fallback L-NOTES |
| `Cross-domain Concepts Layer` | Layer ID | None — fallback L-NOTES |
| `Expression Layer Predicate` | Predicate | always false |
| `Case Study Layer` | Layer ID | None — fallback L-NOTES |
| `Source Note Layer` | Layer ID | None — fallback L-NOTES |
| `Research Synthesis Layer` | Layer ID | None — fallback L-NOTES |

## New Page Placement Rule

| Order | Testable page predicate | Registered target Layer ID |
|---:|---|---|
| 1 | The page is a dated entry whose title starts with an ISO date. | L-NOTES |
| Last | Otherwise | L-NOTES |

## Terminology Structure

| Bounded term class | Registered target Layer ID | Inclusion/exclusion boundary |
|---|---|---|
| Device and service names used in more than one note. | L-NOTES | Included when the name is ambiguous across vendors; excluded when the vendor's own documentation is the only reader-facing form. |

## Foundation Depth Requirements

| Bounded foundation page class | Testable completeness predicate |
|---|---|
| A page describing a device or service the maintainer must restore. | The page names the device, its current firmware or version, where its configuration backup lives, and the one command or screen used to verify it is working. |

## Production System Reasoning Applicability

- Applicability: Not applicable — this vault documents one household network; it records no production system whose failure, cost, or scaling behaviour would need separate reasoning.

| Page predicate covered by production-system reasoning |
|---|

## Representative Sample Plan

- Applicability: Not applicable — the vault holds fewer than fifty pages and is reviewed in full, so no sample stands in for the whole.

| Note type | Selection predicate |
|---|---|

## Dependency-ordered Build Sequence

- Applicability: Not applicable — notes are written one at a time when the underlying change happens; there is no bulk build with ordered stages.

| Order | Stage | Depends on | Output |
|---:|---|---|---|
