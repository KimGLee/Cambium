# Answer Patterns

Shapes harvested from the shipped examples (`profiles/examples/agent-atlas/profile.toml`, `profiles/examples/worked-planning/profile.toml`) and from the Agent Systems Atlas adopter's field experience. **A pattern is a shape, never an answer**: discuss this corpus's own content, without reusing an example's identity, paths, or scale of ambition. These patterns support the single empty `profiles/_template/profile.toml` candidate; they add neither defaults nor another template tier. The interview determines the depth, the user confirms decisions, and the agent records answers through the [candidate Tools](README.md#agent-read-edit-and-review). The user does not need to copy snippets or author TOML.

The following natural-language patterns illustrate possible content, not executable predicates or new obligations. Their destination is the corresponding semantic field under `slots.<slot-id>`; Kernel contracts define legality, and the Tool owns serialization. A discussed pattern is neither a complete Profile nor authorization to adopt it.

## 1. One-line Knowledge Spine (Q9)

`One page per <unit — device, service, procedure, concept>; each page names what it depends on`, located by a stated field or an opening-paragraph statement. A one-line spine is fully legal; layered corpora extend it into a stage chain (foundations → mechanism → system → outcome).

## 2. Four-element Foundation Depth (Q10)

`A page describing <the class the maintainer must act on>` is complete when it names: the thing, its current version, where its backup or definition lives, and the observable condition or stable check capability that verifies it works. Swap the four elements for the corpus's own act-on-it needs; keep the predicate testable.

## 3. Own-observation Source (Q7)

For a personal or operational corpus: register `<maintainer>-observation` — what the maintainer observed on the running system — as a source class, with the retrieval date recorded in the note. Pair it with the primary vendor or upstream documentation as the higher-ranked authority for documented claims. "This corpus has no sources" is almost never true.

## 4. Six-class Research Source Taxonomy (Q7, research corpora)

official / standard / paper / book / ecosystem-implementation / community, each with its own pinning rule (release or commit; edition and section; DOI and version; publication year; repo commit; corroboration state). Discuss which classes actually serve this corpus; neither all six classes nor these pinning choices are defaults.

## 5. Capability Scale 0-4 (corpus-planning expansion)

`0 Missing / 1 Outline / 2 Core / 3 System / 4 Defensible`, with `target_eligible` false below 2, is one example to discuss. Confirm the corpus's own labels and target threshold; contiguous ranks from 0 follow the existing Corpus Planning contract, not this pattern. Store ranks as integers and `target_eligible` as a boolean.

## 6. Readiness Axis Three-piece (expression-layer expansion)

A readiness field + a reviewer role bound in Role Registry + one extension gate that alone grants the terminal value. Use this only when an adopter needs a durable readiness claim distinct from authoring, mapping, and learning status; merely registering an expression artifact does not require it.

## 7. Residual-scan Archetype (C1)

`<X>-type structure belongs only under <X's root>`; the scan reports it leaking anywhere else. Instances include dated scratch entries outside the daily-log folder or a registered expression structure outside its expression layer. On a corpus that already has pages, matchers come from strings that really occur under the accepted root. On an empty one they are declared from the page structure just confirmed, and bounded founding creates the witness page that carries them before any batch or runtime state exists. The production scan requires the repository to contain at least one file the matchers recognize, so a declared class must be materialized rather than left on paper. The positive control does not catch a fabricated matcher; it synthesizes its own inputs and proves only self-consistency.

## 8. Term-band Rule (bilingual corpora, language expansion)

Body prose defaults to the body language; a foreign-language term appears only in one of two bands — identifier band (verbatim interface/product names, kept exactly; translating would break the source correspondence) or term-anchor band (first use as `native term (foreign term)`, native-only afterward). Per-term test, no counting thresholds.

## 9. Volatility Domains And Section-role Display (C2)

`slots.vocabulary-extensions.volatility_defaults` maps the corpus's real stable domain IDs to `fast`, `slow`, or `stable`. An illustrative `general = "slow"` is not prefilled in the empty candidate: discuss it only for a genuinely undivided corpus; otherwise use the confirmed domain IDs without inventing a second domain taxonomy.

`slots.metadata-contract.section_roles` is the sole instance binding for the Kernel roles `sources` and `related`. For each role actually used by the corpus, record its accepted reader-facing title or titles and only the bounded aliases that existing content or a confirmed migration requires. Language Contract states the human-facing language and display policy; it does not repeat the `section_roles` mapping.

## Also Available As Worked Examples

The shipped examples demonstrate how to fill the same candidate template at different levels of detail. They do not establish vendor-specific comparison duties, experiment systems, source defaults, or a second template tier.
