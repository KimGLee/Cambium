# Scope And Architecture

Interface: [Profile Scope slot](../../README.md#profile-scope-slot)

## Goal

| Knowledge-base goal (one sentence) | Intended reader role(s) |
|---|---|
| Build a Chinese-first, source-traceable knowledge corpus that lets readers explain, design, evaluate, operate, and defend Agent and LLM systems from foundations through production. | Agent / LLM Systems Engineer candidates, working engineers, and reviewers of production AI systems. |

## Content Priority Factors

| Rank | Ranked content-priority factor |
|---:|---|
| 1 | A prerequisite or control boundary whose absence prevents an end-to-end Agent or Harness capability from being designed, executed, verified, or recovered. |
| 2 | Production behavior that determines correctness, reliability, evaluation validity, security, latency, cost, capacity, or incident diagnosis. |
| 3 | Modeling, ML, DL, LLM, Retrieval, or RAG foundations needed to explain why an Agent-system behavior occurs. |
| 4 | A target-role competency that must be explained and defended in a system-design or project interview. |
| 5 | Evidence that reconciles multiple modules, sources, implementations, or cases without creating a second canonical mechanism owner. |

## Excluded Scope

| Bounded excluded content (`None — no exclusions` allowed) | Destination or handling (`Not applicable` when none) |
|---|---|
| `Archive/` | Historical material is not an active owner. Re-admit an item only through an explicit intake or migration task into a registered active layer. |
| `.obsidian/` | Knowledge-host and UI configuration; keep under the registered host/UI role and outside canonical content decisions. |
| Embedded standards snapshots, including `Knowledge Base Standards/` | Not an Atlas knowledge layer. Active governance loads the Cambium kernel plus the selected profile; keep any snapshot outside the active corpus. |
| `Python Algorithm Agent Training/` | Standalone training curriculum. It enters Agent Systems Atlas only through a later profile-scope revision with explicit owners and placement. |
| `.DS_Store` and other host-generated filesystem metadata | Delete or ignore; never treat as corpus content or evidence. |

## Logical Architecture

| Stable Layer ID | Repository-relative directories | Single layer responsibility |
|---|---|---|
| `L-FOUNDATION` | `Modeling Fundamentals`; `Machine Learning Knowledge`; `Deep Learning Knowledge`; `LLM Knowledge` | Own reusable mathematical, data, model, training, inference, retrieval, and grounding mechanisms independent of one Agent implementation. |
| `L-AGENT` | `Agent Knowledge` | Own Agent decision loops and Harness contracts for context, state, memory, tools, policy, coordination, verification, and recovery. |
| `L-PRODUCTION` | `AI Systems Engineering` | Own deployable cross-component systems, evaluation infrastructure, operations, reliability, safety, capacity, cost, and evidence paths. |
| `L-CASES` | `Industry Cases` | Reconstruct bounded real systems from evidence while separating reported facts, inference, and recommendations. |
| `L-SOURCES` | `Knowledge Sources` | Preserve one external source's identity, claims, evidence, limitations, and verification state without owning the general mechanism. |
| `L-SYNTHESIS` | `Research Synthesis` | Reconcile claims from multiple sources and route stable conclusions to their canonical owners. |
| `L-INTERVIEW` | `Interview Preparation` | Derive Interview Cards, Roadmaps, and Cheat Sheets from canonical knowledge for spoken recall and review. |

## Interview Layer Organization

The registered `L-INTERVIEW` layer uses this internal organization:

```text
Interview Preparation/
├── Interview Overview.md
├── Roadmaps/
├── Topic Cards/
│   ├── Modeling/
│   ├── Machine Learning/
│   ├── Deep Learning/
│   ├── LLM/
│   ├── Agent/
│   └── AI Systems Engineering/
└── Cheat Sheets/
```

## Knowledge Spine

| Page-to-page organizing logic / Knowledge Spine | Field or statement locating each page on that spine |
|---|---|
| Foundations → model behavior → Agent decision → Harness control and execution → production system → evaluation, recovery, and outcome. Source Notes and Research Synthesis feed evidence into this spine; cases and interview artifacts consume it. | The page's relative directory identifies its layer; `domain`, `type`, and `scope` identify its role; `prerequisites` and explicit owner links identify its upstream and downstream position. |

## Placement Layer Registrations

| Kernel role | Binding type | Registered binding or inactive form |
|---|---|---|
| `Shared Foundation Layer` | Layer ID | `L-FOUNDATION` |
| `Production Systems Layer` | Layer ID | `L-PRODUCTION` |
| `Cross-domain Concepts Layer` | Layer ID | `None` — fallback `L-FOUNDATION`; place the concept with the closest reusable mechanism owner. |
| `Expression Layer Predicate` | Predicate | The page has `type: interview-card`, `roadmap`, or `cheat-sheet` and either lives under `Interview Preparation/` or is one of the pre-adoption Roadmap/Cheat Sheet paths registered in `profiles/examples/agent-atlas/expression-layer.md`. |
| `Case Study Layer` | Layer ID | `L-CASES` |
| `Source Note Layer` | Layer ID | `L-SOURCES` |
| `Research Synthesis Layer` | Layer ID | `L-SYNTHESIS` |

## New Page Placement Rule

This table places corpus content. The three durable planning files use the
exact paths bound by [Corpus Planning](corpus-planning.yaml)
and are maintained through R13; they are not a logical knowledge layer or a
fallback destination. Cambium runtime state is written only under `.cambium/`
and does not enter the content-placement sequence.

| Order | Testable page predicate | Registered target Layer ID |
|---:|---|---|
| 1 | The page records one external source and has `type: source-note`. | `L-SOURCES` |
| 2 | The page reconciles two or more sources and has `type: research-synthesis`. | `L-SYNTHESIS` |
| 3 | The registered Expression Layer Predicate is true. | `L-INTERVIEW` |
| 4 | The page reconstructs a bounded deployed system and has `type: case-study`. | `L-CASES` |
| 5 | The page owns production infrastructure, cross-component integration, evaluation operations, reliability, safety, cost, or capacity. | `L-PRODUCTION` |
| 6 | The page owns Agent decision behavior or a Harness contract for context, state, memory, tools, policy, coordination, verification, or recovery. | `L-AGENT` |
| 7 | The page owns a reusable modeling, ML, DL, LLM, retrieval, or grounding mechanism. | `L-FOUNDATION` |
| Last | Otherwise, record an unadmitted semantic candidate in the bound [Gap Register](corpus-planning.yaml); do not create an unowned content page until R13 resolves a canonical owner in a registered layer. | `None — placement blocked pending R13 admission` |

## Terminology Structure

| Bounded term class | Registered target Layer ID | Inclusion/exclusion boundary |
|---|---|---|
| Mathematical, statistical, data, evaluation, training, inference, retrieval, or grounding term reused outside one Agent implementation | `L-FOUNDATION` | Include only when a stable definition or mechanism needs a reusable owner; aliases alone do not justify a page. |
| Agent decision, Harness runtime, memory, tool, policy, coordination, or recovery term | `L-AGENT` | Include the Agent/Harness contract; production deployment details remain in `L-PRODUCTION`. |
| Deployment, observability, reliability, security, capacity, cost, or production-evaluation term | `L-PRODUCTION` | Include cross-component operational semantics; do not duplicate a foundational or Agent mechanism. |

## Foundation Depth Requirements

| Bounded foundation page class | Testable completeness predicate |
|---|---|
| Mathematical or statistical mechanism | Defines symbols and assumptions, states the governing relation, works one numerical or concrete example, and names at least one boundary or failure condition. |
| ML or DL mechanism | Explains the training or inference mechanism, required data/state, evaluation method, failure modes, and a criterion for choosing it over an alternative. |
| LLM, Retrieval, or RAG mechanism | Explains the source of observed behavior, configuration or state contract, grounding/evaluation boundary, and at least one diagnosable failure path; a tool list alone fails. |
| Agent or Harness page consuming foundations | Links every required foundation owner and adds only the Agent-system context, interfaces, state changes, controls, and failures that the foundation owner does not own. |

## Production System Reasoning Applicability

- Applicability: Configured

| Page predicate covered by production-system reasoning |
|---|
| A P0 or P1 page under `Agent Knowledge/`, `AI Systems Engineering/`, or `Industry Cases/` that claims an executable system path, deployment behavior, metric, control, side effect, or recovery outcome. |

## Representative Sample Plan

- Applicability: Configured

| Note type | Selection predicate |
|---|---|
| Modeling foundation | One P0/P1 page that must satisfy the mathematical/statistical foundation predicate. |
| ML or DL mechanism | One page with a visible training/inference state boundary and an evaluable failure mode. |
| LLM, Retrieval, or RAG mechanism | One page connecting model behavior to a grounded or typed system interface. |
| Agent/Harness canonical page | One P0 control-path owner spanning intent, execution, evidence, and recovery. |
| Production system design | One P0/P1 page with interfaces, state, observability, capacity, security, and rollback decisions. |
| Source-to-synthesis pair | One Source Note and one Research Synthesis that demonstrate claim extraction, comparison, and canonical routing. |
| Industry case | One case with explicit reported-fact, inference, recommendation, and evidence-gap boundaries. |
| Interview artifact | One mapped Interview Card whose answers resolve to accepted canonical owners. |

## Dependency-ordered Build Sequence

- Applicability: Configured

| Order | Stage | Depends on | Output |
|---:|---|---|---|
| 1 | Architecture and inventory | None | Registered layer map, current inventory, and the bound [Global Map, Capability Matrix, and Gap Register](corpus-planning.yaml). |
| 2 | Representative foundations | 1 | Accepted samples for modeling, ML/DL, and LLM/Retrieval depth. |
| 3 | Agent and Harness vertical slice | 2 | One end-to-end decision, execution, verification, and recovery chain. |
| 4 | Exposed prerequisite repair | 3 | Missing canonical foundations closed before downstream expansion. |
| 5 | Production systems integration | 3, 4 | Deployable system path with evaluation, operations, security, cost, and capacity. |
| 6 | Evaluation, reliability, safety, and governance | 5 | Cross-cutting evidence and control owners connected to the production path. |
| 7 | Sources, synthesis, and cases | 4, 5, 6 | Traceable evidence intake, cross-source conclusions, and bounded case reasoning. |
| 8 | Interview integration | 2 through 7 | Cards, Roadmaps, and Cheat Sheets derived from accepted canonical owners. |
