package profile

import "list"

// K01/01-K01/04 owns these instance extension meanings. No file layout or
// Markdown syntax is part of this contract. Array order preserves precedence.
#ScopeFields: {
	goal?: {statement: #Text, readers: [#Text, ...#Text]}
	content_priority_factors?: [...{rank: int & >=1, factor: #Text}]
	excluded_scope?: #Registration & {items: [...{content: #Text, handling: #Text}]}
	logical_architecture?: [...{layer_id: #Text, directories: [#Text, ...#Text], responsibility: #Text}]
	knowledge_spine?: {organizing_logic: #Text, locator: #Text}
	placement_layer_registrations?: [...{
		role_id: "Shared Foundation Layer" | "Production Systems Layer" | "Cross-domain Concepts Layer" | "Expression Layer Predicate" | "Case Study Layer" | "Source Note Layer" | "Research Synthesis Layer"
		binding: {kind: "layer" | "fallback", layer_id: #Text} | {kind: "predicate", predicate: #Text}
	}]
	new_page_placement_rule?: [...{predicate: #Text, layer_id: #Text, fallback: bool}]
	terminology_structure?: [...{term_class: #Text, layer_id: #Text, boundary: #Text}]
	foundation_depth_requirements?: [...{page_class: #Text, predicate: #Text}]
	production_system_reasoning_applicability?: #Applicability & {items: [...{predicate: #Text}]}
	representative_sample_plan?: #Applicability & {items: [...{note_type: #Text, selection_predicate: #Text}]}
	dependency_ordered_build_sequence?: #Applicability & {items: [...{stage: #Text, depends_on: [...#Text], output: #Text}]}
}
#Scope: #ScopeFields & {
	goal: _
	content_priority_factors: _
	excluded_scope: _
	logical_architecture: _
	knowledge_spine: _
	placement_layer_registrations: _
	// The former fixed-key rows required every role exactly once. Array order
	// is presentation only; the role set and its bindings remain complete.
	placement_layer_registrations: list.MinItems(7) & list.MaxItems(7)
	_unique_placement_roles: true & list.UniqueItems([for item in placement_layer_registrations {item.role_id}])
	new_page_placement_rule: _
	terminology_structure: _
	foundation_depth_requirements: _
	production_system_reasoning_applicability: _
	representative_sample_plan: _
	dependency_ordered_build_sequence: _
}
