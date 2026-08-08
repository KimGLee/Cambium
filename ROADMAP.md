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
| Profile setup | Copy the 13-file `_template`, fill it manually, and run `check_profile.py` |
| Execution | The kernel defines sequential work, concurrent disjoint batches, independent review contexts, and serial integration |
| Persistent work state | `.cambium/` separates object-level Coverage, the canonical Required Queue, task-level Progress, and hash-bound restricted-YAML complex-batch Work Specs; standard-library tools initialize, compile, validate, transition, apply Amendment-bound cross-Ledger changes, recover interrupted-write evidence, and render Queue state |
| Active-task Standards adoption | One restricted-YAML plan binds approved governance bytes, deterministic Kernel/Profile snapshots, old/new Contract/Standards/Profile/load set, changed predicates, dimension/boundary-specific invalidated evidence, immediate Queue consistency, and deferred gates; after required pre-rollbacks/holds, `adopt_standards.py` synchronizes all three runtime identities without changing lifecycle/holds, while append-only receipts preserve producer-era history, filter invalidated-evidence receipt IDs from current use, recover interruption, and avoid a prose duplicate |
| Runtime | No bundled orchestrator, scheduler, workspace manager, or host adapter |
| OpenAI Plugin adapter | No Plugin manifest, Skills, MCP configuration, Hooks, or marketplace entry. The candidate design is a host-specific adapter over the host-neutral Core, not a replacement for the kernel, selected Profile, or adopter-owned state |
| Corpus planning and impact inputs | A configured Profile explicitly binds restricted-YAML Global Map, Capability Matrix, and Gap Register artifacts; `check_corpus_plan.py` validates structure/reconciliation and emits deterministic JSON, while `record_corpus_acceptance.py` records the distinct Profile-authorized semantic decision as append-only JSONL; no duplicate Markdown report is persisted |
| Automatic dependency propagation | The kernel defines semantic dependency invalidation and downstream `needs_rereview`, but no bundled compiler or change detector yet calculates an affected set from the explicit planning inputs |
| Independent completeness and consistency evaluation | Current gates prove integrity within the declared Coverage, Queue, Delta, receipt, and snapshot boundaries. No bundled independent pass yet re-derives the expected corpus or impact set without trusting those declarations, or evaluates paraphrased cross-document contradictions as a general capability |
| Tools | Deterministic checks, schemas, receipts, vocabulary/Card compilation, Corpus Planning validation/semantic acceptance/on-demand Agent projection, Required Queue and Work Spec control, guarded Amendment and active-task Standards-adoption transactions, and single-delta application |

## Profile Onboarding Assistant

Provide a simpler path from operator decisions to a candidate profile without
creating a second profile interface.

The assistant should:

1. Create a validated `profiles/<profile-id>/` skeleton.
2. Collect answers in stages: identity and corpus goal; scope, architecture,
   and Corpus Planning applicability/bindings; language, priority, and
   sources; roles and expression artifacts; optional scans, routes, and gates.
3. Support both an existing corpus and a corpus that will be built from zero.
4. Project confirmed answers into the existing 13 canonical profile files.
5. Show the resulting diff and unresolved decisions before writing.
6. Run `check_profile.py` and report structural failures in user-facing terms.

The assistant must produce only a candidate. It must not infer unconfirmed
domain policy, copy example answers as defaults, write the active K00 state,
approve the profile, or bypass R09.

## Reference Execution Runtime

Implement the existing batch protocol as a host-neutral reference runtime.
The runtime consumes the existing `.cambium/state/required_queue.yaml`; it does
not create a parallel scheduler-owned batch ledger.

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
- consume Queue readiness, use the integrator-only transition tool for batch
  activation, and own guidance disposition without bypassing canonical state;
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

## OpenAI Plugin Host Adapter

Implement a single `cambium` OpenAI Plugin as the first concrete Cambium host
adapter and distribution surface. This capability is planned and is not
currently shipped. The Plugin may package Skills, a local MCP adapter, and
generated release resources, but it is not a new normative layer. The kernel,
exactly one selected Profile, and the target repository's `.cambium/` state
remain authoritative.

