# Audit Dimension Registry

Interface: [Audit Dimension Registry slot](../../README.md#audit-dimension-registry-slot)

## Extension Dimensions

Keep this block and its declaration even when nothing is registered: the Terminal Completion Gate reads it to enumerate the receipt dimensions a Terminal Proof must cover, and an absent or unfilled block is an unreadable registry rather than an empty one. A `receipt` target obliges every Terminal Proof to account for that dimension in `dimension_coverage`, on the same terms as the seven base dimensions (K12/16); a `review`-only registration does not.

Use `Configured` with one or more rows, or `None` with no rows. Give each extension a unique lower-snake-case ID that does not reuse a base dimension, and use exactly `review`, `receipt`, or `review + receipt` in the target cell.

- Registration: TODO(profile)

| Dimension ID | Target list(s): `review`, `receipt`, or `review + receipt` | Meaning |
|---|---|---|

## Judgment Items

The required starter row registers Foundation Depth; copy it for other profile-owned audit predicates.

| Stable Judgment Item ID | Base or registered receipt Dimension ID | Exact kernel audit-layer name | Bounded audit object one run proves | Evidence role: `emits`, `consumes`, or `triggers` | Predicate owner (repo-relative path; optional `#heading`) |
|---|---|---|---|---|---|
| TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) |
