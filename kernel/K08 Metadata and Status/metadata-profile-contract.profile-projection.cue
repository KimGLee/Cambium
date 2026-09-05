package profile

// GENERATED: do not edit this projection.
// Semantic owner: K08/06+K08/08+K08/09
// Source: kernel/K08 Metadata and Status/metadata-profile-contract.yaml
// Source SHA256: 4f9acc7198a2298738c229d739583a8074e176d68a26543065e1a3ce97a98ef5
// Projected checks: object fields, scalar/list types, declared enums and applicability shapes.
// Owner evaluator still checks identities, graph/reference closure, tightening,
// conditional nonempty configuration, external vocabularies and evidence.
import "struct"
#MetadataClause: {field: #Text, "in": [_, ..._]} | {field: #Text, absent: true}
#MetadataCondition: {all?: [#MetadataClause, ...#MetadataClause], any?: [#MetadataClause, ...#MetadataClause]} & struct.MinFields(1)
#MetadataApplicabilityDifference: {field: #Text, mode: "required" | "conditional", condition?: #MetadataCondition, note?: #Text
if mode == "conditional" {condition: #MetadataCondition}
}
#MetadataExtensionField: {field: #Text, mode: "required" | "conditional" | "optional" | "derived" | "projection" | "user-owned" | "forbidden", shape: "nonempty-string" | "date" | "url" | "path" | "list-of-strings" | "list-of-paths" | "delegated", owner: #Text, condition?: #MetadataCondition
if mode == "conditional" {condition: #MetadataCondition}
}
#MetadataRelationshipExtension: {field: #Text, mode: "required" | "conditional" | "optional" | "derived" | "projection" | "user-owned" | "forbidden", direction: #Text, target: #Text | [#Text, ...#Text], shape: "nonempty-string" | "date" | "url" | "path" | "list-of-strings" | "list-of-paths" | "delegated", owner: #Text, condition?: #MetadataCondition
if mode == "conditional" {condition: #MetadataCondition}
}
#MetadataSectionRole: {role: "sources" | "related", titles: [#Text, ...#Text], owner: #Text, aliases?: [...#Text]}
#MetadataContract: {schema_version: 1, applicability: {state: "kernel-defaults" | "configured"}, applicability_differences: [...#MetadataApplicabilityDifference], extension_fields: [...#MetadataExtensionField], relationship_extensions: [...#MetadataRelationshipExtension], section_roles: [...#MetadataSectionRole], boundary_projection?: {labels: {preamble?: #Text, owns?: #Text, excludes?: #Text, owner?: #Text, goals?: #Text, non_goals?: #Text}}
if applicability.state == "kernel-defaults" {applicability_differences: [], extension_fields: [], relationship_extensions: [], section_roles: [], boundary_projection?: _|_}
}
