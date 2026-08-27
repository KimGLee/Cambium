# Profile Extension Interface

## Purpose

The Profile interface is the common boundary through which one adopting
knowledge repository binds choices that the Kernel deliberately leaves open.
The Kernel owns the existence, meaning, minimum constraints, and invalid forms
of each extension point. A selected Profile owns only the confirmed instance
value bound to it.

The machine-readable authority for the common slot set is
[`profile-interface.yaml`](profile-interface.yaml). Human-oriented Profile
documentation, interviews, templates, examples, and validator code may project
or consume that registry; none of them may create a second interface.

## Binding Contract

- A Profile manifest has one stable Profile identity and binds every registered
  slot exactly once to a Profile-owned file.
- A binding stays within that Profile and resolves canonically. It cannot borrow
  another Profile, a template, an example, or a repository-root fallback.
- The slot file contains only the adopting repository's stable decision and
  parameters. The Kernel owner named by the interface retains the shared rule;
  Tool capability registries retain implementation identities; runtime state
  retains the current selection and evidence.
- A Profile may reference a stable Read Set, Tool capability, host capability,
  corpus artifact, or adopter-runtime object ID only where the owning extension
  point permits it. A runtime-object reference names the stable object, never
  its current `.cambium` path or value. A reference does not transfer ownership
  of the target.
- `None`, `not-applicable`, `kernel-defaults`, or an inactive registration is a
  complete value only where the interface permits it and the user confirms
  that its condition is true for the repository.

## Confirmation, Validation, And Selection

Templates, interviews, examples, and agents can propose candidate values but
cannot confirm them for the user. Mechanical derivations such as an ID-bound
path may be generated when they are reproducible from confirmed inputs.

Profile validation proves only structure, allowed values, identity, reference
closure, and machine consistency. It does not prove semantic quality, user
confirmation, or adoption. A directory, successful validation, template, or
example never selects a Profile. Selection and its revision history exist only
through the Standards adoption operation and belong to adopter runtime state.

## Ownership Boundary

Profile files do not carry common slot schemas, Kernel defaults, task routes,
Read Set membership, Card actions, Tool commands or implementation paths,
receipt schemas, state transitions, current Queue or Coverage values, receipts,
or recovery history. If a common interface rule must change, its Kernel owner
and the machine registry referenced by `profile-interface.yaml` change;
instance Profiles are then revalidated without becoming owners of that
change. For example, K12 owns audit-dimension values even though the Profile
interface exposes a slot that binds instance-specific audit extensions.
