package profile

// K07/01-K07/06 owns the source extension boundary. Source text and freshness
// policies are instance decisions; parsing a string never executes its prose.
#SourcesFields: {
	source_authority?: [...{rank: int & >=1, source_id: #Text, location: #Text, claim_class: #Text, version_policy: #Text}]
	verification_entry_points?: [...{claim_class: #Text, source_id: #Text, verification: #Text, freshness: #Text}]
	staleness_triggers?: [...{event: #Text, affected_scope: #Text}]
	domain_comparison_rules?: #Registration & {items: [...{condition: #Text, rule: #Text}]}
	provenance_extensions?: #Registration & {items: [...{trigger: #Text, requirement: #Text, target_ref: #Text}]}
}
#Sources: #SourcesFields & {source_authority: _, verification_entry_points: _, staleness_triggers: _, domain_comparison_rules: _, provenance_extensions: _}
