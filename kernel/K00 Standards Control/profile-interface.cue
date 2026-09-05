package profile

// K00/19 composes independently owned extension contracts. These definitions
// carry governance data only; TOML, directories, transports and UI belong to Tool.
#Text:            string & =~"[^\\s\\p{Z}]"
#FieldId:         string & =~"^[a-z][a-z0-9_]*$"
#StableId:        string & =~"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"
#VocabularyValue: string & =~"^[a-z0-9][a-z0-9_-]*$"
#ProfileGateId:   string & =~"^P:[a-z0-9][a-z0-9_-]*:[a-z][a-z0-9]*(-[a-z0-9]+)*$"
#Registration: {mode: "none", items: []} | {mode: "configured", items: [_, ...]}
#Applicability: {mode: "not-applicable", reason: #Text, items: []} | {mode: "configured", items: [_, ...]}

// The semantic slot-ID/value relation has no document root, serialization
// version, directory identity, or validation-mode entry point.
#SlotFields: {
	"profile-scope"?:             #ScopeFields
	"corpus-planning"?:           #CorpusPlanning
	"structure-registry"?:        #StructureRegistry
	"metadata-contract"?:         #MetadataContract
	"priority-rubric"?:           #PriorityFields
	"vocabulary-extensions"?:     #VocabularyExtensions
	"language-contract"?:         #LanguageFields
	"expression-layer-entry"?:    #ExpressionFields
	"rendering-contract"?:        #RenderingContract
	"source-policy"?:             #SourcesFields
	"role-registry"?:             #RolesFields
	"audit-dimension-registry"?:  #AuditFields
	"registered-scan-registry"?:  #ScansFields
	"routing-and-gate-registry"?: #RoutingFields
	"escalation-policy"?:         #EscalationFields
}
#ProfileSlots: #SlotFields & {
	"profile-scope":             #Scope
	"corpus-planning":           #CorpusPlanning
	"structure-registry":        #StructureRegistry
	"metadata-contract":         #MetadataContract
	"priority-rubric":           #Priority
	"vocabulary-extensions":     #VocabularyExtensions
	"language-contract":         #Language
	"expression-layer-entry":    #Expression
	"rendering-contract":        #RenderingContract
	"source-policy":             #Sources
	"role-registry":             #Roles
	"audit-dimension-registry":  #Audit
	"registered-scan-registry":  #Scans
	"routing-and-gate-registry": #Routing
	"escalation-policy":         #Escalation
}
