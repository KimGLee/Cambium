"""One minimal typed Profile answer set for local contract fixtures.

The data below are synthetic answers, not a schema or semantic authority.
Every package is encoded by the production codec and validated against the
current owner inputs; no Markdown form or runtime lifecycle is reconstructed.
"""

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile

import Tools.governance.profile.profile_codec as profile_codec
import Tools.governance.profile.profile_contract as profile_contract
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.platform.common.kblib as kblib
from Tools.tests.support.profile_load_fixture import (
    install_current_profile_load_inputs,
)


REPOSITORY = Path(__file__).resolve().parents[3]
SYNTHETIC_PROFILE = REPOSITORY / "Tools/tests/fixtures/synthetic_profile"
MANIFEST_NAME = profile_layout_contract.PROFILE_MANIFEST_NAME


def _none():
    return {"mode": "none", "items": []}


def _inactive(reason):
    return {"mode": "not-applicable", "reason": reason, "items": []}


def minimal_profile_document(profile_id="test-profile"):
    """Return independent, complete synthetic answers for one Profile ID."""
    prefix = "profiles/%s/" % profile_id
    manifest = prefix + MANIFEST_NAME
    residual = prefix + "policies/residual-disposition.md#Residual Disposition"
    scope = {
        "goal": {"statement": "Keep synthetic knowledge pages usable.",
                 "readers": ["Fixture maintainer"]},
        "content_priority_factors": [
            {"rank": 1, "factor": "Pages required by the bounded fixture task."}],
        "excluded_scope": _none(),
        "logical_architecture": [{
            "layer_id": "L-TOPICS", "directories": ["Topics"],
            "responsibility": "Own the synthetic knowledge pages exercised by runtime tests."}],
        "knowledge_spine": {
            "organizing_logic": "One canonical page per synthetic topic.",
            "locator": "The page title identifies its synthetic topic."},
        "placement_layer_registrations": [
            {"role_id": role, "binding": {"kind": kind, "layer_id": "L-TOPICS"}}
            for role, kind in (
                ("Shared Foundation Layer", "layer"),
                ("Production Systems Layer", "fallback"),
                ("Cross-domain Concepts Layer", "fallback"),
                ("Case Study Layer", "fallback"),
                ("Source Note Layer", "fallback"),
                ("Research Synthesis Layer", "fallback"))] + [{
                    "role_id": "Expression Layer Predicate",
                    "binding": {"kind": "predicate",
                                "predicate": "A registered reader-facing artifact is an Expression page, not a canonical synthetic topic."}}],
        "new_page_placement_rule": [{
            "predicate": "Every synthetic canonical page.",
            "layer_id": "L-TOPICS", "fallback": True}],
        "terminology_structure": [{
            "term_class": "Synthetic terms", "layer_id": "L-TOPICS",
            "boundary": "Only terms needed by the fixture pages."}],
        "foundation_depth_requirements": [{
            "page_class": "Synthetic knowledge page",
            "predicate": "A synthetic page has a title and one non-empty body paragraph."}],
        "production_system_reasoning_applicability":
            _inactive("No production system is governed by this fixture."),
        "representative_sample_plan":
            _inactive("The fixture exercises a bounded synthetic page."),
        "dependency_ordered_build_sequence":
            _inactive("The fixture does not prescribe a corpus build sequence."),
    }
    slots = {
        "profile-scope": scope,
        "corpus-planning": {
            "schema_version": 1,
            "applicability": {"state": "not-applicable",
                "reason": "Synthetic runtime fixture has no corpus-wide planning artifacts."},
            "artifact_bindings": {}, "capability_scale": [], "pass_authority": {}},
        "structure-registry": {
            "schema_version": 2,
            "applicability": {"state": "not-applicable",
                "reason": "Synthetic single-page fixture corpus; nothing passes the K01/05 module admission test."},
            "units": [], "support_layers": []},
        "metadata-contract": {
            "schema_version": 1, "applicability": {"state": "kernel-defaults"},
            "applicability_differences": [], "extension_fields": [],
            "relationship_extensions": [], "section_roles": []},
        "vocabulary-extensions": {
            "schema_version": 1, "frontmatter_extensions": {"fields": []},
            "fields": {}, "volatility_defaults": {"general": "slow"}},
        "rendering-contract": {"schema_version": 1, "registration": "none", "rules": []},
        "priority-rubric": {
            "profile_owned_grant_criteria": {"P0": {"mode": "none"}, "P1": {"mode": "none"}},
            "priority_quota": _none()},
        "language-contract": {
            "language_routing": {
                "body_language": "English", "secondary_language": {"mode": "none"},
                "proper_names": "Preserve official names.",
                "external_names": "Preserve external source names.",
                "machine_identifiers": "Preserve exact machine identifiers."},
            "canonical_naming": {
                "folders": "English Title Case with spaces.",
                "pages": "English Title Case with spaces.",
                "term_notes": "The canonical term.",
                "image_assets": "Lowercase kebab-case."},
            "terminology_and_display": {
                "aliases": "Include accepted synonyms.",
                "headings": "Use stable descriptive headings.",
                "abbreviations": "Expand abbreviations at first use.",
                "display_order": "Explain the term before using its abbreviation.",
                "file_annotations": "File names contain only the canonical title."},
            "content_length_unit": "words",
            "scoped_anti_pattern_extensions": _none(),
            "formatting_migration_invalidations": _none()},
        "expression-layer-entry": {
            "registered_artifacts": _none(), "artifact_contracts": []},
        "source-policy": {
            "source_authority": [{
                "rank": 1, "source_id": "fixture-observation",
                "location": "The synthetic test input.",
                "claim_class": "Claims about the synthetic fixture.",
                "version_policy": "Bind the exact fixture input version."}],
            "verification_entry_points": [{
                "claim_class": "Claims about the synthetic fixture.",
                "source_id": "fixture-observation",
                "verification": "Compare with the declared fixture input.",
                "freshness": "Current test invocation."}],
            "staleness_triggers": [{
                "event": "The fixture input changes.",
                "affected_scope": "Claims derived from that input."}],
            "domain_comparison_rules": _none(), "provenance_extensions": _none()},
        "role-registry": {
            "process_roles": {"proposer": "Agent", "gatekeeper": "Maintainer",
                              "executor": "Agent", "stopper": "Maintainer"},
            "knowledge_host": {"host": "Markdown tree", "ui": "Headless"},
            "metric_traceability_roles":
                _inactive("This fixture does not register a metric workflow."),
            "extension_roles": _none()},
        "audit-dimension-registry": {
            "extension_dimensions": _none(),
            "judgment_items": [{
                "item_id": profile_id + "-foundation-depth",
                "dimension_id": "content_and_depth", "audit_layer": "Single Note Review",
                "audit_object": "One synthetic page satisfies the fixture depth predicate.",
                "evidence_role": "emits",
                "predicate_owner": manifest + "#slots.profile-scope.foundation_depth_requirements",
            }, {
                "item_id": profile_id + "-residual-disposition",
                "dimension_id": "coverage_and_integration", "audit_layer": "Batch Review",
                "audit_object": "Every synthetic residual candidate has a disposition.",
                "evidence_role": "emits", "predicate_owner": residual,
            }],
            "residual_disposition": {"body_ref": residual}},
        "registered-scan-registry": {"scan_registrations": [{
            "scan_id": profile_id + "-residuals",
            "activation_role": "K12/09 item 6 — residual-content scan",
            "scope": "Run once from the repository root.",
            "verifier_capability": "residual-content-scan-v1",
            "configuration_ref": prefix + "scan-configs/residual-scan.yaml",
            "candidate_predicate": "A synthetic scratch heading outside the accepted root is a candidate.",
            "judgment_item_id": profile_id + "-residual-disposition",
        }]},
        "escalation-policy": {"escalation_triggers": _none()},
        "routing-and-gate-registry": {
            name: _none() for name in (
                "supplemental_routes", "additional_l_tier_triggers",
                "specialized_audit_invariants", "batch_review_requirements",
                "extension_gates")},
    }
    return {"schema_version": 1, "profile_id": profile_id,
            "execution_default_overrides": {}, "slots": slots}


