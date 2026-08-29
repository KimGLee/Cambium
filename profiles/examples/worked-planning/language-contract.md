# Language Contract

Interface: [Kernel-owned Profile interface](../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Language Contract slot

## Language Routing

| Concern | Profile rule |
|---|---|
| Body language (language name or tag) | English (`en`). |
| Secondary language and canonical form on disagreement (`None — monolingual` allowed) | None — monolingual |
| General proper-name display (localized, original, or bilingual; include occurrence scope) | The manufacturer's own spelling everywhere, including headings and tables. |
| Official external-name display around preserved identity | The product name exactly as printed on the service document, followed by the workshop's shelf label in parentheses on first use per page. |
| Machine-identifier display around the exact token | Part numbers, document revisions, and tool sizes appear in backticks and are never re-cased. |

## Canonical Naming

| Object | Language, casing, and separators |
|---|---|
| Folders | English, Title Case, spaces. |
| Pages | English, Title Case, spaces. |
| Term notes | English, Title Case, spaces; the manufacturer's casing wins when it differs. |
| Image assets | English, lowercase, hyphens; the owning page's slug is the prefix. |

## Terminology And Display

| Concern | Profile rule |
|---|---|
| Alias forms (included name/language forms) | The shelf label and the printed product name are both registered as aliases. |
| Headings and labels (display pattern) | Sentence case, no trailing punctuation. |
| Abbreviation first use (form and page/vault scope) | Expanded once per page on first use, then the abbreviation alone. |
| Reader-facing display order (ordered components) | What is being decided, how it is observed, what is done, how the result is checked. |
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
