---
type: runtime-card
route_id: R09
read_set: kernel/Read Sets/R09 Standards Governance Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R09 Standards Governance Read Set.md
  - kernel/K00 Standards Control/01 Operating Role and Reading Protocol.md
  - kernel/K00 Standards Control/03 Standards Governance.md
  - kernel/K00 Standards Control/11 Standards Map and Rule Registry.md
  - kernel/K00 Standards Control/12 Control Registry.md
  - kernel/K00 Standards Control/17 Profile Dependency Closure.md
  - kernel/K00 Standards Control/18 Tool Module Boundary Contract.md
  - kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis.md
  - kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching.md
  - kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning.md
  - kernel/K09 Wiki Link and Navigation/03 Path Alias and Heading Links.md
  - kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns.md
  - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
  - kernel/K11 Expression Layer/06 Sequence and Progress Semantics.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md
  - kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map.md
  - kernel/K12 Quality Assurance/10 Standards Version Adoption.md
  - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
readback_sources:
  - kernel/K00 Standards Control/02 Task Routing.md
  - kernel/K00 Standards Control/04 Control State and Scope.md
  - kernel/K00 Standards Control/05 Core Principles.md
  - kernel/K00 Standards Control/06 Completion Precedence and Task Contract.md
  - kernel/K00 Standards Control/07 Effort Tiering and Priority Quota.md
  - kernel/K00 Standards Control/08 Maintenance Run Envelope.md
  - kernel/K00 Standards Control/09 Default Constraints Snapshot.md
  - kernel/K00 Standards Control/10 Batch Execution Checklist.md
  - kernel/K00 Standards Control/13 Runtime Admission and Recovery.md
  - kernel/K00 Standards Control/14 Card And Read Set Skeleton.md
  - kernel/K00 Standards Control/15 Read Set Loading Boundaries.md
  - kernel/K00 Standards Control/16 Leaf Module Size Register.md
  - kernel/K12 Quality Assurance/02 Rendering Verification.md
  - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
readback_policy: activation
source_hash: '70b6091d01b7'
compiled_source_hash: '70b6091d01b7'
---
# R09 Standards Governance Card

> Navigation only. A governance decision MUST read R09 Read Set and every Start module it lists in full. This Card is never sufficient evidence for revising the Standards.

## Use When

Modify kernel rules, Read Sets, Cards, versions, directories, ownership, tooling contracts, or control-plane structure. Ordinary content work must not enter this route implicitly.

## Before Start

- [ ] Obtain explicit user authorization for the governance change.
- [ ] Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]], then verify
  the activation Bundle delivered [[kernel/Read Sets/R09 Standards Governance Read Set|R09 Read Set]]
  and its Start list in full under `readback_policy: activation`.
- [ ] Choose the branch: for initial adoption, prove the canonical adopter Standards state is absent, freeze upstream provenance, then admit the candidate through `profile-load`; for a later revision, freeze the current state bytes and separately admit the after Profile through the same Gate. A broken current Profile is impact evidence, not a prerequisite that can deadlock correction. In both branches freeze affected modules, incoming links, changed predicates, active-task impact, and rollback/conservation boundary.
- [ ] Identify the single canonical owner for every rule being changed and the existing control that is superseded.

## During

- Record the affected Standards and reason, update rules/routing and changed predicates, and let the adoption transaction append history receipts. Initial adoption creates `.cambium/governance/standards_state.yaml`; later changes advance it. Both recompose vocabulary and stamp Cards. For each affected task, declare the Contract-version edge, ensure Work Specs are compatible, and bind its K12/10 YAML to unchanged K00/03 rule bytes, the exact state before-image, deterministic Kernel/Profile snapshots, and the after Profile's typed-contract fingerprint. Keep that derived closure outside Read Set load lists; never write task Ledgers or create a second revision/prose copy.
- For a structural migration, map every original H2 block to exactly one new owner. Never use splitting as reduction, summary, or silent deletion.
- Keep the Overview, Standard Module MOCs, Read Sets, rule registry, control registry, links, and module paths synchronized.
- For a new or re-scoped check, register its receipt dimension, audit layer, object, evidence role, and acceptance owner before closure.
- Freeze the inputs needed for affected tasks to re-resolve their load set. K12/10 decides targeted invalidated evidence and gate reruns; R07/K13/15 executes the runtime transaction. R09 does not copy or reimplement either contract.
- Use the registered `profile-load` producer as the sole linker for manifest, slot, scan-config, verifier, and predicate-owner authority. Do not replace it with a copy-time rewrite checklist or a consumer-specific Markdown parser.
- Preserve the boundary between current authorization and historical verification: a Standards change may invalidate a Receipt for new execution without erasing the completed event it historically proves, and history must never be used as a fallback authorization source.
- A revision that moves a shipped tool module, widens what one module offers another, or changes which module depends on which is a change to the boundary contract: update `Tools/module-boundaries.yaml` in the same revision, and carry any consumption it cannot yet declare as a registered exception with a retirement condition. Import cycles take no exception.
- Regenerate affected kernel Cards from their source owners. Stamp observed hashes first; only after reviewing the regenerated guidance run `stamp_cards.py --acknowledge-compiled`. Do not acknowledge unchanged prose merely to clear a stale hash.

## Gate

- [ ] Content conservation, owner uniqueness, routing, headings, tables, fences, links, MOCs, and coverage are verified.
- [ ] Coverage reconciliation does not read a sequence position, checkbox, file existence, resolvable link, or `Related` reference as authoring completion.
- [ ] The Revision Write-back Checklist is complete for every affected snapshot location.
- [ ] `python3 Tools/stamp_cards.py . --check` exits 0; observed and acknowledged semantic hashes agree, every Read Set leaf has one compiled/read-back disposition, and missing/stale Cards, an exceeded registered growth cap, or a contradictory K00/12 Gate row blocks close.
- [ ] Every affected existing task has one validated agent-readable adoption plan or an explicit blocker; no persistent prose adoption report or direct Ledger edit was created.
- [ ] Every candidate/after Profile has a passing `profile-load` snapshot and contract fingerprint, and the adoption writer revalidates that exact after-image inside its transaction.
- [ ] Applicable rendering evidence and the governance Completion Gate pass.

## Read Back When

Always. Use this Card as a checklist after reading the sources, never as the basis for a governance judgment.