OpenAI currently documents Plugins as an installable package that may combine
Skills, MCP servers, Hooks, and assets. Its package contract is an evolving
product contract rather than a versioned Cambium dependency. Every Cambium
Plugin release must therefore be checked against the current
[OpenAI Plugins documentation](https://developers.openai.com/plugins) and
[builder contract](https://developers.openai.com/plugins/build/plugins), then
tested through real installation and ingestion.

### Architecture And Authority Boundary

The adapter must preserve these boundaries:

- Plugin installation or enablement is not Cambium adoption, activation, or
  Profile approval.
- Plugin reinstall, upgrade, downgrade, or removal must not migrate, replace,
  or delete an adopter's active Standard, selected Profile, task state, or
  receipt history.
- Kernel or Profile changes continue through the explicit Standards-adoption
  path and may not bypass R09.
- `plugin_resource_root`, `workspace_root`, and `state_root` are distinct
  capabilities. Plugin cache or `PLUGIN_DATA` may contain disposable caches,
  preferences, and indexes only.
- The adopter repository owns the adopted governance snapshot and canonical
  `.cambium/` Coverage, Queue, Progress, Work Specs, receipts, and evidence.
- Skills describe workflows, decision points, and user interaction. They do
  not enforce invariants, own normative rules, or prove conformance.
- MCP exposes a closed set of typed, high-level Core operations. It must not
  expose an arbitrary command runner, unrestricted path access, or a second
  state-writing implementation.
- The adapter consumes the canonical Required Queue. It must not create a
  scheduler-owned task or batch ledger in Plugin state.
- A generic adoption mode may inspect a repository and produce a candidate
  Profile when no Profile is selected. Runtime operations require exactly one
  selected and validated Profile.
- Hooks are optional defence-in-depth interaction controls. They require user
  trust and are neither protocol authority nor audit evidence.
- Repository-provided Profile verifiers are not executed automatically. Their
  source, requested capability, and effect must be disclosed and explicitly
  authorized, with allowlisting or isolation where applicable.
- Host-provided actor names, reviewer labels, or context identifiers do not by
  themselves prove authenticated execution or independent review.
- Plugin release artifacts are generated from canonical Core and adapter
  sources. Normative files are not maintained as independent manual copies
  inside the package.

An adapter must declare missing filesystem, isolation, cancellation, identity,
or controlled-writer capabilities and fail safely. It must not fabricate the
evidence that an unavailable Host capability would have produced.

### Initial Package Shape

The first release candidate should contain one `cambium` Plugin rather than a
suite of interdependent Plugins. Its source and generated artifact should be
separate so that package construction cannot silently fork the Core:

```text
adapters/openai-plugin/             # adapter source
  mcp_server/
  skills/
  tests/
packaging/                          # reproducible package builder
dist/plugins/cambium/               # generated installable artifact
  .codex-plugin/plugin.json
  skills/
  .mcp.json
  assets/
.agents/plugins/marketplace.json    # repository distribution metadata
```

New adapter and distribution paths require an explicit licensing and
attribution decision. A Plugin bundle that contains differently licensed
Tools, standards, documentation, or examples must retain the applicable
per-path notices rather than collapsing them into an inaccurate package-wide
claim.

The initial interaction surface should remain small:

- `adopt`: inspect the repository, collect operator-confirmed decisions,
  produce a candidate Profile and diff, and run structural validation without
  selecting or approving the Profile;
- `operate`: inspect or resume existing state, explain the deterministic next
  action, and route any later write through a controlled Core transaction;
- `audit`: inspect receipts, invalidations, batch-close evidence, and Terminal
  Proof while distinguishing deterministic results, semantic judgment,
  candidate findings, and unavailable evidence.

The first MCP adapter is local and read-only. Candidate operations include
workspace inspection, Profile validation, resume status, Queue validation,
receipt inspection, audit preview, and Terminal Proof verification. UI, remote
repository access, automatic agent dispatch, and public-directory distribution
remain deferred.

### Phase 0 — Core And Packaging Stabilization

Prepare Cambium for adapter use without changing kernel or Profile semantics:

- extract a stable, typed Core API from repository-layout-dependent scripts;
- normalize filesystem roots and path aliases across supported platforms;
- separate Plugin resources, target workspace, and canonical state;
- define Plugin, protocol, receipt, and minimum-Core compatibility;
- add platform CI and conformance fixtures for empty scans, path aliases,
  symlinks, hardlinks, stale revisions, concurrent writers, and interrupted
  writes;
- define generated-package, attribution, upgrade, rollback, and support rules.

Exit requires the complete supported test matrix and negative fixtures to
pass, a documented compatibility contract, and no critical verifier depending
on an ambiguous repository-relative `Tools/` root.

### Phase 1 — Read-only Private Alpha

Validate Plugin discovery and interaction without accepting write risk:

- package the three Skills and a read-only local MCP adapter;
- support workspace inspection, Profile validation, existing-state resume,
  status explanation, and audit explanation;
- distribute through a local or repository marketplace;
- omit Hooks, UI, remote MCP, and automatic agent dispatch.

Exit requires successful manifest validation, real installation and new-task
loading, positive and negative Skill activation tests, zero target-state
mutation, and proof that reinstall or upgrade leaves canonical state
unchanged.

### Phase 2 — Guarded Local Beta

Add writes only through Core transactions:

- expose explicit dry-run and apply operations;
- require exact workspace roots, expected revisions, locks, receipts, and
  interruption recovery;
- support candidate Profile onboarding and the bounded
  initialize/compile/transition/apply/close/complete lifecycle;
- preserve single-writer integration and explicit user authority.

Exit requires successful clean adoption, existing-state resume, interrupted
writer recovery, build and maintenance completion paths, and fail-closed tests
for stale revisions, path escape, prompt injection, unauthorized verifier
execution, and arbitrary-command input. Uninstall or reinstall must not lose
target state.

### Phase 3 — Codex Execution Adapter

Implement the execution capabilities defined by the Reference Execution
Runtime, in this order:

1. durable assignment state;
2. the single-writer integrator loop;
3. isolated workers;
4. clean-context reviewers;
5. cancellation, interruption, reassignment, and observability.

Exit requires replayable parallel batch work with serial integration, explicit
safe failure for unsupported Host capabilities, and evidence-backed actor and
reviewer claims. An inherited-context agent must not be represented as an
independent reviewer.

### Phase 4 — Workspace And Ecosystem Distribution

Only after the Core API, compatibility model, and permission boundary are
stable, evaluate:

- Workspace sharing;
- host-specific source and event connectors;
- a read-only observer or status UI;
- a public Skills-only educational package that makes no conformance claim;
- remote MCP and Universal Plugin Directory submission.

A connector may contribute source, event, or authenticated identity evidence.
It must not become Profile authority, dependency policy, semantic ownership,
or completion authority. Public remote MCP remains blocked until the local
repository data path, authorization, retention, and threat model are complete.

### Release Gates

- **G0 — Current Plugin contract:** validate against current official
  documentation and real ingestion; test manifest, MCP, Hooks, cache, new-task,
  upgrade, and rollback behavior; do not claim a frozen Plugin "v1".
- **G1 — Protocol and Core:** all supported tests and negative fixtures pass;
  plain-filesystem and Host-adapter fixtures produce equivalent Cambium
  semantics.
- **G2 — Plugin archive:** install, reinstall, upgrade, and new-task loading
  pass; package resources are complete; Plugin lifecycle cannot migrate active
  Cambium state.
- **G3 — Adapter E2E:** adoption, resume, interrupted-write recovery, batch
  integration, Terminal Proof, maintenance completion, Standards adoption, and
  uninstall/reinstall persistence pass.
- **G4 — Security and trust:** no arbitrary-command surface; exact workspace
  capabilities; prompt-injection and path-escape coverage; no credentials in
  logs or receipts; accurate tool side-effect annotations; no actor, reviewer,
  or isolation claim without Host evidence.
- **G5 — Public distribution:** immutable release, support matrix, changelog,
  migration guide, conformance bundle, licensing and attribution review,
  security and privacy policies, sufficient positive and negative tool cases,
  and a closed local-repository or remote-MCP data architecture.

### Non-goals

This roadmap item does not:

- rewrite Cambium as one large Skill or prompt;
- make Plugin files, cache, or a remote service the owner of the active
  Standard or canonical state;
- let Plugin updates silently migrate the kernel, Profile, or an active task;
- claim Cambium conformance from prompt-level behavior;
- provide an arbitrary shell-command MCP tool;
- make UI or Hooks part of the trust boundary;
- auto-execute adopter-controlled verifier code;
- bundle automatic agent dispatch before the Reference Execution Runtime is
  implemented;
- claim authenticated actors, independent review, or workspace isolation
  without corresponding Host evidence;
- require remote MCP or Universal Directory publication for the local MVP;
- split Cambium into multiple dependent Plugins before the single-adapter API
  and upgrade model are stable.

## Typed Dependency Runtime

Turn the kernel's existing dependency, invalidation, and downstream re-review
semantics into a host-independent executable projection. This runtime is an
implementation of current governance rules, not a new source of dependency
policy and not a requirement that every knowledge link become an invalidation
edge.

### Compiled Dependency Model

Compile explicit relationship sources into a normalized typed dependency
graph. Eligible inputs include:

- the configured Global Map's explicit typed dependencies;
- the Capability Matrix's explicit capability priorities, canonical paths,
  evidence, and Gap IDs;
- the Gap Register's explicit capability links and promoted Coverage paths;
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

## Independent Completeness And Consistency Evaluation

Add a read-only evaluation boundary that does not let the execution plan grade
its own completeness. Existing gates remain authoritative for the consistency
of declared Coverage, Queue, Delta, receipt, and snapshot state. This evaluator
addresses the different question of whether those declarations describe the
whole expected scope and impact set.

### Independent Expected-set Re-derivation

At initial inventory, applicable batch close, and Terminal Audit, independently
derive the expected set from upstream accepted inputs. Eligible authorities
include the frozen Task Contract, selected Profile Scope and exclusions,
accepted Global Map, Capability Matrix and Gap Register, baseline and candidate
repository snapshots, accepted Guidance and Amendments, and the compiled typed
dependency projection.

The re-derivation pass must not use the worker's Queue manifest, Delta, changed
file list, completion claim, or self-authored rationale as the authority for
what should be in scope. It may read those artifacts only after deriving the
expected set, in order to compare:

- the independently discovered in-scope corpus with Coverage inventory records;
- the independently derived affected set with planned Queue manifests;
- the planned manifest with the actual Delta and changed-file set;
- the affected set with current review, invalidation, and receipt coverage.

The result reports exact missing, unexpected, deferred, excluded, and
unresolved members. Set disagreement cannot be collapsed into a passing count,
and a zero-member result is not a pass unless an independently verifiable empty
scope predicate applies. When the accepted inputs are insufficient to derive a
member or disposition, the evaluator fails closed or raises an explicit
adjudication candidate rather than silently accepting the executor's choice.

### Cross-document Concept Consistency

Add a bounded evaluation over documents that explicitly share a canonical
concept, owner, dependency edge, capability, Gap, source-supported claim, or
canonical-to-expression binding. It should detect at least:

- incompatible definitions or mechanisms attributed to the same concept;
- conflicting defaults, constants, thresholds, state transitions, or exception
  conditions;
- a derived or expression artifact contradicting its canonical owner;
- two apparent canonical owners for one responsibility;
- a downstream page that still asserts an invalidated upstream conclusion.

Deterministic comparisons over registered fields, identifiers, constants, and
relationships run first. A semantic evaluator may review paraphrases only over
the bounded, explainable concept group and must return the compared passages,
canonical owner, finding rationale, and confidence or adjudication status. It
does not acquire authority to invent dependencies, rewrite content, or approve
its own findings. Lexical duplicate detection remains candidate discovery and
does not substitute for contradiction evaluation.

### Separation And Trust Boundary

The evaluator is a separate read-only pass with independently constructed
inputs and no authority to modify Coverage, Queue, Progress, content, or its own
acceptance threshold. A clean-context reviewer may satisfy the procedural
separation in a local deployment; stronger deployments may use an isolated
runner, protected baseline, signed receipt, or authenticated reviewer identity
through a host adapter. Actor labels and repository-local hashes alone remain
integrity evidence, not proof of independent execution.

External evaluation libraries may be optional adapters for semantic metrics,
datasets, and experiment execution. They must not become the owner of Cambium's
scope, dependency, canonical-ownership, or completion semantics, and an adopter
must be able to run the deterministic expected-set checks without a hosted
service.

### Acceptance

The capability is complete only when:

1. a fresh filesystem inventory independently detects an in-scope Markdown
   file omitted from Coverage;
2. an independently derived impact set detects an affected object omitted from
   the Queue, Delta, review scope, or invalidation set;
3. a negative fixture that updates only half of the true expected set fails
   even when its Coverage, Queue, Delta, receipts, and proof are internally
   consistent with that incomplete half;
4. paraphrased cross-document contradictions are surfaced without treating
   consistent paraphrases as failures;
5. exclusions, deferrals, and not-applicable decisions are explicit,
   authority-bound, and independently checkable;
6. empty scans, missing upstream inputs, ambiguous ownership, and unresolved
   dependency targets cannot produce a green result;
7. evaluation receipts bind the baseline and candidate snapshots, accepted
   upstream authorities, derived expected sets, evaluator version, and exact
   findings;
8. the evaluator is read-only and cannot reuse the executor's expected-set
   artifact as its own derivation;
9. the deterministic layer works on a plain filesystem corpus without a
   particular agent host or external evaluation service; and
10. existing Queue, batch-close, Corpus Planning, and Terminal Proof gates
    continue to validate their current ownership boundaries rather than being
    duplicated inside the evaluator.

## Observability And Conformance

Make orchestration inspectable and testable:

- batch, agent-context, queue, receipt, and blocker status views;
- conflict, timeout, cancellation, and handoff diagnostics;
- interrupted-run and serial-merge recovery tests;
- equivalence tests between sequential and concurrent execution;
- conformance fixtures for profile generation, independent review, receipts,
  delta application, and host-adapter capability claims.

The local baseline deliberately treats repository/tool/evidence writers as a
trust domain. Deployments that include adversarial writers may add signed
receipts, protected-runner attestations, and authenticated actor/reviewer
identity through a host adapter; those controls must strengthen the existing
byte and state bindings rather than replace them.

Add a guarded non-scope Task Contract Amendment transaction for objective,
exclusion, acceptance, timing, and pause-policy changes. The current baseline
intentionally fails closed on direct post-materialization edits and ships only
scope/disposition Amendment writes; until this writer exists, such a change
rolls into a preserved successor task rather than mutating live Contract bytes.

## Implementation Order

Profile onboarding and typed dependency compilation can progress independently
of agent orchestration. The persistent Required Queue is already the execution
interface; the future reference runtime consumes it rather than redefining it.
The dependency runtime consumes accepted corpus state and emits plans; the
reference execution runtime may later schedule those plans without owning their
semantic policy. Filesystem-to-Coverage inventory re-derivation can be delivered
before the full typed dependency runtime; impact-set and bounded semantic
consistency evaluation follow the compiled dependency model so they do not
invent a second relationship authority. Within the orchestration line,
assignment state and the deterministic integrator loop precede parallel worker
automation; observability and recovery tests accompany every stage. This order
protects the shared control plane while still making multi-context execution
the intended scaling path.

Core stabilization precedes every state-writing Plugin capability. The
read-only Plugin alpha may progress alongside Profile onboarding and typed
dependency work because it does not own canonical state. Guarded writers follow
the stable Core API, while the full Codex execution adapter follows the
single-writer integrator loop. Workspace and public distribution are downstream
delivery choices and do not define completion of the host-neutral Cambium
runtime.
