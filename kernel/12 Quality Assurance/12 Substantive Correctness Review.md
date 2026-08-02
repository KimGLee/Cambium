## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[kernel/12 Quality Assurance/11 Content-level Propagation|Content-level Propagation]].

## Purpose

This module owns the review that an execution context other than the author performs on a drafted page, and the rules that stop that review from running forever. It is read by the author when dispatching the review before an L-tier page closes, by the independent reviewer as its whole instruction, and by the Terminal Audit when it grades its own findings on the same three levels. It decides whether a page's reasoning holds against its sources; whether the page is structurally complete is decided by [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review#Single Note Review|Single Note Review]], and whether an existing receipt may stand instead of a fresh review is decided by [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Substantive Correctness Review

Substantive correctness review is mandatory for L-tier pages; it is not mandatory for S / M tiers, which are covered by batch spot checks.

Execution: performed by an independent execution context — a subagent started with a clean context and carrying no author context, or a new session, whose input is only the note body and its Sources, satisfies independence. The main thread MUST NOT produce the review receipt itself; the receipt MUST record the reviewer's execution context identifier. The review MAY be triggered as soon as the page is drafted (drafted and passing the `--scope` self-check), in parallel with subsequent page writing; batch close requires only that the review receipts have all arrived. Review content:

- Re-derive the key reasoning chains and confirm the conclusions actually follow from the premises.
- Spot check 2–3 key claims against the source's original text.
- Check for over-extension of the "the source does not say it that strongly" kind.

The review produces a receipt (`check: substantive_review`, schema as in `Tools/schemas/receipt.template.jsonl`).

Trigger points:

- When the page is newly created.
- When the page is marked `needs_rereview`.
- When `review_by` expires and re-verification is due.

Review object and convergence rules:

- The review judges **document-level correctness** — whether the reasoning chains hold, whether claims are supported by sources, whether there is over-extension; it does not judge whether the described system, protocol, or design is unassailable in an adversarial environment. For design-type content, known weaknesses, open attack surfaces, and engineering trade-offs recorded faithfully in the page's Limitations / Open Questions count as correct statements and do not constitute a review failure.
- Findings are graded on three levels: `critical` (wrong conclusion, reasoning does not hold, claim contradicts the source) MUST be fixed; `major` (over-extension, missing a key qualification) is fixed or the wording downgraded; `minor` (wording improvement) is merely recorded and does not block. Only critical / major findings block close.
- The round cap is 2: round 1 of the review produces graded findings; after fixes, round 2 **only confirms whether round 1's findings are closed and MUST NOT introduce new review scope**. Issues newly found in the confirmation round are recorded in Open Questions or marked `needs_rereview` for a maintenance run to absorb; the current review round is not reopened.
- If the review still cannot close after two rounds, or the review scope keeps expanding between rounds, it MUST be escalated to the user for decision; additional rounds MUST NOT be added unilaterally.
- The two-round cap in this section is a fixed kernel constant, not a default that the selected profile or task contract may override.

Existing-content exemption: the trigger points are limited to the three cases above. A Standards version upgrade does not by itself trigger back-fill work on existing pages — a page already `reviewed`, with `review_by` not expired and not marked `needs_rereview`, does not reopen substantive correctness review because of a standards change; receipt invalidation caused by a standards change only requires re-running the deterministic checks per [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]], and does not amount to reopening manual review.

## Related

- [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]]
- [[kernel/00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
