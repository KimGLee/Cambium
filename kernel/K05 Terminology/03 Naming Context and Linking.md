## Navigation

- Parent: [[kernel/K05 Terminology Standard|K05 Terminology Standard]].
- Previous: [[kernel/K05 Terminology/02 Ownership and Term Structure|Ownership and Term Structure]].
- Next: [[kernel/K05 Terminology/04 Terminology Acceptance|Terminology Acceptance]].

## Naming And Aliases

- File names use the canonical identity registered by the selected profile's `Language Contract`.
- Full names, abbreviations, synonyms, and multilingual names go into `aliases`; the concrete language values are registered by the `Language Contract`.
- Do not create two separate files for an abbreviation and its full name.
- Terms with the same name but different semantics are disambiguated by domain path.
- Before renaming a Term Note, first check incoming links and aliases.

Concrete naming and alias examples are provided by the `Language Contract`'s `Terminology Naming And Aliases`.

## Contextual Use

Not recommended:

```markdown
The system uses [[Idempotency]].
```

Recommended:

```markdown
A tool may already have produced side effects after a timeout, so before a retry it
MUST pass through [[Idempotency]] to avoid a duplicate charge or a duplicate write.
```

The current page explains "why idempotency is needed here"; the Term Note explains "what idempotency fully is".

## Link Frequency

- Create the link at the first meaningful occurrence of the term.
- Later repeated occurrences on the same page are usually not linked again.
- A link cannot replace the context the current paragraph itself needs.
- Do not link ordinary words for the sake of graph density.
- Use a path-qualified wiki link when the path is ambiguous.
