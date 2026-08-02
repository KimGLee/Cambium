# Language Contract

Implements the `Language Contract` slot.

TODO(profile) — fill in the sections below, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

What language the body text is written in, what canonical form names take, how headings and labels are displayed, what unit the kernel's length ranges are counted in, and which language patterns count as defects. The kernel writes its soft length guidance in abstract units because a range that is reasonable in words is not reasonable in characters, and the kernel does not know which one you use.

This slot is referenced from more kernel modules than any other, because the kernel deliberately holds no reader-facing language values of its own. Every section below answers a question some kernel rule defers here.

You may interpret the kernel's soft length ranges in your own units. You may not change the numeric ranges, and you may not turn a soft length reference into a hard gate — length is a signal for review, never a pass/fail condition.

A filled version is in `profiles/examples/eng-handbook/language-contract.md`.

## Body Language

TODO(profile) — state the language body text is written in, and whether a second language is registered. If two languages are in play, state which one is canonical when they disagree.

TODO(profile) — state how proper nouns, product names, and technical identifiers are written: transliterated, kept in their original form, or given in both. Say whether the rule applies on first use only or every time. This is the rule that keeps a vault from drifting into inconsistent naming one page at a time.

## Canonical Identity

TODO(profile) — state the canonical form of a folder name, a file name, and an image file name: which language, which casing, and which separators. The kernel routes all three of these through this slot and holds no naming values of its own, so an unanswered rule here leaves every path in the vault unconstrained.

TODO(profile) — state whether the canonical identity is the same across folders, pages, term notes, and image assets, or differs by kind. If it differs, give each form; a single rule covering all four is a legitimate and simpler answer.

## Terminology Naming And Aliases

TODO(profile) — give concrete naming and alias examples for term notes: one term written in its canonical file-name form, with the alias set that resolves to it. The kernel's terminology rules state that aliases carry full names, abbreviations, synonyms, and multilingual names, and then send the reader here for the actual values.

TODO(profile) — state which language forms belong in `aliases` for this profile, so an author does not have to guess whether a translated name is registered or omitted.

Examples here are normative for this profile, unlike the illustrations under `profiles/examples/`. An author copies the form from this section.

## Display Labels

TODO(profile) — state the format for headings and labels. If a bilingual label format is in effect, give its exact shape, because a registered scan may later be written against it.

TODO(profile) — state the rule for abbreviations and acronyms: whether they are expanded on first use, per page or per vault, and how they are written thereafter.

TODO(profile) — state the display order of reader-facing headings, where more than one order would render correctly. The kernel constrains headings to be stable and unambiguous and then defers the ordering to this file.

TODO(profile) — state the file-name annotation boundary: what may be appended to a file name beyond the name itself, and what may not. This is the rule that stops dates, statuses, and version markers from accumulating in file names one page at a time.

## Content Length Units

TODO(profile) — name the unit the kernel's soft length ranges are counted in for this profile, typically words or characters.

Then confirm the two limits on this slot: the numeric ranges are kernel-owned and unchanged by this file, and length remains a soft reference rather than a gate.

## Language Anti-pattern Definitions

The kernel lists the reader-facing language and formatting anti-patterns it rejects, and then states that their canonical definitions and exception boundaries are provided here.

TODO(profile) — define each anti-pattern in terms a reviewer can apply to a page, and give its scoped exceptions. An anti-pattern with no exception boundary tends to be enforced either universally or not at all.

Two limits are kernel-owned and not yours to relax. An automated language check may only produce review candidates: character ratios, token patterns, and heading or table-header density MUST NOT bypass the exceptions you register here, and MUST NOT rule content failed on their own. The final conclusion comes from a scoped review.

## Formatting Migration Invalidation Mapping

A formatting or language migration invalidates only the audit dimensions it actually touches — heading and link changes invalidate at least structure and links; semantic, source, formula, or expression-artifact changes invalidate their corresponding dimensions.

TODO(profile) — give the concrete mapping from a change kind to the dimensions it invalidates, plus the exceptions. The kernel fixes the principle and requires a mapping to exist; the mapping itself is this profile's.

An active task MUST re-adopt the changed contract, and MUST NOT re-run unrelated receipts indiscriminately. That rule is kernel-owned; your mapping is what makes it applicable.
