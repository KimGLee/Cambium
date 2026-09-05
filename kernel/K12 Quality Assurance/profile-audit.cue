package profile

// K12 owns audit dimensions, judgment roles and scan-to-judgment registration.
// Filesystem evidence, registered capabilities and references are linked by Tool.
#AuditFields: {
	extension_dimensions?: #Registration & {items: [...{dimension_id: #FieldId, targets: #AuditTargets, meaning: #Text}]}
	judgment_items?: [...{item_id: #StableId, dimension_id: #FieldId, audit_layer: #Text, audit_object: #Text, evidence_role: #AuditEvidenceRole, predicate_owner: #Text}]
	residual_disposition?: {body_ref: #Text}
}
#Audit: #AuditFields & {extension_dimensions: _, judgment_items: _, residual_disposition: _}
#ScansFields: {
	scan_registrations?: [...{scan_id: #StableId, activation_role: #Text, scope: #Text, verifier_capability: #Text, configuration_ref?: #Text, candidate_predicate: #Text, judgment_item_id: #StableId}]
}
#Scans: #ScansFields & {scan_registrations: _}
