## Navigation

- Parent: [[kernel/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]].
- Previous: [[kernel/07 Sources and Accuracy/04 Evaluation and Source Quality|Evaluation and Source Quality]].
- Next: [[kernel/07 Sources and Accuracy/06 Source Maintenance and Acceptance|Source Maintenance and Acceptance]].

## Time-sensitive Content

The following topics require `last_verified`:

- Protocols, APIs, and other external interfaces.
- Component or service specifications, capacity limits, pricing, and restrictions.
- Framework versions and library behavior.
- Security recommendations, regulations, and industry standards.
- Cloud services, data services, and runtime platform capabilities.

Time-sensitive conclusions MUST note the verification date and MUST NOT rely on model memory alone.

## Formula Verification

Formula checks include at least:

- Whether symbols are defined.
- Whether subscripts, summation ranges, and normalization are correct.
- Whether input and output dimensions match.
- Whether the directions of loss, metric, and probability are correct.
- Whether boundary cases hold.
- Whether the formula is consistent with the body explanation.
- Whether numeric examples can be recomputed.

## Terminology Accuracy

- Full names, abbreviations, and capitalization MUST be accurate.
- Distinguish similar but different concepts, for example parameter vs hyperparameter, state vs memory.
- Describe protocol definitions separately from common engineering habits.
- Translations specified by the `Language Contract` MUST NOT change the meaning of the original term.
- Canonical definitions of proper nouns follow the [[kernel/05 Terminology Standard|Terminology Standard]].

## Uncertainty And Disagreement

When a conclusion is not a universal fact, the following SHOULD be stated:

- Applicable conditions.
- Different views or implementations.
- The current strength of the evidence.
- Which definition this page adopts, and why.

Empirical trends MUST NOT be written as unconditional laws.
