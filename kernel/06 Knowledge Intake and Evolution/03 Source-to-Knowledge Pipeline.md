## Navigation

- Parent: [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]].
- Previous: [[kernel/06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads|User Guidance Hypotheses and Source Leads]].
- Next: [[kernel/06 Knowledge Intake and Evolution/04 Intake Note Types and Source Roles|Intake Note Types and Source Roles]].

## Source-to-Knowledge Pipeline

```text
Environmental Scanning
 -> Source Capture
 -> Claim Extraction
 -> Evidence Classification
 -> Cross-source Synthesis
 -> Knowledge Gap Analysis
 -> Graph Impact Decision
 -> Note Creation Or Update
 -> Integration And Verification
 -> Maintenance Or Supersession
```

### Stage 1: Environmental Scanning

The goal is to discover changes worth investigating, not to immediately write hot topics into conclusions.

The following need to be recorded:

- Newly emerging problems, capabilities, failure modes, or engineering patterns.
- The discovery source and first-discovery date.
- The originating guidance ID, for user-provided hypotheses or source leads.
- The relationship to the Knowledge Spine declared by `Profile Scope`.
- The existing modules it may affect.
- Why it is worth further investigation.

Community buzz can trigger investigation, but MUST NOT on its own trigger canonical promotion.

Incremental scanning semantics:

- By default, scan only new material that appeared after `scanned_until` in `Tools/state/watermark.yaml` (schema in `Tools/schemas/watermark.template.yaml`).
- The watermark records covered sources and the coverage cutoff date in per-domain sections.
- At batch close, advance the watermark together with the Ledger.
- A full rescan is an explicit exception, used only when onboarding a new domain or when the watermark is suspect, and the reason MUST be recorded in the Ledger.

### Stage 2: Source Capture

Establish a traceable record for sources entering the research pipeline:

- Title, author / organization, publication date, and URL.
- The Source is the actual document, artifact, or verifiable record provided by the user, not the act of relaying itself.
- Source type and source authority.
- The problem the original text addresses.
- The system, experiment, or case boundary the original text provides.
- What the original text does not establish.
- Potential conflicts of interest, vendor bias, and missing information.

Only sources that will actually be reused, compared, or continuously tracked get a standalone Source Note. Ordinary citations do not require creating a file per URL.

### Stage 3: Claim Extraction

Break the source into independently verifiable claims instead of saving one vague summary.

Each key claim records at least:

- Claim statement.
- Claim type.
- Supporting evidence.
- Conditions and assumptions.
- Scope of applicability.
- Source location.
- Confidence and open questions.

The following claim labels are recommended:

- `Reported Claim`: a fact, experiment, or implementation explicitly reported by the source.
- `Reasoned Inference`: a reasonable inference drawn from the source, but not a direct conclusion of the original text.
- `Cross-source Synthesis`: a knowledge-base judgment formed by combining multiple sources.
- `Engineering Recommendation`: a practice recommendation based on evidence and constraints.

These labels MUST NOT be mixed. In particular, an inference MUST NOT be rewritten as a fact the vendor has already confirmed.

### Stage 4: Evidence Classification

Sources MUST NOT be ranked only as "authoritative or not"; the evidence role each source carries MUST also be stated.

Common evidence roles:

- `discovery-signal`: discovers a new problem or practice pain point.
- `mechanism-evidence`: explains why it happens.
- `implementation-evidence`: proves how a system is actually implemented.
- `empirical-evidence`: provides experiments, benchmarks, or production data.
- `generalization-evidence`: proves whether a conclusion holds across models, teams, or scenarios.
- `failure-evidence`: provides failure chains, incidents, or counterexamples.
- `contradicting-evidence`: conflicts with existing conclusions.

The same source MAY carry multiple roles, but the basis MUST be stated for each role.

### Stage 5: Cross-source Synthesis

When multiple sources address the same problem, the following MUST be compared:

- Whether the terms used actually refer to the same phenomenon.
- What the common observations are.
- Why the implementation choices differ.
- Whether experimental conditions and system boundaries are comparable.
- Which conclusions conflict with one another.
- Which are only vendor- or model-specific behavior.
- What the current evidence is sufficient to support, and what it is not.

When conclusions are still forming or span multiple knowledge objects, a Research Synthesis Note SHOULD be created rather than prematurely manufacturing a stable term.

### Stage 6: Knowledge Gap Analysis

Before writing, check the existing knowledge graph:

- Whether a synonymous or closely related canonical note already exists.
- Whether the new information supplements a definition, mechanism, case, failure mode, or evaluation method.
- Whether an existing page has wrong ownership or overly coarse granularity.
- Whether the new knowledge will be reused by two or more pages.
- Whether a prerequisite foundation page needs to be added first.
- Whether it is only source-specific detail with no independent knowledge value.

A knowledge gap MUST be described as "a missing question or mechanism", not merely as "this article is missing".

### Stage 7: Graph Impact Decision

For each group of new evidence, only justified actions MAY be chosen:

| Condition | Action |
|---|---|
| Only reinforces an existing conclusion | Add source or refine existing section |
| An existing page is found to lack a mechanism or failure mode | Expand canonical note |
| A reusable new knowledge object with a clear boundary appears | Create canonical note |
| One page carries multiple independent owners | Split existing note |
| Multiple pages effectively duplicate each other | Merge into one canonical owner |
| Multiple sources address a problem not yet stabilized | Create Research Synthesis Note |
| Describes a specific company's or system's implementation | Create or update Case Study |
| Only an early community signal exists | Capture as signal and monitor |
| Evidence is insufficient or unverifiable | Defer and record open question |
| New evidence overturns an old conclusion | Mark contested or superseded |

One source MAY trigger multiple actions, but each action requires an independent statement of its graph value.

### Stage 8: Note Creation And Integration

When creating or updating a page, the following MUST be synchronized:

- Canonical ownership.
- Parent, prerequisites, components, applications, and failure/control links.
- The explicit relationships of Source Notes, Research Syntheses, and Case Studies to canonical notes.
- Overview / MOC and the coverage map.
- When needed, the expression artifacts and collections registered by `Expression Layer Entry`.
- Metadata, authoring status, expression status, coverage disposition, evidence maturity, and review dates.

Isolated pages MUST NOT be created with relationships left to be filled in later.

### Stage 9: Verification And Promotion

Before a new page enters canonical knowledge from external sources, it MUST pass the promotion gate:

1. The knowledge object has a clear problem, boundary, and owner.
2. Key claims can be traced to specific sources.
3. Reported facts, inferences, syntheses, and recommendations are distinguished.
4. Source applicability and vendor-specific conditions are stated.
5. Synonymous pages and duplicate definitions have been checked.
6. Evidence maturity is consistent with the body tone.
7. The page reaches the corresponding depth class and is not a source summary or an empty shell.
8. Wiki links, Sources, metadata, and rendering have been verified.

Content that has not passed the promotion gate MAY remain as a Source Note or Research Synthesis, but MUST NOT be marked as stable canonical knowledge.

### Stage 10: Maintenance And Supersession

Frontier knowledge on the Knowledge Spine declared by `Profile Scope` requires continuous maintenance:

- Whether new sources support, constrain, or contradict existing conclusions.
- Whether model capability changes invalidate old operational-control assumptions.
- Whether benchmarks, APIs, tools, and the system environment have changed.
- Whether an emerging pattern has gained independent reproduction.
- Whether an old term has been replaced by a more accurate classification.

Superseded pages or conclusions SHOULD retain the supersession relationship and reason; historical judgments MUST NOT be silently deleted.
