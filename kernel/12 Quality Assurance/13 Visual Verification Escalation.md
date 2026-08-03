## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[kernel/12 Quality Assurance/12 Substantive Correctness Review|Substantive Correctness Review]].
- Next: [[kernel/12 Quality Assurance/14 Batch Review|Batch Review]].

## Visual Verification Escalation

This module owns the conditions under which visual evidence may be gathered at all. What counts as visual recognition, and the deterministic levels that MUST be run first, are defined in [[kernel/12 Quality Assurance/02 Rendering Verification#Rendering Verification Levels|Rendering Verification Levels]]; every level below is recorded through [[kernel/12 Quality Assurance/02 Rendering Verification#Escalation Record|Escalation Record]].

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
