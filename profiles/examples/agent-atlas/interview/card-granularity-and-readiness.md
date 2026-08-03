# Card Granularity And Readiness

## Card Granularity

Create an independent Interview Card when the topic satisfies at least one of these predicates:

- it is routinely assessed as a standalone interview topic and requires its own defensible answer;
- it produces at least three materially different follow-up branches;
- it has an independent mechanism, decision boundary, tradeoff, and failure surface;
- a complete 90-second answer cannot be incorporated into a neighboring Card without obscuring the topic's owner or evaluation boundary.

Combine topics in one Card when they are parameters of the same mechanism, are normally evaluated as one comparison, or would become fragmentary when separated. Every combined Card names all canonical topics it covers.

## Card Categories

| Category | Bounded responsibility |
|---|---|
| Concept Card | Explain and defend a concept, mechanism, algorithm, metric, comparison, or risk boundary. |
| System Design Card | Defend an end-to-end architecture, its contracts, state, evaluation, reliability, security, scale, and cost. |
| Project Deep Dive Card | Defend a real project or case through verifiable responsibility, decisions, evidence, outcomes, failures, and improvements. |

The category does not transfer ownership of definitions, mechanisms, metrics, or case facts from their canonical pages.

## Interview Readiness Values

`interview_status` is the Agent Systems Atlas expression-readiness field. Its complete value set is:

| Value | Meaning |
|---|---|
| `not-required` | The canonical topic does not require an independent Card; the record names the accepted combined Card or gives a bounded reason that no interview artifact is required. |
| `missing` | The topic requires interview expression coverage, but no target Card has been registered. |
| `mapped` | A target Card and reciprocal canonical binding resolve, but [[profiles/examples/agent-atlas/interview/interview-review-and-acceptance#Interview Readiness Acceptance\|Interview Readiness Acceptance]] has not passed. |
| `interview-ready` | The mapped Card has passed Interview Readiness Acceptance under the registered gate and authority. |

No intermediate expression values are defined. Drafting progress stays in `authoring_status`; it never creates or advances `interview_status`. Status-axis independence is governed by [[kernel/K11 Expression Layer/02 Expression Coverage and Readiness|K11/02 Expression Coverage and Readiness]] and [[kernel/K08 Metadata and Status/03 Status Axes|K08/03 Status Axes]].
