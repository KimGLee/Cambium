# Scope And Architecture

Kernel owner: K01 Scope and Architecture. Common slot identity is registered in the Kernel Profile interface.

## Goal

| Knowledge-base goal (one sentence) | Intended reader role(s) |
|---|---|
| Build a Chinese-first, source-traceable knowledge base for understanding, designing, evaluating, operating, and explaining Agent and LLM systems. | Agent and LLM Systems Engineer candidates, working engineers, and technical reviewers. |

## Content Priority Factors

| Rank | Ranked content-priority factor |
|---:|---|
| 1 | Knowledge required to design, execute, verify, or recover an end-to-end Agent or LLM system. |
| 2 | Foundations and source evidence needed to explain the system's behavior, limits, and tradeoffs. |
| 3 | Everything else in scope. |

## Excluded Scope

| Bounded excluded content (`None — no exclusions` allowed) | Destination or handling (`Not applicable` when none) |
|---|---|
| `Archive/` | Historical material; re-admit only through a later confirmed task. |
| `.obsidian/` | Knowledge-host configuration, not canonical knowledge content. |
| Embedded Cambium standards snapshots | Use the adopted public components instead of an in-corpus copy. |
| `Python Algorithm Agent Training/` | Separate training curriculum outside the current Atlas scope. |

## Logical Architecture

| Stable Layer ID | Repository-relative directories | Single layer responsibility |
|---|---|---|
| `L-FOUNDATION` | `Modeling Fundamentals`; `Machine Learning Knowledge`; `Deep Learning Knowledge`; `LLM Knowledge` | Reusable mathematical, data, model, training, inference, retrieval, and grounding knowledge. |
| `L-AGENT` | `Agent Knowledge` | Agent behavior and execution-system knowledge. |
| `L-PRODUCTION` | `AI Systems Engineering` | Production architecture, evaluation, operations, reliability, safety, cost, and capacity. |
| `L-CASES` | `Industry Cases` | Bounded real-system cases and their evidence. |
| `L-SOURCES` | `Knowledge Sources` | External-source records and their bounded claims. |
| `L-SYNTHESIS` | `Research Synthesis` | Cross-source comparison and synthesis. |
| `L-INTERVIEW` | `Interview Preparation` | Reader-facing interview preparation derived from canonical knowledge. |

## Knowledge Spine

| Page-to-page organizing logic / Knowledge Spine | Field or statement locating each page on that spine |
|---|---|
| Foundations → model behavior → Agent behavior → production system → evaluation and recovery; sources and synthesis supply evidence, while cases and interview artifacts consume it. | Repository-relative directory identifies the layer; page metadata and explicit links identify the page role and dependencies. |

## Placement Layer Registrations

| Kernel role | Binding type | Registered binding or inactive form |
|---|---|---|
| `Shared Foundation Layer` | Layer ID | `L-FOUNDATION` |
| `Production Systems Layer` | Layer ID | `L-PRODUCTION` |
| `Cross-domain Concepts Layer` | Layer ID | None — fallback `L-FOUNDATION` |
| `Expression Layer Predicate` | Predicate | The page is an Interview Topic Guide, Roadmap, or Cheat Sheet under `Interview Preparation`. |
| `Case Study Layer` | Layer ID | `L-CASES` |
| `Source Note Layer` | Layer ID | `L-SOURCES` |
| `Research Synthesis Layer` | Layer ID | `L-SYNTHESIS` |

## New Page Placement Rule

| Order | Testable page predicate | Registered target Layer ID |
|---:|---|---|
| 1 | The page records one external source. | `L-SOURCES` |
| 2 | The page synthesizes two or more sources. | `L-SYNTHESIS` |
| 3 | The Expression Layer Predicate is true. | `L-INTERVIEW` |
| 4 | The page is a bounded real-system case. | `L-CASES` |
| 5 | The page owns production architecture or operation. | `L-PRODUCTION` |
| 6 | The page owns Agent behavior or execution-system knowledge. | `L-AGENT` |
| Last | Otherwise | `L-FOUNDATION` |

## Terminology Structure

| Bounded term class | Registered target Layer ID | Inclusion/exclusion boundary |
|---|---|---|
| Reusable modeling, ML, DL, LLM, retrieval, or grounding terms | `L-FOUNDATION` | Include when a stable definition or mechanism needs a reusable owner. |
| Agent behavior or execution-system terms | `L-AGENT` | Include Agent-specific semantics; production deployment remains in `L-PRODUCTION`. |
| Production, evaluation, reliability, safety, cost, or capacity terms | `L-PRODUCTION` | Include cross-component operational semantics without duplicating foundation or Agent owners. |

## Foundation Depth Requirements

| Bounded foundation page class | Testable completeness predicate |
|---|---|
| Mathematical or statistical mechanism | Defines its terms and assumptions, explains the governing relation, gives a concrete example, and states a boundary or failure condition. |
| ML, DL, LLM, Retrieval, or RAG mechanism | Explains the mechanism, required inputs or state, evaluation method, failure modes, and when to use it. |
| Agent or execution-system mechanism | Explains its interfaces, state changes, controls, evidence, and recovery boundary. |

## Production System Reasoning Applicability

- Applicability: Configured

| Page predicate covered by production-system reasoning |
|---|
| A page under `Agent Knowledge`, `AI Systems Engineering`, or `Industry Cases` that claims an executable system path, operational behavior, metric, control, side effect, or recovery outcome. |

## Representative Sample Plan

- Applicability: Configured

| Note type | Selection predicate |
|---|---|
| Foundation | One page that exposes assumptions, mechanism, evaluation, and a failure boundary. |
| Agent or execution system | One page that connects intent, execution, evidence, and recovery. |
| Production system | One page that covers interfaces, state, observability, reliability, and rollback. |
| Source or synthesis | One source record and one synthesis that demonstrate claim traceability. |
| Interview artifact | One artifact that resolves to its canonical knowledge owners. |

## Dependency-ordered Build Sequence

- Applicability: Not applicable — Atlas is an existing corpus; work order belongs to each confirmed Task Plan rather than to the stable Profile.

| Order | Stage | Depends on | Output |
|---:|---|---|---|
