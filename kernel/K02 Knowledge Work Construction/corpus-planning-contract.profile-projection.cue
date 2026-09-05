package profile

// GENERATED: do not edit this projection.
// Semantic owner: K02/03+K02/04+K02/05+K02/06+K02/07
// Source: kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml
// Source SHA256: a6193fd7cbc8c48c147f43e2ad625556da275f0a3f58201e43a372397c8a1cac
// Projected checks: object fields, scalar/list types, declared enums and applicability shapes.
// Owner evaluator still checks identities, graph/reference closure, tightening,
// conditional nonempty configuration, external vocabularies and evidence.
#CorpusPlanning: {
    schema_version: 1
    applicability: {state: "configured", reason?: #Text} | {state: "not-applicable", reason: #Text}
    artifact_bindings: {...}
    capability_scale: [...{rank: int & >=0, value: #Text, predicate: #Text, target_eligible: bool}]
    pass_authority: {...}
    if applicability.state == "configured" {
        artifact_bindings: {global_map: #Text, capability_matrix: #Text, gap_register: #Text}
        capability_scale: [_, ..._]
        pass_authority: {role_id: #Text, decision_scope_id: #Text}
    }
    if applicability.state == "not-applicable" {
        artifact_bindings: close({})
        capability_scale: []
        pass_authority: close({})
    }
}
