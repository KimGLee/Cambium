## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/02 Task Routing|Task Routing]].
- Next: [[kernel/K00 Standards Control/04 Control State and Scope|Control State and Scope]].

## Standards State And Adoption History

This page owns governance rules only. It MUST NOT carry an adopter's current
version/Profile values or a chronological adoption register.

The adopter-owned runtime state stores exactly one current Standards/Profile
identity under the stable `standards-state` schema contract: immutable upstream
Git commit, approval status, effective date, selected Profile identity, state
revision, and latest adoption evidence. The legacy `standards_version` spelling
is only a compatibility projection of that full commit SHA; it is not a second
release identity and cannot be chosen independently. Kernel owns the meaning
and required invariants of that identity, not its physical path or current
values. A content task cannot freeze a Task Contract until an authorized
adoption has established the identity.

The canonical history is the append-only Standards-adoption receipt stream.
Each adoption receipt binds its plan, before/after identity, upstream
provenance, deterministic Kernel/Profile snapshots, and transaction outcome.
No Kernel page, Card, Profile slot, or second Markdown table may reproduce
that chronology as authority. A human history view, if rendered, is a
disposable projection from receipts.

The Standards lifecycle is:

```text
draft
 -> approved
 -> superseded
```

When modifying rules, you MUST:

1. Make explicit that this is a governance change, not ordinary content editing.
2. Record the affected Standards and the reason.
3. Resolve the adopted upstream Git ref to its full commit SHA and bind that
   value as the upstream identity. A Profile-only revision retains the same
   upstream identity and is distinguished by its Profile snapshot, typed
   contract fingerprint, state revision, and adoption evidence.
4. Update affected routing and normative owners; never append history to a
   Kernel page or Card.
5. For every existing affected runtime task, publish the changed-predicate input required by [[kernel/K12 Quality Assurance/10 Standards Version Adoption|K12/10]]. R09 owns the governance revision; R07 later executes or resumes the active-task adoption through the sole K13/15 writer. An empty changed-predicate list takes K12/10's no-predicate-change branch rather than bypassing state synchronization.

For an active-task adoption, one machine-readable adoption plan is the
canonical revision input. It binds the exact before identity, deterministic
after snapshots, and the changed predicates. The candidate Profile MUST pass
the `profile-load` Gate. The stable `standards-adoption` transaction capability
then advances the affected adopter state and appends adoption evidence as one
controlled state change. This page specifies the observable invariants; the
transaction algorithm, storage layout, locking, and recovery procedure belong
to the capability implementation.

User approval of the Standards does not equal approval of an immediate bulk Frontmatter migration of all legacy pages. The migration scope still needs to enter a specific task contract.

## Revision Closure Contract

A Standards revision closes only when all changed semantic owners, registered
machine contracts, and affected non-authoritative projections agree with the
candidate revision. A projection may be regenerated or invalidated, but it may
not become a second source of the rule. A revision that changes a Gate's
observable accept or reject behavior also changes the registered producer
protocol identity in the same revision.

Candidate preparation does not advance adopter state. When an existing task is
affected, its explicit changed-predicate plan and the controlled adoption
transaction remain required; a prose report, regenerated projection, or
matching hash cannot substitute for that state transition.

## Control Accretion Rule

For any revision that adds a check, freeze, invalidation, or reconciliation obligation, the Amendment MUST answer three questions:

1. Which layer currently owns this risk? Why is it insufficient?
2. Which layer owns the new obligation's canonical gate? (Multiple coexisting layers are not allowed.)
3. Is the superseded old layer deleted? If not, why?

If the three questions are not fully answered, the revision MUST NOT pass. Control obligations are managed in the Registry just like content rules.

## Single-owner Expression

A governance rule has one semantic owner. Other locations may reference,
project, execute, or store evidence for that rule, but they MUST NOT maintain a
second complete normative copy. Choosing a deterministic expression does not
transfer semantic ownership; it only makes that machine contract the unique
normative carrier for the rule it expresses.
