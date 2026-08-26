# Routing And Gate Registry

Interface: [Kernel-owned Profile interface](../../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Routing And Gate Registry slot

## Supplemental Routes

- Registration: None

| Profile route ID: `P:<profile_id>:<route_name>` | Kernel route ID reference | Repo-relative Profile Read Set path |
|---|---|---|

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
| `agent-atlas-profile-wide-interview-acceptance` | A terminal or release claim declares the Agent Systems Atlas Interview layer profile-wide complete. | Apply `profiles/examples/agent-atlas/registries/audit-dimensions.md#Profile-wide Interview Acceptance`, including the latest residual-scan evidence. | Reuse only still-valid canonical content, source, link, residual, and coverage receipts whose fingerprints cover the complete in-scope snapshot; never infer profile-wide Interview acceptance from a Card-level or other status-axis verdict. |

## Batch Review Requirements

- Registration: Configured

| Judgment Item ID reference | Target selector: `each-manifest-page` or `batch` | Trigger: `before-merge-ready` | Producer kind: `manual-attestation` | Receipt schema | Pass-authority Role ID reference |
|---|---|---|---|---|---|
| `agent-atlas-content-form-classification` | `each-manifest-page` | `before-merge-ready` | `manual-attestation` | `page-batch-judgment-v1` | `content-reviewer` |

## Extension Gates

- Registration: Configured

| Gate ID | Kernel Gate ID or repo-relative owner path, optionally `#heading` | Blocked transition/action ID | Pass-authority Role ID reference | Applicability predicate | Vocabulary field ID or `None` | Registered completion value(s) or `None` | Judgment Item ID reference | Producer kind: `deterministic` or `manual-attestation` | Producer capability | Receipt schema | Consumer capability |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `P:agent-atlas:interview-readiness` | `kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance.md#Acceptance Criteria` | `interview-readiness-promotion` | `interview-reviewer` | Any registered Interview Card or bound canonical topic requesting readiness promotion. | `interview_status` | `interview-ready` | `agent-atlas-interview-readiness-acceptance` | `manual-attestation` | `manual-attestation-v1` | `manual-gate-attestation-v1` | `typed-metadata-transition-v1` |
