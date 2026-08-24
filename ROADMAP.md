# Cambium Roadmap

This roadmap describes product direction. It is not a kernel rule, a Profile
requirement, or a release promise.

A capability is available only when its implementation, documentation, and
tests are present in the repository. A roadmap paragraph alone never makes a
feature available.

## How To Read This Roadmap

Every item has one of four states:

| State | Meaning |
|---|---|
| **Complete** | Shipped in the repository and documented for use |
| **In progress** | Active implementation work; not available until the complete change lands |
| **Next** | Intended next capability with a defined boundary and completion test |
| **Conditional** | Built only if its trigger occurs or a separate product decision is made |

The current user-facing capability summary lives in [README.md](README.md).
This file records what changes next and why.

## Status At A Glance

| Capability | State | Short version |
|---|---|---|
| Profile onboarding reform | Complete | One pre-closed template, scaffolder, interview contract, status view, checks, and end-to-end tests ship |
| Persistent task and Queue runtime | Complete | Coverage, Required Queue, Progress, controlled writers, receipts, recovery, and closure paths ship |
| Workflow progression MVP | Complete | Exact candidate carry, bounded delegated Amendments, and routed-gap settlement ship |
| Host-neutral agent interface | Complete | CLI contract, MCP projection, stdio server, and four host renderers ship |
| Activation transport and Assignment delivery | In progress | Replace an unprovable “server sent it” claim with budgeted delivery, host conformance, acknowledgements, and a delivery gate |
| Reference execution runtime | Next | Add durable Assignment state, a single-writer integrator loop, then isolated workers and reviewers |
| Git-backed workspace and diff adapter | Next | Bind one Assignment to an isolated worktree, reviewable diff, named sources, exact Git snapshots, and serial post-merge read-back without making Git a second Queue |
| Governed retrieval adapter contract | Next | Export deterministic governed-corpus manifests, invalidation feeds, and exact citation envelopes to external retrievers without making Cambium a RAG engine or an index authoritative |
| State-aware operation discovery | Next | Its scope has changed: the shipped MCP surface comes from tool CLIs, and any future discovery view must not become a second policy engine |
| Typed dependency runtime | Next | Compile explicit corpus relationships and produce bounded change-impact plans |
| Independent completeness and consistency evaluation | Next | Re-derive expected scope without trusting the executor's own Queue or Delta |
| Machine-readable review rulings | Next | Make finding, confirmation, conditional fix, and close-gate evidence one load-bearing chain |
| Receipt ledger integrity chain | Next | Add linked receipt history with an external tail anchor and era-aware replay |
| Observability and broader Contract Amendments | Next | Runtime status and two amendment fields ship; orchestration views and additional contract fields remain |
| OpenAI Plugin packaging | Conditional | Consider only after per-corpus binding and package lifecycle requirements are solved |
| Detached state transactions | Conditional | Needed only when an authoritative writer cannot finish on its normal execution channel |
| Concurrent receipt sealing | Conditional | Needed only if Cambium expands beyond the current single-writer maintenance window |
| Sealed-evidence follow-ups | Next | The reported reachability defect is fixed; protected-set derivation, rehydration, and declared projections remain |

## Authority Boundaries That Do Not Change

Every roadmap item must preserve the same control plane:

```text
authority
  = Cambium kernel
  + exactly one selected Profile
  + adopter-owned .cambium state
```

Convenience layers may collect decisions, render views, or call controlled
operations. They may not:

- invent domain policy or approve a Profile;
- weaken a kernel gate or bypass R09 Standards adoption;
- create a second Queue, Progress ledger, or receipt authority;
- expose an arbitrary shell runner or unrestricted repository paths;
- run adopter-provided verifier code without explicit authorization;
- turn a retrieval score, query result, index, or cache into policy,
  dependency, promotion, state-transition, or completion authority;
- claim authenticated identity, isolation, independent review, or delivery
  without evidence from the host that provides it.

## Complete Foundations

These items used to be future roadmap work. They are now part of the current
baseline and remain here only to make the transition visible.

