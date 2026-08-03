---
type: card-index
registry_id: kernel-runtime-routes
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/Read Sets Index.md
  - kernel/K00 Standards Control/01 Operating Role and Reading Protocol.md
  - kernel/K00 Standards Control/02 Task Routing and Pre-execution.md
  - kernel/K00 Standards Control/03 Standards Governance.md
source_hash: cf751c69e5d5
route_registry:
  - route_id: R01
    path: "kernel/Cards/R01 Core Bootstrap Card.md"
    read_set: "kernel/Read Sets/R01 Core Bootstrap Read Set.md"
  - route_id: R02
    path: "kernel/Cards/R02 Single Note Authoring Card.md"
    read_set: "kernel/Read Sets/R02 Single Note Authoring Read Set.md"
  - route_id: R03
    path: "kernel/Cards/R03 Module Build Card.md"
    read_set: "kernel/Read Sets/R03 Module Build Read Set.md"
  - route_id: R04
    path: "kernel/Cards/R04 Source-driven Expansion Card.md"
    read_set: "kernel/Read Sets/R04 Source-driven Expansion Read Set.md"
  - route_id: R05
    path: "kernel/Cards/R05 Expression Layer Card.md"
    read_set: "kernel/Read Sets/R05 Expression Layer Read Set.md"
  - route_id: R06
    path: "kernel/Cards/R06 Migration and Refactor Card.md"
    read_set: "kernel/Read Sets/R06 Migration and Refactor Read Set.md"
  - route_id: R07
    path: "kernel/Cards/R07 Long-running Execution Card.md"
    read_set: "kernel/Read Sets/R07 Long-running Execution Read Set.md"
  - route_id: R08
    path: "kernel/Cards/R08 Audit and Completion Card.md"
    read_set: "kernel/Read Sets/R08 Audit and Completion Read Set.md"
  - route_id: R09
    path: "kernel/Cards/R09 Standards Governance Card.md"
    read_set: "kernel/Read Sets/R09 Standards Governance Read Set.md"
  - route_id: R10
    path: "kernel/Cards/R10 Maintenance Run Card.md"
    read_set: "kernel/Read Sets/R10 Maintenance Run Read Set.md"
  - route_id: R11
    path: "kernel/Cards/R11 Large-scale Work Admission Card.md"
    read_set: "kernel/Read Sets/R11 Large-scale Work Admission Read Set.md"
  - route_id: R12
    path: "kernel/Cards/R12 Targeted and Specialized Audit Card.md"
    read_set: "kernel/Read Sets/R12 Targeted and Specialized Audit Read Set.md"
---
# Kernel Runtime Card Index

Runtime Cards are kernel-owned compiled guidance for routine execution. They
compress their paired Read Sets but never own normative rules; when a Card is
incomplete, disputed, or insufficient for an exception, read its `source_files`
and the paired Read Set. Source text wins.

## Identity Model

`Kxx` identifies a normative Standards module. `Rxx` identifies a runtime
route. The two namespaces are independent: R05 is the Expression Layer route,
not an alias for K05, and one route may compile rules from several K modules.

The index is a registry, not a route, so it has no `route_id` and there is no
R00. Every R01-R12 route has exactly one Read Set and one Runtime Card sharing
the same `route_id`.

## Kernel Routes

| Route | Runtime Card | Read Set | Use |
|---|---|---|---|
| `R01` | [[kernel/Cards/R01 Core Bootstrap Card\|Core Bootstrap]] | [[kernel/Read Sets/R01 Core Bootstrap Read Set\|Read Set]] | Load the common control boundary for every task |
| `R02` | [[kernel/Cards/R02 Single Note Authoring Card\|Single Note Authoring]] | [[kernel/Read Sets/R02 Single Note Authoring Read Set\|Read Set]] | Create or revise one canonical note |
| `R03` | [[kernel/Cards/R03 Module Build Card\|Module Build]] | [[kernel/Read Sets/R03 Module Build Read Set\|Read Set]] | Build or systematically expand a module |
| `R04` | [[kernel/Cards/R04 Source-driven Expansion Card\|Source-driven Expansion]] | [[kernel/Read Sets/R04 Source-driven Expansion Read Set\|Read Set]] | Turn sources into traceable corpus updates |
| `R05` | [[kernel/Cards/R05 Expression Layer Card\|Expression Layer]] | [[kernel/Read Sets/R05 Expression Layer Read Set\|Read Set]] | Create, migrate, or review a registered expression artifact |
| `R06` | [[kernel/Cards/R06 Migration and Refactor Card\|Migration and Refactor]] | [[kernel/Read Sets/R06 Migration and Refactor Read Set\|Read Set]] | Move, rename, split, merge, or restructure |
| `R07` | [[kernel/Cards/R07 Long-running Execution Card\|Long-running Execution]] | [[kernel/Read Sets/R07 Long-running Execution Read Set\|Read Set]] | Run multi-batch work, checkpoint, or resume |
| `R08` | [[kernel/Cards/R08 Audit and Completion Card\|Audit and Completion]] | [[kernel/Read Sets/R08 Audit and Completion Read Set\|Read Set]] | Run task completion acceptance and Terminal Audit |
| `R09` | [[kernel/Cards/R09 Standards Governance Card\|Standards Governance]] | [[kernel/Read Sets/R09 Standards Governance Read Set\|Read Set]] | Modify Standards or the control plane |
| `R10` | [[kernel/Cards/R10 Maintenance Run Card\|Maintenance Run]] | [[kernel/Read Sets/R10 Maintenance Run Read Set\|Read Set]] | Run bounded freshness and maintenance work |
| `R11` | [[kernel/Cards/R11 Large-scale Work Admission Card\|Large-scale Work Admission]] | [[kernel/Read Sets/R11 Large-scale Work Admission Read Set\|Read Set]] | Pass the large-scale Pre-execution Gate |
| `R12` | [[kernel/Cards/R12 Targeted and Specialized Audit Card\|Targeted and Specialized Audit]] | [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set\|Read Set]] | Audit bounded affected scope or one specialized invariant |

## Loading Rules

- Every task loads R01 and the route for the actual work.
- Large-scale creation, moves, or deletion loads R11 before execution; R11 never replaces the route for the actual work.
- Expression-layer work loads R05. The selected profile supplies concrete
  artifact bindings and may add supplemental gates, but cannot replace R05.
- Long-running work combines R07 with the content route.
- Targeted or specialized audits combine R12 with every route relevant to the findings.
- Task completion candidates combine R08 with every route relevant to the completion predicates; R08 uses R12 for the bounded review inside Terminal Audit.
- Governance decisions load R09 and read its Read Set source text in full; the
  Card is navigation only.
- A profile extension uses its own namespaced identity and loads alongside a
  kernel route. It cannot reuse an Rxx identity or weaken the kernel gate.

Record the selected `route_id` values and Card paths. Record Read Set and leaf
paths only when they were actually read back; a broad K-module identifier does
not prove loading.

## Synchronization

The Read Set Index owns the kernel route registry and this index mirrors it.
After a route, Read Set, source path, or normative source changes, run
`python3 Tools/stamp_cards.py .` and then `python3 Tools/stamp_cards.py . --check`.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K00 Standards Overview|Standards Overview]]
- [[kernel/K00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]]
- [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]]
