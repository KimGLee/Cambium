## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/13 Runtime Admission and Recovery|Runtime Admission and Recovery]].
- Next: [[kernel/K00 Standards Control/15 Read Set Loading Boundaries|Read Set Loading Boundaries]].

## Card And Read Set Skeleton

A Runtime Card and a kernel Read Set carry their material in named `##` sections, and a reader keys its loading procedure to those names, so each sequence is fixed here rather than left to whoever compiles next. `Tools/stamp_cards.py` reads the registry below out of this section and rejects any other sequence: a new shape is created by registering it here in the same governance change, never by editing the artifact alone. The two indexes are registries rather than routes and stand outside this contract.

The two sides correspond by role, not by literal name, so a deviation on one side does not require one on the other. Every Read Set section other than `Purpose` and `Related` is a loading boundary. A `- [ ]` item compiles a `MUST` obligation of the source text; `SHOULD` guidance stays prose, because the checkbox form reads as mandatory and would raise the modality its owner assigned.

Every Runtime Card also declares `readback_policy`.  `none` is required when
`readback_sources` is empty.  A nonempty set uses `declared` when its sources
are delivered only after the Card's condition is declared, or `activation`
when every listed source must enter startup context.  The policy controls
delivery timing, not authority: each source remains owned by its Kernel leaf.

| Role | Runtime Card | Kernel Read Set |
|---|---|---|
| When the route applies and what loads with it | `Use When` | `Purpose` |
| What is read or settled before execution begins | `Before Start` | `Start` |
| What execution does, and what a condition adds | `During` | `Triggered` |
| The acceptance items the route gates on | `Gate` | `Gate` |
| Where an uncovered or disputed case escalates | `Read Back When` | `Related` |

Five deviation classes are authorized, and nothing else is. `gate-name`: the gate section is named for the single canonical gate it compiles, and that name is the gate owner's own. `gate-by-tier`: acceptance items differ by tier and each gate section names the tier it applies to. `shared-table`: one extra section carries a table whose canonical owner names this artifact as its only compiled carrier. `admission-only`: a route that authorizes no content operation has no `Before Start` or `During`, and its checklist section carries the admission items instead. `named-boundary`: a Read Set whose route adds no conditional load replaces `Triggered` with a named section stating what it requires, and one that owns no gate of its own also has no `Gate`. A trailing `Related` navigation section carrying no acceptance item is permitted on either side.

| Artifact | H2 sequence | Class |
|---|---|---|
| `Card default` | `Use When`, `Before Start`, `During`, `Gate`, `Read Back When` | Every Card not registered below |
| `Read Set default` | `Purpose`, `Start`, `Triggered`, `Gate`, `Related` | Every Read Set not registered below |
| `R01 Card` | `Use When`, `Shared Tiering`, `Before Start`, `During`, `Gate`, `Read Back When` | `shared-table` |
| `R02 Card` | `Use When`, `Before Start`, `During`, `M-tier Gate`, `Other Tiers And Close`, `Read Back When` | `gate-by-tier` |
| `R04 Card` | `Use When`, `Before Start`, `During`, `Canonical Promotion Gate`, `Read Back When` | `gate-name` |
| `R05 Card` | `Use When`, `Before Start`, `During`, `Gate`, `Read Back When`, `Related` | trailing `Related` |
| `R08 Card` | `Use When`, `Before Start`, `During`, `Completion Gate`, `Read Back When` | `gate-name` |
| `R11 Card` | `Use When`, `Admission Checklist`, `Gate`, `Read Back When` | `admission-only` |
| `R01 Read Set` | `Purpose`, `Start`, `Required Decisions`, `Not Sufficient For`, `Related` | `named-boundary` |
| `R08 Read Set` | `Purpose`, `Start`, `Triggered`, `Completion Rule`, `Related` | `gate-name` |
| `R09 Read Set` | `Purpose`, `Start`, `Required Controls`, `Gate`, `Related` | `named-boundary` |
| `R11 Read Set` | `Purpose`, `Start`, `Triggered`, `Admission Gate`, `Related` | `gate-name` |
