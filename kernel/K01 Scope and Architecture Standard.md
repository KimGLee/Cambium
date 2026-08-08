## Purpose

This page is the stable entry point of the Scope and Architecture standard. The detailed rules have been split into the modules below by responsibility; the original content has not been reduced.

## Reading Rule

- First use this MOC to locate the rule owner, then read the modules required by the current task, event, or quality gate.
- Entering this domain does not require reading all modules at once.
- Each module returns to its parent via `Navigation` and links to the adjacent modules before and after it.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/K01 Scope and Architecture/01 Scope Boundaries\|Scope Boundaries]] | `Purpose`, `Profile Scope Interface` |
| [[kernel/K01 Scope and Architecture/02 Logical Architecture and Knowledge Spine\|Logical Architecture and Knowledge Spine]] | `Logical Architecture`, `Knowledge Spine` |
| [[kernel/K01 Scope and Architecture/03 Foundation Preservation\|Foundation Preservation]] | `Foundation Preservation Rule` |
| [[kernel/K01 Scope and Architecture/04 Folder and Shared Ownership\|Folder and Shared Ownership]] | `Physical Folder Policy`, `Shared Ownership Rule`, `Architecture Anti-patterns`, `Related` |
| [[kernel/K01 Scope and Architecture/05 Structural Unit Interface\|Structural Unit Interface]] + `Structure Registry` | `Structural Unit Interface`, `Unit Roles And Implementation Modes`, `Registry Contract` |
| [[kernel/K01 Scope and Architecture/06 Support Layer Structural Interfaces\|Support Layer Structural Interfaces]] + `Structure Registry` | `Support Layer Structural Interfaces`, `Shared Base`, `Role-specific Interfaces`, `Verification` |

For full effect, the `Profile Scope` registered by the selected profile MUST also be loaded; it provides the concrete objectives, logical layers, knowledge spine, foundation layer directories, shared layer names, and exclusion list.

## Applicable Read Sets

- [[kernel/Read Sets/R03 Module Build Read Set|Module Build]]
- [[kernel/Read Sets/R06 Migration and Refactor Read Set|Migration and Refactor]]

## Related Standards

- [[kernel/K04 Content Depth Standard|K04 Content Depth Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]]
- The `Expression Layer Entry` registered by the selected profile
- [[kernel/K03 Note Types and Ownership Standard|K03 Note Types and Ownership Standard]]
- [[kernel/K05 Terminology Standard|K05 Terminology Standard]]
