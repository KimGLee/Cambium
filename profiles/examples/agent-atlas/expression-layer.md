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
| Profile-rule owner | `profiles/examples/agent-atlas/expression-layer.md#Interview Card Contract` |
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
| Profile-rule owner | `profiles/examples/agent-atlas/expression-layer.md#Interview Roadmap` |
| Existing canonical dependency-map path | `Interview Preparation/Interview Overview.md` |
| Testable regeneration/invalidation predicate | Re-evaluate an affected roadmap when its ordered topic set, prerequisite graph, or linked Interview Card inventory changes. |
| Vocabulary Extensions readiness-field ID | `None` |
| Routing/Gate Registry supplemental Gate ID | `None` |

## Terminology Extraction Extension

For a proper noun, satisfying the profile's [[profiles/examples/agent-atlas/expression-layer#Card Granularity|independent-Card predicate]] is an additional reason to consider a standalone Term Note under [[kernel/K05 Terminology/01 Terminology Extraction#Extraction Criteria|K05/01 Terminology Extraction]]. The Card still does not own the term's definition, and this trigger does not bypass the kernel's Do Not Extract or terminology-acceptance rules.

### Artifact: Interview Cheat Sheet

| Property | Value |
|---|---|
| Stable artifact ID | `agent-atlas-interview-cheat-sheet` |
| Artifact role/type | `cheat-sheet` |
| Reader-facing display label | Interview Cheat Sheet |
| Entry point (target-corpus relative) | `Interview Preparation/Cheat Sheets/` |
| Current pre-adoption target-corpus paths | `Agent Knowledge/Agent Basics Cheat Sheet.md`; `LLM Knowledge/LLM Basics Cheat Sheet.md`; `Machine Learning Knowledge/Algorithms/ML Algorithms Checklist.md` |
| Profile-rule owner | `profiles/examples/agent-atlas/expression-layer.md#Interview Cheat Sheet` |
| Existing canonical dependency-map path | `Interview Preparation/Interview Overview.md` |
| Testable regeneration/invalidation predicate | Re-evaluate an affected cheat sheet when a summarized canonical owner, linked card, or high-priority retrieval route changes. |
| Vocabulary Extensions readiness-field ID | `None` |
| Routing/Gate Registry supplemental Gate ID | `None` |

## Interview Card Contract

This is the stable profile-owned rule entry for Agent Systems Atlas Interview Cards. It owns the concrete Card behavior and organization described below. The cross-profile separation, evidence, status, linking, and migration floor remains owned by [[kernel/K11 Expression Layer Standard|K11 Expression Layer Standard]]; corpus placement remains owned by the profile's [[profiles/examples/agent-atlas/scope-and-architecture|Profile Scope]], and bilingual answer parity remains owned by its [[profiles/examples/agent-atlas/language-contract#Bilingual Answer Contract|Language Contract]].

An Interview Card organizes a defensible spoken answer around knowledge already owned elsewhere in the corpus. The artifact registration above alone owns its stable ID, type, display label, and entry point.

### Knowledge Binding

Each mapped canonical topic records its `interview_status` and an actual Interview Card reference. The Card identifies its supporting owners under `Core Knowledge Links（核心知识链接）`; the canonical page exposes its Card under `Interview Preparation`. The corpus-wide map is navigated from `Interview Preparation/Interview Overview.md`.

These names are Atlas bindings, not replacements for the resolvable, bidirectional, and evidence-maturity requirements in [[kernel/K11 Expression Layer/05 Expression Knowledge Binding|K11/05 Expression Knowledge Binding]]. A future corpus target is written as a plain path until it exists; it becomes a wiki link only after the target resolves.

### Existing Corpus Adoption Boundary

The live Agent Systems Atlas corpus predates Cambium and has since completed a separate formal adoption of Cambium `3.0.0` using a materialized profile. That adoption does not make this example an adoption certificate or imply that every existing `interview_status` value, Card heading, or Roadmap/Cheat Sheet path satisfies the current profile predicates. Each affected object must be re-evaluated under the registered gate and migrated through K11/07 before the relevant `interview-ready` or profile-wide acceptance claim. Existing content is not silently grandfathered, and migration never deletes an old answer or route before its target has been created and verified.

### Card Granularity

Create an independent Interview Card when the topic satisfies at least one of these predicates:

- it is routinely assessed as a standalone interview topic and requires its own defensible answer;
- it produces at least three materially different follow-up branches;
- it has an independent mechanism, decision boundary, tradeoff, and failure surface;
- a complete 90-second answer cannot be incorporated into a neighboring Card without obscuring the topic's owner or evaluation boundary.

Combine topics in one Card when they are parameters of the same mechanism, are normally evaluated as one comparison, or would become fragmentary when separated. Every combined Card names all canonical topics it covers.

### Card Categories

| Category | Bounded responsibility |
|---|---|
| Concept Card | Explain and defend a concept, mechanism, algorithm, metric, comparison, or risk boundary. |
| System Design Card | Defend an end-to-end architecture, its contracts, state, evaluation, reliability, security, scale, and cost. |
| Project Deep Dive Card | Defend a real project or case through verifiable responsibility, decisions, evidence, outcomes, failures, and improvements. |

The category does not transfer ownership of definitions, mechanisms, metrics, or case facts from their canonical pages.

### Interview Readiness Values

`interview_status` is the Agent Systems Atlas expression-readiness field. Its complete value set is:

