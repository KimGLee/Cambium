## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/16 Leaf Module Size Register|Leaf Module Size Register]].
- Next: [[kernel/K00 Standards Control/18 Tool Module Boundary Contract|Tool Module Boundary Contract]].

## Purpose

This module owns the derived dependency closure of one candidate or selected
Profile. It does not own Read Set loading, Profile selection, residual-content
classification, or any predicate's meaning.

## Profile Dependency Closure

The closure begins at the exact Profile manifest, resolves all fourteen
required file bindings, and then resolves every machine-active Profile-owned
dependency declared by those slot interfaces. A manifest slot value uses one
exact canonical path relative to that Profile directory; `inline`, `./`, `..`,
backslashes, case or Unicode aliases, extension guessing, and repository-root
fallbacks are not bindings. The typed edge records the resolved canonical
repository-relative path. Its current transitive file edges are:

- every `Predicate owner` in the Audit Dimension Registry, including an
  optional heading fragment; and
- an explicit `--config` target in the required K12/09 residual-scan command.

A persistent verifier under `Tools/` is governed executable code rather than a
Profile-owned dependency. Corpus pages and Corpus Planning artifacts keep the
external resolution rules of their own contracts and do not become
Profile-owned merely because a Profile names them. A custom verifier with no
`--config` remains legal; arbitrary flags are not inferred to be dependencies.

Every transitive Profile-owned reference MUST use one canonical
repository-relative spelling, and every first-hop or transitive edge MUST
resolve to a safe, singly-linked, strict-UTF-8 file physically inside the same
Profile directory. Absolute paths, empty, `.` or `..` segments, path aliases,
symlinks, hard links, another Profile, and repository-root fallbacks are
invalid. The unfilled sentinel in any file read by this closure is invalid,
regardless of filename suffix. A predicate-owner fragment MUST resolve to
exactly one real Markdown heading;
an absent or ambiguous heading is unresolved. The closure is all-or-nothing:
an invalid edge does not disappear and the foreign target's bytes cannot stand
in for an authorized dependency.

The `profile-load` Gate in [[kernel/K00 Standards Control/12 Control Registry#Control Registry|Control Registry]] is the sole control owner. Its producer derives the closure from one immutable Profile-tree snapshot and emits that snapshot fingerprint, a typed contract fingerprint, and one fingerprint over the complete canonical root-input closure. That closure is nine fixed roots -- the Profile interface, form defaults, execution defaults, operation capabilities, metadata authority, compiled metadata artifact, applicability base, relationship base, and Gate registry -- plus the exact capability-implementation set deterministically enumerated from the frozen operation-capability registry. Consumers invoke that producer once or consume a current receipt; they MUST NOT reparse registry prose, reopen slot bytes, or substitute caller-selected rule inputs into a second authority graph.

Runtime authority membership is a closed machine-readable registry. Active
Standards and `profile-load` are primary compare-and-swap authorities. The
compiled metadata execution contract is a derived authority covered by the
exact `profile-load` root-input closure: the producer compiles it from those
same immutable snapshots, proves the registered artifact byte-equal, and
retains that exact in-process object for runtime consumers. A consumer with an
admitted runtime MUST reuse that object; reopening the artifact would create a
second authority observation and repeat the implementation closure. A future
runtime authority MUST declare whether it is primary or which registered
primary authority covers its complete input set before it can enter the
transaction context.

One runtime validation phase owns one Profile currency bracket. After its
before-check it MAY give nested readers an opaque scope bound to the exact
root, manifest and authorized view. They read that immutable snapshot;
the outer phase owns the after-check. A direct reader owns both checks. The
scope MUST NOT cross a write, validation return, or phase: it removes nested
rereads, not the CAS boundaries protecting state or receipt publication.

The closure is not a Read Set, selects no route, and is never copied into
`selected_read_sets` or `loaded_module_paths`. Because every Profile-owned
target of a passing closure remains inside one Profile directory, the directory
snapshot binds its bytes while the contract fingerprint binds dependency kind,
owner and target identity, canonical path, and optional heading.

A consumer that freezes this identity into mutable runtime state treats one
passing evaluation as a compare value, not a lease. It MUST carry the same
authorized in-process view through every proposed, locked, post-write, and
receipt-producing check in one transaction, then compare the exact manifest,
Profile-tree snapshot, typed-contract fingerprint, root-input fingerprint,
and approved canonical adopter Standards state at each write boundary. A Profile-derived
compiled artifact additionally MUST be byte-equal to the deterministic output
of that view and bind its artifact fingerprint; provenance prose alone is not
authorization. Initial runtime publication stages the shared writer lock in
the unpublished namespace, rechecks immediately before and after the atomic
no-replace rename, and atomically withdraws the still-locked namespace on
drift. If withdrawal or lock ownership cannot be proved, the public recovery
lock remains and initialization fails closed.

`profile-load` proves package authority and resolvability. The separate
`registered-residual-content` Gate executes the admitted scan against corpus
bytes and produces candidates; a configuration fingerprint from that run does
not prove Profile ownership, and neither Gate substitutes for the other.
