# Audit Dimension Registry

Interface: [Audit Dimension Registry slot](../../README.md#audit-dimension-registry-slot)

## Extension Dimensions

- Registration: None

This profile files every judgment item under a base kernel receipt dimension;
it registers no extension dimension because it has no artifact class whose
fitness is judged independently of the seven base dimensions.

| Dimension ID | Target list(s): `review`, `receipt`, or `review + receipt` | Meaning |
|---|---|---|

## Judgment Items

The interface requires these two registrations; a profile cannot opt out of
them. The first registers Foundation Depth; the second is the acceptance item
for the registered residual scan. Item IDs conventionally start with the
profile ID (`<profile-id>-foundation-depth`). The predicate-owner cells point
into this Profile's own files — derive them from your profile ID before
validation (see the README's materialization checklist). `profile-load`
requires each path to remain inside this Profile and each optional heading to
resolve exactly once; it reports a stale owner but never guesses a rewrite.

| Stable Judgment Item ID | Base or registered receipt Dimension ID | Exact kernel audit-layer name | Bounded audit object one run proves | Evidence role: `emits`, `consumes`, or `triggers` | Predicate owner (repo-relative path; optional `#heading`) |
|---|---|---|---|---|---|
| TODO(profile) | `content_and_depth` | `Single Note Review` | One page of the registered foundation class satisfies the registered foundation-depth predicate. | `emits` | TODO(profile) |
| TODO(profile) | `coverage_and_integration` | `Batch Review` | Every candidate the registered residual scan reports outside its accepted roots has an accepted disposition. | `emits` | TODO(profile) |

## Residual Disposition

TODO(profile) — state, in two or three sentences, what the registered scan's
candidates mean for this corpus and the two or three legal ways a candidate is
resolved (moved into its accepted root, or the page states why this structure
is canonical here). The scan is candidate discovery only; a zero-candidate
result proves the registered predicate for the scanned snapshot, nothing more.
