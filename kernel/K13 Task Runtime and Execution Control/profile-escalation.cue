package profile

// K13/17 owns escalation choices. References bind roles; they do not grant
// authentication or let the evaluator interpret arbitrary commands.
#EscalationFields: {
	escalation_triggers?: #Registration & {items: [...{trigger_id: #Text, condition: #Text, check_kind: "machine-checkable" | "review-checkable", deciding_role_id: #Text, resume_condition: #Text}]}
}
#Escalation: #EscalationFields & {escalation_triggers: _}
