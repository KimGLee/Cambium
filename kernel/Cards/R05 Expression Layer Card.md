---
type: runtime-card
route_id: R05
read_set: kernel/Read Sets/R05 Expression Layer Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R05 Expression Layer Read Set.md
  - kernel/K11 Expression Layer Standard.md
  - kernel/K11 Expression Layer/01 Expression Architecture and Separation.md
  - kernel/K11 Expression Layer/02 Expression Coverage and Readiness.md
  - kernel/K11 Expression Layer/04 Evidence-bound Expression.md
  - kernel/K11 Expression Layer/05 Expression Knowledge Binding.md
  - kernel/K11 Expression Layer/06 Sequence and Progress Semantics.md
  - kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance.md
  - kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes.md
  - kernel/K03 Note Types and Ownership/03 Split and Duplication Policy.md
  - kernel/K08 Metadata and Status/03 Status Axes.md
  - kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority.md
  - kernel/K09 Wiki Link and Navigation/01 Link Semantics and Body Links.md
  - kernel/K09 Wiki Link and Navigation/02 Structural and Bidirectional Links.md
  - kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns.md
  - kernel/K10 Writing and Formatting/01 Naming Language and Prose.md
  - kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review.md
  - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
  - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/14 Batch Review.md
readback_sources:
  - kernel/K12 Quality Assurance/02 Rendering Verification.md
  - kernel/K12 Quality Assurance/13 Visual Verification Escalation.md
readback_policy: declared
source_hash: '9d74004976b3'
compiled_source_hash: '9d74004976b3'
---
# R05 Expression Layer Card

> Compiled kernel guidance. Do not hand-edit. The selected profile binds the
> concrete artifact; the kernel owns the separation, evidence, linking,
> migration, and acceptance floor.

## Use When

Create, migrate, or review a registered expression artifact such as a card,
quiz, briefing, or another derived presentation form. Load [[kernel/Cards/R01 Core Bootstrap Card|R01 Core Bootstrap]], the selected profile's `Expression Layer Entry` and `Language Contract`, and any supplemental profile route or gate registered for that artifact.

If the profile registers no expression artifact, there is no valid target.
Stop rather than inventing one or treating an unconfigured artifact as loaded.

## Before Start

- [ ] Resolve the artifact identity, display label, entry point, single rule
  owner, readiness binding, and every applicable supplemental gate.
- [ ] Record the canonical knowledge owners and the exact artifact scope.
- [ ] Separate canonical knowledge responsibility from expression responsibility.
- [ ] Define resolvable links in both directions between the artifact and its
  canonical support.
- [ ] Record evidence gaps and the consequence for claim strength or readiness.

## During

- Derive expression content from canonical owners; do not create a second owner
  for definitions, claims, or mechanisms.
- Preserve source provenance and evidence qualification when content is
  condensed, reordered, or transformed.
- A readiness value is written only by the profile's registered expression gate or receipt, and a mapped-class binding keeps a resolvable reciprocal link; file existence, link resolvability, or another status axis never upgrades readiness (K08/07).
- A registered readiness or other Profile Gate field is projected from current Coverage owner state by its declared transition writer. Do not hand-edit the page copy; content drift invalidates evidence bound to the prior semantic fingerprint before another promotion can be accepted.
- Keep expression readiness independent from canonical authoring and evidence
  status; one axis never implies another.
- Maintain resolvable links from expression to knowledge and from knowledge to
  the registered expression entry.
- For migration, create and verify the target before removing the source, then
  reconcile every item as migrated, merged, retained, deferred, or excluded.
- Treat automation output as candidates until the applicable human or model
  acceptance owner reaches a verdict.
- Apply supplemental profile gates alongside this R05 floor, never instead of it.

## Gate

- [ ] Artifact binding, entry point, and single rule owner resolve.
- [ ] Canonical and expression responsibilities are not mixed.
- [ ] Bidirectional links resolve and the canonical owner remains authoritative.
- [ ] Claims remain traceable to evidence with uncertainty preserved.
- [ ] The artifact passes its registered readiness gate without inferring status
  from a different axis.
- [ ] Sequence or checkbox progress is not reported as knowledge completion.
- [ ] Migration dispositions conserve content and incoming/outgoing bindings.
- [ ] Applicable deterministic, manual, rendering, and supplemental checks pass.

Once an expression artifact enters scope, this kernel gate cannot be marked
`not_applicable`. No registered artifact means no concrete R05 target; it does
not mean that a profile can disable R05 for an artifact it has registered.

## Read Back When

Read [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer Read Set]] for a disputed separation boundary, evidence qualification, readiness promotion, bidirectional binding, migration disposition, or an unlisted artifact case. Combine R03 for module-scale work, R06 for migration, R11 for large-scale admission, R07 for multi-batch execution, R12 for a targeted or specialized expression audit, and R08 only for whole-task completion.

## Related

- [[kernel/Cards/Card Index|Card Index]]
- [[kernel/K11 Expression Layer Standard|Expression Layer Standard]]
- [[profiles/README|Profile Interface]]
