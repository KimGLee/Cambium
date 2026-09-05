package profile

// GENERATED: do not edit this projection.
// Semantic owner: K12/07-K12/08
// Source: kernel/K12 Quality Assurance/audit-dimension-base.yaml
// Source SHA256: 8f8e48a377d9b127b1a483e99ac60332ee0d3216918e3f75972a2937c6db393c
// Projected checks: object fields, scalar/list types, declared enums and applicability shapes.
// Owner evaluator still checks identities, graph/reference closure, tightening,
// conditional nonempty configuration, external vocabularies and evidence.
#AuditEvidenceRole: "emits" | "consumes" | "triggers"
#AuditTargets: ["receipt"] | ["receipt", "review"] | ["review"] | ["review", "receipt"]
