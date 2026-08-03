## Template Usage

This directory is the official starting point for a new profile. It is a skeleton of constraints and unanswered questions: every slot the interface defines exists here as a file, and every answer is left as a `TODO(profile)` marker for you to replace. It is deliberately not runnable. Nothing here describes a domain, and nothing here is a default configuration.

To create your own profile:

1. Copy the whole directory to `profiles/<your-profile-id>/`. Copy it — do not edit this one in place.
2. Set `profile_id` under `Profile Identity` to your own id, and replace the rest of that section with your own description.
3. Work through each slot file. Every file states what the slot must answer and which kernel invariants you may not override, then leaves the answer to you. Use `profiles/README.md` as the authoritative interface when a slot needs clarification.
4. Answer every `TODO(profile)` marker. "This profile registers nothing here" is a legitimate answer for several slots, but it must be written explicitly; a slot left silent is not the same as a slot that declares itself empty.
5. Delete the scaffolding as you go. That means this `Template Usage` section, the `What This Slot Must Answer` section at the top of each slot file, the comment header of `vocabulary-extensions.yaml`, and the two guidance paragraphs above the `Execution Default Overrides` table below. All of it restates `profiles/README.md`; a copy living inside your profile is a second owner that will drift from the first. Each slot file carries a marker reminding you, so nothing here has to be remembered.
6. Validate: `python3 Tools/check_profile.py profiles/<your-profile-id>`.

The validator is a structural gate, not a judge of your answers. It fails while any `TODO(profile)` marker remains anywhere in the directory, while `profile_id` is still a reserved placeholder, and while this section is still present. Those three conditions are checked independently, so clearing one does not mask the others. Passing means the manifest is complete and every slot resolves; it does not mean the answers are good.

The slot bindings below are relative paths, so they keep working after you copy the directory. If you rename a slot file, update its binding in the same edit.

The normative definition of the slots is `profiles/README.md`. It states which slots exist and what constrains each. Where this template and that file disagree, that file wins — this one is a scaffold for filling it in, not a second source of the interface.

## Profile Identity

- `profile_id`: `_template`
- Status: TODO(profile) — state what this profile is and whether it is active for the knowledge base named below.
- Purpose: TODO(profile) — state in one or two sentences which knowledge base this profile governs and who reads it.
- Owner: TODO(profile) — name the person or role accountable for this profile's answers, so a later reader knows whom to ask when a slot answer is disputed.

## Implemented Slots

- `Profile Scope`: `scope-and-architecture.md`
- `Priority Rubric`: `priority-rubric.md`
- `Vocabulary Extensions`: `vocabulary-extensions.yaml`
- `Language Contract`: `language-contract.md`
- `Expression Layer Entry`: `expression-layer.md`
- `Source Policy`: `source-policy.md`
- `Role Registry`: `registries/roles.md`
- `Audit Dimension Registry`: `registries/audit-dimensions.md`
- `Registered Scan Registry`: `registries/registered-scans.md`
- `Routing And Gate Registry`: `registries/routing-and-gates.md`

Every slot the interface defines must be bound here. A slot required by the current task but missing from this list means the composed standard is not fully loaded, and the agent must stop rather than proceed on a partial standard.

## Registered Extensions

- TODO(profile) — list the expression artifacts and extension status axes this profile registers, or write that it registers none. This is a summary of what the slot files register; it does not create registrations by itself.

## Execution Default Overrides

The kernel ships a default for each item below. This table is where you declare, item by item, whether you adopt that default or replace it. An item left unregistered uses the kernel default, so the table exists to make the choice deliberate rather than accidental.

Write `use-kernel-default` in the choice column to adopt the default, or write your own value to override it. Adopting all eight defaults is a normal and common answer — it is a decision, not a gap. When you override, put your value in the effective-value column too.

| Kernel default item | Profile choice | Effective value |
|---|---|---:|
| `concurrency_cap` | TODO(profile) | `3` |
| `batch_size.S` | TODO(profile) | `24` |
| `batch_size.M` | TODO(profile) | `10` |
| `batch_size.L` | TODO(profile) | `6` |
| `priority_quota.P0` | TODO(profile) | `15%` |
| `priority_quota.P1` | TODO(profile) | `35%` |
| `maintenance.unselected_rounds_before_log_only` | TODO(profile) | `3` |
| `maintenance.incoming_retarget_divisor` | TODO(profile) | `6` |

The effective values shown are the kernel defaults, carried here for reference. The kernel modules that define them are the canonical owners; `Tools/schemas/execution_defaults.template.yaml` records which module owns each item.

Only these items are overridable. The two-round caps on substantive review and on Terminal Audit are constitutional constants: do not add them to this table, and do not add any other kernel rule to it. Items not registered here are not overridden by this profile; a task contract may still override them explicitly within the ranges the kernel permits.

## Task Contract Defaults

These are the standing answers a task contract may assume without re-asking. Fill them in so routine work does not re-litigate settled profile decisions.

- Logical center: TODO(profile) — the subject the knowledge base is organized around.
- Expression artifact: TODO(profile) — the default derived artifact, or none.
- Directory and scope decisions: use the structure and scope registered in `Profile Scope`.
- Display language: use `Language Contract`.
- Routing: use `Routing And Gate Registry`.

When a task does not explicitly change these profile defaults, do not re-request approval for them; the kernel's ownership, source-to-knowledge, quality, and safety invariants remain in force regardless of what this profile registers.
