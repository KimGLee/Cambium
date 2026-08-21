---
type: route-index
registry_id: kernel-runtime-routes
route_registry:
  - route_id: R01
    path: "kernel/Read Sets/R01 Core Bootstrap Read Set.md"
  - route_id: R02
    path: "kernel/Read Sets/R02 Single Note Authoring Read Set.md"
  - route_id: R03
    path: "kernel/Read Sets/R03 Module Build Read Set.md"
  - route_id: R04
    path: "kernel/Read Sets/R04 Source-driven Expansion Read Set.md"
  - route_id: R05
    path: "kernel/Read Sets/R05 Expression Layer Read Set.md"
  - route_id: R06
    path: "kernel/Read Sets/R06 Migration and Refactor Read Set.md"
  - route_id: R07
    path: "kernel/Read Sets/R07 Long-running Execution Read Set.md"
  - route_id: R08
    path: "kernel/Read Sets/R08 Audit and Completion Read Set.md"
  - route_id: R09
    path: "kernel/Read Sets/R09 Standards Governance Read Set.md"
  - route_id: R10
    path: "kernel/Read Sets/R10 Maintenance Run Read Set.md"
  - route_id: R11
    path: "kernel/Read Sets/R11 Large-scale Work Admission Read Set.md"
  - route_id: R12
    path: "kernel/Read Sets/R12 Targeted and Specialized Audit Read Set.md"
  - route_id: R13
    path: "kernel/Read Sets/R13 Corpus Planning Read Set.md"
---
## Purpose

A Runtime Route maps one task type to the Standards modules that must be read. Its Read Set solves the complete source-loading boundary; its Runtime Card is the compiled routine view. Neither replaces a rule body.

## Identity Namespace

- `K00` through `K13` identify normative kernel module families and their actual repository paths.
- `R01` through `R13` identify runtime task routes. A Read Set and its Runtime Card share one `route_id`.
- The numeric parts of `Kxx` and `Rxx` have no mapping. For example, R05 compiles the Expression Layer task route whose principal normative owner is K11.
- This Index is a registry, not a route, and therefore has no `R00`.
- A profile supplemental route uses `P:<profile_id>:<route_name>` and loads alongside a kernel route; it cannot reuse an `Rxx` identity.

Every registered kernel route has exactly one kernel-owned Runtime Card listed in [[kernel/Cards/Card Index|Card Index]]. Profiles cannot replace or disable these routes.

## Resolution Order

```text
Open Standards Overview
 -> Load R01 Core Bootstrap
 -> Classify Task
 -> Select One Or More Runtime Routes
 -> Load Each Route's Runtime Card
 -> Resolve Triggered Modules And Profile Bindings
 -> Read Back The Route's Read Set Or Leaf Owner When Required
 -> Record standards_version, selected_profile_manifest, selected_route_ids,
    selected_card_paths, selected_read_sets, And loaded_module_paths
 -> Execute
```

A task MAY combine routes. For example, expanding a system topic from primary sources while building expression artifacts combines R04 Source-driven Expansion, R03 Module Build, and R05 Expression Layer.

## Route Registry

| Route ID | Canonical Read Set | Use |
|---|---|---|
| `R01` | [[kernel/Read Sets/R01 Core Bootstrap Read Set\|Core Bootstrap]] | Common control constraints for every task |
| `R02` | [[kernel/Read Sets/R02 Single Note Authoring Read Set\|Single Note Authoring]] | Create or target one canonical note |
| `R03` | [[kernel/Read Sets/R03 Module Build Read Set\|Module Build]] | Build a complete knowledge module |
| `R04` | [[kernel/Read Sets/R04 Source-driven Expansion Read Set\|Source-driven Expansion]] | Turn sources into traceable corpus updates |
| `R05` | [[kernel/Read Sets/R05 Expression Layer Read Set\|Expression Layer]] | Create, migrate, or review registered expression artifacts |
| `R06` | [[kernel/Read Sets/R06 Migration and Refactor Read Set\|Migration and Refactor]] | Move, rename, split, merge, or restructure |
| `R07` | [[kernel/Read Sets/R07 Long-running Execution Read Set\|Long-running Execution]] | Run multi-batch work, checkpoint, or resume |
| `R08` | [[kernel/Read Sets/R08 Audit and Completion Read Set\|Audit and Completion]] | Review, close, or prove completion |
| `R09` | [[kernel/Read Sets/R09 Standards Governance Read Set\|Standards Governance]] | Modify Standards or the control plane |
| `R10` | [[kernel/Read Sets/R10 Maintenance Run Read Set\|Maintenance Run]] | Run bounded freshness and maintenance work |
| `R11` | [[kernel/Read Sets/R11 Large-scale Work Admission Read Set\|Large-scale Work Admission]] | Pass the Large-scale Pre-execution Gate before execution |
| `R12` | [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set\|Targeted and Specialized Audit]] | Audit a bounded affected scope or one specialized invariant |
| `R13` | [[kernel/Read Sets/R13 Corpus Planning Read Set\|Corpus Planning]] | Maintain the Global Map, Capability Matrix, and Gap Register, or promote a gap into Coverage |

## Selection Rules

- Every task starts with R01, but R01 cannot replace the route for the actual work.
- `Start` modules are read before the corresponding work begins.
- `Triggered` modules are loaded only when their trigger conditions appear.
- `Gate` modules are loaded before closing the applicable note, batch, module, or task.
- R05 is conditional on expression-layer work. If the selected profile registers no expression artifact, there is no valid expression target to create, migrate, or review; the agent stops rather than inventing one.
- Large-scale creation, moves, or deletion combines R11 with the route for the actual work; R11 authorizes no content operation by itself.
- Targeted and specialized audits combine R12 with the route relevant to the finding. A local finding expands only by the bounded systemic-expansion rule.
- Corpus-planning work uses R13. R13 may hand an accepted gap into Coverage, but it does not author content, schedule batches, or perform an audit.
- R08 is reserved for task completion candidates and Terminal Audit; page, batch, module, and maintenance gates remain with their owning routes.
- A module's prerequisites take precedence over the current module. When a dependency cannot be satisfied, record the gap first.
- After the Standards version or route paths change, the affected loaded set MUST be re-resolved.
- Freeze each `route_id`, Card path, and derived Read Set / leaf delivery boundary; do not record a broad K-module number. Actual delivery belongs to the activation/read-back receipt chain.

## Related

- [[kernel/K00 Standards Overview|Standards Overview]]
- [[kernel/Cards/Card Index|Card Index]]
- [[kernel/K00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]]
- [[kernel/K00 Standards Control/02 Task Routing|Task Routing]]
