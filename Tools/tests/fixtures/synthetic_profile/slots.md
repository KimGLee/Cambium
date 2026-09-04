# Synthetic Slot Fixture

This file is the resolved test-only binding for slots whose domain semantics are outside the runtime and Terminal Proof tests.

## Logical Architecture

| Stable Layer ID | Repository-relative directories | Single layer responsibility |
|---|---|---|
| L-TOPICS | Topics | Own the synthetic knowledge pages exercised by runtime tests. |

## Foundation Depth Requirements

| Bounded foundation page class | Testable completeness predicate |
|---|---|
| Synthetic knowledge page | A synthetic page has a title and one non-empty body paragraph. |

## Registered Artifacts

- Registration: None

| Stable artifact ID | Artifact type | Reader-facing label | Entry point | Dependency-map path or `None` | Metadata binding field ID(s) or `None` | Revalidation trigger | Contract reference (Profile path with `#heading`) | Readiness field ID or `None` |
|---|---|---|---|---|---|---|---|---|

## Extension Dimensions

The Terminal Proof gate reads this block to enumerate the receipt dimensions a Proof must account for, so it is stated explicitly even where the fixture registers nothing: an absent block is an unreadable registry, not an empty one.

- Registration: None

| Dimension ID | Target list(s): `review`, `receipt`, or `review + receipt` | Meaning |
|---|---|---|

## Judgment Items

| Stable Judgment Item ID | Base or registered receipt Dimension ID | Exact kernel audit-layer name | Bounded audit object one run proves | Evidence role: `emits`, `consumes`, or `triggers` | Predicate owner (repo-relative path; optional `#heading`) |
|---|---|---|---|---|---|
| `test-profile-foundation-depth` | `content_and_depth` | `Single Note Review` | One synthetic page satisfies the fixture depth predicate. | `emits` | `profiles/test-profile/scope-and-architecture.md#Foundation Depth Requirements` |
| `test-profile-residual-disposition` | `coverage_and_integration` | `Batch Review` | Every synthetic residual candidate has a disposition. | `emits` | `profiles/test-profile/registries/audit-dimensions.md#Residual Disposition` |

## Residual Disposition

The fixture accepts no production candidate; any candidate must be removed or recorded as an intentional fixture exception before the batch closes.

## Synthetic Predicate

A synthetic page has a title and one non-empty body paragraph. This unbound heading exists only for unit tests that deliberately register a temporary Profile-owned reference.

## Scan Registrations

| Stable Scan ID | Activation role | Whole-corpus scope/root | Verifier capability ID | Profile configuration reference or `None` | Candidate predicate/boundary | Judgment Item ID reference |
|---|---|---|---|---|---|---|
| `test-profile-residuals` | `K12/09 item 6 — residual-content scan` | Run once from the repository root. | `residual-content-scan-v1` | `profiles/test-profile/scan-configs/residual-scan.yaml` | A synthetic scratch heading outside the accepted root is a candidate. | `test-profile-residual-disposition` |

## Extension Gates

- Registration: None

| Gate ID | Kernel Gate ID or repo-relative owner path, optionally `#heading` | Blocked transition/action ID | Pass-authority Role ID reference | Applicability predicate | Vocabulary field ID or `None` | Registered completion value(s) or `None` | Judgment Item ID reference | Producer kind: `deterministic` or `manual-attestation` | Producer capability | Receipt schema | Consumer capability |
|---|---|---|---|---|---|---|---|---|---|---|---|

## Priority Quota

- Registration: None

| Class | Maximum corpus share | Rationale |
|---|---|---|
