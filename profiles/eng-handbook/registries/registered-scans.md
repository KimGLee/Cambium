## Navigation

- Profile: [[profiles/eng-handbook/profile|Eng Handbook Profile]].
- Kernel closed list: [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|Batch-close Closed List]].
- Audit dimensions: [[profiles/eng-handbook/registries/audit-dimensions|Audit Dimension Registry]].

## Scan Registrations

| Scan ID | Activation role | Verifier | Candidate boundary and acceptance owner |
|---|---|---|---|
| `eng-handbook-residual-markers` | changed / owned scope; fills the residual-content scan role of Batch-close Closed List item 6 | deterministic grep for `TODO`, `FIXME`, `DRAFT`, and unfilled template placeholders | Produces review candidates only, never direct failures; per-candidate disposition is owned by the batch reviewer under the kernel's Batch Review rules |

This registry binds only scan roles the kernel has reserved; it does not add to, remove from, or reorder the Batch-close Closed List. Frontmatter controlled-vocabulary validation remains Closed List item 7 supplied by [[profiles/eng-handbook/profile#Implemented Slots|Vocabulary Extensions]], not a scan added here.

## Unfilled Scan Roles

No language-candidate scan is registered: the `Language Contract` is monolingual English and defines no bilingual label format for a scanner to check. If the contract later registers display-label rules, a scan may be added here with its verifier and acceptance owner.
