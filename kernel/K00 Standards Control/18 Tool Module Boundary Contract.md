## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/17 Profile Dependency Closure|Profile Dependency Closure]].

## Purpose

This module owns one object: the declared boundary of each shipped tool module
-- its identity, the surface other modules may consume, and the direction its
dependencies run. It owns no rule about what a tool computes, no Gate, and no
size policy. Whether a check may be codified stays with
[[kernel/K12 Quality Assurance/05 Automated and Manual Checks|K12/05]]; which
producer authorizes which Gate stays with
[[kernel/K00 Standards Control/12 Control Registry|K00/12]]; the prose leaf
budget stays with
[[kernel/K00 Standards Control/03 Standards Governance#Leaf Module Size Budget|K00/03]]
and does not extend here.

The boundary needed an owner because its absence had a direction. A tool that
declares no public surface makes every internal function a compatibility
obligation the moment a second module reads it, and each new governance
capability then integrates into whichever module already holds the state --
not because the code could go nowhere else, but because no other protected
entry point existed. That accretion is invisible while it happens and
expensive once discovered.

## Module Boundary Contract

A shipped module is any `Tools/**/*.py` delivered to adopters. The
distribution's own verification trees are not shipped modules; the
[[kernel/K00 Standards Control/03 Standards Governance#Distribution Boundary|Distribution Boundary]]
already declares them.

Every shipped module carries one entry in the root-owned declaration
`Tools/module-boundaries.yaml`, whose three axes are independent:

- **Identity.** `kind` takes exactly one of `cli-entry`, `shared-library`,
  `runtime-library`, `adapter`, `schema`. `authority` is a separate optional
  list of governance standings, currently only `gate-producer`. A module that
  forwards another's surface for compatibility declares `facade_for`. These
  are three questions, not one: a CLI entry point can hold Gate producer
  authority and forward a package's surface at the same time, and collapsing
  them into a single role word would force a false choice.
- **Public surface.** A module consumed across module lines declares the
  symbols it offers. A surface inherited from before this contract existed is
  marked `provisional`: it is guarded against widening, and narrowing it is
  not a compatibility break, because it was never adjudicated as a promise.
- **Direction.** Each module declares its layer or its permitted targets. The
  static import graph over shipped modules MUST be acyclic.

Consumption of a symbol outside the declared surface is a defect. It may be
carried as a registered exception naming the consumer, the symbol, its
necessity, its retirement condition, and a content binding over the
definition it excepted. The binding is what makes the entry a judgment about
specific code rather than a standing permission: when the definition changes,
the exception stops matching and must be argued again.

**No exception is available for a cycle.** A symbol exception is a bounded
compromise about one name; a cycle makes the direction question unanswerable
for every name at once, which is the property this contract exists to keep
decidable.

## What This Contract Does Not See

Naming the gaps is part of the contract, because a guard whose limits are
undocumented gets read as proof of more than it checked.

- **Subprocess invocation** of another tool's command line consumes that
  tool's registered CLI surface, owned by the compiled CLI contract, not the
  import rules here.
- **Registry-driven producer resolution** -- resolving a producer module named
  by the Stable Gate ID Registry and reading its declared Gate constants -- is
  a declared control inversion, verified against that registry's closed target
  set rather than treated as a static import edge.
- **Direct calls from outside the distribution**, whether an execution session
  or an adopter's own code, reach internal functions no machine here can
  observe. Such a call is a defect under this contract and its remedy is a
  declared public entry point, but the enforcement is discipline, not
  detection.

## Enforcement And Observation

The machine consumer is the distribution's own unit suite. It registers no
Gate ID and does not run in an adopter runtime, on the same reasoning the
Distribution Boundary gives: an adopter carries `Tools/` and cannot
reorganize it, so projecting this obligation onto adopters would ask them to
resolve something only the distribution can.

Because a public-surface contract cannot see growth that adds no public
symbol, the same parse also emits a non-blocking report of module size,
top-level definitions, importer counts and dependency components. Those
values give review a factual trigger. They are never a threshold: a byte cap
protects a delivery budget, and no tool module is delivered by the byte, so a
cap here would constrain without protecting anything.

## Related

- [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]]
- [[kernel/K00 Standards Control/12 Control Registry|Control Registry]]
- [[kernel/K00 Standards Control/16 Leaf Module Size Register|Leaf Module Size Register]]
