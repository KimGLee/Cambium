## Navigation

- Parent: [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]].
- Previous: [[kernel/K06 Knowledge Intake and Evolution/06 Intake Anti-patterns and Acceptance|Intake Anti-patterns and Acceptance]].
- Next: [[kernel/K06 Knowledge Intake and Evolution/08 Canonical Promotion Gate|Canonical Promotion Gate]].

## Environmental Scanning

This is Stage 1 of the [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline#Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]]; a maintenance run enters it on its own, without running the stages that follow.

The goal is to discover changes worth investigating, not to immediately write hot topics into conclusions.

The following need to be recorded:

- Newly emerging problems, capabilities, failure modes, or engineering patterns.
- The discovery source and first-discovery date.
- The originating guidance ID, for user-provided hypotheses or source leads.
- The relationship to the Knowledge Spine declared by `Profile Scope`.
- The existing modules it may affect.
- Why it is worth further investigation.

Community buzz can trigger investigation, but MUST NOT on its own trigger canonical promotion.

Incremental scanning semantics:

- By default, scan only new material that appeared after `scanned_until` in `Tools/state/watermark.yaml` (schema in `Tools/schemas/watermark.template.yaml`).
- The watermark records covered sources and the coverage cutoff date in per-domain sections.
- At batch close, advance the watermark together with the Ledger. The state
  records both the enclosing maintenance `last_run_id` and the exact Queue
  `last_batch_id` that performed the final advance; one identifier cannot stand
  in for the other.
- A full rescan is an explicit exception, used only when onboarding a new domain or when the watermark is suspect, and the reason MUST be recorded in the Ledger.
