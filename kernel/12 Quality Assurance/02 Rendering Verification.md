## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]].
- Next: [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]].

## Rendering Verification Levels

Rendering acceptance follows `deterministic-first, visual-by-exception`: first judge source files and static constructs with repeatable, fully-runnable deterministic methods; escalate to UI, screenshots, or visual recognition only when that evidence cannot eliminate uncertainty about the final display.

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

### Level 2: Targeted Visual Recognition Exception

Minimal-scope visual recognition is allowed only when at least one of the following objective conditions holds:

1. Level 0 / Level 1 results conflict with each other, or a specific final-display question still cannot be answered after they pass.
2. The user reports a reproducible visual defect that the source files, compiler, or static artifacts cannot explain or confirm.
3. The knowledge host theme, CSS snippet, plugin, font, or rendering contract bound by the selected profile's `Role Registry` has changed, and the impact cannot be determined from configuration and static verification.
4. Deterministic checks find suspected overflow, occlusion, clipping, layering, or viewport-dependent layout, but the final host behavior cannot be determined.
5. The user explicitly requests visual acceptance of a specified page, region, theme, or viewport.

When performing Level 2, you MUST:

- First record the specific unresolved question and the trigger condition.
- Open only the minimal representative pages, regions, and viewports that can answer that question.
- When evidence is needed, capture only the target region; broad screen recording or vault-wide browsing MUST NOT replace targeting.
- Record target, expected, observed, result, and whether the uncertainty has been eliminated.

Absent the above triggers, the absence of UI, screenshot, or vision-model evidence does not constitute a QA gap.

### Level 3: Expanded Or Full UI Review

Expanding to a module or the whole vault is needed only when:

- Level 2 has confirmed a reproducible systemic issue that may affect pages of the same kind.
- Global CSS, theme, plugin, font, or asset policy was modified.
- A large-scale migration changed the host rendering contract, asset loading, or embed behavior, and deterministic verification is insufficient to cover it.
- The user explicitly requests full visual acceptance.

Level 3 MUST define a bounded sample matrix, including affected patterns, representative pages, viewports, and stop conditions. Checks MUST NOT expand without bounds merely because the UI is already open.

### Level 4: Temporal Recording Exception

Screen recording is used only for time-related or interaction issues that static evidence cannot express, for example:

- scroll, hover, focus, animation, or responsive transition.
- plugin loading, asynchronous asset, state transition, or transient flicker.
- Host-specific failures that can only be reproduced by observing the before/after order of actions.

Static Markdown, tables, formulas, ordinary images, links, body completeness, and single-frame layout MUST NOT be verified by screen recording by default. Level 4 MUST record why source, static artifact, and targeted screenshot are all insufficient, and record only the shortest action sequence needed to reproduce the issue.

### Escalation Record

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

When `rendering_mode` is `source-only` or `deterministic-static`, write `not_applicable` for `visual_trigger`. Levels 2–4 MUST NOT be executed without an objective trigger or unresolved question.

UI, screenshots, and screen recordings can only answer display or interaction questions; they cannot prove that the body is correct, sources are reliable, wiki links resolve, formula semantics are correct, coverage is complete, or the Completion Gate has passed.
