# Priority Rubric

Implements the `Priority Rubric` slot.

TODO(profile) — fill in the sections below, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

The kernel fixes a three-level priority axis — P0, P1, P2 — and uses it for quota coupling, tier derivation, and exemption handling. It does not know what makes a page important in your domain. This file supplies the grant criteria: which pages earn P0, which earn P1, and what falls through to P2.

You must consume the P0 / P1 / P2 axis as it stands. Do not rename the levels, add a fourth, remove one, or redefine what they mean structurally. Do not rewrite tier derivation, quota coupling, or the exemption mechanism; those are kernel-owned. Overridable numeric thresholds — the P0 and P1 quotas among them — are selected in the manifest's `Execution Default Overrides` table, not here.

## P0 Grant Criteria

TODO(profile) — state the test a page must meet to be P0. P0 is the scarcest grade and is quota-limited, so the criteria must exclude most pages; if your P0 test admits half the vault, it is not a test.

TODO(profile) — state the readiness bar for P0: what a P0 page must let its reader do, unaided, for the grant to be justified. This bar is an acceptance condition, not an aspiration; a page that fails it fails acceptance regardless of how complete it looks.

## P1 Grant Criteria

TODO(profile) — state what makes a page P1: needed reliably, but not on the critical path that P0 protects. Name the time horizon that distinguishes P1 from P0 in your domain.

## P2 Default

TODO(profile) — confirm that everything not meeting the P0 or P1 tests defaults to P2, and name the recurring kinds of page that land there. Listing them keeps P2 from reading as a failure grade; most of a healthy knowledge base is P2.

## Quotas And Overrides

TODO(profile) — state which quota values this profile uses, and point to the manifest's `Execution Default Overrides` table as the place that registers them. If you adopt the kernel defaults, the ceilings are P0 at 15% and P1 at 35%.

TODO(profile) — state what the correct response is when P0-qualifying pages exceed the quota. The kernel-consistent answers are to tighten the grant criteria or to raise the quota through an explicit registered override. Silently under-grading pages to fit the ceiling defeats the purpose of the quota and must not be the recorded response.
