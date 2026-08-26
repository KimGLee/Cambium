## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]].
- Next: [[kernel/K00 Standards Control/05 Core Principles|Core Principles]].

## Control State Separation

The state axes are independent and retain their own canonical owners:

- whole-task state: [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|K13/03]];
- batch lifecycle and holds: [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]];
- page authoring, learning, coverage, and evidence axes: [[kernel/K08 Metadata and Status/03 Status Axes|K08/03]];
- expression readiness values: the selected Profile's `Expression Status Axis` binding.

No axis may be used as evidence for another. In particular, batch lifecycle is
not whole-task state or page quality; authoring status is not learning progress
or evidence strength; and expression readiness is not canonical-note depth.

`coverage_disposition` states whether a page or not-yet-created knowledge
object belongs to the current scope. Coverage owns that disposition; Queue
cancellation cannot change it. Any authorized cancellation that changes scope
must use one controlled Amendment transaction whose observable result keeps
Coverage, Queue, and Progress consistent. Direct Queue-only cancellation and a
hand-edited inconsistent staging window are forbidden.

## Scope

This Standard applies to the knowledge-corpus scope explicitly registered by the selected `Profile Scope` and governed by this control plane. The specific goals, knowledge structure, content catalog, and expansion scope are provided by that role; the kernel does not hard-code a deployment inventory.

Explicit exclusions MUST be written into the `Excluded Scope` slot; when no exclusions are registered, that slot MUST still be explicitly empty. Migration, refactoring, or acceptance MUST NOT go beyond the current task contract and that slot; any scope change requires corresponding authorization.

Kernel Standards belong to the control plane and do not count as ordinary content-building output. Only a separately authorized governance task MAY modify them; ordinary content tasks MUST treat them as a read-only protected scope.
