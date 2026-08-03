## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]].
- Next: [[kernel/12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]].

## Rendering Verification Levels

Rendering acceptance follows `deterministic-first, visual-by-exception`: first judge source files and static constructs with repeatable, fully-runnable deterministic methods; escalate to UI, screenshots, or visual recognition only when that evidence cannot eliminate uncertainty about the final display. The escalated levels, and the objective triggers that admit them, are owned by [[kernel/12 Quality Assurance/13 Visual Verification Escalation#Visual Verification Escalation|Visual Verification Escalation]].

In this standard, "visual recognition" includes:

- Manually observing pages after opening the knowledge host UI bound by the selected profile's `Role Registry`.
- Judging layout, occlusion, overflow, color, or readability from screenshots.
- Using OCR, vision models, or screen recognition instead of directly parsing source files.

Adding or modifying a diagram, table, formula, image, callout, or embed is not by itself a reason for visual escalation. By default these trigger the corresponding Level 0 / Level 1 verification.

### Level 0: Source And Structural Validation

All changed pages MUST run:

- Markdown heading, fence, link, and table pipe checks.
- Formula delimiter, image path, embed path, and Mermaid fence checks.
- Direct body extraction, checking structure, duplication, missing sections, and term links.

Plain-text pages usually stop at this level when they contain no renderable constructs. Level 0 is the main path for content and structure checks; it MUST cover everything and MUST NOT be replaced by UI browsing.

### Level 1: Static Render Or Compile

Run the corresponding static verification when the following content appears:

- Mermaid diagram: use the Mermaid compiler.
- Mathematical formulas: use a renderer supporting the current Markdown / Math syntax or a repeatable preview.
- Markdown table: check the actual column count, escaped wiki aliases, and long cells.
- SVG, images, and assets: check file existence, dimensions, reference paths, and resolvability.

Level 1 MUST prefer compilers, parsers, structured extraction, file probing, and repeatable non-interactive previews. Producing a static artifact does not authorize visual judgment; as long as compile results, structured data, and geometry information can already answer the acceptance question, do not proceed to opening the UI or taking screenshots.

Passing Level 1 does not guarantee correctness under every theme, plugin, or CSS of the selected knowledge host role, but that theoretical possibility alone MUST NOT trigger a UI check.

## Escalation Record

Each batch or audit records the highest level actually used with the following enumeration:

```text
rendering_mode:
  source-only
  deterministic-static
  targeted-visual-exception
  expanded-ui
  temporal-recording

visual_trigger:
unresolved_question:
target:
result:
```

When `rendering_mode` is `source-only` or `deterministic-static`, write `not_applicable` for `visual_trigger`. For the other three values, `visual_trigger` and `unresolved_question` MUST be filled with the trigger and the question recorded when the level was entered; a record that names an escalated level and leaves either field empty is not a valid rendering record.

UI, screenshots, and screen recordings can only answer display or interaction questions; they cannot prove that the body is correct, sources are reliable, wiki links resolve, formula semantics are correct, coverage is complete, or the Completion Gate has passed.
