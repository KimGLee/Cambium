## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/13 Runtime Admission and Recovery|Runtime Admission and Recovery]].
- Next: [[kernel/K00 Standards Control/19 Profile Extension Interface|Profile Extension Interface]].

## Purpose

This module owns the derived dependency closure of one candidate or selected
Profile. It does not own Read Set loading, Profile selection, residual-content
classification, or any predicate's meaning.

## Profile Dependency Closure

The closure begins at the exact Profile manifest, resolves every required slot
binding declared by the Profile interface, and follows every machine-active
Profile-owned dependency declared by those slot contracts. A binding uses one
canonical repository-relative path inside that Profile. Aliases, guessed
extensions, and repository-root fallbacks are not bindings. Each typed edge
records its owner, target, dependency kind, canonical path, and any explicit
heading fragment.

A registered Tool capability is governed executable code rather than a
Profile-owned dependency. Corpus pages and Corpus Planning artifacts keep the
resolution rules of their own contracts and do not become Profile-owned merely
because a Profile names them. Tool arguments do not implicitly create
dependency edges; the Profile interface must declare each machine-active edge.

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

The `profile-load` Gate in [[kernel/K00 Standards Control/12 Control Registry#Control Registry|Control Registry]] is the sole control owner. Its `profile_snapshot_sha256` binds exactly the manifest and every Profile-owned file reachable through the authorized typed dependency closure; an unrelated file merely colocated in the Profile directory is not Profile authority and does not enter that identity. The producer additionally emits a typed contract fingerprint and one fingerprint over the complete canonical root-input closure. Consumers invoke that producer once or consume a current receipt; they MUST NOT reparse explanatory prose, reopen slot bytes into a second authority observation, or substitute caller-selected rule inputs into another authority graph. Which root inputs and capability implementations form the closure is owned by the producer's machine contract, not this prose.

Runtime authority membership is a closed machine-readable registry. Active
Standards and `profile-load` are primary authorities; a derived authority is
valid only when a registered primary authority covers its complete input set
and the derived bytes equal the deterministic output of those inputs. A
consumer MUST use one admitted Profile view for one validation or transaction
boundary rather than combine observations from different snapshots.

The closure is not a Read Set, selects no route, and is never copied into
`selected_read_sets` or `loaded_module_paths`. Because every Profile-owned
target of a passing closure remains inside one Profile directory, the projected
Profile snapshot binds exactly those target bytes while the contract
fingerprint binds dependency kind, owner and target identity, canonical path,
and optional heading. Root-owned interface, capability, and contract inputs
remain separately bound by `profile_load_inputs_sha256`.

For a Structure Registry, package admission validates both the Kernel-owned
version-2 shape and every derived role's stable projection-capability/runtime-
object identity against that root-input closure. It does not replace the
`structure-registry` Gate's current corpus-path, heading, Global Map, or
Coverage resolution. During Standards adoption the Structure predicate names
both affected Gates: `profile-load` owns candidate after-image admission, and
`structure-registry` is its semantic leaf for the structural resolution that
the admitted package requires.

A consumer that freezes this identity into mutable runtime state treats a
passing evaluation as a compare value, not a lease. Before committing a result
or publishing evidence, it re-establishes equality of the manifest, Profile
snapshot, typed-contract fingerprint, root-input fingerprint, and approved
Standards identity. A Profile-derived artifact additionally equals the
deterministic output of that admitted view and binds its own fingerprint;
provenance prose alone is not authorization. Drift or uncertain publication
fails closed while preserving recoverable evidence. Locking, publication, and
recovery mechanics belong to Tool.

`profile-load` proves package authority and resolvability. The separate
`registered-residual-content` Gate executes the admitted scan against corpus
bytes and produces candidates; a configuration fingerprint from that run does
not prove Profile ownership, and neither Gate substitutes for the other.
