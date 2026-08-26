## Navigation

- Parent: [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]].
- Previous: [[kernel/K08 Metadata and Status/03 Status Axes|Status Axes]].
- Next: [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]].

## Evidence Maturity

`authoring_status` represents page authoring and review progress; `evidence_maturity` represents the evidence strength of time-sensitive or empirical conclusions. The two MUST NOT substitute for each other.

The registered vocabulary base is the sole normative source for closed value
membership. This page owns the values' meanings:

- `signal`: worth investigating, but without sufficient evidence yet.
- `single-source`: supported by one traceable source.
- `corroborated`: multiple mutually independent sources support the key observation.
- `validated`: reliable experiments, reproduction, or stable production evidence exists.
- `contested`: substantive conflict exists between credible sources.
- `superseded`: the conclusion has been superseded by newer evidence or a more accurate explanation.

Stable mathematical definitions usually do not need `evidence_maturity`. Frontier systems / operational control patterns, industry experience, benchmark conclusions, and Research Synthesis SHOULD fill it in.

A Source Note MAY be `authoring_status: reviewed` while still having only `evidence_maturity: single-source`. This means the source is recorded accurately, not that its conclusion has been established generally.

## Prerequisites

- Record only content that genuinely MUST be understood first.
- Use canonical note paths or stable names.
- Do not put all Related links into prerequisites.
- Circular dependencies require manual inspection.

## Aliases

Aliases are used for:

- English full names and abbreviations.
- Common names in other languages registered by the `Language Contract`.
- Common alternative spellings in the industry.

Aliases MUST NOT be used to mask two actually distinct concepts.
