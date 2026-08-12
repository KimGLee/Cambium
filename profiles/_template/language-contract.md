# Language Contract

Interface: [Language Contract slot](../README.md#language-contract-slot)

## Language Routing

| Concern | Profile rule |
|---|---|
| Body language (language name or tag) | TODO(profile) |
| Secondary language and canonical form on disagreement (`None — monolingual` allowed) | None — monolingual |
| General proper-name display (localized, original, or bilingual; include occurrence scope) | Original spelling everywhere, including headings and tables. |
| Official external-name display around preserved identity | The official product or project string, unchanged; add a short body-language gloss on first use per page when the name alone is unclear. |
| Machine-identifier display around the exact token | Identifiers, commands, fields, and file paths appear in backticks and are never re-cased or translated. |

## Canonical Naming

Confirm or replace these operational defaults; for an existing corpus, "as
found" naming that these rows describe is preferable to a renaming campaign.

| Object | Language, casing, and separators |
|---|---|
| Folders | Body language, Title Case, spaces; preserve official casing where it differs. |
| Pages | Body language, Title Case, spaces; preserve official casing where it differs. |
| Term notes | The most common official term, using its conventional casing and punctuation. |
| Image assets | Lowercase, hyphens; the owning page's slug is the prefix. |

## Terminology And Display

| Concern | Profile rule |
|---|---|
| Alias forms (included name/language forms) | Register the official full form and any materially distinct established synonym; do not create aliases for spelling noise. |
| Headings and labels (display pattern) | Sentence case, no trailing punctuation, no numbering. |
| Abbreviation first use (form and page/vault scope) | Expanded once per page on first use, then the abbreviation alone. |
| Reader-facing display order (ordered components) | What it is, where it lives, how to verify it, what breaks it. |
| File-name annotation boundary (allowed annotations or `None`) | None — the file name carries the title only. |

## Content Length Unit

- Unit (`words` or `characters`): words

Confirm with the body language: CJK body languages use `characters`.

## K10/04 Scoped Anti-pattern Extensions

- Registration: None

| Kernel anti-pattern ID or profile extension ID | Scoped exception or added predicate | Predicate-owner path |
|---|---|---|

## Additional Formatting Migration Invalidations

- Registration: None

| K10/04 change-kind ID or profile trigger | Additional invalidated dimensions | Scoped exception | Rule-owner path |
|---|---|---|---|
