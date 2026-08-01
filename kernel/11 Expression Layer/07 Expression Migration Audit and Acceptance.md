## Navigation

- Parent: [[kernel/11 Expression Layer Standard|11 Expression Layer Standard]].
- Previous: [[kernel/11 Expression Layer/06 Sequence and Progress Semantics|Sequence and Progress Semantics]].

## Migration Policy

When migrating expression content from an existing location, the order MUST be:

1. Identify the mapping between the canonical knowledge owner, the target expression owner, and the old content.
2. Create the complete content in the target owner first.
3. Verify that the target content, evidence binding, and links are all usable.
4. Create a resolvable wiki link at the original location pointing to the target owner.
5. Only after confirming content conservation, delete the duplicate expression at the original location.
6. Verify that there is no content loss, duplicate owner, or broken link.

Deleting old content first and waiting to build the target later is prohibited. Split, duplication, and owner rules are also subject to [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]].

## Scoped Migration Audit

Each migration batch scans its changed / owned scope; the global residue scan runs only in the registered batch close gate. Terminal verification reuses still-valid receipts and re-audits in depth only changed, invalidated, overdue, and sampled items.

Every candidate MUST be assigned exactly one of the following dispositions:

| Disposition | Meaning |
|---|---|
| Migrate | The complete expression content is migrated into an already established target owner |
| Minimal Context | The original location retains only the one minimal explanatory sentence needed to keep the current canonical passage readable |
| Owner Link | The original location retains only a resolvable wiki link to the target expression owner |
| Not Expression Content | The heading is similar, but the content actually belongs to a canonical mechanism, evidence, or evaluation owner |

## Candidate-only Automation

Automated scans can only discover migration candidates; they MUST NOT delete or re-classify content directly. While the target owner has not yet been fully established and passed link verification, old content MUST NOT be emptied; scan results MUST go through item-by-item disposition.

For the candidate boundary of similar automated checks, see [[kernel/10 Writing and Formatting/04 Rendering and Formatting Review#Formatting Anti-patterns|Formatting Anti-patterns]].

## Acceptance Criteria

- The target expression owner exists and resolves before duplicate content is deleted.
- Canonical notes no longer maintain duplicate expressions fully owned by an expression owner.
- The necessary links between canonical owners and expression artifacts are bidirectional, resolvable, and unambiguous.
- Every migration candidate has an explicit disposition; after migration there is no content loss, duplicate owner, or broken link.
- Definitions, mechanisms, metrics, and case conclusions can be traced back to canonical knowledge, evidence, and evaluation provenance.
- `emerging`, `contested`, `unknown`, and other evidence qualifications remain preserved after migration.
- Automated scan results serve only as candidate evidence and are never treated as automatic deletion authorization or proof of completion.