### Profile Onboarding Reform

Cambium now ships one template rather than “minimal” and “full” template
families. The template pre-closes switches that have a safe legal exit state
and leaves repository-specific decisions open.

The shipped flow includes:

- `profiles/template-files.yaml` as the exact-copy whitelist;
- `Tools/scaffold_profile.py` for safe candidate creation;
- `profiles/interview.yaml` as the machine-readable question contract;
- `Tools/profile_onboarding_status.py` as a read-only state and `next_action`
  view;
- `Tools/check_profile.py` for structural and dependency validation;
- end-to-end fixtures for existing and empty corpora.

An assisting agent may prepare a candidate. It may not approve the Profile,
select it, or infer unconfirmed domain policy.

The former target of “at most 15 operator decisions in 30 minutes” is now a
product-experience measurement, not an implementation claim. It remains
unproven until measured with real adopters. An automated interview runner is a
possible convenience layer, not a missing governance mechanism.

### Persistent Runtime And Workflow Progression

The adopter-owned runtime now separates:

- object state in Coverage;
- batch state in the Required Queue;
- whole-task state in Progress;
- complex-batch instructions in immutable Work Specs;
- proposed changes in Deltas and controlled plans;
- append-only evidence in receipts.

Three workflow debts are also closed:

1. `exact-carry-v1` reuses only the review disposition of an exact unchanged
   observation from the immediately previous successful close.
2. `amendment_authority` can delegate only registered bounded operational
   change classes; delegation cannot expand itself.
3. Every gap routed to a batch must be settled or rerouted before that batch
   reaches `merge-ready`.

These mechanisms reuse the existing ledgers and writers. They do not create a
parallel control plane.

### Host-neutral Agent Interface

The host-neutral interface is complete:

```text
each tool's argparse declaration
  -> Tools/compiled/cli-contract.yaml
  -> Tools/compiled/mcp-tools.json
  -> Tools/mcp_server.py
  -> generated host configuration
```

Claude Code, Codex, Kimi Code, and dsh consume generated registration and
workspace binding. The MCP server runs tools as subprocesses and passes their
verdicts through. It does not decide whether an operation is allowed or whether
evidence is sufficient.

This delivery changed the Plugin plan: Cambium no longer needs an OpenAI Plugin
to obtain a callable agent interface. A Plugin would add packaging and
distribution only.

### Sealed Evidence Reachability Fix

Receipt sealing now preserves the evidence a recorded Queue transition
consumed, resolves the required body from verified cold storage, and fails
closed when evidence exists in neither hot nor cold storage.

