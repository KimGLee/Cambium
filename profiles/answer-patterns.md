# Answer Patterns

Shapes harvested from the shipped examples (`profiles/examples/minimal-notes/`, `profiles/examples/agent-atlas/`) and from the Agent Systems Atlas adopter's field experience. **A pattern is a shape, never an answer**: instantiate it with this corpus's own content, and do not reuse an example's identity, paths, or scale of ambition. These patterns only help discuss candidate answers; they do not add defaults or another template tier.

## 1. One-line Knowledge Spine (Q9)

`One page per <unit — device, service, procedure, concept>; each page names what it depends on`, located by a stated field or an opening-paragraph statement. A one-line spine is fully legal; layered corpora extend it into a stage chain (foundations → mechanism → system → outcome).

## 2. Four-element Foundation Depth (Q10)

`A page describing <the class the maintainer must act on>` is complete when it names: the thing, its current version, where its backup or definition lives, and the observable condition or stable check capability that verifies it works. Swap the four elements for the corpus's own act-on-it needs; keep the predicate testable.

## 3. Own-observation Source (Q7)

For a personal or operational corpus: register `<maintainer>-observation` — what the maintainer observed on the running system — as a source class, with the retrieval date recorded in the note. Pair it with the primary vendor or upstream documentation as the higher-ranked authority for documented claims. "This corpus has no sources" is almost never true.

## 4. Six-class Research Source Taxonomy (Q7, research corpora)

official / standard / paper / book / ecosystem-implementation / community, each with its own pinning rule (release or commit; edition and section; DOI and version; publication year; repo commit; corroboration state). Near-verbatim reusable for any research-flavored corpus; only the storage paths are local.

## 5. Capability Scale 0-4 (corpus-planning expansion)

`0 Missing / 1 Outline / 2 Core / 3 System / 4 Defensible`, with `target_eligible` false below 2. Domain-free; adopt as-is or rename values, keep ranks contiguous from 0.

## 6. Readiness Axis Three-piece (expression-layer expansion)

A readiness field (`not-required / missing / mapped / ready`-shaped values) + a reviewer role bound in Role Registry + one extension gate that alone grants the terminal value. The same shape serves any derived-artifact pipeline (interview cards, published digests, release notes).

## 7. Residual-scan Archetype (C1)

`<X>-type structure belongs only under <X's root>`; the scan reports it leaking anywhere else. Instances: dated scratch entries outside the daily-log folder; interview-card structure outside the interview layer. On a corpus that already has pages, matchers come from strings that really occur under the accepted root. On an empty one they are declared from the page structure just confirmed, and bounded founding creates the witness page that carries them — before any batch or runtime state exists: the production scan requires the repository to contain at least one file the matchers recognise, so a declared class must be materialized rather than left on paper. The positive control does not catch a fabricated matcher — it synthesizes its own inputs and proves only self-consistency.

## 8. Term-band Rule (bilingual corpora, language expansion)

Body prose defaults to the body language; a foreign-language term appears only in one of two bands — identifier band (verbatim interface/product names, kept exactly; translating would break the source correspondence) or term-anchor band (first use as `native term (foreign term)`, native-only afterward). Per-term test, no counting thresholds.

## Also Available As Worked Examples

Two-provider comparison rules and evaluation-provenance extensions (metric-reporting corpora) have configured forms in `profiles/examples/agent-atlas/source-policy.md`; the inactive forms of every switch are in `profiles/examples/minimal-notes/`.
