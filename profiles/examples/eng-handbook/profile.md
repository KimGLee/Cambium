## Profile Identity

- `profile_id`: `eng-handbook`
- Status: non-normative example. This profile is a worked illustration of one way an engineering-documentation domain could fill the profile interface. It is not a standard, not a default configuration, and not a source of requirements for any other profile.
- Purpose: to show the form and the level of specificity each slot answer needs. The domain choices made here — the four-layer architecture, the incident-centred priority rubric, the English-only language contract — belong to this example alone and do not bind other profiles.
- Not a copy-and-edit starting point. The official starting point is the domain-neutral `profiles/_template/`, which does not yet exist in this repository. Until it does, read `profiles/README.md` for the normative slot interface — which slots exist, and what constrains each — and write your own profile against that, using this example only to see what a filled answer looks like.
- Once `profiles/_template/` exists, the official flow will be: copy the template, reference this example, fill and validate your own profile, then have the agent load `kernel/` plus your profile.

## Implemented Slots

- `Profile Scope`: [[profiles/examples/eng-handbook/scope-and-architecture|Scope And Architecture]]
- `Priority Rubric`: [[profiles/examples/eng-handbook/priority-rubric|Priority Rubric]]
- `Vocabulary Extensions`: [Vocabulary Extensions](vocabulary-extensions.yaml)
- `Language Contract`: [[profiles/examples/eng-handbook/language-contract|Language Contract]]
- `Expression Layer Entry`: [[profiles/examples/eng-handbook/expression-layer|Expression Layer]]
- `Source Policy`: [[profiles/examples/eng-handbook/source-policy|Source Policy]]
- `Role Registry`: [[profiles/examples/eng-handbook/registries/roles|Role Registry]]
- `Audit Dimension Registry`: [[profiles/examples/eng-handbook/registries/audit-dimensions|Audit Dimension Registry]]
- `Registered Scan Registry`: [[profiles/examples/eng-handbook/registries/registered-scans|Registered Scan Registry]]
- `Routing And Gate Registry`: [[profiles/examples/eng-handbook/registries/routing-and-gates|Routing And Gate Registry]]
- `Runtime Card Provider`: declared inline below (`mode: none`)

## Registered Extensions

- None. This profile registers no expression artifacts and no extension status axes; the kernel base vocabularies and the seven base audit dimensions apply unchanged.

## Runtime Card Provider Binding

- Mode: `none`.
- Meaning: no derived runtime cards exist for this profile; agents load rules from kernel Read Sets and leaf modules directly.
- Consequence: card synchronization checks (`Tools/stamp_cards.py`) are `not_applicable` for this profile and their absence does not block governance close. If a future task compiles cards for this profile, this binding must be upgraded to an explicit provider before those cards may be loaded.

## Execution Default Overrides

| Kernel default item | Profile choice | Effective value |
|---|---|---:|
| `concurrency_cap` | `use-kernel-default` | `3` |
| `batch_size.S` | `use-kernel-default` | `24` |
| `batch_size.M` | `use-kernel-default` | `10` |
| `batch_size.L` | `use-kernel-default` | `6` |
| `priority_quota.P0` | `use-kernel-default` | `15%` |
| `priority_quota.P1` | `use-kernel-default` | `35%` |
| `maintenance.unselected_rounds_before_log_only` | `use-kernel-default` | `3` |
| `maintenance.incoming_retarget_divisor` | `use-kernel-default` | `6` |

Items not registered here are not overridden by this profile; a task contract may still override them explicitly within the ranges the kernel permits.

## Task Contract Defaults

- Logical center: the team's production services and the incident lifecycle around them.
- Expression artifact: none registered.
- Directory and scope decisions: use the structure and scope registered in `Profile Scope`.
- Display language: use `Language Contract`.
- Routing: use `Routing And Gate Registry`.

When a task does not explicitly change these profile defaults, do not re-request approval for them; the kernel's ownership, source-to-knowledge, quality, and safety invariants remain in force.
