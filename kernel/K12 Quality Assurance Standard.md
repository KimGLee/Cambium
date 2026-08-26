## Purpose

This page is the stable entry for the Quality Assurance standard. Detailed
rules are maintained by the responsibility-specific modules below.

## Reading Rule

- Use this MOC only to locate the canonical semantic owner. Loading decisions
  are owned outside Kernel; opening this index is not evidence that any leaf was
  loaded.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review\|Quality Dimensions and Single Note Review]] | `Purpose`, `Quality Dimensions`, `Single Note Review`, `M-tier Gate Checklist` |
| [[kernel/K12 Quality Assurance/02 Rendering Verification\|Rendering Verification]] | `Rendering Verification Levels`, `Escalation Record` |
| [[kernel/K12 Quality Assurance/03 Module and Coverage Review\|Module and Coverage Review]] | `Module Review`, `Coverage Reconciliation Review` |
| [[kernel/K12 Quality Assurance/04 Guidance and Source Review\|Guidance and Source Review]] | `Guidance Reconciliation Review`, `Source Intake And Promotion Review` |
| [[kernel/K12 Quality Assurance/05 Automated and Manual Checks\|Automated and Manual Checks]] | `Automated Checks`, `Codification Admission`, `Domain-specific Checks`, `Manual Checks` |
| [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting\|Completion Gate and Reporting]] | `Completion Gate`, `Final Report`, `Related` |
| [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|Audit Evidence Reuse and Invalidation]] and [`audit-dimension-base.yaml`](<K12 Quality Assurance/audit-dimension-base.yaml>) | `Purpose`, `Audit Layers`, `Dimension-specific Audit Receipt`, `Reuse Gate`, `Invalidation`, `Specialized Audit Boundary`, `Receipt Sealing and the Cold Chain`, `Terminal Reconciliation Rules`, `Related`; the YAML is the sole machine registry for base receipt dimensions, evidence roles, and Profile extension-target mappings |
| [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map\|Judgment Item Dimension Map]] | `Purpose`, `Terms`, `Evidence Role`, `Uniform Sections`, `Item Map`, `Reverse Check`, `Profile Registration`, `Related`; this half files the Single Note Review layer |
| [[kernel/K12 Quality Assurance/09 Batch-close Closed List\|Batch-close Closed List]] and [`batch-close-closed-list.yaml`](<K12 Quality Assurance/batch-close-closed-list.yaml>) | `Purpose`, `Batch-close Closed List`, `Related`; the YAML is the sole machine registry for current membership and order |
| [[kernel/K12 Quality Assurance/10 Standards Version Adoption\|Standards Version Adoption]] | `Purpose And Sole Ownership`, `Trigger And Invariants`, `Adoption Plan Contract`, `Adoption Branches`, `Acceptance And Resume` |
| [[kernel/K12 Quality Assurance/11 Content-level Propagation\|Content-level Propagation]] | `Purpose`, `Content-level Propagation`, `Related` |
| [[kernel/K12 Quality Assurance/12 Substantive Correctness Review\|Substantive Correctness Review]] | `Purpose`, `Substantive Correctness Review`, `Related` |
| [[kernel/K12 Quality Assurance/13 Visual Verification Escalation\|Visual Verification Escalation]] | `Visual Verification Escalation` |
| [[kernel/K12 Quality Assurance/14 Batch Review\|Batch Review]] | `Batch Review` |
| [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence\|Terminal Audit and Convergence]] | `Terminal Audit`, `Terminal Findings And Convergence` |
| [[kernel/K12 Quality Assurance/16 Terminal Proof Contract\|Terminal Proof Contract]] | `Terminal Proof Contract`, `Evidence Bindings`, `Terminal Completion Gate`, `Evidence Trust Boundary` |
| [[kernel/K12 Quality Assurance/17 Gate Receipt Payload Contract\|Gate Receipt Payload Contract]] | `Purpose`, `Gate Receipt Payload`, `Recording Authority`, `Standards-adoption Boundary Authority`, `Consumption And Rejection`, `Related` |
| [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map\|Cross-page and Control-plane Dimension Map]] | `Purpose`, `Item Map`, `Gate Receipt Dimension Boundary`, `Reverse Check`; this half files the layers above one page and the control-plane Gates |
| [[kernel/K12 Quality Assurance/19 Incremental Audit Planning\|Incremental Audit Planning]] | `Incremental Audit Planning`, `Incremental By Default` |
| `Audit Dimension Registry` + `Registered Scan Registry` + `Routing And Gate Registry` | profile-owned QA dimensions, scans, and extension gates |

## Related Standards

- [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]]
- [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]]
- [[kernel/K04 Content Depth Standard|K04 Content Depth Standard]]
- [[kernel/K07 Sources and Accuracy Standard|K07 Sources and Accuracy Standard]]
- [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]]
- The selected profile's `Expression Layer Entry`, `Audit Dimension Registry`, and `Registered Scan Registry`
