## Navigation

- Parent: [[kernel/K11 Expression Layer Standard|K11 Expression Layer Standard]].
- Previous: [[kernel/K11 Expression Layer/06 Sequence and Progress Semantics|Sequence and Progress Semantics]].

## Migration Policy

An expression migration is valid only when the canonical knowledge owner, the target expression owner, and the old content are mapped; the target owner and its evidence bindings and links are usable before the old duplicate is removed; and content, evidence qualifications, ownership, and resolvable links are conserved. This semantic owner does not prescribe the action sequence; registered capabilities own deterministic scanning and link verification.

Deleting old content before the verified replacement exists is prohibited. Split, duplication, and owner rules are also subject to [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]].

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

For the candidate boundary of similar automated checks, see [[kernel/K10 Writing and Formatting/04 Rendering and Formatting Review#Formatting Anti-patterns|Formatting Anti-patterns]].

## Acceptance Criteria

- The target expression owner exists and resolves before duplicate content is deleted.
- Canonical notes no longer maintain duplicate expressions fully owned by an expression owner.
- The necessary links between canonical owners and expression artifacts are bidirectional, resolvable, and unambiguous.
- Every migration candidate has an explicit disposition; after migration there is no content loss, duplicate owner, or broken link.
- Definitions, mechanisms, metrics, and case conclusions can be traced back to canonical knowledge, evidence, and evaluation provenance.
- `signal`, `single-source`, `contested`, `unknown`, and other evidence qualifications remain preserved after migration.
- Automated scan results serve only as candidate evidence and are never treated as automatic deletion authorization or proof of completion.
