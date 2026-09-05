package profile

// GENERATED: do not edit this projection.
// Semantic owner: K12/02
// Source: kernel/K12 Quality Assurance/profile-rendering-contract.yaml
// Source SHA256: f34fc4dee3ee189f51ffe90e84a03a7caf4412b2b9891a4c892451e2fe74db2b
// Projected checks: object fields, scalar/list types, declared enums and applicability shapes.
// Owner evaluator still checks identities, graph/reference closure, tightening,
// conditional nonempty configuration, external vocabularies and evidence.
#RenderingContract: {
    schema_version: 1
    registration: "none" | "configured"
    rules: [...{rule_id: #Text & =~"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", construct: #Text, capability_id: #Text, acceptance: #Text}]
    if registration == "none" {rules: []}
    if registration == "configured" {rules: [_, ..._]}
}
