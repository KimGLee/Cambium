# Language Contract

Interface: [Kernel-owned Profile interface](../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Language Contract slot

## Language Routing

| Concern | Profile rule |
|---|---|
| Body language (language name or tag) | English (`en`). |
| Secondary language and canonical form on disagreement (`None — monolingual` allowed) | None — monolingual |
| General proper-name display (localized, original, or bilingual; include occurrence scope) | Original vendor spelling everywhere, including headings and tables. |
| Official external-name display around preserved identity | The vendor's own product string, unchanged, followed by the household nickname in parentheses on first use per page. |
| Machine-identifier display around the exact token | Hostnames, interface names, and file paths appear in backticks and are never re-cased or translated. |

## Canonical Naming

| Object | Language, casing, and separators |
|---|---|
| Folders | English, Title Case, spaces. |
| Pages | English, Title Case, spaces; a dated entry starts with `YYYY-MM-DD `. |
| Term notes | English, Title Case, spaces; the vendor's own casing wins when it differs. |
| Image assets | English, lowercase, hyphens; the owning page's slug is the prefix. |

## Terminology And Display

| Concern | Profile rule |
|---|---|
| Alias forms (included name/language forms) | The household nickname and the vendor product string are both registered as aliases of the page. |
| Headings and labels (display pattern) | Sentence case, no trailing punctuation, no numbering. |
| Abbreviation first use (form and page/vault scope) | Expanded once per page on first use, then the abbreviation alone. |
| Reader-facing display order (ordered components) | What it is, where it lives, how to verify it, what breaks it. |
| File-name annotation boundary (allowed annotations or `None`) | None — the file name carries the title only. |

## Content Length Unit

- Unit (`words` or `characters`): words

## K10/04 Scoped Anti-pattern Extensions

- Registration: None

| Kernel anti-pattern ID or profile extension ID | Scoped exception or added predicate | Predicate-owner path |
|---|---|---|

## Additional Formatting Migration Invalidations

- Registration: None

| K10/04 change-kind ID or profile trigger | Additional invalidated dimensions | Scoped exception | Rule-owner path |
|---|---|---|---|
