# Routing And Gate Registry

Interface: [Routing And Gate Registry slot](../../../README.md#routing-and-gate-registry-slot)

## Supplemental Routes

- Registration: Configured

| Profile route ID: `P:<profile_id>:<route_name>` | Kernel route ID reference | Repo-relative Profile Read Set path |
|---|---|---|
| `P:agent-atlas:interview-content` | `R05` | `profiles/examples/agent-atlas/interview/interview-content-read-set.md` |

## Additional L-tier Triggers

- Registration: Configured

| Testable materiality predicate | Why full L-tier review is required |
|---|---|
| The work creates, migrates, or jointly reviews an Interview Card set spanning more than one canonical topic. | The change crosses artifact, canonical-owner, evidence, navigation, and readiness boundaries. |
| The work creates or materially changes a System Design or Project Deep Dive Interview Card. | Its multi-level evidence chain, bilingual answer, failure analysis, scoring signals, and project claims require the full review path. |

## Specialized Audit Invariants

- Registration: Configured

| Judgment Item ID reference | Applicability / trigger predicate | Verification procedure or existing Scan/receipt-source reference | Evidence-reuse predicate/boundary |
|---|---|---|---|
| `agent-atlas-profile-wide-interview-acceptance` | A terminal or release claim declares the Agent Systems Atlas Interview layer profile-wide complete. | Apply `profiles/examples/agent-atlas/interview/interview-review-and-acceptance.md#Profile-wide Interview Acceptance` through `P:agent-atlas:interview-content`, including the latest residual-scan evidence. | Reuse only still-valid canonical content, source, link, residual, and coverage receipts whose fingerprints cover the complete in-scope snapshot; never infer profile-wide Interview acceptance from a Card-level or other status-axis verdict. |

## Extension Gates

- Registration: Configured

| Gate ID | Kernel Gate ID or repo-relative owner path, optionally `#heading` | Blocked transition/action | Pass-authority Role ID reference | Applicability predicate | Vocabulary field ID or `None` | Registered completion value(s) or `None` | Judgment Item ID reference |
|---|---|---|---|---|---|---|---|
| `P:agent-atlas:interview-readiness` | `kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance.md#Acceptance Criteria` | Promote `interview_status` to `interview-ready`. | `interview-reviewer` | Any registered Interview Card or bound canonical topic requesting readiness promotion. | `interview_status` | `interview-ready` | `agent-atlas-interview-readiness-acceptance` |
