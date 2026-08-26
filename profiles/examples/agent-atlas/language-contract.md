# Language Contract

Interface: [Kernel-owned Profile interface](../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Language Contract slot

## Language Routing

| Concern | Profile rule |
|---|---|
| Body language (language name or tag) | Simplified Chinese (`zh-Hans`) for explanations, mechanisms, causality, comparisons, limitations, and conclusions. |
| Secondary language and canonical form on disagreement (`None — monolingual` allowed) | English preserves official identities, source wording, machine interfaces, and designated English Interview answers. When translations disagree, the exact external identity or source-language claim remains fixed and the Chinese explanation is corrected to the same bounded meaning. |
| General proper-name display (localized, original, or bilingual; include occurrence scope) | At first meaningful use, show `English identity（中文解释）`; later uses follow the Term Band Rule: identifier-band names keep the stable English identity, and all other terms continue in Chinese. |
| Official external-name display around preserved identity | Preserve the organization's, product's, model's, protocol's, framework's, library's, or algorithm's official English name and explain its role in Chinese nearby. |
| Machine-identifier display around the exact token | Preserve code identifiers, fields, enum values, commands, paths, formulas, and configuration literals exactly in code formatting; explain their semantics in adjacent Chinese prose. |

## Term Band Rule

The default language of reader-facing body prose is Chinese. An English word
or phrase in body prose must belong to one of the following bands. A general
computing term with an established Chinese rendering belongs to neither band
and is written in Chinese.

1. **Identifier band — preserve English.** Source, configuration, and
   documented interface identities such as `Store`, `namespace`,
   `checkpointer`, and `thread_id`, plus official product, organization, and
   protocol names such as LangGraph, MCP, and PostgreSQL, retain their exact
   spelling. Translating these strings would break the evidence path to their
   source. Machine identifiers remain in code formatting.
2. **Term-anchor band — Chinese after one English anchor.** A domain term whose
   Chinese rendering is unsettled, or whose Chinese form is insufficient for
   source retrieval, appears at first meaningful use as
   `中文译名（English term）`. Later uses on the same page use the Chinese form.

Review applies this test to each English phrase independently. A compound
phrase is split by band: in `namespace authorization`, `namespace` remains an
identifier and `authorization` is rendered in Chinese.

## Bilingual Answer Contract

For an Interview Card, the 30-second and 90-second answers are complete in
both English and Chinese. Follow-up prompts use bilingual labels, and every
follow-up intended for spoken delivery includes an English answer or a usable
English answer skeleton. The two language versions preserve the same claim,
limitation, uncertainty, and metric meaning.

This section owns only Interview Card answer parity. General body language,
naming, display order, protected identifiers, and formatting remain owned by
the other sections of this Language Contract. Interview Card structure and
evidence requirements remain owned by
[[profiles/examples/agent-atlas/expression-layer#Interview Card Contract|Expression Layer]].

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
| Headings and labels (display pattern) | Markdown section headings are stable navigation labels. Pure English and `English Title（中文解释）` both conform; a bilingual heading must not invert the order as `中文（English）`. Table headers and other reader-facing explanatory labels stay Chinese-first under the Term Band Rule. The Section Role Display registration below separately owns `Sources` and `Related`. Changing an existing heading triggers the `ATLAS-LANG-MIG-001` anchor and inbound-link check. |
| Abbreviation first use (form and page/vault scope) | On each page, introduce an abbreviation as `English Full Name（中文解释，ABBR）`; later uses may use `ABBR` for identifier-band names and inside tables, labels, and code. Non-identifier terms in body prose continue in Chinese under the Term Band Rule. |
| Reader-facing display order (ordered components) | Identifier-band names use exact English identity first and a full-width Chinese explanation second. Term-anchor-band terms use `中文译名（English term）` at first use in body prose only; headings remain identity-first. |
| File-name annotation boundary (allowed annotations or `None`) | None — do not append translations, statuses, bracketed explanations, or convenience labels to canonical file names. |

## Section Role Display

This contract owns the reader-facing display forms of the kernel section roles
defined by K07/02 (`sources`) and K09/04 (`related`). The machine projection in
`metadata-contract.yaml` carries the same binding and never replaces this
prose owner.

| Role | Display titles | Migration-period aliases |
|---|---|---|
| `sources` | `Sources（来源）`; `来源` | `Sources` |
| `related` | `Related（相关）`; `相关` | `Related`; `Related（相关内容）` |

Aliases are accepted only for existing content during migration. New and
rewritten pages use a registered display title. One page carries at most one
sources-role section.

## Content Form Review

Review each content block on two independent axes. `form_class` records what
the source block naturally is; `rewrite_disposition` records whether the
current evidence authorizes a form change. A form classification never by
itself authorizes content that is absent from the source.

The closed `form_class` values are:

1. **`contract-enumeration`.** Responsibility boundaries (`owns`, `excludes`,
   goals, non-goals) and external-reference sets belong in the frontmatter
   `boundary` block. `boundary-contract` validates that block, and
   `render_boundary_projection.py` produces its reader view. Body prose may
   refer to the projection but must not duplicate the enumeration. The author
   chooses where the projection markers appear.
2. **`native-structure`.** Comparison tables, sequence diagrams,
   architecture diagrams, structure definitions, pseudocode, and formulas
   keep their native form. Marker comments distinguish authored content from
   generated projections.
3. **`compressed-narrative`.** Parallel bullets qualify only when the source
   items themselves state causal, mechanistic, trade-off, or failure
   relations that connected prose can preserve. A noun-phrase list or bare
   enumeration is not this class, regardless of list density, page type, or
   the amount of surrounding prose.
4. **`natural-prose`.** Existing prose is edited for clarity without changing
   its form.

The closed `rewrite_disposition` values are:

- **`retain`** — the natural form remains appropriate or no migration is
  needed;
- **`rewrite`** — the proposed form change can be completed entirely from
  relations already supported by the current content and admitted evidence;
- **`source-gap`** — the target prose would require a relation or mechanism
  the source does not state. Keep the neutral source form and register the
  missing question, evidence, or canonical owner; do not supply a connective,
  ordering, quantity, modal strengthening, absolute, or causal explanation to
  make the rewrite appear complete.

`source-gap` is a rewrite disposition, not a fifth form class. The applicable
depth and acceptance rules decide whether the registered gap blocks the
page's target status; the formatting rule never makes that decision.

A responsibility block belongs only to a page that asserts who owns a
concern. Overview, module-entry, and system-design pages commonly qualify;
source notes, cases, and Interview Cards ordinarily express evidence or
narrative scope instead. Concern slugs use a layer prefix and remain an open
kebab-case vocabulary until a later Profile revision explicitly closes the
set. Kernel projection labels remain in effect because this Profile declares
no `boundary_projection` override.

An `excludes` owner may be a kernel or Profile page. A missing boundary on an
out-of-manifest owner remains an advisory gap; it does not excuse a qualifying
manifest page from carrying its own boundary. When a batch introduces its
first new boundary block, Batch Review records the slug design for integrator
review.

Before `merge-ready`, Batch Review records both axes for every reviewed block
on every manifest page in that page's content-correctness evidence. A `retain`
result is valid; `source-gap` additionally names the registered gap; an
omitted axis or a bare statement such as “reviewed” is not a completed
judgment. Rewrites of `compressed-narrative` and `natural-prose` also apply the
Term Band Rule. The two-axis judgment is not a separate checkpoint artifact.
Pages not reached by ordinary batches are handled by a finishing batch before
Queue exhaustion can be claimed.

## Registered Term Displays

The following sense-aware table is the current word-level display authority.
An unregistered term follows the Term Band Rule, and a provisional mapping
needed during a batch is recorded as a gap. Adding or changing a stable entry
is a governed Profile revision, not a batch-close side effect. A new entry
does not authorize a bulk rewrite; affected pages align when they next enter
scope unless an explicit migration is approved.

| Term | Sense | Band | First display literal | Subsequent literal | Accepted variants | Canonical owner |
|---|---|---|---|---|---|---|
| `Harness` | Agent execution runtime shell | identifier | `Harness（执行外壳）` | `Harness` | `Agent Harness` | `Agent Knowledge/Harness/Agent Harness.md` |
| `span` | One timed unit in a distributed trace | term-anchor | `追踪跨度（span）` | `追踪跨度` | `span_id` | `Agent Knowledge/Harness/Tracing.md` |
| `trace` | Causal tree of spans as an object | term-anchor | `链路追踪（trace）` | `链路追踪` | `trace_id` | `Agent Knowledge/Harness/Tracing.md` |
| `trace` | Act of following causality | term-anchor | `追踪` | `追踪` | None | `Agent Knowledge/Harness/Tracing.md` |
| `artifact` | General produced and versioned output | term-anchor | `产物（artifact）` | `产物` | None | `Agent Knowledge/Harness/Artifact Lifecycle.md` |
| `artifact` | Build or release output | term-anchor | `构建制品（artifact）` | `构建制品` | None | None |
| `artifact` | Audit evidence object | term-anchor | `证据产物（artifact）` | `证据产物` | None | None |

## Content Length Unit

- Unit (`words` or `characters`): characters

## K10/04 Scoped Anti-pattern Extensions

- Registration: Configured

| Kernel anti-pattern ID or profile extension ID | Scoped exception or added predicate | Predicate-owner path |
|---|---|---|
| `ATLAS-LANG-001` | In reader-facing Atlas content, an English-only explanatory table label or figure caption, or a bilingual display inverted as `中文（English）`, is a review failure unless the text is an exact external title, a machine identifier, or part of a designated English Interview-answer block. Markdown section headings are exempt. In body prose, an English term that is neither an identifier-band name nor a first-use term-anchor gloss is also a review failure. | `profiles/examples/agent-atlas/language-contract.md#K10/04 Scoped Anti-pattern Extensions` |

## Additional Formatting Migration Invalidations

- Registration: Configured

| K10/04 change-kind ID or profile trigger | Additional invalidated dimensions | Scoped exception | Rule-owner path |
|---|---|---|---|
| `ATLAS-LANG-MIG-001`: add, remove, or reorder a Chinese annotation in a heading; rename a canonical page, folder, or term | Heading-link resolution, canonical naming, aliases, and reader-facing language conformance for the changed target and all incoming references | Exact external and machine identities remain unchanged, but their surrounding links and explanations are still checked. | `profiles/examples/agent-atlas/language-contract.md#Additional Formatting Migration Invalidations` |
