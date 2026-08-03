---
type: runtime-card
route_id: R09
read_set: kernel/Read Sets/R09 Standards Governance Read Set.md
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/R09 Standards Governance Read Set.md
  - kernel/K00 Standards Control/01 Operating Role and Reading Protocol.md
  - kernel/K00 Standards Control/03 Standards Governance.md
  - kernel/K00 Standards Control/11 Standards Map and Rule Registry.md
  - kernel/K00 Standards Control/12 Control Registry.md
  - kernel/K02 Build Execution/02 Mid-task Guidance and Amendment.md
  - kernel/K09 Wiki Link and Navigation/03 Path Alias and Heading Links.md
  - kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns.md
  - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md
  - kernel/K12 Quality Assurance/10 Standards Version Adoption.md
  - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
source_hash: 370ba6342f6d
---
# R09 Standards Governance Card

> Navigation only. A governance decision MUST read R09 Read Set and every Start module it lists in full. This Card is never sufficient evidence for revising the Standards.

## Use When

Modify kernel rules, Read Sets, Cards, versions, directories, ownership, tooling contracts, or control-plane structure. Ordinary content work must not enter this route implicitly.

## Before Start

- [ ] Obtain explicit user authorization for the governance change.
- [ ] Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]], then read [[kernel/Read Sets/R09 Standards Governance Read Set|R09 Read Set]] and its Start list in full.
- [ ] Freeze the current Standards state, affected modules, incoming links, changed predicates, active-task impact, and rollback/conservation boundary.
- [ ] Identify the single canonical owner for every rule being changed and the existing control that is superseded.

## During

- Record the affected Standards and reason, update version/state when instantiated, update routing, and record the change summary and changed-predicate list.
- For a structural migration, map every original H2 block to exactly one new owner. Never use splitting as reduction, summary, or silent deletion.
- Keep the Overview, Standard Module MOCs, Read Sets, rule registry, control registry, links, and module paths synchronized.
- For a new or re-scoped check, register its receipt dimension, audit layer, object, evidence role, and acceptance owner before closure.
- Re-resolve affected tasks and execute Active-task Adoption; reuse only receipts that remain valid.
- Regenerate affected kernel Cards from their source owners, then stamp hashes/version. Do not edit only a Card.

## Gate

- [ ] Content conservation, owner uniqueness, routing, headings, tables, fences, links, MOCs, and coverage are verified.
- [ ] The Revision Write-back Checklist is complete for every affected snapshot location.
- [ ] `python3 Tools/stamp_cards.py . --check` exits 0; missing or stale Cards block governance close.
- [ ] Active-task adoption and receipt invalidation are recorded.
- [ ] Applicable rendering evidence and the governance Completion Gate pass.

## Read Back When

Always. Use this Card as a checklist after reading the sources, never as the basis for a governance judgment.
