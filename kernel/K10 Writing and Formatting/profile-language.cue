package profile

// K10 owns permitted language/naming choices, not a Markdown form's labels.
#LanguageFields: {
	language_routing?: {
		body_language: #Text
		secondary_language: {mode: "none"} | {mode: "configured", rule: #Text}
		proper_names: #Text
		external_names: #Text
		machine_identifiers: #Text
	}
	canonical_naming?: {folders: #Text, pages: #Text, term_notes: #Text, image_assets: #Text}
	terminology_and_display?: {aliases: #Text, headings: #Text, abbreviations: #Text, display_order: #Text, file_annotations: #Text}
	content_length_unit?: "words" | "characters"
	scoped_anti_pattern_extensions?: #Registration & {items: [...{rule_id: #Text, predicate: #Text, predicate_owner: #Text}]}
	formatting_migration_invalidations?: #Registration & {items: [...{change_id: #Text, invalidated_dimensions: [...#Text], exception: #Text, rule_owner: #Text}]}
}
#Language: #LanguageFields & {language_routing: _, canonical_naming: _, terminology_and_display: _, content_length_unit: _, scoped_anti_pattern_extensions: _, formatting_migration_invalidations: _}
