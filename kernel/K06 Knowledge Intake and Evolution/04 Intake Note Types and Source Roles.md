## Navigation

- Parent: [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]].
- Previous: [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]].
- Next: [[kernel/K06 Knowledge Intake and Evolution/05 Evidence Maturity and Batch Policy|Evidence Maturity and Batch Policy]].

## Note Types In The Intake Layer

### Source Note

A Source Note faithfully describes a single source:

```text
Source Identity
Problem Addressed
System Or Experiment Context
Key Claims
Evidence Provided
Assumptions And Scope
Limitations
What The Source Does Not Establish
Affected Knowledge Notes
Open Questions
```

A Source Note does not own general definitions or mechanisms.

### Research Synthesis Note

A Research Synthesis Note integrates multiple sources around one question:

```text
Research Question
Source Set And Selection Boundary
Terminology Mapping
Agreements
Disagreements
Evidence Comparison
Generalizable Mechanisms
Vendor-specific Choices
Unresolved Questions
Recommended Graph Changes
```

A Research Synthesis is not a permanent replacement for canonical notes. Once conclusions stabilize, the mechanisms SHOULD be promoted to the correct owner, with the synthesis retaining the research process, disagreements, and source relationships.

## Source Role Policy

### Official Company Sources

In intake, official articles from different companies serve as primary implementation evidence, used to prove the systems, experiments, and engineering experience that company has publicly disclosed; they do not automatically prove industry-wide laws. The canonical policy is in [[kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification|K07/03]].

### Community Sources

In intake, community discussions serve mainly as discovery signals and failure evidence, used to discover problems, collect practice experience, and form hypotheses requiring further verification; community consensus is not fact. The canonical hierarchy and role positioning are in [[kernel/K07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles|K07/01]].

### Papers Benchmarks And Reproductions

- Papers are responsible for theory, methods, and controlled experiments; they do not automatically represent production performance.
- A benchmark MUST record task, dataset, grader, harness, and contamination risk together.
- Independent reproductions are used to judge whether conclusions hold across implementations.
- Postmortems are high-value for failure paths and recovery, but their conclusions remain constrained by the specific system.
