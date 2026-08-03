---
type: read-set
route_id: R05
---
## Purpose

Used for creating, migrating, or reviewing expression artifacts that the selected profile has registered. The kernel fixes the separation, evidence, status, binding, migration, and acceptance floor; the profile supplies concrete artifact identities, labels, entry points, readiness values, and supplemental gates.

If the selected profile registers no expression artifact, there is no valid expression target. The agent stops rather than inventing an artifact or treating an unconfigured target as loaded.

## Start

First load [[kernel/Read Sets/R01 Core Bootstrap Read Set|R01 Core Bootstrap]], then read:

- [[kernel/K11 Expression Layer/01 Expression Architecture and Separation|Expression Architecture and Separation]]
- [[kernel/K11 Expression Layer/02 Expression Coverage and Readiness|Expression Coverage and Readiness]]
- [[kernel/K11 Expression Layer/04 Evidence-bound Expression|Evidence-bound Expression]]
- [[kernel/K11 Expression Layer/05 Expression Knowledge Binding|Expression Knowledge Binding]]
- [[kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]]
- [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]
- [[kernel/K08 Metadata and Status/03 Status Axes|Status Axes]]
- [[kernel/K09 Wiki Link and Navigation/01 Link Semantics and Body Links|Link Semantics and Body Links]]
- [[kernel/K09 Wiki Link and Navigation/02 Structural and Bidirectional Links|Structural and Bidirectional Links]]
- [[kernel/K10 Writing and Formatting/01 Naming Language and Prose|Naming Language and Prose]]
- The selected profile's `Expression Layer Entry` and `Language Contract`.
- Any supplemental route or gate explicitly registered by the profile. It loads alongside R05 and cannot replace its kernel floor.

Before authoring begins, resolve the artifact identity, display label, entry point, single rule owner, readiness binding, canonical owners, target scope, and applicable gates.

## Triggered

- Sequence, checkbox, practice, or evaluation progress: read [[kernel/K11 Expression Layer/06 Sequence and Progress Semantics|Sequence and Progress Semantics]].
- Migration, split, merge, or deletion of existing expression content: read [[kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance|Expression Migration Audit and Acceptance]] and combine [[kernel/Read Sets/R06 Migration and Refactor Read Set|R06 Migration and Refactor]].
- Missing or insufficient canonical knowledge: combine [[kernel/Read Sets/R02 Single Note Authoring Read Set|R02 Single Note Authoring]]; when new sources or claims are needed, also combine [[kernel/Read Sets/R04 Source-driven Expansion Read Set|R04 Source-driven Expansion]] and the profile's `Source Policy`.
- A readiness promotion: load the profile's `Vocabulary Extensions`, its registered readiness gate owner, and [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]].
- Changed canonical support or invalidated evidence: read [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] and mark affected artifacts through the registered dependency mapping.
- Work spanning multiple artifacts or a module: combine [[kernel/Read Sets/R03 Module Build Read Set|R03 Module Build]].
- Large-scale expression work: pass [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|R11 Large-scale Work Admission]] before execution.
- Multi-batch execution, checkpoint, or resume: combine [[kernel/Read Sets/R07 Long-running Execution Read Set|R07 Long-running Execution]].
- Formulas, tables, code, diagrams, images, embeds, or a display question: load the applicable K10 formatting modules and [[kernel/K12 Quality Assurance/02 Rendering Verification|Rendering Verification]]; visual escalation additionally requires the objective trigger defined by [[kernel/K12 Quality Assurance/13 Visual Verification Escalation|Visual Verification Escalation]].
- A targeted or specialized expression audit: combine [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|R12 Targeted and Specialized Audit]].
- A whole-task completion candidate: combine [[kernel/Read Sets/R08 Audit and Completion Read Set|R08 Audit and Completion]].

## Gate

Before an expression artifact closes or advances readiness, read:

- [[kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance#Acceptance Criteria|Expression Acceptance Criteria]]
- [[kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]]
- The applicable dimensions of [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- The profile's supplemental audit dimensions, scans, readiness gate, and extension gates that apply to the artifact.

Once an expression artifact enters scope, the R05 kernel floor cannot be marked `not_applicable`. A profile with no registered artifact has no concrete R05 task target; that is absence of an object, not permission to bypass the route.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K11 Expression Layer Standard|Expression Layer Standard]]
- [[profiles/README|Profile Interface]]
