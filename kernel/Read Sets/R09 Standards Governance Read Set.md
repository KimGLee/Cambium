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
- [[kernel/K00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]]
- [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]]
- [[kernel/K00 Standards Control/04 Control State and Scope|Control State and Scope]]
- [[kernel/K00 Standards Control/05 Core Principles|Core Principles]]
- [[kernel/K00 Standards Control/11 Standards Map and Rule Registry|Standards Map and Rule Registry]]
- [[kernel/K00 Standards Control/12 Control Registry|Control Registry]]
- [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]]
- [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
- [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]]
- [[kernel/K00 Standards Control/09 Default Constraints Snapshot|Default Constraints Snapshot]]
- [[kernel/K00 Standards Control/10 Batch Execution Checklist|Batch Execution Checklist]]
- [[kernel/K02 Build Execution/02 Mid-task Guidance and Amendment|Mid-task Guidance and Amendment]] (the revision process involves the Amendment Log)
- [[kernel/K09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]]
- Profile input for the applicable branch:
  - initial adoption: the filled candidate manifest that passed `check_profile.py` and its bound `Language Contract`; no prior selected profile is required;
  - later profile change: the active selected profile's `Language Contract`, plus the checked candidate manifest and its bound `Language Contract`.
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]

## Required Controls

- The user MUST explicitly authorize the governance change.
- Before a later revision, freeze the active Standards version and selected profile manifest. For initial adoption, freeze the four uninstantiated K00/03 state values and the upstream tag, commit, or archive checksum instead; an old profile does not exist and is not a prerequisite. In both branches, freeze affected modules, incoming links, and active task impact.
- Initial profile selection and every later selection change occur only here. Initial adoption validates the candidate, instantiates all four K00/03 state values, and creates the first Change Summary entry. A later change validates the candidate, records old and new selections, and bumps `standards_version`. Both branches recompose vocabulary and stamp Cards; only existing affected tasks enter Active-task Adoption.
- A structural migration MUST establish a complete mapping from old content blocks to new owners.
- A split MUST NOT be used as reduction, summarization, or silent deletion of rules.
- Read Sets and the overall Index MUST stay synchronized with module paths.
- Affected active, paused, and completion-candidate tasks MUST re-resolve their loaded set (selected Rxx route IDs and Runtime Card paths, any combined namespaced profile route, and every Read Set or leaf path actually read back).
- Governance changes still follow the deterministic-first rendering boundary; modifying only Markdown rules does not automatically trigger the selected knowledge-host role's interactive UI, screenshots, or recordings.

## Gate

- Use [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]] to verify directories, MOC, and coverage.
- Use [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] to record affected active tasks' receipt compatibility and invalidation scope, and [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]] to execute the adoption plan.
- When the revision adds, retires, or re-scopes a check, use [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]] to fix the item's receipt dimension, audit layer, audit object, and evidence role before the revision closes.
- Use [[kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]] to verify vault-wide incoming links.
- When rendering policy, diagrams, tables, formulas, assets, or host behavior are involved, use [[kernel/K12 Quality Assurance/02 Rendering Verification|Rendering Verification]] to select and record the actual level.
- Use [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]] to close the governance task.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K00 Standards Overview|Standards Overview]]
