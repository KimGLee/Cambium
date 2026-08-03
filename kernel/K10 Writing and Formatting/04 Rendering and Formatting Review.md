## Navigation

- Parent: [[kernel/K10 Writing and Formatting Standard|K10 Writing and Formatting Standard]].
- Previous: [[kernel/K10 Writing and Formatting/03 Diagrams and Assets|Diagrams and Assets]].
- Next profile slot: `Language Contract`.

## Rendering Workflow

Content and structure checks rely primarily on directly extracted Markdown; rendering checks follow deterministic-first with visual recognition as the exception. The canonical definitions of the rendering levels and their escalation conditions are in [[kernel/K12 Quality Assurance/02 Rendering Verification|K12/02]].

Execution-side points: plain-text edits do not by default require opening the selected knowledge host's UI. Adding a diagram, table, formula, image, callout, or embed does not automatically trigger the UI either; first run the corresponding compiler, parser, path, dimension, and structure verification.

Only when the objective conditions of [[kernel/K12 Quality Assurance/13 Visual Verification Escalation#Level 2: Targeted Visual Recognition Exception|Level 2]] hold is the minimal page opened or the target screenshot inspected. Screen recording applies only to timing or interaction issues that static evidence cannot express. Passing Reading View only means the inspected target displays correctly; it does not mean content, sources, links, and the Completion Gate have passed.

## Formatting Anti-patterns

- `AP01` — Duplicated titles.
- `AP02` — Dates appearing in ordinary concept titles.
- `AP03` — Only bullet lists, with no explanatory paragraphs.
- `AP04` — Undefined formula symbols.
- `AP05` — Markdown tables broken by wiki pipes.
- `AP06` — Overlong tables replacing full sections.
- `AP07` — Images with no explanatory relationship to the body.
- `AP08` — Forcing all flowcharts into the same direction.
- `AP09` — Deleting key flows or failure paths to fit a single viewport.
- `AP10` — Treating a newly added visual construct itself as a reason for UI sampling, without first running deterministic verification.
- `AP11` — Repeatedly opening pages, taking screenshots, or recording video every round, without logging the still-unresolved display issue.
- `AP12` — Using visual recognition to read body text, links, table structure, or configuration that could be parsed directly.
- `AP13` — Using heavy bold and decorative symbols to fabricate false hierarchy.

These IDs and default meanings are kernel-owned. The selected profile's `Language Contract` may register a domain-scoped exception or an additional anti-pattern; it does not restate or redefine the kernel list.

### Automated Language Review Boundary

Automated checks such as character ratio, token pattern, and heading or table-header density can only produce review candidates; they MUST NOT bypass the `Language Contract`'s scoped exceptions or directly rule content failed. The final conclusion MUST come from a scoped review.

### Formatting Migration Invalidation

| Change-kind ID | Direct change | Minimum invalidation |
|---|---|---|
| `FM01` | Heading or link | Structure and links |
| `FM02` | Semantic content | Corresponding content/audit dimension |
| `FM03` | Source or provenance | Source/evidence dimension |
| `FM04` | Formula or mathematical notation | Formula/correctness dimension |
| `FM05` | `Expression Layer Artifact` | Corresponding expression and dependency dimensions |

The selected profile's `Language Contract` may add stricter invalidation or a scoped exception that does not fall below these minima. An active task MUST re-adopt the changed contract and MUST NOT indiscriminately re-run unrelated receipts.

## Related

- [[kernel/K04 Content Depth Standard|Content Depth Standard]]
- [[kernel/K09 Wiki Link and Navigation Standard|Wiki Link and Navigation Standard]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- The selected profile's `Language Contract`
