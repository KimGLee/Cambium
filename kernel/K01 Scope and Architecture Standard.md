## Purpose

This page is the stable entry point of the Scope and Architecture standard. Detailed rules are maintained by the responsibility-specific modules below.

## Reading Rule

- Use this MOC only to locate the canonical semantic owner. Loading decisions
  are owned outside Kernel; opening this index is not evidence that any leaf was
  loaded.

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

## Related Standards

- [[kernel/K04 Content Depth Standard|K04 Content Depth Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]]
- The `Expression Layer Entry` registered by the selected profile
- [[kernel/K03 Note Types and Ownership Standard|K03 Note Types and Ownership Standard]]
- [[kernel/K05 Terminology Standard|K05 Terminology Standard]]
