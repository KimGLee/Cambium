## Reference

- Profile manifest: `profiles/<your-profile-id>/profile.md`
- Slot interface: `profiles/README.md`, `Registered Scan Registry Slot`
- Kernel closed list: `kernel/K12 Quality Assurance/09 Batch-close Closed List.md`, section `Batch-close Closed List`

Implements the `Registered Scan Registry` slot.

TODO(profile) — fill in the sections below, correct the manifest path above, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

The kernel reserves a fixed set of scan roles that run before a batch closes — the Batch-close Closed List. The list is closed: its membership is a kernel constant. This file supplies the concrete scans that *fill* those reserved roles for this profile.

Three limits apply, and they are the reason this registry exists separately from a list of useful checks:

You may not add a role to the Batch-close Closed List, remove one, or reorder it. A scan registered here fills a role the kernel already reserved; it does not create a new gate.

A scan that produces candidates must not promote them to failures on its own. A deterministic text scan finds strings, not defects. The boundary between "this matched" and "this is wrong" is a judgment, and it belongs to the batch reviewer under the kernel's Batch Review rules.

A scan never substitutes for human or model review. It narrows what review must look at.

## Scan Registrations

TODO(profile) — register each scan as a row. The kernel requires three declarations from every registered scan: its scope, its candidate boundary, and its acceptance owner. The remaining columns bind it to the closed-list role it fills and to the verifier that runs it.

Scope is what the scan actually reads — the paths, the file kinds, and the exclusions. A scan whose scope is unstated cannot be reused as audit evidence, because a receipt is only valid over a scope someone can name.

| Scan ID | Activation role | Scope | Verifier | Candidate boundary and acceptance owner |
|---|---|---|---|---|
| TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) |

If this profile registers no scans, delete the table and write that explicitly, stating that the reserved roles are filled by review alone.

TODO(profile) — confirm in prose that this registry binds only roles the kernel has reserved and does not alter the Batch-close Closed List. Name any closed-list item that is supplied elsewhere in this profile rather than by a scan here, so an auditor does not read its absence from this table as a gap.

## Unfilled Scan Roles

TODO(profile) — list any reserved scan role this profile does not fill, and say why. A role left unfilled deliberately is a recorded decision; a role left unfilled silently is an audit finding.

State what would need to exist before each unfilled role could be filled. A scan can only be written against a rule that is specific enough to check mechanically, so an unfilled role usually points at a contract that has not yet fixed a checkable format.
