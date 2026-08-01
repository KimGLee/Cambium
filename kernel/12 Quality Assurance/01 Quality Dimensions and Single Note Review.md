## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Next: [[kernel/12 Quality Assurance/02 Rendering Verification|Rendering Verification]].

## Purpose

This standard defines how a single note, a module, and the whole vault are accepted. File creation completed, test scripts passing, or sufficient word count cannot individually represent knowledge completion.

## Quality Dimensions

Every piece of content is accepted against the following kernel dimensions:

- Coverage: whether the questions that should be answered are covered.
- Correctness: whether facts, formulas, and terminology are accurate.
- Depth: whether reasons, mechanisms, assumptions, and failures are explained.
- Structure: whether sections follow a logical progression.
- Reuse: whether proper nouns are canonicalized.
- Integration: whether the body and the parent entry are correctly linked.
- Application: whether there are examples, evaluation, and engineering considerations.
- Provenance: whether key claims, metrics, and cases can be traced back to evidence and the measurement process.
- Evidence maturity: whether the body's tone matches the signal, corroborated, validated, or contested state.
- Maintainability: whether sources, metadata, and ownership are explicit.
- Rendering: whether Markdown, formulas, tables, and images render properly.

The selected profile MAY add language, expression readiness, or other extension dimensions through the `Audit Dimension Registry`, but MUST NOT delete, replace, or weaken the kernel dimensions above.

## Single Note Review

Applicability: the full checklist in this section applies to L-tier pages; M-tier pages are accepted against the corresponding Gate checklist provided by the `Runtime Card Provider` and folded into the batch gate; S-tier pages receive only deterministic script checks, with sampled re-review at batch close (for tiering rules see [[kernel/00 Standards Control/02 Task Routing and Pre-execution|tiering rules]]).

### Structure

- The note type is explicit.
- The opening states the topic's position or the problem to be solved.
- Section order follows the logic from problem to mechanism to application and failure.
- No duplicate headings, dates, or meaningless meta-information.

### Content

- Not just definitions and lists.
- Key mechanisms are explained, not merely stated as results.
- Important assumptions and boundaries are stated.
- At least one example appropriate to the note type.
- Failure Mode includes trigger, symptom, cause, detection, mitigation.
- Terminology explanations do not unnecessarily crowd out the current topic.
- Foundational knowledge pages can explain their discipline's mechanisms independently and MUST NOT be compressed into explanations that serve only the selected profile's application mainline; the concrete completeness predicates are provided by `Profile Scope`.
- System pages cover execution, state, coordination, evidence, and recovery paths.
- Language acceptance is provided by the selected profile's `Language Contract` and incorporated into the applicable gate via the `Audit Dimension Registry`.

### Accuracy

- Formulas, symbols, and numeric examples have been checked.
- Time-sensitive facts have been verified.
- Sources directly support the key conclusions.
- Empirical advice is not written as absolute fact.
- Reported claim, inference, cross-source synthesis, and recommendation are distinguished.
- Metrics can be traced back to task, dataset, trial, execution runtime, grader, and aggregation; the concrete runtime role names are bound by the selected profile's `Role Registry`.

### Links

- Parent, prerequisites, and key dependencies are navigable.
- Terms are linked at their first meaningful occurrence in the body.
- Related is not the only place a reference appears.
- The relationships among Source Note, Research Synthesis, canonical note, and Case Study are navigable.
- No unresolved or ambiguous link.
- The applicable expression layer structural links are declared by the selected profile's `Expression Layer Entry`, with gates provided by the `Routing And Gate Registry`.

### Rendering

- Mathematical formulas display properly.
- Table columns are not broken by wiki alias pipes.
- Image paths and dimensions are usable.
- Code blocks have correct fences and languages.
- Mermaid, SVG, embeds, and callouts are readable in the way they are actually used.
- Diagrams express the knowledge structure completely, without deleting key nodes, branches, or failure paths to fit the viewport.

A rendering pass proves only that the presentation layer meets requirements; it does not prove Coverage, Correctness, Depth, or Provenance.

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
