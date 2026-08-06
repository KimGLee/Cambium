---
type: read-set
route_id: R02
---

## Purpose

Used for creating, rewriting, or targetedly completing one canonical knowledge note. It does not automatically cover a whole module, registered planning artifacts, or Expression Layer migration.

## Start

First read [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]], then read:

- [[kernel/K03 Note Types and Ownership/01 Note Type Catalog|Note Type Catalog]]
- [[kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]]
- [[kernel/K04 Content Depth/01 Depth Model and Foundation|Depth Model and Foundation]]
- By page type, select [[kernel/K04 Content Depth/02 Core Concept Structure|Core Concept Structure]], [[kernel/K04 Content Depth/03 Process and Flow Structure|Process and Flow Structure]], [[kernel/K04 Content Depth/04 System and Production Reasoning|System and Production Reasoning]], or [[kernel/K04 Content Depth/05 Source and Evaluation Depth|Source and Evaluation Depth]].
- [[kernel/K08 Metadata and Status/01 Frontmatter and Core Vocabularies|Frontmatter and Core Vocabularies]]
- [[kernel/K08 Metadata and Status/02 Scope Level Depth and Priority|Scope Level Depth and Priority]]
- [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
- [[kernel/K08 Metadata and Status/03 Status Axes|Status Axes]]
- [[kernel/K09 Wiki Link and Navigation/01 Link Semantics and Body Links|Link Semantics and Body Links]]
- [[kernel/K10 Writing and Formatting/01 Naming Language and Prose|Naming Language and Prose]]
- The `Language Contract` registered by the selected profile, as a mandatory `Start` module of this Read Set.
- The selected profile's `Vocabulary Extensions`, which is the separate slot registering extension frontmatter fields and their values; the `Language Contract` does not carry them.

## Triggered

- A reusable proper noun appears: read [[kernel/K05 Terminology/01 Terminology Extraction|Terminology Extraction]], [[kernel/K05 Terminology/02 Ownership and Term Structure|Ownership and Term Structure]], and [[kernel/K05 Terminology/03 Naming Context and Linking|Naming Context and Linking]]; before closing a term note, read [[kernel/K05 Terminology/04 Terminology Acceptance|Terminology Acceptance]].
- Key claims or external articles: read [[kernel/K07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles|Source Hierarchy and Evidence Roles]] and [[kernel/K07 Sources and Accuracy/02 Claims Sources and Classification|Claims Sources and Classification]].
- Official vendor material or conclusions needing independent verification: read [[kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification|Official and Cross-source Verification]].
- Benchmark, accuracy, backtest, or production metrics: read [[kernel/K07 Sources and Accuracy/04 Evaluation and Source Quality|Evaluation and Source Quality]].
- Time-sensitive claims, formulas, terminology conflicts, or uncertainty: read [[kernel/K07 Sources and Accuracy/05 Time Formula Terminology and Uncertainty|Time Formula Terminology and Uncertainty]].
- Mathematics, tables, or code: read [[kernel/K10 Writing and Formatting/02 Mathematics Tables and Code|Mathematics Tables and Code]].
- Diagrams, images, or visualizations: read [[kernel/K10 Writing and Formatting/03 Diagrams and Assets|Diagrams and Assets]].
- Deep-dive cases, failure modes, or debugging needed: read [[kernel/K04 Content Depth/06 Examples Deep Dives and Failure Analysis|Examples Deep Dives and Failure Analysis]].
- Mechanism sections of an existing page (Definition, Mechanism, formulas, core conclusions) are substantively modified: read [[kernel/K12 Quality Assurance/11 Content-level Propagation|Content-level Propagation]] and mark the direct downstream notes.

## Gate

Before closing the page, read:

- [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- For an L-tier page, [[kernel/K12 Quality Assurance/12 Substantive Correctness Review|Substantive Correctness Review]]; the author dispatches it to an independent execution context and MUST NOT produce the receipt.
- When formatting or renderable constructs changed, read [[kernel/K10 Writing and Formatting/04 Rendering and Formatting Review|Rendering and Formatting Review]].
- When the page contains a diagram, table, formula, image, callout, or embed, or a specific display problem exists, read [[kernel/K12 Quality Assurance/02 Rendering Verification|Rendering Verification]]. Run Level 0 / Level 1 by default; visual levels are entered only under [[kernel/K12 Quality Assurance/13 Visual Verification Escalation|Visual Verification Escalation]], with a recorded objective trigger and unresolved question.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K03 Note Types and Ownership Standard|Note Types and Ownership]]
- [[kernel/K04 Content Depth Standard|Content Depth]]
