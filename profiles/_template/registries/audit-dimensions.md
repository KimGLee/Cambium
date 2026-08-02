## Reference

- Profile manifest: `profiles/<your-profile-id>/profile.md`
- Slot interface: `profiles/README.md`, `Audit Dimension Registry Slot`
- Kernel review dimensions: `kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review.md`, section `Quality Dimensions`
- Kernel receipt dimensions: `kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md`

Implements the `Audit Dimension Registry` slot.

TODO(profile) — fill in the sections below, correct the manifest path above, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile. A filled version to read for form is `profiles/examples/eng-handbook/registries/audit-dimensions.md`.

## What This Slot Must Answer

The kernel fixes two base dimension lists, at two different granularities, and names this registry as the append point for both. The review dimensions are the ones a page is accepted against during single-note review. The receipt dimensions are the coarser identifiers a verification result is filed under when it becomes reusable audit evidence. This file is where a profile registers *additional* dimensions its domain needs.

Registration is append-only. You may add extension dimensions; you may not delete, rename, redefine, or weaken a kernel dimension in either list, and you may not register a predicate that some other slot in this profile already owns — duplicating a predicate creates two places to change it and one place to forget.

Each extension dimension needs three things to be usable: the objects it applies to, a single owner of its acceptance predicate — the one place that decides pass or fail — and which of the two base lists it appends to. A dimension without a named predicate owner cannot be consumed by a gate, because there is nobody to ask. A dimension that does not say which list it joins cannot be filed as a receipt, because the receipt's `dimension` field has no value to take.

The kernel publishes no mapping between the two lists, so if your dimension appends to the review list, also state which receipt dimension a gate should file its verdict under.

Registering nothing is the common answer. The kernel's base dimensions cover most domains.

## Extension Dimensions

TODO(profile) — register each extension dimension with its name, the objects it applies to, its single acceptance predicate owner, and the base list it appends to. If this profile needs none, write that explicitly and state that the kernel's base dimensions apply unchanged to every page.

Declaring the registry empty is the minimal legal implementation of this slot: the file exists so the manifest binding resolves, and it says so rather than leaving the slot silent.

## Interpretation Notes For This Domain

TODO(profile) — record how the base dimensions are read against this profile's own owners. These notes point at existing owners; they do not create dimensions.

The usual form is one line per base dimension that needs domain grounding, naming the file and section that decides it. For example, depth is typically judged against the depth requirements registered in `Profile Scope`, and provenance against `Source Policy`.

If no interpretation notes are needed, write that the base dimensions apply as written.

## Extension Path

TODO(profile) — state what someone must supply to add a dimension later: its applicable objects, its single acceptance predicate owner, and the base list it appends to, all registered here before any gate may consume it. Naming the requirement now prevents a future dimension from being enforced informally before it is registered.
