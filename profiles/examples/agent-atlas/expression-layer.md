# Expression Layer

Interface: [Expression Layer Entry slot](../../README.md#expression-layer-entry-slot)

## Registered Artifacts

- Registration: Configured

### Artifact: Interview Card

| Property | Value |
|---|---|
| Stable artifact ID | `agent-atlas-interview-card` |
| Artifact role/type | `interview-card` |
| Reader-facing display label | Interview Card |
| Entry point (target-corpus relative) | `Interview Preparation/Topic Cards/` |
| Profile-rule owner | `profiles/examples/agent-atlas/interview/interview-content-standard.md#Interview Card` |
| Existing canonical dependency-map path | `Interview Preparation/Interview Overview.md` |
| Testable regeneration/invalidation predicate | Re-evaluate every bound card when its canonical owner, `interview_card` mapping, supporting evidence, answer-level contract, or acceptance predicate changes. |
| Vocabulary Extensions readiness-field ID | `interview_status` |
| Routing/Gate Registry supplemental Gate ID | `P:agent-atlas:interview-readiness` |

### Artifact: Interview Roadmap

| Property | Value |
|---|---|
| Stable artifact ID | `agent-atlas-interview-roadmap` |
| Artifact role/type | `roadmap` |
| Reader-facing display label | Interview Roadmap |
| Entry point (target-corpus relative) | `Interview Preparation/Roadmaps/` |
| Current pre-adoption target-corpus paths | `Agent Knowledge/Agent Interview Roadmap.md`; `Deep Learning Knowledge/DL Interview Roadmap.md`; `LLM Knowledge/LLM Interview Roadmap.md`; `Machine Learning Knowledge/ML Interview Roadmap.md` |
| Profile-rule owner | `profiles/examples/agent-atlas/interview/roadmap-and-cheat-sheet.md#Interview Roadmap` |
| Existing canonical dependency-map path | `Interview Preparation/Interview Overview.md` |
| Testable regeneration/invalidation predicate | Re-evaluate an affected roadmap when its ordered topic set, prerequisite graph, or linked Interview Card inventory changes. |
| Vocabulary Extensions readiness-field ID | `None` |
| Routing/Gate Registry supplemental Gate ID | `None` |

## Terminology Extraction Extension

For a proper noun, satisfying the profile's independent-Card predicate in [[profiles/examples/agent-atlas/interview/card-granularity-and-readiness#Card Granularity|Card Granularity]] is an additional reason to consider a standalone Term Note under [[kernel/K05 Terminology/01 Terminology Extraction#Extraction Criteria|K05/01 Terminology Extraction]]. The Card still does not own the term's definition, and this trigger does not bypass the kernel's Do Not Extract or terminology-acceptance rules.

### Artifact: Interview Cheat Sheet

| Property | Value |
|---|---|
| Stable artifact ID | `agent-atlas-interview-cheat-sheet` |
| Artifact role/type | `cheat-sheet` |
| Reader-facing display label | Interview Cheat Sheet |
| Entry point (target-corpus relative) | `Interview Preparation/Cheat Sheets/` |
| Current pre-adoption target-corpus paths | `Agent Knowledge/Agent Basics Cheat Sheet.md`; `LLM Knowledge/LLM Basics Cheat Sheet.md`; `Machine Learning Knowledge/Algorithms/ML Algorithms Checklist.md` |
| Profile-rule owner | `profiles/examples/agent-atlas/interview/roadmap-and-cheat-sheet.md#Interview Cheat Sheet` |
| Existing canonical dependency-map path | `Interview Preparation/Interview Overview.md` |
| Testable regeneration/invalidation predicate | Re-evaluate an affected cheat sheet when a summarized canonical owner, linked card, or high-priority retrieval route changes. |
| Vocabulary Extensions readiness-field ID | `None` |
| Routing/Gate Registry supplemental Gate ID | `None` |
