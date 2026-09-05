package profile

import "list"

// K00/07 owns the priority extension. A missing proposal is not a no-grants
// decision. Prose predicates remain decisions of the semantic authority.
#Grant: {mode: "none"} | {mode: "configured", predicate: #Text, protected_capability: #Text}
#QuotaRecord: {priority: "P0" | "P1", maximum_share: number & >=0 & <=1, rationale: #Text}
#QuotaItems: [] | [#QuotaRecord & {priority: "P0"}, #QuotaRecord & {priority: "P1"}] | [#QuotaRecord & {priority: "P1"}, #QuotaRecord & {priority: "P0"}]
#PriorityFields: {
	profile_owned_grant_criteria?: {P0: #Grant, P1: #Grant}
	priority_quota?: #Registration & {items: #QuotaItems}
}
#Priority: #PriorityFields & {profile_owned_grant_criteria: _, priority_quota: _}

// K00/19 owns role binding identity, not authentication or actor approval.
#RolesFields: {
	process_roles?: {proposer: #Text, gatekeeper: #Text, executor: #Text, stopper: #Text}
	knowledge_host?: {host: #Text, ui: #Text}
	metric_traceability_roles?: #Applicability & {items: [...{role_id: #Text, binding: #Text}]}
	extension_roles?: #Registration & {items: [...{role_id: #StableId, actor: #Text, responsibility: #Text}]}
}
#Roles: #RolesFields & {process_roles: _, knowledge_host: _, metric_traceability_roles: _, extension_roles: _}

// K00/02+K00/12 owns permitted extension registration relationships. Tool
// capability identities are resolved against their own owner, not defined here.
#RoutingFields: {
	supplemental_routes?: #Registration & {items: [...{route_id: #Text, kernel_route_id: #Text, read_set_ref: #Text}]}
	additional_l_tier_triggers?: #Registration & {items: [...{predicate: #Text, rationale: #Text}]}
	specialized_audit_invariants?: #Registration & {items: [...{judgment_item_id: #Text, applicability: #Text, verification: #Text, evidence_reuse: #Text}]}
	batch_review_requirements?: #Registration & {items: [...{judgment_item_id: #StableId, target_selector: "each-manifest-page" | "batch", trigger: "before-merge-ready", producer_kind: "manual-attestation", receipt_schema: "page-batch-judgment-v2", pass_authority_role_id: #Text}]}
	extension_gates?: #Registration & {items: [...{
		gate_id: #ProfileGateId
		owner_ref: #Text
		blocked_transition: #StableId
		pass_authority_role_id: #Text
		applicability: #Text
		vocabulary_field?: #FieldId
		completion_values: [...#VocabularyValue] & list.UniqueItems
		judgment_item_id: #StableId
		producer_kind: "deterministic" | "manual-attestation"
		producer_capability: #Text
		receipt_schema: #Text
		consumer_capability: #Text
	}]}
}
#Routing: #RoutingFields & {supplemental_routes: _, additional_l_tier_triggers: _, specialized_audit_invariants: _, batch_review_requirements: _, extension_gates: _}
