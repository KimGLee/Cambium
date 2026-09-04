# Language Contract

Kernel owner: K10 Writing and Formatting. Common slot identity is registered in the Kernel Profile interface.

## Language Routing

| Concern | Profile rule |
|---|---|
| Body language (language name or tag) | Simplified Chinese (`zh-Hans`). |
| Secondary language and canonical form on disagreement (`None — monolingual` allowed) | English preserves official external identities, source-language claims, and machine interfaces; Chinese is the canonical explanatory language. |
| General proper-name display (localized, original, or bilingual; include occurrence scope) | Preserve the official name and add a concise Chinese explanation at first meaningful use when needed. |
| Official external-name display around preserved identity | Keep the official product, project, model, protocol, organization, or publication name unchanged. |
| Machine-identifier display around the exact token | Keep identifiers, commands, fields, paths, formulas, and configuration literals exact and format them as code. |

## Canonical Naming

| Object | Language, casing, and separators |
|---|---|
| Folders | English Title Case with spaces; preserve official casing. |
| Pages | English Title Case or official casing with spaces. |
| Term notes | The most common official English term or industry-standard acronym, using conventional casing and punctuation. |
| Image assets | Lowercase English kebab-case; use the owning page slug as the prefix when practical. |

## Terminology And Display

| Concern | Profile rule |
|---|---|
| Alias forms (included name/language forms) | Include the official full form, accepted acronym, common Chinese name, and materially distinct established synonyms. |
| Headings and labels (display pattern) | Use concise stable headings; explanatory labels are Chinese, while official identities remain unchanged. |
| Abbreviation first use (form and page/vault scope) | Expand once on first use per page, with a Chinese explanation when needed; use the abbreviation thereafter. |
| Reader-facing display order (ordered components) | Present the Chinese explanation around the preserved official or machine identity. |
| File-name annotation boundary (allowed annotations or `None`) | None — file names carry only the canonical title. |

## Content Length Unit

- Unit (`words` or `characters`): characters

## K10/04 Scoped Anti-pattern Extensions

- Registration: None

| Kernel anti-pattern ID or profile extension ID | Scoped exception or added predicate | Predicate-owner path |
|---|---|---|

## Additional Formatting Migration Invalidations

- Registration: None

| K10/04 change-kind ID or profile trigger | Additional invalidated dimensions | Scoped exception | Rule-owner path |
|---|---|---|---|
