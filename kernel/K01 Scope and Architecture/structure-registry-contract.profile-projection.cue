package profile

// GENERATED: do not edit this projection.
// Semantic owner: K01/05+K01/06
// Source: kernel/K01 Scope and Architecture/structure-registry-contract.yaml
// Source SHA256: 0e4c3cc87bb55b43ca7c3bcbe36ed53b09e9b4b102e65f285d33606ebd8b9ece
// Projected checks: object fields, scalar/list types, declared enums and applicability shapes.
// Owner evaluator still checks identities, graph/reference closure, tightening,
// conditional nonempty configuration, external vocabularies and evidence.
#StructureRole: ({mode: "embedded", path: #Text, heading: #Text} | {mode: "standalone", path: #Text} | {mode: "derived", generator_capability: #Text & =~"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", inputs_owner: #Text, path?: #Text, heading?: #Text} | {mode: "not-applicable", reason: #Text})
#StructureUnit: {id: #Text, kind: "domain" | "module", parent?: #Text, root: #Text, entry: {path: #Text, expected_type?: #Text}, global_map_entry?: #Text, roles: {sequence: #StructureRole, coverage: #StructureRole, quick_reference: #StructureRole, expression: #StructureRole}
if kind == "domain" {parent?: _|_}
if kind == "module" {parent: #Text}
}
#StructureSupport: {layer_id: #Text, role: "cases" | "sources" | "synthesis" | "expression", root: #Text, entry: {path: #Text, expected_type?: #Text}, layout: "flat" | "grouped", taxonomy?: {axis: #Text, page_field: #Text, classes: [{class: #Text, directory: #Text}, ...{class: #Text, directory: #Text}]}, coverage: #StructureRole, global_map_entry?: #Text, bindings: {...}
if layout == "flat" {taxonomy?: _|_}
if layout == "grouped" {taxonomy: {axis: #Text, page_field: #Text, classes: [{class: #Text, directory: #Text}, ...{class: #Text, directory: #Text}]}}
if role == "cases" { bindings: {evidence_binding_owner: #Text} }
if role == "sources" { bindings: {authority_taxonomy_ref: #Text, intake_policy_ref: #Text, freshness_policy_ref: #Text, index_mode: "derived" | "none"} }
if role == "synthesis" { bindings: {question_identity_field: #Text, promotion_policy_ref: #Text} }
if role == "expression" { bindings: {artifact_registry_ref: #Text, preparation_route_ref: #Text, readiness_projection: #StructureRole} }
}
#StructureRegistry: {
    schema_version: 2
    applicability: {state: "configured"} | {state: "not-applicable", reason: #Text}
    units: [...#StructureUnit]
    support_layers: [...#StructureSupport]
    if applicability.state == "configured" { units: [_, ..._] }
    if applicability.state == "not-applicable" { units: [], support_layers: [] }
}
