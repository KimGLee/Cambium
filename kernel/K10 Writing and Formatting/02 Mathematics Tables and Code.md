## Navigation

- Parent: [[kernel/K10 Writing and Formatting Standard|K10 Writing and Formatting Standard]].
- Previous: [[kernel/K10 Writing and Formatting/01 Naming Language and Prose|Naming Language and Prose]].
- Next: [[kernel/K10 Writing and Formatting/03 Diagrams and Assets|Diagrams and Assets]].

## Mathematics

- Inline formulas use `$...$`.
- Standalone formulas use `$$...$$`.
- Explain each symbol's meaning and dimension at its first occurrence.
- After a formula, state the intuition, assumptions, and boundaries.
- Every important formula comes with at least one numeric or shape example.
- Plain-text pseudo-formulas MUST NOT be written as hard-to-render symbol strings.
- Math formatting requires a unified check across the whole vault.

## Tables

- Tables are used only for data that requires comparison on unified dimensions.
- The dimension of each column MUST be explicit and consistent across all rows.
- Reader-facing table headers, comparison dimensions, and explanatory cells follow the selected profile's `Language Contract`; this page is responsible only for table structure and rendering boundaries.
- Wiki aliases in tables use the `\|` escape.
- When cell content grows too long, convert it to paragraphs or multiple sections.
- Hard-to-render multi-line code blocks MUST NOT be placed in tables.

## Code And Pseudocode

- Use fenced code blocks with a language tag.
- The knowledge base MAY use pseudocode, interfaces, and data structures; it need not copy large amounts of Python.
- Code examples MUST serve the explanation of mechanism.
- Examples SHOULD state inputs, outputs, key states, and error paths.
