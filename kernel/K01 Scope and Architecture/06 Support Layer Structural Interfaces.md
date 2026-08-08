## Navigation

- Parent: [[kernel/K01 Scope and Architecture Standard|K01 Scope and Architecture Standard]].
- Previous: [[kernel/K01 Scope and Architecture/05 Structural Unit Interface|Structural Unit Interface]].

## Support Layer Structural Interfaces

A support layer is a formal content layer whose pages follow an intake, evidence, synthesis, or expression workflow instead of the domain build workflow. Four roles are defined: `cases`, `sources`, `synthesis`, and `expression`. A profile registers each support layer it operates in the `support_layers` block of the same Structure Registry owned by [[kernel/K01 Scope and Architecture/05 Structural Unit Interface|K01/05]]; no separate profile file per layer is created.

A support layer MUST NOT be forced to copy the domain skeleton: it owes no learning roadmap, no quick reference, and no expression artifact of its own. Its entry page provides navigation and boundaries only and MUST NOT copy Coverage, Queue, readiness, or receipt state.

## Shared Base

Every registered support layer declares: the `layer_id` registered by `Profile Scope`, its `role`, its `root` directory, exactly one canonical `entry` page, its `layout`, a `coverage` projection mode from the K01/05 mode set, and its `global_map_entry`.

`layout` is `flat` or `grouped`:

- `flat`: content pages sit directly under the root; navigation groupings in the entry page own no physical taxonomy. Flat is a legitimate registered choice, not an unfinished state.
- `grouped`: requires one stable classification axis, a closed set of registered classes, a one-to-one mapping from class to directory, and a controlled page field carrying each page's class. The checker verifies only that the declared class and the path agree; it never infers a class from content, titles, or vendors.

An unregistered subdirectory of a support layer is instance history, not taxonomy; pages MUST NOT be mass-moved onto it, and current Queue paths MUST NOT harden into an implicit standard.

## Role-specific Interfaces

Each role adds only structural bindings. The referenced semantics stay with their owners — [[kernel/K03 Note Types and Ownership/01 Note Type Catalog|K03]] for note types, [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|K06]] for intake and promotion, [[kernel/K07 Sources and Accuracy Standard|K07]] for source authority, and [[kernel/K11 Expression Layer Standard|K11]] for expression artifacts; this interface restates none of them.

- `cases`: a `taxonomy` (the grouped-layout declarations above, or flat) and an `evidence_binding_owner` pointing at the owner of the case-to-evidence relation.
- `sources`: an `authority_taxonomy_ref`, an `intake_policy_ref`, and a `freshness_policy_ref` into the profile's `Source Policy`, plus an `index_mode` of `derived` or `none`. The entry page stays a thin route: member and topic indexes are generated deterministically from registered metadata, reproducible and invalidated when inputs change, and are never a canonical owner and never written back into policy or page classification. A long hand-maintained member index is not a registrable mode.
- `synthesis`: a `question_identity_field` naming the controlled field that identifies each page's research question, and a `promotion_policy_ref`. Grouped layout additionally requires the stable predicate of the shared base; lifecycle, vendor, author, or current-Queue groupings are not stable axes.
- `expression`: an `artifact_registry_ref` to the profile's `Expression Layer Entry`, a `preparation_route_ref`, and a `readiness_projection` mode. Readiness state itself stays with its registered status owner.

## Verification

The `structure-registry` gate of K01/05 covers this block with the same run: shape, closed fields, path and entry resolution, layout consistency, grouped-class-to-directory agreement, and reference resolvability. Judging whether a class assignment, promotion, or evidence binding is semantically right remains manual review under [[kernel/K12 Quality Assurance/03 Module and Coverage Review|K12/03]].
