## Reference

- Profile manifest: `profiles/<your-profile-id>/profile.md`
- Slot interface: `profiles/README.md`, `Routing And Gate Registry Slot`
- Kernel routing contract: `kernel/K00 Standards Control/02 Task Routing and Pre-execution.md`
- Kernel route registry: `kernel/Read Sets/Read Sets Index.md`
- Quality kernel: `kernel/K12 Quality Assurance Standard.md`

Implements the `Routing And Gate Registry` slot.

TODO(profile) — fill in the sections below, correct the manifest path above, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

Three things: the supplemental task routes this profile defines, the Read Sets those routes load, and any gates this profile adds beyond the kernel's.

One rule governs the whole file: a profile route that is not registered here must not be implied as loaded. Every registered profile route uses `P:<profile_id>:<route_name>` and loads alongside an applicable Rxx kernel route; it never occupies or replaces the Rxx namespace.

## Profile Task Routes

TODO(profile) — register each profile-specific supplemental route with its `P:<profile_id>:<route_name>` identity, the Rxx route it supplements, and the Read Set it loads; or write that this profile registers none and its tasks use only the kernel routes.

If you register none, say so in a way that closes the question: no supplemental profile route is loaded. The kernel R01-R10 registry is unaffected.

## Effort Tier Bindings

The kernel owns the S / M / L effort axis, dispute escalation, quota coupling, and acceptance rituals. This section only says which of *this profile's* material lands in which tier.

TODO(profile) — state the additional tier triggers for this profile, and give the reason for each L-tier trigger. L tier draws the full single-note review, so it is the expensive one; a trigger without a stated reason tends to spread.

TODO(profile) — state the default tier for ordinary pages in this profile, and which material sits below it.

## Specialized Audit Invariants

The kernel runs a Specialized Audit over invariants that no single batch can verify, because they only hold or break across batches. Source identity, case consistency, migration conservation, and currentness are the kernel's own; anything beyond those is a profile invariant, and the kernel looks for it here.

TODO(profile) — register each cross-batch invariant this profile needs audited, or write that it registers none and the Specialized Audit covers only the kernel's own invariants.

Each registered invariant needs the statement that must hold across batches, the objects it ranges over, and how a violation is detected. An invariant with no detection method is a wish, and the audit that consumes this section has no way to reach a verdict on it.

State the reuse boundary too: which passed content receipts an audit of this invariant may reuse. The kernel's rule is that a specialized audit reuses canonical content review unrelated to its invariant rather than redoing page-by-page review — your boundary says which review that is here.

## Extension Gates

TODO(profile) — register any gate this profile adds beyond the kernel's batch gates, note gates, and Terminal Audit, or write that it registers none.

Each registered gate needs the kernel role it binds to, what it blocks, and who can pass it. A gate that blocks progress without a named party able to clear it stops work permanently rather than governing it.

TODO(profile) — state any object class to which a supplemental profile gate does not apply, with the reason. Do not mark an Rxx kernel gate `not_applicable`: when the profile registers no object of that kind there is no task target, and when an object enters scope its kernel gate applies.
