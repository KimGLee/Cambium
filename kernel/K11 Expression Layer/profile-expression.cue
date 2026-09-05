package profile

import "list"

// K11 owns the expression extension floor. Body references identify one
// Profile policy owner; they neither inline shared rules nor prove readiness.
#ExpressionFields: {
	registered_artifacts?: #Registration & {items: [...{
		artifact_id: #StableId
		artifact_type: #Text
		label: #Text
		entry_point: #Text
		dependency_map?: #Text
		metadata_fields: [...#FieldId] & list.UniqueItems
		revalidation_trigger: #Text
		contract_ref: #Text
		readiness_field?: #FieldId
	}]}
	artifact_contracts?: [...{contract_id: #Text, body_ref: #Text}]
}
#Expression: #ExpressionFields & {registered_artifacts: _, artifact_contracts: _}
