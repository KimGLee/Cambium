# Language Contract

Interface: [Language Contract slot](../../README.md#language-contract-slot)

## Language Routing

| Concern | Profile rule |
|---|---|
| Body language (language name or tag) | Simplified Chinese (`zh-Hans`) for explanations, mechanisms, causality, comparisons, limitations, and conclusions. |
| Secondary language and canonical form on disagreement (`None — monolingual` allowed) | English preserves official identities, source wording, machine interfaces, and designated English Interview answers. When translations disagree, the exact external identity or source-language claim remains fixed and the Chinese explanation is corrected to the same bounded meaning. |
| General proper-name display (localized, original, or bilingual; include occurrence scope) | At first meaningful use, show `English identity（中文解释）`; later uses may keep the stable English identity or an unambiguous Chinese form. |
| Official external-name display around preserved identity | Preserve the organization's, product's, model's, protocol's, framework's, library's, or algorithm's official English name and explain its role in Chinese nearby. |
| Machine-identifier display around the exact token | Preserve code identifiers, fields, enum values, commands, paths, formulas, and configuration literals exactly in code formatting; explain their semantics in adjacent Chinese prose. |

## Bilingual Answer Contract

For an Interview Card, the 30-second and 90-second answers are complete in both English and Chinese. Follow-up prompts use bilingual labels, and every follow-up intended for spoken delivery includes an English answer or a usable English answer skeleton. The two language versions preserve the same claim, limitation, uncertainty, and metric meaning.

This section owns only Interview Card answer parity. General body language, naming, display order, protected identifiers, and formatting remain owned by the other sections of this Language Contract. Interview Card structure and evidence requirements remain owned by [[profiles/examples/agent-atlas/expression-layer#Interview Card Contract|Expression Layer]].

## Canonical Naming

| Object | Language, casing, and separators |
|---|---|
| Folders | English Title Case with spaces; preserve official acronyms and product casing. |
| Pages | English canonical name in Title Case or official casing; spaces between words; no Chinese translation, status, or version suffix unless the version is part of the official identity. |
| Term notes | The most common official English term or industry-standard acronym, using its conventional casing and punctuation. |
| Image assets | Lowercase English kebab-case plus the source extension, for example `activation-functions-overview.svg`. |

## Terminology And Display

| Concern | Profile rule |
|---|---|
| Alias forms (included name/language forms) | Include the English full form, accepted acronym, common Chinese name, and a materially distinct established synonym; do not create aliases for spelling noise. |
| Headings and labels (display pattern) | Reader-facing structure uses Chinese or `English Title（中文解释）`. Exact external titles and machine identifiers may remain unchanged where translating them would alter identity. |
| Abbreviation first use (form and page/vault scope) | On each page, introduce an abbreviation as `English Full Name（中文解释，ABBR）`; later uses may use `ABBR`. |
| Reader-facing display order (ordered components) | Exact English identity, then full-width Chinese explanation, then the Chinese sentence; never reverse the identity as `中文（English）`. |
| File-name annotation boundary (allowed annotations or `None`) | None — do not append translations, statuses, bracketed explanations, or convenience labels to canonical file names. |

## Content Length Unit

- Unit (`words` or `characters`): characters

## K10/04 Scoped Anti-pattern Extensions

- Registration: Configured

| Kernel anti-pattern ID or profile extension ID | Scoped exception or added predicate | Predicate-owner path |
|---|---|---|
| `ATLAS-LANG-001` | In reader-facing Atlas content, an English-only explanatory heading or table label, or bilingual display ordered as `中文（English）`, is a review failure unless the text is an exact external title, machine identifier, or inside a designated English Interview-answer block. | `profiles/examples/agent-atlas/language-contract.md#K10/04 Scoped Anti-pattern Extensions` |

## Additional Formatting Migration Invalidations

- Registration: Configured

| K10/04 change-kind ID or profile trigger | Additional invalidated dimensions | Scoped exception | Rule-owner path |
|---|---|---|---|
| `ATLAS-LANG-MIG-001`: add, remove, or reorder Chinese annotation in a heading; rename a canonical page, folder, or term | Heading-link resolution, canonical naming, aliases, and reader-facing language conformance for the changed target and all incoming references | Exact external and machine identities remain unchanged, but their surrounding links and explanations are still checked. | `profiles/examples/agent-atlas/language-contract.md#Additional Formatting Migration Invalidations` |
