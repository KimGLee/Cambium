## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]].
- Next: [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]].

## Rendering Verification Levels

Rendering acceptance follows `deterministic-first, visual-by-exception`: first judge source files and static constructs with repeatable, fully-runnable deterministic methods; escalate to UI, screenshots, or visual recognition only when that evidence cannot eliminate uncertainty about the final display. The escalated levels, and the objective triggers that admit them, are owned by [[kernel/K12 Quality Assurance/13 Visual Verification Escalation#Visual Verification Escalation|Visual Verification Escalation]].

In this standard, "visual recognition" includes:

- Manually observing pages after opening the knowledge host UI bound by the selected profile's `Role Registry`.
- Judging layout, occlusion, overflow, color, or readability from screenshots.
- Using OCR, vision models, or screen recognition instead of directly parsing source files.

Adding a visual construct does not itself justify escalation. Profile-specific checks enter only through a canonical construct selector and acceptance contract.

### Level 0: Source And Structural Validation

Every changed Markdown page runs fence closure and the canonical wiki-link Gate; a page with a Mermaid fence also runs Mermaid fence closure. [`deterministic-rendering-contract.yaml`](deterministic-rendering-contract.yaml) owns this exact base, and K12/05 routes it.

Required sections belong to the Page Contract or Profile; terminology links to the Profile and semantic review. Other prose items without one acceptance predicate remain semantic review. A Tool cannot invent a grammar, threshold, normalization, or page set and promote them into this base.

Plain pages normally stop here. UI browsing cannot replace Level 0, and fence closure proves neither compilation nor readability.

### Level 1: Static Render Or Compile

The only Level 1 Kernel base predicate is conditional outer-pipe-table structure: delimiter row, column counts, and escaped wiki alias pipes. Cell length has no universal threshold.

Mermaid compilation, formula rendering, paths, assets, dimensions, and long-cell policy belong to a typed Profile Rendering Contract. [`profile-rendering-contract.yaml`](profile-rendering-contract.yaml) owns the common answer shape; [`changed-scope-check-registry.yaml`](changed-scope-check-registry.yaml) registers its AuditPlan extension point without adding these choices to the Kernel base. A Tool supplies its registered compiler, renderer, parser, or probe; the Host binds that capability. Mermaid fence closure and compilation are separate evidence.

Level 1 MUST prefer compilers, parsers, structured extraction, file probing, and repeatable non-interactive previews. Producing a static artifact does not authorize visual judgment; as long as compile results, structured data, and geometry information can already answer the acceptance question, do not proceed to opening the UI or taking screenshots.

Passing Level 1 does not guarantee correctness under every theme, plugin, or CSS of the selected knowledge host role, but that theoretical possibility alone MUST NOT trigger a UI check.

After applicability has one canonical selector, the state is: no construct → `not-applicable`; construct plus valid typed contract → run its registered deterministic capability; construct without that contract → `contract-gap` / HOLD, never pass. Files, free prose, installed software, or Host claims cannot substitute for the binding.

An unresolved-contract inventory may identify missing selectors or acceptance contracts only to prevent Tool-created obligations and false passes. An inventory entry is not completion evidence, an acceptance predicate, or a second specification, and cannot substitute for a typed contract.

## Escalation Record

[`rendering-verification-contract.yaml`](rendering-verification-contract.yaml) owns this record's shape and AuditPlan projection; it does not prove the underlying checks passed.

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
