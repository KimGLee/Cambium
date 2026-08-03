# Expression Layer

Implements the `Expression Layer Entry` slot.

TODO(profile) — fill in the sections below, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

The expression layer is where derived presentation forms live: flashcards, quiz sets, interview cards, briefing sheets — anything compiled from knowledge pages for a particular way of consuming them. The kernel-owned R05 route defines how such artifacts behave once they exist. This file identifies the concrete targets to which R05 applies.

This slot supplies bindings, not a replacement route. Do not restate the kernel's expression-layer rules here; a copy of a rule is a second owner of it.

Registering no artifacts is a normal answer. Many profiles have no expression layer at all.

## Registered Expression Artifacts

TODO(profile) — list each registered artifact with its stable artifact ID and type, display label, resolvable entry point, and the one page that owns its profile-specific rules; or write that this profile registers none.

For each artifact, also bind its canonical-to-expression dependency mapping, the event that invalidates or regenerates it, and — if it carries its own progress or readiness axis — the matching field/value owner and promotion gate in `vocabulary-extensions.yaml` and the profile registries. Until all applicable bindings resolve, the artifact is not part of the composed standard and must not be treated as loaded.

## Consequences

TODO(profile) — state what follows from the list above.

If nothing is registered, state that the profile supplies no concrete expression target. R05 remains a kernel route, but there is no object on which to invoke it; this is absence of a target, not a profile override or a passed expression gate.

If artifacts are registered, state which supplemental gates apply and what happens when a canonical source page changes after the derived artifact was compiled. The R05 kernel gate always remains in force for an in-scope artifact.

## Extension Path

TODO(profile) — state what someone must do to add an artifact later, so that a future addition follows this slot instead of appearing informally. The requirement to state is that until an artifact is registered here, it may not be implied as part of the composed standard.
