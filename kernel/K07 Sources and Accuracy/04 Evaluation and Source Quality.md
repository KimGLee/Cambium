## Navigation

- Parent: [[kernel/K07 Sources and Accuracy Standard|K07 Sources and Accuracy Standard]].
- Previous: [[kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification|Official and Cross-source Verification]].
- Next: [[kernel/K07 Sources and Accuracy/05 Time Formula Terminology and Uncertainty|Time Formula Terminology and Uncertainty]].

## Evaluation Provenance

Any Accuracy, success rate, pass rate, benchmark improvement, or production-effect figure MUST state:

```text
Task Definition
 -> Dataset And Sampling
 -> Ground Truth
 -> Trial Setup And Repeat Count
 -> Model + Prompt + Execution / Control Setup + Tools + Environment
 -> Grader
 -> Metric And Aggregation
 -> Uncertainty And Slice Analysis
 -> Leakage Contamination Or Selection Bias Check
 -> Reproduction Boundary
```

Reproduction Boundary MUST state to what degree the conclusion can be reproduced and where the reproduction boundary lies. Elements that cannot be obtained MUST be explicitly recorded as `unknown` with the reason stated.

The selected profile's additional evaluation provenance requirements are registered by `Source Policy`.

## Source Quality

- Links MUST directly support the corresponding conclusion.
- Search result pages MUST NOT be used as sources.
- One unrelated article MUST NOT be used to support multiple different conclusions.
- Vendor marketing language MUST NOT be treated as neutral fact.
- Where multiple implementations differ, explicitly mark "implementation-specific".
- Empirical recommendations state their applicable environment and limitations.
