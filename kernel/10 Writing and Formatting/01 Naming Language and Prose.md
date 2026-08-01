## Navigation

- Parent: [[kernel/10 Writing and Formatting Standard|10 Writing and Formatting Standard]].
- Next: [[kernel/10 Writing and Formatting/02 Mathematics Tables and Code|Mathematics Tables and Code]].

## Purpose

This standard defines file naming, heading structure, paragraphs, and lists. Reader-facing language, identity preservation boundaries, and display order are maintained separately by the selected profile's `Language Contract`.

## Naming

- Folder and file names use the canonical identity registered by the selected profile's `Language Contract`.
- File names use the most common formal name in the industry.
- Abbreviations and full names are handled through aliases; duplicate files MUST NOT be created.
- Dates MUST NOT be added to file names, unless the file is inherently a log or a time record.
- Names with vague meaning MUST NOT be used, for example `Notes`, `Basics 2`, `Advanced Stuff`.
- Types such as Overview, Sequence Guide, Checklist, Cheat Sheet, and Expression Layer Artifact are expressed explicitly in the file name.
- A Source Note file name SHOULD identify the organization / author and the source topic, for example `Example Organization - Reliable Distributed Systems`; the publication date goes in metadata and is not placed in the file name by default.
- A Research Synthesis is named after the research question or phenomenon; it does not use the title of one particular article, nor does it masquerade as a canonical Term Note while conclusions are not yet stable.

## Language Routing（语言规则路由）

- Reader-facing language choices for all body text, headings, tables, diagrams, Source Notes, and `Expression Layer Artifact` uniformly read the selected profile's `Language Contract`.
- Concrete display order, identity preservation values, and exception boundaries are provided by the `Language Contract`.
- One question can have only one canonical owner; other rules reference the language contract through a slot and MUST NOT copy a slightly different policy.
- This page does not copy the language policy, so that Naming, Terminology, Expression Layer, and Formatting do not develop multiple owners.

General decision skeleton:

```text
Machine-consumed identifier? -> preserve exact identity
External identity or official name? -> preserve exact identity
Selected Language Contract has an unambiguous reader-facing form? -> use that form
Identity preservation is required? -> use the Language Contract display form
Otherwise -> use the Language Contract default prose form
```

## Titles

- Do not display the file name and the H1 redundantly.
- By default, start from `## Definition`, `## Purpose`, or the first second-level heading the content requires.
- Do not display redundant fields such as date, subject, or today's deliverables on ordinary knowledge pages.
- Headings SHOULD be stable and unambiguous, with heading links taken into account.
- Headings at the same level use consistent semantics; do not mix in too many synonymous headings.
- The display order of reader-facing headings and the file-name annotation boundary are constrained by the selected profile's `Language Contract`.

### Stable Heading Migration

When a `Language Contract` display change would alter an existing heading anchor, incoming heading links MUST first be inventoried, then the heading and its references updated atomically, the missing / ambiguous / heading resolution checks run, and the migration evidence recorded. When the current batch cannot migrate safely, keep the old heading and register a Required repair; references MUST NOT be silently broken, and a temporary compatibility state MUST NOT be declared as final compliance.

## Paragraphs And Lists

- Paragraphs are responsible for explaining causality and mechanism; lists are responsible for enumeration; lists MUST NOT replace all reasoning.
- A section MUST NOT consist of only one sentence long-term.
- Avoid multiple consecutive bullet lists containing only nouns and short phrases.
- When comparing multiple options, use unified dimensions instead of writing an asymmetric description paragraph for each.
- For complex hierarchies, prefer splitting into sections; avoid overly deep nested bullets.
