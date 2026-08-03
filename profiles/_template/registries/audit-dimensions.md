## Reference

- Profile manifest: `profiles/<your-profile-id>/profile.md`
- Slot interface: `profiles/README.md`, `Audit Dimension Registry Slot`
- Kernel review dimensions: `kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review.md`, section `Quality Dimensions`
- Kernel receipt dimensions: `kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md`
- Kernel judgment item map: `kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md`

Implements the `Audit Dimension Registry` slot.

TODO(profile) — fill in the sections below, correct the manifest path above, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

The kernel fixes two base dimension lists, at two different granularities, and names this registry as the append point for both. The review dimensions are the ones a page is accepted against during single-note review. The receipt dimensions are the coarser identifiers a verification result is filed under when it becomes reusable audit evidence. This file is where a profile registers *additional* dimensions its domain needs.

Registration is append-only. You may add extension dimensions; you may not delete, rename, redefine, or weaken a kernel dimension in either list, and you may not register a predicate that some other slot in this profile already owns — duplicating a predicate creates two places to change it and one place to forget.

Each extension dimension needs three things to be usable: the objects it applies to, a single owner of its acceptance predicate — the one place that decides pass or fail — and which of the two base lists it appends to. A dimension without a named predicate owner cannot be consumed by a gate, because there is nobody to ask. A dimension that does not say which list it joins cannot be filed as a receipt, because the receipt's `dimension` field has no value to take.

Adding a dimension and adding a check are different acts, and this slot is the append point for both. A new dimension gives the receipt `dimension` field a new legal value. A new check is a judgment item — one thing that can be run once and returns pass or fail — and the kernel maps its own items to receipt dimensions in `kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md`.

A judgment item registered here MUST declare five things: the receipt dimension it files under, its audit layer, its audit object — what one run of it proves, and at which layer — its evidence role (`emits`, `consumes`, or `triggers`), and the single owner of its acceptance predicate. An entry missing the receipt dimension cannot be filed, because the receipt field has no value to take. An entry missing the audit object cannot be told apart from a check the kernel already runs, which is how the same work ends up filed twice under two names.

Registering nothing is the common answer. The kernel's base dimensions cover most domains.

## Extension Dimensions

TODO(profile) — register each extension dimension with its name, the objects it applies to, its single acceptance predicate owner, and the base list it appends to; register each judgment item with the five declarations above. If this profile needs neither, write that explicitly and state that the kernel's base dimensions and its judgment item map apply unchanged to every page.

Declaring the registry empty is the minimal legal implementation of this slot: the file exists so the manifest binding resolves, and it says so rather than leaving the slot silent.

## Interpretation Notes For This Domain

TODO(profile) — record how the base dimensions are read against this profile's own owners. These notes point at existing owners; they do not create dimensions.

The usual form is one line per base dimension that needs domain grounding, naming the file and section that decides it. For example, depth is typically judged against the depth requirements registered in `Profile Scope`, and provenance against `Source Policy`.

If no interpretation notes are needed, write that the base dimensions apply as written.

## Extension Path

TODO(profile) — state what someone must supply later to add a dimension, and what to add a judgment item: for a dimension, its applicable objects, its single acceptance predicate owner, and the base list it appends to; for a judgment item, the five declarations above. Both are registered here before any gate may consume them. Naming the requirement now prevents a future check from being enforced informally before it is registered.
