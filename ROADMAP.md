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
| Dependency propagation | The kernel defines semantic dependency invalidation and downstream `needs_rereview`, but no bundled compiler or change detector calculates the affected set |
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

## Typed Dependency Runtime

Turn the kernel's existing dependency, invalidation, and downstream re-review
semantics into a host-independent executable projection. This runtime is an
implementation of current governance rules, not a new source of dependency
policy and not a requirement that every knowledge link become an invalidation
edge.

### Compiled Dependency Model

Compile explicit relationship sources into a normalized typed dependency
graph. Eligible inputs include:

- frontmatter `prerequisites`;
- canonical-to-derived-artifact bindings;
- source and supported-claim bindings;
- registered MOC or collection membership;
- schema, profile, and Standards contract bindings;
- profile-registered relationship extensions that do not redefine kernel
  semantics.

Each normalized edge identifies the dependency, the dependent object, the
relationship type, its invalidation policy, and the declaration from which the
edge was compiled. The generated graph is a deterministic artifact. Knowledge
pages, profiles, registries, and ledgers remain authoritative, and rebuilding
the graph from the same accepted inputs must produce the same result.

Raw backlinks are discovery input, not dependency authority. A wiki link may
mean prerequisite, ownership, evidence, comparison, alternative, application,
or navigation. Only an explicit kernel relationship or profile-registered
extension participates in automatic semantic propagation. This prevents a
popular navigation target from invalidating every page that merely mentions
it.

### Change-impact Planning

Compare the latest accepted snapshot with the current candidate snapshot and
classify changes to content, paths, headings, aliases, governed metadata,
canonical ownership, evidence, schemas, profiles, or Standards contracts.
Resolve the directly affected dependents through the compiled graph and emit
an explainable impact plan containing:

- the changed object and change kind;
- the dependency edge that caused propagation;
- the affected object;
- the invalidated quality dimension;
- the required deterministic check or semantic review;
- the evidence needed to close or reuse the affected receipt.

The impact plan must integrate with the existing AuditPlan, Coverage Delta,
`needs_rereview` candidate pool, and AuditReceipt reconciliation contracts. It
discovers and plans affected work; it does not edit knowledge pages or write
the canonical ledgers directly.

Propagation remains bounded. Direct dependents are the default affected set.
Further expansion requires a registered transitive relationship, an observed
systemic failure, or explicit task authority. A local change must not trigger
an unconditional full-corpus LLM review, while a declared dependency must not
be ignored merely to reduce review cost.

### Host Independence

The core compiler and impact planner must operate on ordinary Markdown, YAML
frontmatter, profiles, registries, ledgers, and receipts without requiring
Obsidian or another knowledge host.

A host adapter may contribute wiki-link extraction, backlinks, rename events,
or host-specific identities. It must normalize them into the same dependency
model and must not make host configuration an authority for semantic edges.
In particular, the runtime must not depend on Obsidian Graph View state or
`.obsidian/graph.json`. A plain filesystem corpus and a host-backed corpus with
equivalent declarations must compile to equivalent normalized relationships.

### Runtime Boundary

The Typed Dependency Runtime may compile relationships, detect changes,
validate declared targets, produce affected sets, and emit receipts. It must
not:

- infer an unconfirmed domain dependency from semantic similarity alone;
- treat every backlink as a dependency;
- rewrite affected content automatically;
- promote authoring, evidence, learning, or expression-readiness status;
- bypass AuditPlan, Coverage Delta, or integrator authority;
- perform unbounded transitive review;
- declare batch or task completion.

This roadmap item is limited to note- and governed-object-level dependencies.
Inline or block-level dependency markup is outside its scope.

### Acceptance

The capability is complete only when:

1. identical accepted inputs produce a byte-identical normalized graph;
2. every declared dependency resolves or carries an explicit future, deferred,
   retired, or otherwise profile-authorized disposition;
3. an upstream change finds every directly affected dependent and explains
   each propagation path;
4. ordinary comparison, alternative, and navigation links do not trigger
   semantic invalidation;
5. path, heading, alias, content, evidence, and contract changes invalidate
   only their applicable dimensions;
6. the output can be consumed by existing AuditPlan and Coverage Delta flows;
7. empty scans, malformed declarations, and missing required inputs fail
   closed;
8. the runtime never modifies knowledge content while calculating impact;
9. bounded propagation and receipt reuse remain consistent with the kernel;
10. the conformance suite passes against both a plain Markdown fixture and a
    host-adapter fixture without host-specific semantic differences.

## Observability And Conformance

Make orchestration inspectable and testable:

- batch, agent-context, queue, receipt, and blocker status views;
- conflict, timeout, cancellation, and handoff diagnostics;
- interrupted-run and serial-merge recovery tests;
- equivalence tests between sequential and concurrent execution;
- conformance fixtures for profile generation, independent review, receipts,
  delta application, and host-adapter capability claims.

## Implementation Order

Profile onboarding and typed dependency compilation can progress independently
of agent orchestration. The dependency runtime consumes accepted corpus state
and emits plans; the reference execution runtime may later schedule those plans
without owning their semantic policy. Within the orchestration line, assignment
state and the deterministic integrator loop precede parallel worker automation;
observability and recovery tests accompany every stage. This order protects the
shared control plane while still making multi-context execution the intended
scaling path.