def write_profile_document(profile, document):
    """Encode one explicitly supplied mutable answer object; do not fill it."""
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    manifest = profile / MANIFEST_NAME
    manifest.write_bytes(profile_codec.dumps_profile(document))
    return manifest


def install_profile_package(profile, profile_id="test-profile", *, document=None):
    """Install the minimal typed package and its real independent support files."""
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    for source in sorted(SYNTHETIC_PROFILE.rglob("*")):
        if source.is_file():
            target = profile / source.relative_to(SYNTHETIC_PROFILE)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return write_profile_document(
        profile, minimal_profile_document(profile_id) if document is None else document)


class CurrentProfileContractFixture:
    """One current contract root, without adoption or a runtime lifecycle."""

    def __init__(self, owner):
        self.temporary = tempfile.TemporaryDirectory()
        owner.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "repo"
        self.root.mkdir()
        install_current_profile_load_inputs(self.root)
        self.profile = self.root / "profiles/test-profile"
        self.document = minimal_profile_document()
        self.manifest = install_profile_package(self.profile, document=self.document)
        self.scan_config = self.profile / "scan-configs/residual-scan.yaml"
        self.predicate = self.profile / "policies/synthetic-predicate.md"
        self.residual_policy = self.profile / "policies/residual-disposition.md"
        self.operation_capabilities = self.root / "Tools/operation-capabilities.yaml"

    def slot(self, name):
        return self.document["slots"][profile_contract.slot_id(name)]

    def save(self):
        return write_profile_document(self.profile, self.document)

    def load(self, sentinel="TODO(profile)"):
        self.save()
        return profile_contract.load_profile_contract(
            self.root, self.manifest, sentinel=sentinel)

    def checks(self, contract=None):
        contract = contract or self.load()
        return {diagnostic.check for diagnostic in contract.diagnostics}

    def install_profile_load_inputs(self):
        return install_current_profile_load_inputs(self.root)

    @staticmethod
    def replace(path, old, new):
        """Mutate a real owner/support file, never a synthesized slot carrier."""
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise AssertionError("fixture anchor is absent: %r" % old)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def enable_gate_contract(self, *, field_id="expression_status",
                             values=("pending", "ready"),
                             role="Expression Status Axis"):
        field = {"values": list(values)}
        if role is not None:
            field["role"] = role
        self.document["slots"]["vocabulary-extensions"] = {
            "schema_version": 1, "frontmatter_extensions": {"fields": []},
            "fields": {field_id: field}, "volatility_defaults": {"general": "slow"}}
        self.document["slots"]["metadata-contract"] = {
            "schema_version": 1, "applicability": {"state": "configured"},
            "applicability_differences": [],
            "extension_fields": [{
                "field": field_id, "mode": "optional", "shape": "nonempty-string",
                "owner": "profiles/test-profile/profile.toml#slots.expression-layer-entry"}],
            "relationship_extensions": [], "section_roles": []}
        custom_tool = self.root / "Tools/custom_profile_capability.py"
        custom_tool.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        capabilities = [{
            "capability_id": capability_id, "kind": kind,
            "capability_version": "1.0.0",
            "implementation_owner": "Tools/custom_profile_capability.py",
            "writers": [], "checkers": [], "consumers": [],
            "operations": ([{"operation": operation}] if operation else []),
        } for capability_id, kind, operation in (
            ("project-page-state-v2", "writer", "profile-extension-enum-owner-projection-v1"),
            ("typed-metadata-transition-v1", "consumer", "typed-field-metadata-transition"),
            ("manual-attestation-v1", "producer", None),
            ("registered-scan-v1", "producer", None),
            ("manual-gate-attestation-v1", "receipt-schema", None),
            ("deterministic-gate-result-v1", "receipt-schema", None),
        )]
        self.operation_capabilities.write_text(kblib.canonical_yaml({
            "schema_version": 3, "capabilities": capabilities}), encoding="utf-8")
        self.save()

    def gate_row(self, *, gate_id="P:test-profile:expression-ready",
                 owner="profiles/test-profile/policies/synthetic-predicate.md#Synthetic Predicate",
                 transition="expression-ready", role="stopper",
                 applicability="Expression is ready.",
                 field="expression_status", completions=("ready",),
                 judgment="test-profile-foundation-depth",
                 producer_kind="manual-attestation",
                 producer_capability="manual-attestation-v1",
                 receipt_schema="manual-gate-attestation-v1",
                 consumer_capability="typed-metadata-transition-v1"):
        row = {
            "gate_id": gate_id, "owner_ref": owner,
            "blocked_transition": transition, "pass_authority_role_id": role,
            "applicability": applicability, "completion_values": list(completions),
            "judgment_item_id": judgment, "producer_kind": producer_kind,
            "producer_capability": producer_capability, "receipt_schema": receipt_schema,
            "consumer_capability": consumer_capability}
        if field is not None:
            row["vocabulary_field"] = field
        return row

    def configure_gate(self, **overrides):
        self.slot("routing-and-gate-registry")["extension_gates"] = {
            "mode": "configured", "items": [self.gate_row(**overrides)]}
        self.save()

    def configure_extension_dimensions(self, rows):
        """Set typed dimension records; each target is an explicit list item."""
        rows = deepcopy(list(rows))
        if any(not isinstance(row, dict) for row in rows):
            raise TypeError("extension dimensions require typed record dictionaries")
        self.slot("audit-dimension-registry")["extension_dimensions"] = {
            "mode": "configured" if rows else "none", "items": rows}
        self.save()

    def expression_artifact_row(
            self, *, artifact_id="test-expression-guide",
            artifact_type="cheat-sheet", label="Expression Guide",
            entry_point="Expression/Guide.md",
            dependency_map="Expression/Overview.md", binding_fields=(),
            revalidation="Revalidate when a bound canonical owner changes.",
            contract_reference=(
                "profiles/test-profile/policies/synthetic-predicate.md#Synthetic Predicate"),
            readiness=None):
        row = {
            "artifact_id": artifact_id, "artifact_type": artifact_type,
            "label": label, "entry_point": entry_point,
            "metadata_fields": list(binding_fields),
            "revalidation_trigger": revalidation, "contract_ref": contract_reference}
        if dependency_map is not None:
            row["dependency_map"] = dependency_map
        if readiness is not None:
            row["readiness_field"] = readiness
        return row

    def configure_expression_artifacts(self, rows):
        """Set typed artifacts and their matching independently owned bodies."""
        rows = deepcopy(list(rows))
        if any(not isinstance(row, dict) for row in rows):
            raise TypeError("expression artifacts require typed record dictionaries")
        slot = self.slot("expression-layer-entry")
        slot["registered_artifacts"] = {
            "mode": "configured" if rows else "none", "items": rows}
        references = sorted({row["contract_ref"] for row in rows})
        slot["artifact_contracts"] = [
            {"contract_id": "fixture-contract-%d" % index, "body_ref": reference}
            for index, reference in enumerate(references, 1)]
        self.save()


__all__ = [
    "CurrentProfileContractFixture", "install_profile_package",
    "minimal_profile_document", "write_profile_document",
]
