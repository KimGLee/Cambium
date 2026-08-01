## Purpose

This page is the stable entry for the Quality Assurance standard. The detailed rules have been split by responsibility into the modules below; the original content has not been reduced.

## Reading Rule

- First use this MOC to locate the rule owner, then read the modules required by the current task, event, or quality gate.
- Entering this domain does not require reading all modules at once.
- Each module returns to its parent via `Navigation` and connects to its adjacent previous and next modules.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review\|Quality Dimensions and Single Note Review]] | `Purpose`, `Quality Dimensions`, `Single Note Review`, `Substantive Correctness Review` |
| [[kernel/12 Quality Assurance/02 Rendering Verification\|Rendering Verification]] | `Rendering Verification Levels` |
| [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review\|Module Coverage and Batch Review]] | `Module Review`, `Coverage Reconciliation Review`, `Batch Review` |
| [[kernel/12 Quality Assurance/04 Guidance and Source Review\|Guidance and Source Review]] | `Guidance Reconciliation Review`, `Source Intake And Promotion Review` |
| [[kernel/12 Quality Assurance/05 Automated and Manual Checks\|Automated and Manual Checks]] | `Automated Checks`, `Domain-specific Checks`, `Manual Checks` |
| [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report\|Completion Terminal Audit and Final Report]] | `Completion Gate`, `Terminal Audit`, `Terminal Findings And Convergence`, `Final Report`, `Related` |
| [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|Audit Evidence Reuse and Invalidation]] | `Purpose`, `Audit Layers`, `Dimension-specific Audit Receipt`, `Reuse Gate`, `Invalidation`, `Content-level Propagation`, `Incremental Audit Planning`, `Batch-close Closed List`, `Incremental By Default`, `Specialized Audit Boundary`, `Terminal Reconciliation Rules`, `Active-task Adoption`, `Related` |
| `Audit Dimension Registry` + `Registered Scan Registry` + `Routing And Gate Registry` | profile-owned QA dimensions, scans, and extension gates |

## Post-migration Extensions

The content-conservation denominator of a frozen baseline does not change retroactively because an extension is registered later. Migration and version history do not enter the active standard; the kernel extension registry is currently empty:

| Extension | Canonical owner | Responsibility |
|---|---|---|

## Applicable Read Sets

- [[kernel/Read Sets/02 Single Note Authoring Read Set|Single Note Authoring]]
- [[kernel/Read Sets/03 Module Build Read Set|Module Build]]
- [[kernel/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]]
- The `Expression Layer Read Set` registered by the selected profile's `Routing And Gate Registry`
- [[kernel/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]]
- [[kernel/Read Sets/07 Long-running Execution Read Set|Long-running Execution]]
- [[kernel/Read Sets/08 Audit and Completion Read Set|Audit and Completion]]
- [[kernel/Read Sets/09 Standards Governance Read Set|Standards Governance]]

## Related Standards

- [[kernel/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
- [[kernel/04 Content Depth Standard|04 Content Depth Standard]]
- [[kernel/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]]
- [[kernel/08 Metadata and Status Standard|08 Metadata and Status Standard]]
- The selected profile's `Expression Layer Entry`, `Audit Dimension Registry`, and `Registered Scan Registry`
