## Navigation

- Parent: [[kernel/K11 Expression Layer Standard|K11 Expression Layer Standard]].
- Previous: [[kernel/K11 Expression Layer/01 Expression Architecture and Separation|Expression Architecture and Separation]].
- Next: [[kernel/K11 Expression Layer/04 Evidence-bound Expression|Evidence-bound Expression]].

## Expression Coverage And Readiness

Expression layer readiness is an optional independent status axis. It applies only when the selected Profile explicitly registers a persistent readiness field, its allowed values, and its promotion Gate under [[kernel/K08 Metadata and Status/03 Status Axes#Profile Readiness Status|Profile Readiness Status]]. Registering an expression artifact alone creates no readiness field, reviewer role, Gate, or completion obligation. When no readiness axis is registered, the artifact remains subject to the ordinary K11 and K12 content, evidence, binding, and acceptance rules without acquiring a separate readiness state.

When readiness is registered, it MUST NOT be inferred automatically from `authoring_status`, `evidence_maturity`, learning progress, file existence, or any other status axis.

A resolvable expression artifact link proves only that the target has been mapped; it does not automatically prove that the artifact is complete, reviewed, or usable for its target scenario.

An expression artifact MAY bind multiple closely related canonical notes, but every bound canonical note MUST be able to navigate to that artifact, and the artifact MUST explicitly link back to the corresponding canonical owners. For the link semantics of the bidirectional relationship, see [[kernel/K09 Wiki Link and Navigation/02 Structural and Bidirectional Links#Bidirectional Knowledge Flow|Bidirectional Knowledge Flow]].