That closes the reported defect where sealing could silently reopen an already
discharged obligation. The broader follow-ups are listed under
[Sealed-evidence Hardening](#sealed-evidence-hardening).

## In Progress

### Activation Transport And Assignment Delivery

**State: In progress; not shipped until the complete standards, tools,
generated artifacts, and tests land together.**

The original activation protocol treated a server result delivered to an MCP
session as proof that the model context received the complete Card bundle. A
real host measurement showed that an oversized result could be externalized
while the receipt still claimed machine delivery. The server could prove what
it sent, but not what the host placed in context.

The replacement design separates four facts:

1. Queue admission freezes the exact Card and startup Read Set manifest.
2. Content travels one complete file at a time under a measured result-size
   budget.
3. The receiving execution context returns a nonce for each delivered piece.
4. A current Host Adapter conformance record proves that a within-budget result
   is delivered inline rather than truncated or externalized.

An Assignment then moves through:

```text
pending -> delivering -> delivered -> running
```

Only the Assignment delivery gate may authorize `running`. Queue `open` still
means the batch is admitted; it does not mean a worker has received its Cards.

Delivery evidence is bound to one Assignment, one execution context, one
Bundle, and one attempt. Reassignment or Profile/Bundle change requires
delivery again. Even a valid `delivered` state proves delivery, not that the
agent read, understood, or obeyed the material.

This item is complete when:

- the piece budget is derived from reproducible positive and negative host
  measurements;
- oversized leaves fail during admission rather than mid-delivery;
- every piece is hash-bound, delivered, and acknowledged in one context;
- a versioned Host Adapter conformance record is current;
- a durable Assignment writer and gate consume the complete acknowledgement
  set;
- resume and reassignment invalidate old delivery evidence;
- unsupported hosts fall back to an explicit degraded state;
- the generated CLI/MCP artifacts and negative fixtures agree with the new
  protocol.

## Next Capabilities

### Reference Execution Runtime

Cambium defines batch lifecycle and serial integration, but does not yet run
agents. The reference runtime will consume the existing Required Queue rather
than inventing a scheduler-owned ledger.

Delivery order:

1. **Durable Assignment state** — map one admitted batch to one temporary
   execution context, role, write scope, delivery attempt, and checkpoint.
2. **Git-backed workspace and diff adapter** — bind that Assignment to an
   exact base commit/tree, batch-private worktree, admitted write surface,
   reviewable diff, and recoverable before/after identities.
3. **Single-writer integrator loop** — admit ready disjoint batches, collect
   Deltas and receipts, merge one batch at a time, and run global checks after
   each merge.
4. **Isolated workers** — one write owner per active batch with batch-private
   outputs.
5. **Clean-context reviewers** — receive only the review inputs required by
   the governing review contract.
6. **Recovery and observability** — cancellation, interruption, reassignment,
   conflict, timeout, and handoff diagnostics.

The active-batch limit remains separate from the number of agent contexts.
Host adapters must declare unsupported isolation, cancellation, identity, or
filesystem capabilities and fall back safely.

This capability is complete when parallel disjoint work is replayable, shared
integration remains serial, interrupted work resumes from durable state, and
no actor, reviewer, delivery, or isolation claim exceeds Host evidence.

### Git-backed Workspace And Diff Adapter

**State: Next; a reference adapter under the Reference Execution Runtime, not
a new control plane.**

Git already owns version history, textual diffs, commits, trees, and rollback.
Cambium must not recreate those mechanisms or treat a branch as a second task
ledger. The Required Queue remains the only canonical batch lifecycle, the
Assignment remains the execution-context record, and receipts remain the
evidence history. The adapter's job is to bind those existing authorities to
reviewable repository effects.

The reference flow is:

```text
Required batch + durable Assignment
  -> declared base commit and tree
  -> batch-private branch and worktree
  -> worker changes inside the admitted manifest
  -> reviewable diff bound to named sources
  -> batch-local checks and Delta/receipt publication
  -> single-writer serial integration
  -> exact post-merge tree read-back and global checks
```

For each attempt the adapter will record or bind, at minimum:

- repository identity, declared base commit, and base tree;
- Assignment, Task, Batch, Work Spec, admitted manifest, and allowed paths;
- the named sources or source-receipt IDs the change claims to use;
- branch/worktree identity without treating its name as authenticated actor
  identity;
- head commit, resulting tree, canonical diff bytes or patch ID, and their
  hashes;
- dirty, untracked, ignored, submodule, symlink, hard-link, and unsafe-file
  observations relevant to the admitted write surface;
- the exact merge or apply result, canonical post-merge commit/tree read-back,
  and the global check receipts run against that resulting repository state.

The worker may propose a commit or diff, but it may not advance shared Queue,
Progress, Standards, Profile, or integration state. Only the logical
integrator may accept one current attempt, apply it to the current canonical
tree, re-read the resulting tree, run the required global checks, and advance
the existing lifecycle. A tool or Agent transcript saying that a write or
merge succeeded is not evidence of the resulting repository state.

The adapter must fail closed on a stale base, out-of-manifest path, dirty or
unbound effect, partial commit, missing named-source binding, changed diff,
unexpected tree, unresolved textual conflict, interrupted merge, or
post-merge read-back mismatch. Recovery must preserve the branch, worktree,
lock, diff, and before/after identities until the integrator can reconcile the
attempt; cleanup must never discard unintegrated user or Agent bytes merely
because an Assignment was cancelled.

Git provides visibility and rollback, not semantic governance. A clean merge
does not prove correctness, completeness, reviewer independence, or actor
identity. In particular, Git may merge two Agents editing the same concept in
different files without a textual conflict. Canonical ownership, typed
dependencies, source review, cross-file consistency checks, and completion
gates remain Cambium responsibilities. External database or API side effects
are outside this adapter; an external-system adapter must perform an
authoritative post-action read-back and bind that observation before claiming
success.

This capability is complete when:

- one admitted Assignment can create or recover one isolated worktree from an
  exact declared base without modifying the operator's working tree;
- allowed-path and named-source checks bind a deterministic reviewable diff to
  its Assignment, Batch, Work Spec, base commit/tree, and head commit/tree;
- the integrator can serially apply one accepted attempt to the current
  canonical tree, re-read the exact result, and bind global checks to it;
- stale-base, path-escape, dirty-state, untracked/ignored-file, interrupted
  commit/merge, textual-conflict, and post-merge-drift fixtures fail without
  losing recoverable bytes;
- documentation states explicitly that Git detects textual repository changes,
  not cross-file semantic conflicts or whole-task completion;
- no Git branch, commit message, author label, generated graph, diff view, or
  adapter record becomes a second Queue, Progress ledger, receipt authority,
  Profile authority, or identity proof.

### Governed Retrieval Adapter Contract

**State: Next; a downstream consumption adapter, not a RAG engine, knowledge
base, or second knowledge-state authority.**

Cambium governs repository work, evidence, recovery, and closure, but it does
not yet define how an external search, RAG, Wiki, or Agent runtime consumes the
resulting governed corpus. Each adopter would otherwise have to invent which
objects are eligible, how stale or invalidated evidence is excluded, how an
index maps back to exact canonical bytes, and what must be rebuilt after a
change. That duplication creates inconsistent authority and makes the value of
governance hard to observe in downstream use.

The contract will expose a deterministic governed retrieval view over the
existing authority model:

```text
kernel + selected Profile + adopter-owned state + exact corpus snapshot
  -> typed, owner-bound eligibility projection
  -> eligible consumer manifest + separately authorized exclusion diagnostics
  -> principal-scoped change/invalidation feed
  -> disposable external lexical, vector, graph, or hybrid index
  -> currentness gate over manifest/index/permission watermarks
  -> retrieval result with an exact canonical citation envelope
  -> user or Agent consumer
```

The eligibility projection is derived from existing owners. It does not add a
universal `accepted` field, a retrieval-owned status ledger, or an implicit
promotion path. Its policy ownership is explicit:

- the kernel owns only protocol floors: exact snapshot binding, fail-closed
  unsupported states, and the rule that retrieval artifacts have no governance
  authority;
- the selected Profile owns corpus-specific retrieval eligibility through a
  typed, registered policy that maps existing authoritative facts to eligible,
  ineligible, or diagnostic-only outcomes;
- Coverage, property, evidence, source, claim, and invalidation owners continue
  to own their facts; the retrieval policy may read but not reinterpret or
  rewrite them;
- the Host owns identity and permission evidence; the adapter may project that
  evidence but may not invent a principal or access decision.

If the selected Profile has no legal retrieval policy for an object class, or
if a required owner fact is absent or ambiguous, eligibility is `unsupported`
and fails closed. The adapter must not infer `accepted` from
`authoring_status`, evidence maturity, recency, popularity, or a retrieval
score.

The contract must bind, at minimum:

- corpus/workspace identity and the exact filesystem or repository snapshot;
- current Standards and selected-Profile identity;
- canonical object identity, path, exact span, and content hash;
- the authoritative Coverage, property, currentness, and invalidation facts
  that determine inclusion or exclusion;
- registered source and claim references when the adopter's Profile provides
  them;
- Host Adapter conformance identity, tenant/workspace boundary, caller or
  principal identity, resource-permission snapshot or epoch, observation time,
  validity/expiry, and enforcement mode when permission-aware retrieval is
  claimed;
- an explicit unsupported result when current identity or permission evidence
  cannot be proved; a pre-bounded trusted corpus may be used only when that
  narrower boundary and its authorizing evidence are named, never as a claim
  of user-specific permission enforcement;
- adapter, manifest schema, chunker, embedding, graph, and reranker identities
  for every layer actually used.

The adapter will define four interoperable outputs:

1. **Eligible consumer manifest** — only objects the typed policy and current
   permission evidence admit, with exact byte/span identities, governing
   inclusion reasons, snapshot identity, `manifest_id`, and permission epoch.
2. **Principal-scoped change and invalidation feed** — deterministic additions,
   replacements, removals, permission revocations, evidence invalidations, and
   reindex scope between two manifests, with `from_manifest_id`,
   `to_manifest_id`, and a monotonic feed watermark. A revocation may identify
   a previously visible object so that a consumer can delete it; a never-visible
   unauthorized object must not appear.
3. **Citation and result envelope** — the returned passage plus canonical
   object/span/hash, current snapshot and Standards/Profile identity, available
   source/claim references, eligibility facts, retrieval trace, applied
   `manifest_id`, index watermark, permission epoch, and currentness verdict.
4. **Authorized exclusion diagnostics** — a separate reviewer/operator output,
   never part of the ordinary consumer manifest. Object identity and paths are
   shown only when current diagnostic permission evidence allows them;
   otherwise the report exposes only safe aggregate reasons and counts.

An external index must acknowledge the exact `manifest_id`, permission epoch,
and feed watermark it has applied. A query-time currentness gate compares that
acknowledgement with the current governed view, or performs an authoritative
read-through validation of the cited bytes and permissions. A result may claim
`current` only when one of those checks succeeds. A lagging, expired, or
unverifiable consumer is explicitly stale or fails closed. The acknowledgement
is consumption evidence, not a new knowledge or permission authority.

External retrievers may use BM25, embeddings, graph traversal, reranking, or a
combination. Those mechanisms are discovery and ranking inputs only:

- retrieval score is not evidence maturity, factual confidence, or promotion
  authority;
- retrieval miss does not prove that knowledge is absent;
- semantic similarity does not create a dependency edge or invalidation rule;
- an index, cache, chunk store, or generated graph is disposable and
  rebuildable, never canonical knowledge;
- a query or answer may not change Coverage, Queue, Progress, Profile,
  Standards, receipts, page state, or completion;
- permission-aware retrieval may be claimed only when current Host evidence
  binds the caller and source permissions; otherwise the adapter fails closed
  or exposes only an explicitly authorized pre-bounded corpus without claiming
  user-specific enforcement.

Cambium will not build general-purpose connectors, OCR, document parsing, a
vector database, relevance infrastructure, Chat UI, or a model gateway as part
of this capability. A small reference adapter and conformance fixtures may use
one lexical and one vector path solely to prove the contract. External systems
remain responsible for ingestion mechanics, indexing, retrieval, ranking, and
answer generation.

This capability can progress in parallel with the Reference Execution Runtime.
The Git-backed adapter supplies an exact repository tree when Git is the
workspace, but Git is not mandatory: a plain-filesystem adopter must be able to
bind an equivalent exact snapshot. Typed dependency runtime can later improve
change-impact precision; v1 may consume only explicit registered relationships
and invalidations and must not infer missing authority from similarity.

This capability is complete when:

- identical corpus, policy, Host-conformance, principal, permission-epoch, and
  adapter inputs produce a byte-identical eligible consumer manifest and
  principal-scoped change/invalidation feed;
- every returned passage resolves to the exact current canonical object, span,
  content hash, corpus snapshot, and governing eligibility facts;
- fixtures classified ineligible by the typed Profile policy are absent from
  the consumer manifest; never-visible unauthorized objects leak no identity,
  path, span, or governing reason, while authorized diagnostics and revocation
  tombstones reveal no more than their proven scope permits;
- content, state, evidence, Standards, Profile, or permission changes produce
  the required removal or reindex event, and a stale index watermark,
  permission epoch, expired lease, or mismatched `manifest_id` prevents an old
  result from claiming currentness;
- at least one disposable reference index can be deleted and rebuilt from the
  eligible manifest without losing authority, provenance, or exclusion
  semantics;
- a reference external-retriever fixture proves manifest ingestion,
  incremental invalidation, index acknowledgement, permission revocation,
  currentness rejection, citation round-trip, and fail-closed behavior;
- the adapter exposes no shared-state write operation, and negative fixtures
  prove that Cambium controlled writers and gates reject retrieval scores,
  similarities, cached results, envelopes, and Agent answers as promotion,
  dependency, state-transition, receipt, evidence-reuse, or completion
  authority;
- documentation and generated interface artifacts describe the same contract
  and make unsupported identity, ACL, source, and retrieval capabilities
  explicit.

### State-aware Operation Discovery

The earlier roadmap proposed one Operation Capability Registry as the source of
the MCP tool list. Delivery proved that two different questions were being
mixed:

- **What can this distribution call?** The shipped compiled CLI contract owns
  this answer.
- **What may this state do next?** Kernel rules and each controlled tool own
  this answer; `check_queue --resume-status` projects `next_action`.

The existing `Tools/operation-capabilities.yaml` has a narrower job: it binds
metadata fields and transitions to installed writers, consumers, producers,
and receipt schemas. K00/12 separately owns Gate capability and revalidation
mapping. Neither is a universal task-state permission table.

A future capability-discovery view is justified only if a runtime needs one.
If built, it must compose the compiled CLI contract with current state and
return an explainable permitted-operation set. It must not hand-list tools,
replace a writer's validation, or become a second transition authority.

This item is no longer a prerequisite for the MCP surface or Plugin packaging.

### Typed Dependency Runtime

Cambium already validates explicit Corpus Planning inputs and Profile
dependency closure. The missing capability is a host-independent compiler for
corpus relationships and change impact.

Eligible inputs include explicit Global Map dependencies, Capability and Gap
links, frontmatter prerequisites, canonical-to-derived bindings, source and
claim bindings, MOC membership, schemas, Profiles, Standards, and registered
relationship extensions.

The compiler will produce a deterministic graph. Every edge must name:

- the dependency and dependent object;
- the relationship type and invalidation policy;
- the declaration that authorized the edge.

A change-impact planner will compare accepted and candidate snapshots, explain
which edge caused each affected object, name the invalidated quality dimension,
and identify the required check or review.

Raw backlinks and semantic similarity are discovery inputs, not dependency
authority. The runtime must not rewrite content, promote status, perform
unbounded review, or declare completion.

This capability is complete when identical inputs produce byte-identical
graphs, every declared edge resolves or has an authorized disposition, direct
impact is complete and explainable, ordinary navigation links do not trigger
invalidation, and plain-filesystem and host-backed fixtures produce equivalent
semantics.

### Independent Completeness And Consistency Evaluation

Current gates prove that declared Coverage, Queue, Delta, receipt, and snapshot
state agree. They do not independently prove that the declarations cover the
whole expected corpus.

The new evaluator will first derive the expected set from upstream accepted
inputs such as the Task Contract, Profile scope, Corpus Planning artifacts,
repository snapshots, accepted Amendments, and the typed dependency graph. It
will then compare that set with Coverage, Queue manifests, Deltas, changed
files, invalidations, and receipts.

It must not use the executor's Queue, Delta, changed-file list, or completion
claim as the authority for what should exist.

The same read-only boundary will perform bounded cross-document checks for
conflicting definitions, defaults, thresholds, ownership, mechanisms, and
stale downstream conclusions. Deterministic comparisons run first; semantic
review is limited to explicit concept groups and returns the exact passages and
rationale.

This capability is complete when an internally consistent but incomplete half
of the true expected set fails, missing or ambiguous inputs cannot pass, empty
scope needs an independently verifiable predicate, and the evaluator cannot
modify state or approve its own findings.

### Machine-readable Review Rulings

Batch Review Requirements and judgment receipts now provide a machine-readable
batch-level foundation. K12/12 substantive review findings and confirmation
rulings are still prose.

The load-bearing sequence must be:

1. A review context writes stable finding IDs, grade, target, and judged bytes.
2. A distinct confirmation context writes one verdict per finding.
3. A conditional-fix writer resolves that verdict, checks the pre-image, applies
   the literal bounded patch under lock, and writes a receipt.
4. The batch-close gate refuses an unresolved or unexecuted conditional finding.

Until the first producer exists, a second-round `not-closed` result escalates.
An executor-created field that no independent producer writes and no close gate
consumes would not solve the problem.

### Receipt Ledger Integrity Chain

Receipts are append-only JSONL and many authorizing fields are already
cross-bound to state, plans, or anchors. A remaining structural class has only
one durable carrier and therefore cannot prove its own historical value.

The planned integrity layer adds:

- `prev_receipt_sha256` on each receipt in a chained producer era;
- a declared genesis value for the first line;
- an external tail anchor written into the canonical state transaction that
  appended the receipt;
- producer-era replay so pre-chain receipts remain valid under their original
  rules;
- fail-closed uncertain-tail and broken-suffix recovery.

A chain without an external anchor is insufficient because a writer could
rebuild the whole file. This feature adds forensic integrity; it does not grant
new authority or defend against an adversary who can rewrite state, tools,
plans, and evidence together.

### Observability And Contract Amendments

State-level observability already ships through `check_queue --resume-status`
and derived Queue reports. The reference runtime still needs views for
Assignments, agent contexts, delivery attempts, conflicts, cancellation,
timeouts, and handoffs.

The guarded Contract Amendment writer currently supports:

- `policy_exceptions`;
- `amendment_authority`.

Objective, exclusions, acceptance, timing, and pause policy still require a
successor task. Each field may gain a guarded transaction only with an explicit
authority rule, complete before/after binding, lock-time revalidation, recovery,
and consumer tests. A generic arbitrary Contract diff is not a goal.

### Sealed-evidence Hardening

The original hot-to-cold reachability defect is fixed. Three broader debts
remain:

1. The protected hot-reference set is still enumerated by hand rather than
   derived from consumers.
2. No sanctioned rehydration path moves a required cold row back to hot state.
3. The cold projection schema is fixed instead of being declared by consumers.

These are bounded follow-ups. They must extend the existing verified hot/cold
catalog rather than introduce a second receipt store.

## Conditional Extensions

### OpenAI Plugin Packaging

Cambium already works through generated MCP configuration. An OpenAI Plugin is
therefore an optional packaging and distribution layer, not part of Cambium
Core or the reference runtime.

The measured Agent Plugins shell cannot currently establish the adopter's
per-corpus workspace binding at handshake: it exposes no roots, an omitted
working directory resolves to the Plugin resource root, and environment
whitelist forwarding is unavailable. Codex therefore uses project-level
`.codex/config.toml` today.

Plugin work should resume only when that binding is solved upstream or another
explicit, tested carrier exists. If resumed, the first package should contain
one `cambium` Plugin with small `adopt`, `operate`, and `audit` Skills over the
existing host-neutral interface.

Required boundaries:

- install, update, downgrade, or removal never changes adopter-owned Standards,
  Profile, task state, or receipts;
- Plugin cache stores only disposable preferences, indexes, and caches;
- no arbitrary command runner or unrestricted path access;
- adoption produces a candidate and diff, never automatic approval;
- repository-provided verifiers require disclosed, explicit authorization;
- package contents are generated from canonical sources with correct
  per-path licensing and attribution.

Before any release, validate against the current
[OpenAI Plugins documentation](https://developers.openai.com/plugins) and
[builder contract](https://developers.openai.com/plugins/build/plugins), then
test real installation, new-task loading, upgrade, rollback, and removal.

Public marketplace distribution, remote MCP, UI, and Workspace sharing remain
later product decisions. They do not define completion of the host-neutral
runtime.

### Detached State Transactions

This protocol is needed only if the authoritative execution channel cannot
allow a state writer to finish.

The safe design is:

1. `detached prepare` locks the real authoritative namespace and records the
   complete before-image, including state files, receipt tails, pending Deltas,
   archive moves, and locks.
2. Another environment computes against exactly that before-image.
3. `detached commit` rechecks the full before-image under the still-held real
   lock, appends only new receipt bytes, and installs the explicit after-image.
4. Any drift aborts and follows normal recovery.

Copying state out, computing elsewhere, and copying it back with only three
state-file hashes is not a reusable protocol. It does not protect the
authoritative receipt frontier or concurrent namespace changes.

### Concurrent Receipt Sealing

Current receipt sealing deliberately requires a maintenance window with one
writer. The append mutex catches ordinary competing appenders but does not
claim cross-host, adversarial, or fully concurrent exclusion.

A true concurrent version is required only if Cambium chooses to widen that
boundary. It would need a shared epoch or cutover protocol that every appender
participates in, explicit exclusion invariants, cross-host recovery, and tests
with real racing writers.

This is not incremental hardening of the current marker. Until the product
boundary changes, the single-writer maintenance window remains the supported
contract.

## Adjusted Or Retired Directions

The following older directions should not be revived without a new decision:

- **Plugin-first delivery.** The host-neutral CLI/MCP interface shipped first;
  Plugin work is now optional packaging.
- **One universal Operation Capability Registry as the MCP source.** The CLI
  contract owns callable shape; state permission remains with kernel rules and
  controlled tools.
- **Two Profile template depths.** One pre-closed template plus interview
  expansion packs is the supported design.
- **A scheduler-owned batch ledger.** The Required Queue remains the only
  canonical batch lifecycle.
- **Queue admission as proof of worker delivery.** Admission and Assignment
  delivery are separate facts.
- **Automatic execution of adopter verifiers.** Verifier code stays disclosed
  and explicitly authorized.
- **Prompt behavior as conformance evidence.** Skills and prompts guide use;
  gates, writers, receipts, and host evidence carry claims.

## Delivery Order

The current critical path is:

```text
activation transport assurance
  -> durable Assignment state and delivery gate
  -> Git-backed workspace and reviewable-diff adapter
  -> single-writer integrator loop
  -> isolated workers
  -> clean-context reviewers
  -> cancellation, reassignment, and orchestration observability
```

Three lines can progress in parallel:

```text
explicit planning inputs
  -> typed dependency graph
  -> change-impact plans
  -> independent expected-set and consistency evaluation

batch-level review evidence
  -> per-finding review rulings
  -> conditional fix writer
  -> close-gate consumption

governed corpus eligibility projection
  -> deterministic manifest and change/invalidation feed
  -> citation and result envelope
  -> disposable reference adapter
  -> external-retriever conformance
```

The governed retrieval line adds a downstream interface without changing the
current execution-runtime critical path. Listing it as `Next` does not begin
implementation or imply extra capacity; scheduling it requires an explicit
priority and capacity decision against the other `Next` capabilities.

Receipt-chain integrity, Contract Amendment expansion, and sealed-evidence
hardening are independent control-plane improvements, but each must preserve
producer-era replay and existing authority boundaries.

Plugin packaging, remote MCP, UI, and ecosystem distribution remain downstream
choices. None is a prerequisite for completing the host-neutral Cambium
runtime.

## Definition Of Complete

No roadmap item is complete merely because its happy path works. Completion
requires:

- tracked implementation and current user documentation;
- deterministic or explicitly bounded semantic authority;
- negative fixtures for stale state, malformed input, missing evidence, path
  escape, interruption, and unsupported Host capabilities where applicable;
- recovery behavior that preserves evidence rather than guessing;
- generated artifacts recomputed and checked;
- no new policy owner, ledger, or trust claim hidden in an adapter or view.
