## Navigation

- Parent: [[kernel/11 Expression Layer Standard|11 Expression Layer Standard]].
- Previous: [[kernel/11 Expression Layer/01 Expression Architecture and Separation|Expression Architecture and Separation]].
- Next: [[kernel/11 Expression Layer/04 Evidence-bound Expression|Evidence-bound Expression]].

## Expression Coverage And Readiness

Expression layer readiness is an independent status axis. The field, allowed values, and promotion gates are registered by the selected profile and are subject to [[kernel/08 Metadata and Status/03 Status Axes#Profile Readiness Status|Profile Readiness Status]]; it MUST NOT be inferred automatically from `authoring_status`, `evidence_maturity`, learning progress, file existence, or any other status axis.

A resolvable expression artifact link proves only that the target has been mapped; it does not automatically prove that the artifact is complete, reviewed, or usable for its target scenario.

An expression artifact MAY bind multiple closely related canonical notes, but every bound canonical note MUST be able to navigate to that artifact, and the artifact MUST explicitly link back to the corresponding canonical owners. For the link semantics of the bidirectional relationship, see [[kernel/09 Wiki Link and Navigation/02 Structural and Bidirectional Links#Bidirectional Knowledge Flow|Bidirectional Knowledge Flow]].
