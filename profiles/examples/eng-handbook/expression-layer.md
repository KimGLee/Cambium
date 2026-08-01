# Expression Layer

Implements the `Expression Layer Entry` slot for `eng-handbook`.

## Registered Expression Artifacts

None. This profile registers no expression-layer artifacts: the handbook's knowledge pages are consumed directly, and no derived presentation form (flashcards, interview cards, quiz sets) is maintained.

## Consequences

- The kernel's `Expression Layer Link` resolves to nothing for this profile; expression-related audit items are `not_applicable` and their absence does not block any gate.
- No expression status axis is added to the vocabulary; pages carry only the kernel base status axes.

## Extension Path

If the team later wants a derived artifact (for example onboarding flashcards), it must be registered here with a display label, an owner page for its rules, and — if it needs a status axis — a corresponding entry in `vocabulary-extensions.yaml`. Until registered, no such artifact may be implied as part of the composed standard.