| Value | Meaning |
|---|---|
| `not-required` | The canonical topic does not require an independent Card; the record names the accepted combined Card or gives a bounded reason that no interview artifact is required. |
| `missing` | The topic requires interview expression coverage, but no target Card has been registered. |
| `mapped` | A target Card and reciprocal canonical binding resolve, but [[profiles/examples/agent-atlas/registries/audit-dimensions#Interview Readiness Acceptance|Interview Readiness Acceptance]] has not passed. |
| `interview-ready` | The mapped Card has passed Interview Readiness Acceptance under the registered gate and authority. |

No intermediate expression values are defined. Drafting progress stays in `authoring_status`; it never creates or advances `interview_status`. Status-axis independence is governed by [[kernel/K11 Expression Layer/02 Expression Coverage and Readiness|K11/02 Expression Coverage and Readiness]] and [[kernel/K08 Metadata and Status/03 Status Axes|K08/03 Status Axes]].

### Required Card Structure

Every Interview Card contains these reader-facing sections in this order, with category-specific additions after `Deep-Dive Follow-up Tree（深挖追问树）` when required:

```text
Scope（范围）
Knowledge Prerequisites（知识前置）
Core Knowledge Links（核心知识链接）
30-Second Answer（30 秒回答）
  English（英文回答）
  中文
90-Second Answer（90 秒回答）
  English（英文回答）
  中文
Deep-Dive Follow-up Tree（深挖追问树）
Follow-up Answers（追问答案）
Common Misconceptions（常见误解）
Strong Answer Signals（强回答信号）
Weak Answer Signals（弱回答信号）
Comparison Questions（比较类问题）
Scenario Questions（场景类问题）
Self-test Questions（自测问题）
Related Interview Cards（相关面试卡片）
```

### Thirty-second Answer

The 30-second answer identifies the topic, the problem it solves, its core mechanism or decision, and the main value or boundary. It is a direct answer, not an outline of sections to be covered later.

### Ninety-second Answer

The 90-second answer forms one coherent chain:

```text
Problem
→ Core mechanism
→ Main components or decision steps
→ Key tradeoff or failure boundary
→ Representative use case
```

It must remain supportable by the Card's canonical links and cannot introduce an unsupported claim merely to improve fluency.

### Deep-dive Follow-ups

A Card that is required for a P0 or P1 topic provides at least three levels of substantive follow-up. The branches test causes, assumptions, alternatives, failures, evidence, and production consequences; every posed follow-up has an answer or an explicitly bounded unknown. Scoring signals and self-test questions must distinguish a defensible answer from keyword recall.

### System And Project Deep Dive Applicability

The following evidence-chain requirements apply to every System Design Card and Project Deep Dive Card. A Concept Card uses them only when the Card claims an end-to-end system, production result, or personal project outcome.

### System Deep-dive Evidence Chain

A System Design Card covers each applicable item and marks a genuinely inapplicable item explicitly:

1. problem and measurable success criteria;
2. why an agent is needed and what the harness controls;
3. end-to-end execution path;
4. state ownership, persistence, and artifact boundaries;
5. coordination and handoff behavior;
6. tool, permission, and policy boundaries;
7. evaluation provenance and authoritative outcome evidence;
8. replay, regression, or backtesting strategy;
9. failure propagation, retry, rollback, and recovery;
10. observability and incident diagnosis;
11. latency, cost, capacity, and scale;
12. alternatives and rejected designs.

### Project Deep-dive Evidence Chain

A Project Deep Dive Card distinguishes verified project facts from the speaker's inference and covers:

- the business or user problem and the speaker's bounded responsibility;
- the initial constraints, baseline, and success measure;
- the architecture decision and rejected alternatives;
- the execution and evaluation artifacts supporting reported metrics;
- deployment, monitoring, failure, recovery, and follow-up changes;
- what the result does not prove and what would be improved next.

A source note or public case cannot be presented as personal project evidence. Quantitative claims remain traceable through the evaluation-provenance requirements in the profile's [[profiles/examples/agent-atlas/source-policy#Provenance Extensions|Source Policy]].

## Interview Roadmap

An Interview Roadmap orders preparation by prerequisites, role relevance, priority, and verification milestones. The canonical entry for new Roadmaps is `Interview Preparation/Roadmaps/`; the pre-adoption paths listed in the artifact registration above remain migration inputs until moved. Roadmaps link to both canonical knowledge and applicable Interview Cards. They may name a practice or review checkpoint, but they do not contain the complete answers owned by Cards.

A roadmap checkbox reports the learner's progress on that roadmap only. It does not promote `authoring_status`, `interview_status`, evidence maturity, or corpus completion; the governing progress semantics are [[kernel/K11 Expression Layer/06 Sequence and Progress Semantics|K11/06 Sequence and Progress Semantics]].

## Interview Cheat Sheet

An Interview Cheat Sheet is a compact retrieval aid whose canonical entry for new files is `Interview Preparation/Cheat Sheets/`; the pre-adoption paths listed in the artifact registration above remain migration inputs until moved. It may contain concise distinctions, decision cues, failure cues, formula reminders, and links to the canonical page and Interview Card. It does not own definitions, mechanisms, evidence, complete 30/90-second answers, or readiness decisions.

When a Cheat Sheet conflicts with a canonical owner or an accepted Card, it is stale and must be corrected from those owners; it is never used as the authority for resolving the conflict.

## Related

- [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer Read Set]]
