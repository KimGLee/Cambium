"""Minimal typed Profile inputs and real Corpus Planning artifact bytes.

These are example values, not a second field registry. Profile values stay
dictionaries; only the separate YAML planning artifacts below use text.
"""

CONFIGURED_SLOT = {
    "schema_version": 1,
    "applicability": {"state": "configured"},
    "artifact_bindings": {
        "global_map": "planning/global-map.yaml",
        "capability_matrix": "planning/capability-matrix.yaml",
        "gap_register": "planning/gap-register.yaml"},
    "capability_scale": [
        {"rank": 0, "value": "Missing", "predicate": "No canonical owner exists.",
         "target_eligible": False},
        {"rank": 1, "value": "Core",
         "predicate": "Core explanation has accepted evidence.",
         "target_eligible": True},
        {"rank": 2, "value": "Defensible",
         "predicate": "Evidence can withstand challenge.",
         "target_eligible": True}],
    "pass_authority": {
        "role_id": "stopper", "decision_scope_id": "corpus-plan-semantic-acceptance"},
}

INACTIVE_SLOT = {
    "schema_version": 1,
    "applicability": {
        "state": "not-applicable",
        "reason": "this bounded task neither needs nor changes corpus-wide planning artifacts"},
    "artifact_bindings": {}, "capability_scale": [], "pass_authority": {},
}

SCOPE = {"logical_architecture": [{
    "layer_id": "L1", "directories": ["Topics"],
    "responsibility": "Canonical topic pages."}]}

ROLES = {"process_roles": {"stopper": "Human authority"}}

MANIFEST = {"schema_version": 1, "profile_id": "test-profile", "slots": {
    "profile-scope": SCOPE, "role-registry": ROLES,
    "corpus-planning": CONFIGURED_SLOT,
}}

GLOBAL_MAP = """schema_version: 1
entries:
  - entry_id: E-A
    layer_id: L1
    canonical_markdown_path: Topics/A.md
    single_responsibility: Own topic A.
  - entry_id: E-B
    layer_id: L1
    canonical_markdown_path: Topics/B.md
    single_responsibility: Own topic B.
typed_dependencies:
  - edge_id: D-1
    upstream_entry_id: E-A
    downstream_entry_id: E-B
    relation_type: prerequisite-for
"""

MATRIX = """schema_version: 1
capabilities:
  - capability_id: C-1
    capability: Explain the complete fixture topic path.
    priority: P0
    map_entry_ids: [E-A, E-B]
    canonical_markdown_paths: [Topics/A.md, Topics/B.md]
    current_level: Core
    target_level: Defensible
    evidence_paths: [Topics/A.md]
    gap_ids: [G-1]
"""

GAPS = """schema_version: 1
gaps:
  - gap_id: G-1
    gap_statement: Defensible support for the complete fixture topic path is missing.
    capability_ids: [C-1]
    candidate_owner_entry_id: E-B
    status: promoted
    close_condition: Topics/B.md contains accepted evidence for the complete path.
    evidence_paths: [Topics/A.md]
    promoted_coverage_path: Topics/B.md
    rationale: Coverage has admitted the missing defensibility work.
"""


__all__ = [
    "CONFIGURED_SLOT", "GAPS", "GLOBAL_MAP", "INACTIVE_SLOT", "MANIFEST",
    "MATRIX", "ROLES", "SCOPE",
]
