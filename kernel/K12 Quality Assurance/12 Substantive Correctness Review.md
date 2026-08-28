## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/11 Content-level Propagation|Content-level Propagation]].
- Next: [[kernel/K12 Quality Assurance/13 Visual Verification Escalation|Visual Verification Escalation]].

## Purpose

This module owns the review that an execution context other than the author performs on a drafted page, and the rules that stop that review from running forever. It is read by the author when dispatching the review before an L-tier page closes, by the independent reviewer as its whole instruction, and by the Terminal Audit when it grades its own findings on the same three levels. It decides whether a page's reasoning holds against its sources; whether the page is structurally complete is decided by [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review#Single Note Review|Single Note Review]], and whether an existing receipt may stand instead of a fresh review is decided by [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Substantive Correctness Review

Substantive correctness review is mandatory for L-tier pages. It is not a standalone obligation for M-tier pages: M is reviewed only through the M checklist inside Batch Review. S-tier review remains the bounded sample owned by Batch Review. Neither route invokes this substantive-review contract.

Execution is performed by a procedurally separate review context carrying only the note body and its Sources, not the author's working context. The recorded context identifier is a declared label; actual isolation is supplied by the operator or Host. The authoring context MUST NOT produce its own review receipt. Review may begin once the page is drafted and its changed-scope self-check passes. Batch admission requires current `substantive_review` evidence for every L-tier manifest page. Review content:

- Re-derive the key reasoning chains and confirm the conclusions actually follow from the premises.
- Spot check 2–3 key claims against the source's original text.
- Check for over-extension of the "the source does not say it that strongly" kind.

The review produces `substantive_review` producer evidence under the sole machine authority of [`substantive-review-contract.yaml`](substantive-review-contract.yaml). The unique producer route is capability `substantive-review-attestation-v1`; the `batch-review` Gate is its consumer. At the `pre-merge` due stage, a passing record discharges only the exact AuditPlan obligation it binds, as `audit-receipt` evidence in dimension `content_and_depth` against acceptance predicate `content-correctness`. The AuditPlan layer completes the producer record into the full [`AuditReceipt`](audit-receipt-contract.yaml) rather than treating that record as a second receipt schema.

Trigger-to-partition projection is fixed as follows:

- A newly created L-tier page maps to `initial-semantic-review`.
- An L-tier page marked `needs_rereview` maps to `invalidated-semantic-review`.
- An L-tier page whose `review_by` has expired maps to `overdue-targeted-review`.

`initial-semantic-review` records why the existing L-tier obligation was triggered. It does not create another review duty, change the acceptance predicate, or merge the L execution route with the M checklist.

Review object and convergence rules:

- The review judges **document-level correctness** — whether the reasoning chains hold, whether claims are supported by sources, whether there is over-extension; it does not judge whether the described system, protocol, or design is unassailable in an adversarial environment. For design-type content, known weaknesses, open attack surfaces, and engineering trade-offs recorded faithfully in the page's Limitations / Open Questions count as correct statements and do not constitute a review failure.
- Findings are graded on three levels: `critical` (wrong conclusion, reasoning does not hold, claim contradicts the source) MUST be fixed; `major` (over-extension, missing a key qualification) is fixed or the wording downgraded; `minor` (wording improvement) is merely recorded and does not block. Only critical / major findings block close.
- The round cap is 2: round 1 of the review produces graded findings; after fixes, round 2 **only confirms whether round 1's findings are closed and MUST NOT introduce new review scope**. Issues newly found in the confirmation round are recorded in Open Questions or marked `needs_rereview` for a maintenance run to absorb; the current review round is not reopened.
- If the review still cannot close after two rounds, or the review scope keeps expanding between rounds, it MUST be escalated to the user for decision; additional rounds MUST NOT be added unilaterally.
- The two-round cap in this section is a fixed kernel constant, not a default that the selected profile or task contract may override.

Existing-content exemption: the trigger points are limited to the three cases above. A Standards version upgrade does not by itself trigger back-fill work on existing pages — a page already `reviewed`, with `review_by` not expired and not marked `needs_rereview`, does not reopen substantive correctness review because of a standards change; receipt invalidation caused by a standards change only requires re-running the deterministic checks per [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|K12/07]], and does not amount to reopening manual review.

## Related

- [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]
- [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
