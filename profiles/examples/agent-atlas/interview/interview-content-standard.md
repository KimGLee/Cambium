# Interview Content Standard

## Purpose

This is the stable profile-owned entry for Agent Systems Atlas interview material. It defines the concrete Interview Card artifact, its corpus locations, and the Atlas-specific knowledge-binding shape. The cross-profile separation, evidence, status, linking, and migration floor remains owned by [[kernel/K11 Expression Layer Standard|K11 Expression Layer Standard]].

## Interview Card

The profile's [[profiles/examples/agent-atlas/expression-layer|Expression Layer Registry]] binds the registered Interview Card artifact to this section as its single profile-rule owner. The registry alone owns its stable ID, type, display label, and entry point. This section owns the Atlas-specific behavior: an Interview Card organizes a defensible spoken answer around knowledge already owned elsewhere in the corpus. The linked modules each own their named granularity, structure, deep-dive, navigation, or acceptance predicates; this section does not re-own them.

## Atlas Layout

The artifact family uses these corpus locations:

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

The concrete placement predicate and registered `Interview Preparation` layer remain in the profile's [[profiles/examples/agent-atlas/scope-and-architecture|Profile Scope]].

## Knowledge Binding

Each mapped canonical topic records its `interview_status` and an actual Interview Card reference. The Card identifies its supporting owners under `Core Knowledge Links（核心知识链接）`; the canonical page exposes its Card under `Interview Preparation`. The corpus-wide map is navigated from `Interview Preparation/Interview Overview.md`.

These names are Atlas bindings, not replacements for the resolvable, bidirectional, and evidence-maturity requirements in [[kernel/K11 Expression Layer/05 Expression Knowledge Binding|K11/05 Expression Knowledge Binding]]. A future corpus target is written as a plain path until it exists; it becomes a wiki link only after the target resolves.

## Existing Corpus Adoption Boundary

The current Agent Systems Atlas corpus predates this filled example. Its existing `interview_status` values, Card headings, and Roadmap/Cheat Sheet locations are migration inputs, not proof that this profile's current predicates have passed. If the example is materialized and selected as an active profile, the adopting revision re-evaluates affected Cards under the registered gate, migrates the named pre-adoption paths through K11/07, and records new receipts before claiming `interview-ready` or profile-wide acceptance. Existing content is not silently grandfathered, and migration never deletes an old answer or route before its target has been created and verified.

## Module Index

| Module | Canonical sections |
|---|---|
| [[profiles/examples/agent-atlas/interview/card-granularity-and-readiness\|Card Granularity And Readiness]] | `Card Granularity`, `Card Categories`, `Interview Readiness Values` |
| [[profiles/examples/agent-atlas/interview/card-structure-and-answer-levels\|Card Structure And Answer Levels]] | `Required Card Structure`, `Thirty-second Answer`, `Ninety-second Answer`, `Deep-dive Follow-ups` |
| [[profiles/examples/agent-atlas/interview/system-and-project-deep-dive\|System And Project Deep Dive]] | `Applicability`, `System Deep-dive Evidence Chain`, `Project Deep-dive Evidence Chain`, `Bilingual Answer Contract` |
| [[profiles/examples/agent-atlas/interview/roadmap-and-cheat-sheet\|Roadmap And Cheat Sheet]] | `Interview Roadmap`, `Interview Cheat Sheet` |
| [[profiles/examples/agent-atlas/interview/interview-review-and-acceptance\|Interview Review And Acceptance]] | `Interview Card Review`, `Interview Readiness Acceptance`, `Residual-content Disposition`, `Profile-wide Interview Acceptance` |

## Related

- [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer Read Set]]
- [[profiles/examples/agent-atlas/interview/interview-content-read-set|Agent Atlas Interview Content Read Set]]
- [[profiles/examples/agent-atlas/expression-layer|Agent Atlas Expression Layer]]
