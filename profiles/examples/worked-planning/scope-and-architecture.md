# Scope And Architecture

Interface: [Kernel-owned Profile interface](../../../kernel/K00%20Standards%20Control/profile-interface.yaml) — Profile Scope slot

## Goal

| Knowledge-base goal (one sentence) | Intended reader role(s) |
|---|---|
| Let any trained volunteer at a community bicycle workshop decide, perform, and stand behind a wheel service without asking the one person who has done it before. | Trained workshop volunteers, and the service lead who accepts their work. |

## Content Priority Factors

| Rank | Ranked content-priority factor |
|---:|---|
| 1 | A volunteer is standing at the bench with a member's wheel and needs the answer now. |
| 2 | The answer commits the workshop to a part order or to a figure it must stand behind. |
| 3 | The answer explains why an existing procedure is written the way it is. |

## Excluded Scope

| Bounded excluded content (`None — no exclusions` allowed) | Destination or handling (`Not applicable` when none) |
|---|---|
| Frame and fork structural repair. | Referred out; the workshop does not perform it and keeps no guidance for it. |
| Member records, membership fees, and rota scheduling. | The workshop's separate administrative system. |

## Logical Architecture

| Stable Layer ID | Repository-relative directories | Single layer responsibility |
|---|---|---|
| L-FOUNDATION | profiles/examples/worked-planning/corpus/Foundations | Own the concepts a service decision depends on, independent of any one procedure. |
| L-PROCEDURE | profiles/examples/worked-planning/corpus/Procedures | Own the bench procedures, each with its own finish condition. |
| L-CASES | profiles/examples/worked-planning/corpus/Service Cases | Own completed services as worked cases with retained measurements. |
| L-SOURCES | profiles/examples/worked-planning/corpus/Source Notes | Own which external documents are canonical and what each is canonical for. |

## Knowledge Spine

| Page-to-page organizing logic / Knowledge Spine | Field or statement locating each page on that spine |
|---|---|
| Concept, then procedure that applies it, then case that evidences it, with source notes naming what each figure is quoted from. | The Global Map entry's typed dependency edges; every page is the downstream end of at least one. |

## Placement Layer Registrations

| Kernel role | Binding type | Registered binding or inactive form |
|---|---|---|
| `Shared Foundation Layer` | Layer ID | L-FOUNDATION |
| `Production Systems Layer` | Layer ID | L-PROCEDURE |
| `Cross-domain Concepts Layer` | Layer ID | None — fallback L-FOUNDATION |
| `Expression Layer Predicate` | Predicate | always false |
| `Case Study Layer` | Layer ID | L-CASES |
| `Source Note Layer` | Layer ID | L-SOURCES |
| `Research Synthesis Layer` | Layer ID | None — fallback L-FOUNDATION |

## New Page Placement Rule

| Order | Testable page predicate | Registered target Layer ID |
|---:|---|---|
| 1 | The page records one completed service on one member's machine. | L-CASES |
| 2 | The page states what an external document is canonical for. | L-SOURCES |
| 3 | The page ends in a bench finish condition. | L-PROCEDURE |
| Last | Otherwise | L-FOUNDATION |

## Terminology Structure

| Bounded term class | Registered target Layer ID | Inclusion/exclusion boundary |
|---|---|---|
| Bearing families and wheel-geometry terms used by more than one procedure. | L-FOUNDATION | Included when two procedures depend on the same distinction; excluded when only one procedure uses the word and its meaning is local to that bench step. |

## Foundation Depth Requirements

| Bounded foundation page class | Testable completeness predicate |
|---|---|
| A page a procedure depends on for a decision. | The page states the distinction being made, how a volunteer observes it at the bench, what downstream decision changes because of it, and which source note is canonical for its published figures. |

## Production System Reasoning Applicability

- Applicability: Configured

| Page predicate covered by production-system reasoning |
|---|
| The page describes a bench procedure whose failure modes, tool dependencies, and finish condition must hold across volunteers and sessions. |

## Representative Sample Plan

- Applicability: Configured

| Note type | Selection predicate |
|---|---|
| Bench procedure | The procedure most recently run by a volunteer who had not run it before. |
| Service case | The most recent case whose retained measurements are cited as evidence by a capability. |

## Dependency-ordered Build Sequence

- Applicability: Configured

| Order | Stage | Depends on | Output |
|---:|---|---|---|
| 1 | Foundation concepts a decision depends on | Nothing | The distinctions every procedure page may assume. |
| 2 | Bench procedures with finish conditions | Stage 1 | Procedures a trained volunteer can follow unattended. |
| 3 | Source notes naming canonical documents | Stage 2 | Every quoted figure traced to a document revision. |
| 4 | Worked service cases with retained measurements | Stages 2 and 3 | Evidence that closes the capability's evidence requirement. |
