## Navigation

- Parent: [[kernel/K05 Terminology Standard|K05 Terminology Standard]].
- Next: [[kernel/K05 Terminology/02 Ownership and Term Structure|Ownership and Term Structure]].

## Purpose

This standard specifies how proper nouns are split into reusable canonical Term Notes, avoiding topic pages repeatedly explaining the same concept, and also avoiding fragmentation of the knowledge base through over-splitting.

## Core Rule

```text
Term Note owns the definition.
Concept Note owns the mechanism.
System Note owns component interaction.
Case Study owns application.
Expression Layer Artifact owns expression.
```

A proper noun is fully explained in only one standalone Markdown file. Other pages only state the noun's role in the current topic and reference it via a wiki link.

## Extraction Criteria

When any one of the following conditions is met, creating a standalone Term Note SHOULD be considered:

- Used in two or more pages.
- A complete explanation needs more than two or three sentences.
- It has an independent formal definition, notation, data structure, or lifecycle.
- It has common misconceptions or easily confused similar concepts.
- It will be reused by multiple top-level domains.
- Its definition changes with protocols, frameworks, or versions and needs independent maintenance.

The selected profile MAY register extended extraction criteria via the `Expression Layer Entry`.

## Do Not Extract

The following usually SHOULD NOT get a standalone file:

- Local variables or temporary classifications used in only one page.
- Ordinary words explainable in one sentence.
- Syntactic names with no independent knowledge value.
- Content that would form only a two-or-three-sentence empty shell after splitting.
- Local concepts that are meaningful only by depending on the current page's context.
- New labels that appear in only a single article, have unclear boundaries, and have not yet been adopted by other sources.

## Source-discovered Terminology

For a new term discovered from official articles, papers, or community discussions, first judge whether it is:

- A new name for an existing concept.
- A local term of a specific vendor or implementation.
- A vague umbrella name for multiple phenomena.
- A new knowledge object with clear boundaries and reusability.

Before a new term enters canonical terminology, it requires:

1. Collecting the original definition and usage context in the source.
2. Checking whether other sources use the same term to express the same meaning.
3. Checking whether the existing knowledge base already has a synonymous concept.
4. Making explicit what it includes and what it does not include.
5. Judging whether it should become an alias, a temporary label in a Research Synthesis, or a standalone Term / Concept Note.

While terminology is still evolving, a terminology mapping SHOULD be maintained in a Research Synthesis, annotated as a provisional definition. A stable Term Note MUST NOT be created immediately just to follow community hype.
