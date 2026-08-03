# Expression Layer

Implements the `Expression Layer Entry` slot.

TODO(profile) — fill in the sections below, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

The expression layer is where derived presentation forms live: flashcards, quiz sets, interview cards, briefing sheets — anything compiled from knowledge pages for a particular way of consuming them. The kernel defines how such artifacts behave once they exist. This file only routes and names them: which artifacts this profile registers, and what each is called.

This slot handles routing and naming only. Do not restate the kernel's expression-layer rules here; a copy of a rule is a second owner of it.

Registering no artifacts is a normal answer. Many profiles have no expression layer at all.

## Registered Expression Artifacts

TODO(profile) — list each registered artifact with its display label and the page that owns its rules, or write that this profile registers none.

If you register an artifact, it needs three things before it can be used: a display label, a single owner page for its rules, and — if it carries its own progress or readiness axis — a matching entry in `vocabulary-extensions.yaml`. Until all three exist, the artifact is not part of the composed standard and must not be treated as loaded.

## Consequences

TODO(profile) — state what follows from the list above.

If nothing is registered, the kernel's `Expression Layer Link` resolves to nothing for this profile, expression-related audit items are `not_applicable`, and their absence does not block any gate. Write that out rather than leaving it implied: an unstated `not_applicable` is indistinguishable from an unnoticed gap during audit.

If artifacts are registered, state which gates consume them and what happens when a source page changes after the derived artifact was compiled.

## Extension Path

TODO(profile) — state what someone must do to add an artifact later, so that a future addition follows this slot instead of appearing informally. The requirement to state is that until an artifact is registered here, it may not be implied as part of the composed standard.
