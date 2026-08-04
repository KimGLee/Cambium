# Cambium Roadmap

This roadmap is non-normative. It describes product implementation directions,
not kernel rules, profile requirements, current capabilities, or release
commitments. A feature is available only when the repository contains its
implementation and the current documentation says how to use it.

The kernel and profile interface remain the authority for governed knowledge
work. Future convenience layers may collect, project, and execute decisions;
they may not invent domain policy, approve a profile, weaken a kernel gate, or
bypass R09 adoption.

## Current Baseline

| Area | Current state |
|---|---|
| Profile setup | Copy the 11-file `_template`, fill it manually, and run `check_profile.py` |
| Execution | The kernel defines sequential work, concurrent disjoint batches, independent review contexts, and serial integration |
| Runtime | No bundled orchestrator, scheduler, workspace manager, or host adapter |
| Tools | Deterministic checks, schemas, receipts, vocabulary/Card compilation, and single-delta application |

## Profile Onboarding Assistant

Provide a simpler path from operator decisions to a candidate profile without
creating a second profile interface.

The assistant should:

1. Create a validated `profiles/<profile-id>/` skeleton.
2. Collect answers in stages: identity and corpus goal; scope and architecture;
   language, priority, and sources; roles and expression artifacts; optional
   scans, routes, and gates.
3. Support both an existing corpus and a corpus that will be built from zero.
4. Project confirmed answers into the existing 11 canonical profile files.
5. Show the resulting diff and unresolved decisions before writing.
6. Run `check_profile.py` and report structural failures in user-facing terms.

The assistant must produce only a candidate. It must not infer unconfirmed
domain policy, copy example answers as defaults, write the active K00 state,
approve the profile, or bypass R09.

## Reference Execution Runtime

Implement the existing batch protocol as a host-neutral reference runtime.

### Assignment State

Track the mapping between durable work and temporary execution contexts:

- `batch_id`;
- `execution_context_id` and optional parent context;
- role (`integrator`, `writer`, `reviewer`, or `researcher`);
- permitted write scope;
- runtime status and handoff checkpoint.

Batch identity must survive an agent interruption or reassignment. Agent and
subagent topology remains runtime metadata rather than profile configuration.

### Integrator Loop

Implement the single-writer control path before automating parallel workers:

- admit only dependency-ready batches with disjoint manifests;
- own shared ledgers, queues, batch activation, and guidance disposition;
- collect each batch's receipts and delta;
- merge one batch at a time and run the global checks after each merge;
- checkpoint, pause, resume, and reassign interrupted work safely.

### Parallel Workers And Independent Review

Add isolated worker execution after the integrator loop is reliable:

- one write owner for each active batch;
- isolated workspaces and batch-private receipt/delta locations;
- parallel research and deterministic checks where they do not create shared
  writes;
- clean-context reviewers for L-tier substantive correctness review;
- explicit escalation when dependencies, review rounds, or merge checks do not
  converge.

The active-batch cap remains separate from the number of agent contexts.

### Host Adapters

Map the reference runtime onto concrete environments without making any one
host part of the kernel. An adapter may provide agent creation, workspace
isolation, cancellation, event delivery, and context identifiers. It must
declare unsupported capabilities and fall back safely rather than simulating
evidence it cannot produce.

## Observability And Conformance

Make orchestration inspectable and testable:

- batch, agent-context, queue, receipt, and blocker status views;
- conflict, timeout, cancellation, and handoff diagnostics;
- interrupted-run and serial-merge recovery tests;
- equivalence tests between sequential and concurrent execution;
- conformance fixtures for profile generation, independent review, receipts,
  delta application, and host-adapter capability claims.

## Implementation Order

Profile onboarding can progress independently of the runtime work. Within the
runtime line, assignment state and the deterministic integrator loop precede
parallel worker automation; observability and recovery tests accompany every
stage. This order protects the shared control plane while still making
multi-context execution the intended scaling path.
