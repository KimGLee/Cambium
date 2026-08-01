## Purpose

Used for modifying the Standards' rule content, module boundaries, Read Sets, versions, directory structure, or control plane. Ordinary knowledge content tasks MUST NOT enter this Read Set implicitly.

## Start

First read:

- [[kernel/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]]
- [[kernel/00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]]
- [[kernel/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]]
- [[kernel/00 Standards Control/03 Standards Governance|Standards Governance]]
- [[kernel/00 Standards Control/04 Control State and Scope|Control State and Scope]]
- [[kernel/00 Standards Control/05 Core Principles and Standards Map|Core Principles and Standards Map]]
- [[kernel/00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]]
- [[kernel/02 Build Execution/02 Mid-task Guidance and Amendment|Mid-task Guidance and Amendment]] (the revision process involves the Amendment Log)
- [[kernel/09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]]
- The selected profile's `Language Contract`.
- [[kernel/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]

## Required Controls

- The user MUST explicitly authorize the governance change.
- Before the change, freeze the Standards version, the affected modules, incoming links, and the active task impact.
- A structural migration MUST establish a complete mapping from old content blocks to new owners.
- A split MUST NOT be used as reduction, summarization, or silent deletion of rules.
- Read Sets and the overall Index MUST stay synchronized with module paths.
- Affected active, paused, and completion-candidate tasks MUST re-resolve their loaded set (`Runtime Card Provider` artifacts and modules read back on escalation).
- Governance changes still follow the deterministic-first rendering boundary; modifying only Markdown rules does not automatically trigger the selected knowledge-host role's interactive UI, screenshots, or recordings.

## Gate

- Use [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]] to verify directories, MOC, and coverage.
- Use [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] to record affected active tasks' receipt compatibility, invalidation scope, and adoption plan.
- Use [[kernel/09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]] to verify vault-wide incoming links.
- When rendering policy, diagrams, tables, formulas, assets, or host behavior are involved, use [[kernel/12 Quality Assurance/02 Rendering Verification|Rendering Verification]] to select and record the actual level.
- Use [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]] to close the governance task.

## Related

- [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[kernel/00 Standards Overview|Standards Overview]]
