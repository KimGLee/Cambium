## Navigation

- Parent: [[kernel/K10 Writing and Formatting Standard|K10 Writing and Formatting Standard]].
- Previous: [[kernel/K10 Writing and Formatting/02 Mathematics Tables and Code|Mathematics Tables and Code]].
- Next: [[kernel/K10 Writing and Formatting/04 Rendering and Formatting Review|Rendering and Formatting Review]].

## Diagrams

Add a diagram only when it significantly reduces the cost of understanding:

- Architecture diagram: components and dependencies.
- Sequence diagram: call order and state changes.
- Data flow: how data is transformed.
- Function plot: activation functions, loss, or distributions.
- Decision table / tree: option selection.

Use Mermaid, reliable SVG, or generated images when necessary. A diagram MUST be followed by body-text explanation; a diagram MUST NOT carry all the knowledge on its own.

### Direction And Completeness

Diagram direction is decided by the knowledge structure; a uniform top-to-bottom strip template is not used:

- Long ordered execution chains, pipelines, and cross-component handoffs preferentially consider horizontal `LR`.
- Hierarchies, dependency trees, state decompositions, and ownership maps preferentially consider vertical `TD`.
- Multi-actor interactions preferentially consider a sequence diagram or explicit swimlanes.
- Loops, rollback, and recovery MUST draw the back edge or a separate failure path.

A diagram's first goal is content completeness and correct order; single-screen visual compactness comes second. Key steps, branches, states, permission checks, effect receipts, or recovery paths MUST NOT be deleted to avoid horizontal scrolling.

When a diagram becomes too complex, split it by knowledge responsibility into:

```text
Overview Architecture
 -> Detailed Execution / Sequence
 -> Failure And Recovery Flow
```

After splitting, every diagram MUST have a clear entry, a clear exit, and a hand-off note connecting it to the other diagrams. Horizontal scrolling is acceptable; missing semantics is not acceptable.

### Diagram Semantics

- Node names describe real objects, states, or actions; names with vague meaning such as `Process`, `Handle`, `Do Work` MUST NOT be used.
- The language, identity preservation values, and display order of reader-facing labels are defined by the selected profile's `Language Contract`; this page retains only diagram semantics and structural completeness.
- Edges represent explicit calls, data, control, state transitions, or authority transfer; use labels when needed.
- proposer output, gatekeeper validation / authorization, and external execution use different nodes or lanes.
- Happy path, retry, timeout, cancel, unknown outcome, and terminal verification SHOULD NOT be blended into a single unconditional edge.
- The order and direction in a diagram MUST be consistent with the body description.

## Assets

- Images go in the Profile-declared asset location associated with their
  owning module.
- Image file names use the canonical identity registered by the selected profile's `Language Contract` and express the content.
- Purely decorative images MUST NOT be used.
- All images are first verified for path, format, dimensions, and references; when adding or modifying a diagram, image, or embed, run Level 0 / Level 1 per [[kernel/K12 Quality Assurance/02 Rendering Verification#Rendering Verification Levels|Rendering Verification Levels]].
- After modifying a diagram, first verify nodes, edges, labels, order, and completeness using the compiler, structure extraction, and dimension data. Only when deterministic evidence cannot judge specific readability, overflow, occlusion, or host-specific display does it escalate to a minimal-scope visual exception.
- Check the corresponding viewport only when the content explicitly depends on a specific desktop or mobile viewport and an unresolved layout issue exists; the existence of multiple viewports MUST NOT mean operating the UI for each one by default.
