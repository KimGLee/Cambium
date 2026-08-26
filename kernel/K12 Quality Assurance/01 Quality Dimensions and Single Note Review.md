## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Next: [[kernel/K12 Quality Assurance/02 Rendering Verification|Rendering Verification]].

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

These eleven are acceptance vocabulary and grouping labels, not checks, and they are not the values an `AuditReceipt` `dimension` field may take. The map from each judgment item below to its receipt dimension is held by [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]].

## Single Note Review

Applicability: the full checklist in this section applies to L-tier pages; M-tier pages are accepted against the M-tier Gate Checklist below and folded into the batch gate; S-tier pages receive only deterministic checks, with sampled re-review at batch close (for tiering rules see [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|tiering rules]]).

Several items below are satisfied by evidence produced at another layer rather than by a separate single-note verdict; which ones, and what each remaining item files under, is fixed by [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map#Item Map|K12/08]].

## M-tier Gate Checklist

This is the canonical minimum page-level checklist for an M-tier page. A non-authoritative action projection may compress or link to it, but MUST NOT add, remove, or redefine its acceptance items.

- The note type, canonical owner, scope, depth, priority, tier, and applicable status fields are explicit and internally consistent.
- The opening states the problem or position; the body explains the key mechanism or causal chain, its important boundary, and at least one example appropriate to the note type.
- Applicable failure behavior is concrete enough to identify trigger, symptom, cause, detection, and mitigation; an item that is genuinely not applicable is stated as such rather than silently omitted.
- Key, time-sensitive, or quantitative claims are supported by evidence whose role is clear; reported claim, inference, synthesis, and recommendation are not conflated.
- Parent, prerequisite, key dependency, and first meaningful terminology links are present in the body; no missing or ambiguous link remains.
- The selected profile's `Language Contract` and all triggered source, terminology, propagation, and rendering obligations have been applied.
- Applicable deterministic checks pass. Rendering remains at Level 0 / Level 1 unless an objective visual exception trigger and unresolved question are recorded.

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
- For an in-scope expression artifact, the concrete links declared by the selected profile's `Expression Layer Entry` satisfy the R05 bidirectional-binding gate and any supplemental profile gate.

### Rendering

- Mathematical formulas display properly.
- Table columns are not broken by wiki alias pipes.
- Image paths and dimensions are usable.
- Code blocks have correct fences and languages.
- Mermaid, SVG, embeds, and callouts are readable in the way they are actually used.
- Diagrams express the knowledge structure completely, without deleting key nodes, branches, or failure paths to fit the viewport.

A rendering pass proves only that the presentation layer meets requirements; it does not prove Coverage, Correctness, Depth, or Provenance.
