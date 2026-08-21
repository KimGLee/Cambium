---
type: read-set
route_id: R09
---

## Purpose

Used for modifying the Standards' rule content, module boundaries, Read Sets, versions, directory structure, or control plane. Ordinary knowledge content tasks MUST NOT enter this Read Set implicitly.

## Start

First read:

- [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]]
- [[kernel/K00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]]
- [[kernel/K00 Standards Control/02 Task Routing|Task Routing]]
- [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]]
- [[kernel/K00 Standards Control/04 Control State and Scope|Control State and Scope]]
- [[kernel/K00 Standards Control/05 Core Principles|Core Principles]]
- [[kernel/K00 Standards Control/11 Standards Map and Rule Registry|Standards Map and Rule Registry]]
- [[kernel/K00 Standards Control/12 Control Registry|Control Registry]]
- [[kernel/K00 Standards Control/13 Runtime Admission and Recovery|Runtime Admission and Recovery]]
- [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]]
- [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
- [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]]
- [[kernel/K00 Standards Control/09 Default Constraints Snapshot|Default Constraints Snapshot]]
- [[kernel/K00 Standards Control/10 Batch Execution Checklist|Batch Execution Checklist]]
- [[kernel/K00 Standards Control/14 Card And Read Set Skeleton|Card And Read Set Skeleton]]
- [[kernel/K00 Standards Control/15 Read Set Loading Boundaries|Read Set Loading Boundaries]]
- [[kernel/K00 Standards Control/16 Leaf Module Size Register|Leaf Module Size Register]]
- [[kernel/K00 Standards Control/17 Profile Dependency Closure|Profile Dependency Closure]]
- [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis|Guidance Classification and Impact Analysis]], [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching|Guidance Disposition and Safe Switching]], and [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|Amendment Log and Controlled Replanning]] (when the revision involves an active-task Amendment; preserve the current-registration versus historical-verification boundary)
- [[kernel/K09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]]
- Profile input for the applicable branch:
  - initial adoption: the filled candidate manifest that passed `profile-load` and its bound `Language Contract`; no prior selected profile is required;
  - later profile change: the active selected profile identity and, when its current closure resolves, its `Language Contract`, plus the candidate manifest that passed `profile-load` and its bound `Language Contract`. A broken current closure is recorded as impact, not treated as a prerequisite for migrating away from it.
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]

## Required Controls

- The user MUST explicitly authorize the governance change.
- Before a later revision, freeze the active Standards version and selected profile manifest. For initial adoption, freeze the four uninstantiated K00/03 state values and the upstream tag, commit, or archive checksum instead; an old profile does not exist and is not a prerequisite. In both branches, freeze affected modules, incoming links, and active task impact.
- Initial profile selection and every later selection change occur only here. Initial adoption validates the candidate through the canonical `profile-load` Gate, instantiates all four K00/03 state values, and creates the first Change Summary entry. A later change validates the after candidate through the same Gate, records old and new selections, and bumps `standards_version`. Both branches recompose vocabulary and stamp Cards. For each existing affected runtime task, R09 freezes the authorized revision identity and changed predicates and produces the K12/10 restricted-YAML adoption input; it does not edit that task's Coverage, Queue, or Progress. Predicate, Profile-path, Profile-contract, or resolved-load-set change also requires a new Task `contract_version`; a pure no-predicate-change identity update may keep it.
- If the revised Standards cannot parse or validate a currently bound Work Spec, complete that compatibility migration through the Work Spec's owning process before producing an admissible adoption plan. R09 cannot hide it inside the adoption transaction.
- Bind each plan to the complete approved K00/03 bytes and deterministic after snapshots of the `kernel/` tree and selected Profile directory. A `profile-load` boundary targets exactly `selected_profile_manifest_after`; admission binds the passing Profile snapshot and contract fingerprint before any runtime write. The derived Profile closure remains separate from `selected_read_sets` and `loaded_module_paths`. Its changed predicates are that task's canonical machine list; do not create a second revision YAML or prose adoption copy.
- A structural migration MUST establish a complete mapping from old content blocks to new owners.
- A split MUST NOT be used as reduction, summarization, or silent deletion of rules.
- Read Sets and the overall Index MUST stay synchronized with module paths.
- Affected active, paused, and completion-candidate tasks MUST re-resolve their frozen reading plan (selected Rxx route IDs, Runtime Card paths, any combined namespaced Profile route, and the derived Read Set / leaf delivery boundary).
- Governance changes still follow the deterministic-first rendering boundary; modifying only Markdown rules does not automatically trigger the selected knowledge-host role's interactive UI, screenshots, or recordings.
- A current Profile that fails the new load contract blocks ordinary execution, not correction. R09 may inspect its exact before identity and produce a corrective plan, but only an after Profile that passes `profile-load` may be admitted; K13/15 remains the sole runtime writer.

## Gate

- Use [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]] to verify directories, MOC, and coverage. Where that reconciliation meets a sequence position, checkbox, or other progress marker, read [[kernel/K11 Expression Layer/06 Sequence and Progress Semantics|Sequence and Progress Semantics]], which it names as the owner of that status separation.
- Use [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]] as the sole owner of affected-task compatibility, targeted invalidation, and required gate reruns. After governance closure, hand each validated agent-readable plan to R07; K13/15's writer performs the runtime transaction. R09 neither duplicates those rules nor mutates active-task state.
- Use the `profile-load` producer registered by [[kernel/K00 Standards Control/12 Control Registry|Control Registry]] for candidate/after-image admission. R09 does not add a prose self-path checklist, and downstream tools consume the same typed contract rather than reparsing the registries.
- When the revision adds, retires, or re-scopes a check, use [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]] and [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map|Cross-page and Control-plane Dimension Map]] to fix the item's receipt dimension, audit layer, audit object, and evidence role before the revision closes.
- Use [[kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]] to verify vault-wide incoming links.
- When rendering policy, diagrams, tables, formulas, assets, or host behavior are involved, use [[kernel/K12 Quality Assurance/02 Rendering Verification|Rendering Verification]] to select and record the actual level.
- Use [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]] to close the governance task.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K00 Standards Overview|Standards Overview]]
