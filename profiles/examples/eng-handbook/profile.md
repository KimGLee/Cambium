## Profile Identity

- `profile_id`: `eng-handbook`
- Status: non-normative example. This profile is a worked illustration of one way an engineering-documentation domain could fill the profile interface. It is not a standard, not a default configuration, and not a source of requirements for any other profile.
- Purpose: to show the form and the level of specificity each slot answer needs. The domain choices made here — the four-layer architecture, the incident-centred priority rubric, the English-only language contract — belong to this example alone and do not bind other profiles.
- Not a copy-and-edit starting point. The official starting point is the domain-neutral `profiles/_template/`, which carries the constraints and the TODO markers for every slot and no domain answers at all. Copying this example instead would carry an engineering domain's answers into a profile that is not about engineering, and those answers are easy to leave in place without noticing.
- The official flow is: copy `profiles/_template/` to `profiles/<your-profile-id>/`, read `profiles/README.md` for the normative slot interface — which slots exist, and what constrains each — consult this example for the form and specificity a filled answer needs, fill in your own profile, run `python3 Tools/check_profile.py profiles/<your-profile-id>` until it passes, then have the agent load `kernel/` plus your profile.
- That check is mechanical, not advisory. It fails while any part of the copied skeleton is still visible, so a half-filled profile cannot be loaded and reported as working. It checks structure only, and never judges whether a slot answer is a good one.

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

## Registered Extensions

- None. This profile registers no expression artifacts and no extension status axes; the kernel base vocabularies and the seven base audit dimensions apply unchanged.

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
