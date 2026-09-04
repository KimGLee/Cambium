# Expression Layer

Kernel owner: K11 Expression Layer. Common slot identity is registered in the Kernel Profile interface.

## Registered Artifacts

- Registration: Configured

| Stable artifact ID | Artifact type | Reader-facing label | Entry point | Dependency-map path or `None` | Metadata binding field ID(s) or `None` | Revalidation trigger | Contract reference (Profile path with `#heading`) | Readiness field ID or `None` |
|---|---|---|---|---|---|---|---|---|
| `agent-atlas-interview-topic-guide` | `interview-topic-guide` | Interview Topic Guide | `Interview Preparation/Topic Guides` | `Interview Preparation/Interview Overview.md` | `interview_guide`, `canonical_bindings` | Its canonical knowledge binding or supporting evidence changes. | `profiles/examples/agent-atlas/expression-layer.md#Interview Topic Guide Contract` | `None` |
| `agent-atlas-interview-roadmap` | `roadmap` | Interview Roadmap | `Interview Preparation/Roadmaps` | `Interview Preparation/Interview Overview.md` | `canonical_bindings` | Its ordered topic set or prerequisite relation changes. | `profiles/examples/agent-atlas/expression-layer.md#Interview Roadmap Contract` | `None` |
| `agent-atlas-interview-cheat-sheet` | `cheat-sheet` | Interview Cheat Sheet | `Interview Preparation/Cheat Sheets` | `Interview Preparation/Interview Overview.md` | `canonical_bindings` | A summarized canonical owner changes. | `profiles/examples/agent-atlas/expression-layer.md#Interview Cheat Sheet Contract` | `None` |

## Artifact Contracts

The common Expression Layer rules in K11 continue to apply. The contracts below define only Atlas-specific reader-facing form and content boundaries.

### Interview Topic Guide Contract

An Interview Topic Guide organizes one interview topic, or one cohesive topic family, into concise answers and follow-up discussion.

Its reader-facing body must contain a topic boundary, navigation to the relevant canonical knowledge, a 30-second answer, a 90-second answer, and follow-up questions with actual answers. The 30-second and 90-second answers must each provide a Chinese version and an English version; follow-up answers are not required to be bilingual.

Prerequisites, related reading, misconceptions, answer-quality cues, practice prompts, comparisons, scenarios, project discussion, whiteboard material, formulas, and code are conditional content and appear only when useful for the topic. A separate source section is required only when the Guide introduces a factual claim or conclusion not already carried by the relevant canonical knowledge.

### Interview Roadmap Contract

An Interview Roadmap orders preparation topics and provides a navigational path to the relevant knowledge and Topic Guides. It contains sequencing and preparation guidance rather than complete topic answers or a declaration of learner completion.

### Interview Cheat Sheet Contract

An Interview Cheat Sheet provides compact retrieval cues and links for last-mile review. It contains prompts, keywords, distinctions, or other concise recall aids rather than complete explanations of the underlying knowledge.
