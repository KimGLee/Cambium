## Navigation

- Parent: [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]].
- Previous: [[kernel/K06 Knowledge Intake and Evolution/04 Intake Note Types and Source Roles|Intake Note Types and Source Roles]].
- Next: [[kernel/K06 Knowledge Intake and Evolution/06 Intake Anti-patterns and Acceptance|Intake Anti-patterns and Acceptance]].

## Evidence Maturity

Authoring completion state and evidence maturity MUST be kept separate. The authoring_status transitions are in [[kernel/K08 Metadata and Status/03 Status Axes|K08/03]].

```text
Evidence maturity:
signal -> single-source -> corroborated -> validated
                     \-> contested
validated / contested -> superseded
```

The canonical definitions of the six values are in [[kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata|K08/04]].

Evidence maturity describes conclusion strength; it does not represent page authoring quality, nor expression-layer priority.

## Batch Policy

A source-driven expansion batch completes at least:

1. The batch MUST run through all stages of the [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] in full; a deferral requires a recorded reason.
2. Sources, metadata, QA, and the progress ledger are updated.
3. The originating guidance, Amendment Record, and resulting scope / queue change are reconciled.

"How many articles have been read" or "how many Source Notes have been created" MUST NOT serve as the completion criterion for knowledge expansion.
