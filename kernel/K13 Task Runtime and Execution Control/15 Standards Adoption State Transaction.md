## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]].
- Next: [[kernel/K13 Task Runtime and Execution Control/16 Resume Next Action Vocabulary|Resume Next Action Vocabulary]].

## Purpose And Boundary

This module owns only the controlled runtime-state transaction for active-task Standards adoption. [[kernel/K12 Quality Assurance/10 Standards Version Adoption|K12/10]] owns semantic validity, changed predicates, invalidated evidence, enforcement boundaries, and required Gate projection. The registered `standards-adoption` transaction capability is the sole writer.

## Permitted Transaction

The transaction may change only:

- canonical adopter Standards and selected Profile identity, effective
  authorization and upstream provenance, latest adoption evidence, and one
  adopter-state revision;
- the corresponding Standards and selected Profile identity in Coverage and
  Queue;
- those identity fields and, when K12/10 requires it, Contract version in
  Progress;
- Queue structural revision exactly once and Progress's accepted Queue
  reference;
- the resolved loading selection frozen by the adopted Task Contract; and
- one append-only Progress adoption entry binding the plan, before and after
  identities, invalidations, Gate evidence, and exact state fingerprints.

Everything else remains semantically and historically unchanged. Adoption cannot alter task state, objective, scope, completion semantics, Queue lifecycle revision, batch membership/order/dependencies, holds, manifests, Work Specs, Amendments, checkpoints, completion history, Coverage dispositions, receipts, or knowledge content. It is not a Queue transition, replan, schema migration, or batch execution.

## External Transaction Contract

The Standards-adoption transaction must:

- consume one current plan conforming to the K12/10 machine contract;
- compare the exact task state, Standards/Profile identity, Queue revisions,
  and authoritative before-state fingerprints;
- accept only `active` or `paused` tasks and reject every requested effect
  outside the permitted set;
- establish the candidate after Profile through `profile-load` and resolve the
  after loading identity before authority changes;
- produce complete after images whose cross-state identities agree and whose
  structural revision advances exactly once;
- consume after-image `required-queue-consistency`;
- publish immutable prepare/commit or abort evidence sufficient to distinguish
  completed, rejected, and uncertain outcomes;
- preserve all historical receipt bytes and represent invalidation through new
  references rather than mutation.

The multi-object result is not claimed to be one filesystem-atomic write. Currentness protection, publication order, rollback, and recovery belong to the Tool implementation. Kernel requires only that no partial or uncertain outcome can authorize work, before images and evidence remain recoverable, and a successful commit is externally verifiable against all after-state objects.

The commit evidence chains the before and after Task Contract anchors. Evidence created under the old Contract remains historical and cannot authenticate the new bytes.

## Resume Boundary

At restart, `runtime-startup-recovery` gives any unresolved adoption transaction precedence over batch execution. Recovery reconciles the plan identity, current state fingerprints, and prepare/commit/abort chain through the registered transaction capability. A committed adoption resumes under K12/10 without a second state rewrite; an uncertain transaction remains fail-closed until its single outcome is established.

## Related

- [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]]
- [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace|Runtime State Model and Namespace]]
- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
- [[kernel/K00 Standards Control/12 Control Registry|Control Registry]]
