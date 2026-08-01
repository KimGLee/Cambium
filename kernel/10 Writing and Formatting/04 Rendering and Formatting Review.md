## Navigation

- Parent: [[kernel/10 Writing and Formatting Standard|10 Writing and Formatting Standard]].
- Previous: [[kernel/10 Writing and Formatting/03 Diagrams and Assets|Diagrams and Assets]].
- Next profile slot: `Language Contract`.

## Rendering Workflow

Content and structure checks rely primarily on directly extracted Markdown; rendering checks follow deterministic-first with visual recognition as the exception. The canonical definitions of the rendering levels and their escalation conditions are in [[kernel/12 Quality Assurance/02 Rendering Verification|12/02]].

Execution-side points: plain-text edits do not by default require opening the selected knowledge host's UI. Adding a diagram, table, formula, image, callout, or embed does not automatically trigger the UI either; first run the corresponding compiler, parser, path, dimension, and structure verification.

Only when the objective conditions of [[kernel/12 Quality Assurance/02 Rendering Verification#Level 2: Targeted Visual Recognition Exception|Level 2]] hold is the minimal page opened or the target screenshot inspected. Screen recording applies only to timing or interaction issues that static evidence cannot express. Passing Reading View only means the inspected target displays correctly; it does not mean content, sources, links, and the Completion Gate have passed.

## Formatting Anti-patterns

- Duplicated titles.
- Dates appearing in ordinary concept titles.
- Only bullet lists, with no explanatory paragraphs.
- Undefined formula symbols.
- Markdown tables broken by wiki pipes.
- Overlong tables replacing full sections.
- Images with no explanatory relationship to the body.
- Forcing all flowcharts into the same direction.
- Deleting key flows or failure paths to fit a single viewport.
- Treating a newly added visual construct itself as a reason for UI sampling, without first running deterministic verification.
- Repeatedly opening pages, taking screenshots, or recording video every round, without logging the still-unresolved display issue.
- Using visual recognition to read body text, links, table structure, or configuration that could be parsed directly.
- Using heavy bold and decorative symbols to fabricate false hierarchy.
The canonical definitions and exception boundaries of the reader-facing language anti-patterns above are provided by the selected profile's `Language Contract`.

### Automated Language Review Boundary

Automated checks such as character ratio, token pattern, and heading or table-header density can only produce review candidates; they MUST NOT bypass the `Language Contract`'s scoped exceptions or directly rule content failed. The final conclusion MUST come from a scoped review.

### Formatting Migration Invalidation

A formatting or language migration invalidates only the directly affected audit dimensions: heading / link changes invalidate at least structure and links; semantic, source, formula, or `Expression Layer Artifact` changes invalidate the corresponding dimensions respectively. The selected profile's `Language Contract` provides the concrete mapping and exceptions; an active task MUST re-adopt the changed contract and MUST NOT indiscriminately re-run unrelated receipts.

## Related

- [[kernel/04 Content Depth Standard|Content Depth Standard]]
- [[kernel/09 Wiki Link and Navigation Standard|Wiki Link and Navigation Standard]]
- [[kernel/12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- The selected profile's `Language Contract`
