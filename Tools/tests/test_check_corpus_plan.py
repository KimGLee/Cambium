import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS))

import check_corpus_plan
import kblib
from Tools.tests.profile_fixture import install_loadable_profile


MANIFEST = """# Test Profile

## Profile Identity

- `profile_id`: `test-profile`

## Implemented Slots

- `Profile Scope`: `scope-and-architecture.md`
- `Corpus Planning`: `corpus-planning.yaml`
- `Role Registry`: `roles.md`
"""

SCOPE = """# Scope And Architecture

## Logical Architecture

| Stable Layer ID | Repository-relative directories | Single layer responsibility |
|---|---|---|
| `L1` | `Topics` | Canonical topic pages. |
"""

ROLES = """# Role Registry

## Process Roles

| Kernel role | Bound actor or system ID/name |
|---|---|
| `stopper` | Human authority |
"""

CONFIGURED_SLOT = """schema_version: 1
applicability:
  state: configured
  reason: null
artifact_bindings:
  global_map: planning/global-map.yaml
  capability_matrix: planning/capability-matrix.yaml
  gap_register: planning/gap-register.yaml
capability_scale:
  - rank: 0
    value: Missing
    predicate: No canonical owner exists.
    target_eligible: false
  - rank: 1
    value: Core
    predicate: Core explanation has accepted evidence.
    target_eligible: true
  - rank: 2
    value: Defensible
    predicate: Evidence can withstand challenge.
    target_eligible: true
pass_authority:
  role_id: stopper
  decision_scope_id: corpus-plan-semantic-acceptance
"""

INACTIVE_SLOT = """schema_version: 1
applicability:
  state: not-applicable
  reason: this bounded task neither needs nor changes corpus-wide planning artifacts
artifact_bindings:
  global_map: null
  capability_matrix: null
  gap_register: null
capability_scale: []
pass_authority:
  role_id: null
  decision_scope_id: null
"""

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


class CorpusPlanFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        profile = install_loadable_profile(self.root)
        manifest = profile / "profile.md"
        manifest.write_text(
            manifest.read_text(encoding="utf-8")
            .replace("- `Profile Scope`: `slots.md`",
                     "- `Profile Scope`: `scope-and-architecture.md`")
            .replace("- `Role Registry`: `slots.md`",
                     "- `Role Registry`: `roles.md`"),
            encoding="utf-8")
        (profile / "scope-and-architecture.md").write_text(
            SCOPE, encoding="utf-8")
        (profile / "roles.md").write_text(ROLES, encoding="utf-8")
        (profile / "corpus-planning.yaml").write_text(
            CONFIGURED_SLOT, encoding="utf-8")
        planning = self.root / "planning"
        planning.mkdir()
        (planning / "global-map.yaml").write_text(GLOBAL_MAP, encoding="utf-8")
        (planning / "capability-matrix.yaml").write_text(
            MATRIX, encoding="utf-8")
        (planning / "gap-register.yaml").write_text(GAPS, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def profile(self):
        return self.root / "profiles/test-profile"

    @property
    def slot(self):
        return self.profile / "corpus-planning.yaml"

    @property
    def scope(self):
        return self.profile / "scope-and-architecture.md"

    @property
    def global_map(self):
        return self.root / "planning/global-map.yaml"

    @property
    def matrix(self):
        return self.root / "planning/capability-matrix.yaml"

    @property
    def gaps(self):
        return self.root / "planning/gap-register.yaml"

    def validate(self, profile=None):
        return check_corpus_plan.validate_corpus_plan(
            self.root, profile=profile)

    def assert_error(self, result, fragment):
        messages = [error["details"] for error in result["errors"]]
        self.assertTrue(any(fragment in message for message in messages),
                        messages)

    def replace(self, path, old, new):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def load_yaml(self, path):
        return kblib.load_yaml_file(path)

    def write_yaml(self, path, value):
        path.write_text(kblib.canonical_yaml(value), encoding="utf-8")

    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "check_corpus_plan.py"),
             str(self.root), *args],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )


class CheckCorpusPlanPositiveTests(CorpusPlanFixture):
    def test_configured_plan_resolves_selected_profile_and_runtime(self):
        result = self.validate()
        self.assertEqual([], result["errors"])
        self.assertEqual("configured", result["applicability"])
        self.assertEqual(1, len(result["profile_scope"]["layers"]))
        self.assertEqual(2, len(result["global_map"]["entries"]))
        self.assertEqual(1, len(result["matrix"]["capabilities"]))
        promotion = result["gap_register"]["promotions"][0]
        self.assertEqual("B2", promotion["queue_item"]["id"])
        self.assertEqual("required",
                         promotion["coverage"]["coverage_disposition"])

    def test_explicit_profile_directory_is_accepted(self):
        result = self.validate("profiles/test-profile")
        self.assertEqual([], result["errors"])
        self.assertEqual("profiles/test-profile/profile.md",
                         result["profile_manifest"])

    def test_runtime_reuses_the_same_profile_load_evaluation(self):
        producer = check_corpus_plan.check_queue.check_profile.\
            evaluate_profile_load
        with mock.patch.object(
                check_corpus_plan.check_queue.check_profile,
                "evaluate_profile_load", wraps=producer) as evaluate:
            result = self.validate()
        self.assertEqual([], result["errors"])
        self.assertEqual(1, evaluate.call_count)

    def test_slot_validation_reads_authorized_snapshot_not_transient_live_bytes(self):
        view, view_errors = \
            check_corpus_plan.check_queue.profile_load_authorized_view(
                self.root, "profiles/test-profile/profile.md")
        self.assertEqual([], view_errors)
        self.slot.write_text(INACTIVE_SLOT, encoding="utf-8")

        # Model A -> B -> A around every live-tree CAS observation.  If the
        # validator reopened the slot it would see not-applicable B; the
        # producer's immutable snapshot must keep the admitted configured A.
        with mock.patch.object(
                check_corpus_plan.check_queue,
                "profile_load_authorized_view", return_value=(view, [])), \
                mock.patch.object(
                    check_corpus_plan.check_queue.check_profile.
                        ProfileLoadEvaluation,
                    "rebind_profile_snapshot",
                    return_value=view["_profile_snapshot"]):
            result = self.validate()
        self.assertEqual([], result["errors"])
        self.assertEqual("configured", result["applicability"])

    def test_unrelated_unloadable_slot_blocks_corpus_plan_pass(self):
        manifest = self.profile / "profile.md"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "- `Priority Rubric`: `slots.md`",
                "- `Priority Rubric`: `broken-priority.md`"),
            encoding="utf-8")
        (self.profile / "broken-priority.md").write_text(
            "TODO(profile)\n", encoding="utf-8")
        result = self.validate()
        self.assert_error(result, "selected Profile failed profile-load")

    def test_canonical_profile_input_change_invalidates_shared_view(self):
        view, view_errors = \
            check_corpus_plan.check_queue.profile_load_authorized_view(
                self.root, "profiles/test-profile/profile.md")
        self.assertEqual([], view_errors)
        interface = (
            self.root /
            check_corpus_plan.check_queue.check_profile.DEFAULT_INTERFACE)
        interface.write_text(
            interface.read_text(encoding="utf-8") +
            "\n<!-- canonical input revision B -->\n",
            encoding="utf-8",
        )
        with mock.patch.object(
                check_corpus_plan.check_queue,
                "profile_load_authorized_view", return_value=(view, [])):
            result = self.validate()

        self.assert_error(result, "canonical profile-load inputs changed")

    def test_not_applicable_profile_has_no_artifacts_or_runtime(self):
        self.slot.write_text(INACTIVE_SLOT, encoding="utf-8")
        shutil.rmtree(self.root / ".cambium")
        result = self.validate("profiles/test-profile/profile.md")
        self.assertEqual([], result["errors"])
        self.assertEqual("not-applicable", result["applicability"])
        self.assertIn("bounded task", result["applicability_reason"])
        self.assertIsNone(result["runtime"])

    def test_cli_writes_machine_receipt(self):
        completed = self.command(
            "--receipts", ".cambium/receipts/corpus-plan.jsonl")
        self.assertEqual(0, completed.returncode, completed.stdout)
        rows = [json.loads(line) for line in (
            self.root / ".cambium/receipts/corpus-plan.jsonl"
        ).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, len(rows))
        self.assertEqual("pass", rows[0]["result"])
        self.assertEqual("check_corpus_plan", rows[0]["tool"])
        self.assertEqual("corpus-plan-structure", rows[0]["gate_id"])

    def test_cli_json_is_normalized_deterministic_and_excludes_raw_text(self):
        first = self.command("--json")
        second = self.command("--json")
        self.assertEqual(0, first.returncode, first.stdout)
        self.assertEqual(first.stdout, second.stdout)
        payload = json.loads(first.stdout)
        self.assertTrue(payload["structural_reconciliation_valid"])
        self.assertNotIn("valid", payload)
        self.assertEqual("not-recorded",
                         payload["semantic_acceptance"]["status"])
        self.assertEqual("E-A",
                         payload["global_map"]["entries"][0]["entry_id"])
        self.assertNotIn("text", first.stdout)

        document = self.load_yaml(self.global_map)
        document["entries"][0]["extra"] = "invalid"
        self.write_yaml(self.global_map, document)
        failed = self.command("--json")
        self.assertEqual(1, failed.returncode)
        failed_payload = json.loads(failed.stdout)
        self.assertFalse(
            failed_payload["structural_reconciliation_valid"])
        self.assertEqual("unavailable",
                         failed_payload["semantic_acceptance"]["status"])
        self.assertTrue(failed_payload["errors"])

    def test_pass_receipt_binds_profile_plan_state_and_repository_bytes(self):
        result = self.validate()
        self.assertEqual([], result["errors"])
        receipt = check_corpus_plan.make_pass_receipt(result)
        self.assertEqual([], check_corpus_plan.pass_receipt_errors(
            self.root, receipt, result=result))
        self.assertEqual(
            kblib.sha256_file(self.profile / "profile.md"),
            receipt["selected_profile_manifest_sha256"])
        self.assertEqual(kblib.sha256_file(self.slot),
                         receipt["corpus_planning_slot_sha256"])
        self.assertEqual("profiles/test-profile/scope-and-architecture.md",
                         receipt["profile_scope_path"])
        self.assertEqual(kblib.sha256_file(self.scope),
                         receipt["profile_scope_sha256"])
        self.assertEqual(kblib.sha256_file(self.global_map),
                         receipt["global_map_sha256"])
        self.assertEqual(kblib.sha256_file(self.matrix),
                         receipt["capability_matrix_sha256"])
        self.assertEqual(kblib.sha256_file(self.gaps),
                         receipt["gap_register_sha256"])
        self.assertEqual(
            result["_authorized_profile_view"]["profile_snapshot_sha256"],
            receipt["profile_snapshot_sha256"])
        self.assertEqual(
            result["_authorized_profile_view"][
                "profile_contract_fingerprint"],
            receipt["profile_contract_fingerprint"])
        self.assertEqual(
            result["_authorized_profile_view"][
                "profile_load_inputs_sha256"],
            receipt["profile_load_inputs_sha256"])
        self.assertEqual(kblib.repository_snapshot_sha256(self.root),
                         receipt["repository_snapshot_sha256"])

    def test_stale_validated_profile_slot_cannot_be_rebound_into_pass(self):
        result = self.validate()
        self.assertEqual([], result["errors"])
        self.slot.write_text("not: valid: yaml\n", encoding="utf-8")

        with self.assertRaisesRegex(
                ValueError, "selected Profile changed after profile-load"):
            check_corpus_plan.make_pass_receipt(
                result,
                repository_snapshot_sha256=
                    kblib.repository_snapshot_sha256(self.root),
            )

    def test_stale_validated_planning_artifact_cannot_be_rebound_into_pass(self):
        result = self.validate()
        self.assertEqual([], result["errors"])
        self.global_map.write_text(
            self.global_map.read_text(encoding="utf-8") +
            "\nunsupported: revision-b\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
                ValueError, "Global Map changed after"):
            check_corpus_plan.make_pass_receipt(
                result,
                repository_snapshot_sha256=
                    kblib.repository_snapshot_sha256(self.root),
            )

    def test_receipt_binding_rechecks_currency_after_assembly(self):
        result = self.validate()
        self.assertEqual([], result["errors"])
        real_currency = check_corpus_plan._result_currency_errors
        calls = []

        def changes_after_first_check(candidate):
            calls.append(None)
            if len(calls) == 1:
                return real_currency(candidate)
            return ["Global Map changed during receipt assembly"]

        with mock.patch.object(
                check_corpus_plan, "_result_currency_errors",
                side_effect=changes_after_first_check):
            with self.assertRaisesRegex(
                    ValueError, "changed while receipt binding was assembled"):
                check_corpus_plan.make_pass_receipt(
                    result,
                    repository_snapshot_sha256=
                        kblib.repository_snapshot_sha256(self.root),
                )
        self.assertEqual(2, len(calls))

    def test_changed_plan_or_repository_bytes_invalidate_pass_receipt(self):
        result = self.validate()
        receipt = check_corpus_plan.make_pass_receipt(result)
        self.slot.write_text(
            self.slot.read_text(encoding="utf-8") + "\n",
            encoding="utf-8")
        current = self.validate()
        errors = check_corpus_plan.pass_receipt_errors(
            self.root, receipt, result=current)
        self.assertTrue(any("corpus_planning_slot_sha256" in error
                            for error in errors), errors)
        self.assertTrue(any("repository_snapshot_sha256" in error
                            for error in errors), errors)

    def test_changed_profile_scope_invalidates_pass_receipt(self):
        result = self.validate()
        receipt = check_corpus_plan.make_pass_receipt(result)
        self.scope.write_text(
            self.scope.read_text(encoding="utf-8").replace(
                "Canonical topic pages.", "Changed topic responsibility."),
            encoding="utf-8")
        current = self.validate()
        errors = check_corpus_plan.pass_receipt_errors(
            self.root, receipt, result=current)
        self.assertTrue(any("profile_scope_sha256" in error
                            for error in errors), errors)

    def test_explicit_relations_expand_affected_set_without_inference(self):
        result = self.validate()
        self.assertEqual([], result["errors"])
        affected = set(check_corpus_plan.planning_artifact_paths(result))
        self.assertTrue({
            "profiles/test-profile/profile.md",
            "profiles/test-profile/corpus-planning.yaml",
            "profiles/test-profile/scope-and-architecture.md",
            "planning/global-map.yaml",
            "planning/capability-matrix.yaml",
            "planning/gap-register.yaml",
            "Topics/A.md",
            "Topics/B.md",
        }.issubset(affected), affected)
        self.assertNotIn("Topics/Agent.md", affected)

        required, triggers = check_corpus_plan.close_requirement(
            result["runtime"], {"manifest": ["Topics/A.md"]}, result)
        self.assertTrue(required)
        self.assertEqual(["manifest"], triggers)
        required, triggers = check_corpus_plan.close_requirement(
            result["runtime"], {
                "manifest": ["profiles/test-profile/profile.md"]},
            result)
        self.assertTrue(required)
        self.assertEqual(["manifest"], triggers)
        required, triggers = check_corpus_plan.close_requirement(
            result["runtime"], {
                "manifest": [
                    "profiles/test-profile/scope-and-architecture.md"]},
            result)
        self.assertTrue(required)
        self.assertEqual(["manifest"], triggers)
        required, triggers = check_corpus_plan.close_requirement(
            result["runtime"], {"manifest": ["Topics/Agent.md"]}, result)
        self.assertFalse(required)
        self.assertEqual([], triggers)


class CheckCorpusPlanSlotTests(CorpusPlanFixture):
    def test_applicability_mapping_is_closed(self):
        self.replace(self.slot, "  reason: null",
                     "  reason: null\n  registration: configured")
        self.assert_error(self.validate(), "unsupported field(s): registration")

    def test_bare_none_is_not_an_inactive_value(self):
        self.replace(self.slot, "  state: configured", "  state: null")
        self.assert_error(self.validate(),
                          "must be exactly configured or not-applicable")

    def test_not_applicable_requires_inactive_payload(self):
        self.replace(self.slot, "  state: configured",
                     "  state: not-applicable")
        self.replace(self.slot, "  reason: null", "  reason: bounded task")
        result = self.validate()
        self.assert_error(result, "not-applicable requires null")

    def test_configured_requires_exact_three_binding_fields(self):
        self.replace(self.slot, "  gap_register:", "  other:")
        result = self.validate()
        self.assert_error(result, "missing field(s): gap_register")
        self.assert_error(result, "unsupported field(s): other")

    def test_binding_cannot_escape_repository(self):
        self.replace(self.slot, "planning/global-map.yaml", "../map.yaml")
        self.assert_error(self.validate(), "must not contain")

    def test_binding_cannot_use_runtime_namespace(self):
        reports = self.root / ".cambium/reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "global-map.yaml").write_text(GLOBAL_MAP, encoding="utf-8")
        self.replace(self.slot, "planning/global-map.yaml",
                     ".cambium/reports/global-map.yaml")
        self.assert_error(self.validate(), "may not be inside .cambium")

    def test_artifact_binding_requires_yaml_suffix(self):
        self.replace(self.slot, "planning/global-map.yaml",
                     "planning/global-map.md")
        (self.root / "planning/global-map.md").write_text(
            GLOBAL_MAP, encoding="utf-8")
        self.assert_error(self.validate(), "repository-relative .yaml path")

    def test_pass_authority_must_be_registered(self):
        self.replace(self.slot, "  role_id: stopper",
                     "  role_id: unknown-role")
        self.assert_error(self.validate(), "not registered")

    def test_configured_slot_rejects_template_sentinel(self):
        self.replace(self.slot, "Core explanation has accepted evidence.",
                     "TODO(profile)")
        self.assert_error(self.validate(), "unfilled sentinel")

    def test_capability_scale_rank_is_explicit_and_contiguous(self):
        self.replace(self.slot, "  - rank: 1\n    value: Core",
                     "  - rank: 7\n    value: Core")
        self.assert_error(self.validate(), "zero-based list position 1")

    def test_capability_scale_requires_target_eligible_level(self):
        self.slot.write_text(
            self.slot.read_text(encoding="utf-8").replace(
                "target_eligible: true", "target_eligible: false"),
            encoding="utf-8")
        self.assert_error(self.validate(),
                          "at least one scale item must be target eligible")

    def test_matrix_target_must_be_target_eligible(self):
        self.replace(self.slot, "    value: Defensible\n"
                     "    predicate: Evidence can withstand challenge.\n"
                     "    target_eligible: true",
                     "    value: Defensible\n"
                     "    predicate: Evidence can withstand challenge.\n"
                     "    target_eligible: false")
        self.assert_error(self.validate(), "target level is not Target eligible")

    def test_pass_authority_scope_is_closed(self):
        self.replace(self.slot, "corpus-plan-semantic-acceptance",
                     "all-decisions")
        self.assert_error(self.validate(),
                          "must be corpus-plan-semantic-acceptance")

    def test_slot_rejects_extra_top_level_and_nested_fields(self):
        self.slot.write_text(
            CONFIGURED_SLOT + "extra: invalid\n", encoding="utf-8")
        self.assert_error(self.validate(), "unsupported field(s): extra")
        self.slot.write_text(CONFIGURED_SLOT.replace(
            "  global_map: planning/global-map.yaml",
            "  global_map: planning/global-map.yaml\n  note: invalid"),
            encoding="utf-8")
        self.assert_error(self.validate(), "unsupported field(s): note")

    def test_slot_requires_exact_top_level_fields_and_schema_version(self):
        self.replace(self.slot, "schema_version: 1", "schema_version: 2")
        self.assert_error(self.validate(), "schema_version must be integer 1")
        self.slot.write_text(CONFIGURED_SLOT.replace(
            "pass_authority:\n"
            "  role_id: stopper\n"
            "  decision_scope_id: corpus-plan-semantic-acceptance\n",
            ""), encoding="utf-8")
        self.assert_error(self.validate(), "missing field(s): pass_authority")


class CheckCorpusPlanMapTests(CorpusPlanFixture):
    def test_profile_scope_layer_id_is_unique(self):
        self.replace(
            self.profile / "scope-and-architecture.md",
            "| `L1` | `Topics` | Canonical topic pages. |",
            "| `L1` | `Topics` | Canonical topic pages. |\n"
            "| `L1` | `Topics` | Duplicate topic pages. |",
        )
        self.assert_error(self.validate(), "duplicate Stable Layer ID")

    def test_profile_scope_layer_can_bind_multiple_directories(self):
        other = self.root / "Other"
        other.mkdir()
        (other / "C.md").write_text("# C\n", encoding="utf-8")
        self.replace(self.profile / "scope-and-architecture.md",
                     "`Topics` | Canonical topic pages.",
                     "`Topics`; `Other` | Canonical topic pages.")
        document = self.load_yaml(self.global_map)
        document["entries"].append({
            "entry_id": "E-C", "layer_id": "L1",
            "canonical_markdown_path": "Other/C.md",
            "single_responsibility": "Own topic C.",
        })
        self.write_yaml(self.global_map, document)
        self.assertEqual([], self.validate()["errors"])

    def test_entry_requires_known_layer(self):
        document = self.load_yaml(self.global_map)
        document["entries"][1]["layer_id"] = "MISSING"
        self.write_yaml(self.global_map, document)
        self.assert_error(self.validate(), "unknown Layer ID")

    def test_entry_must_stay_in_declared_layer(self):
        (self.root / "planning/Outside.md").write_text(
            "# Outside\n", encoding="utf-8")
        document = self.load_yaml(self.global_map)
        document["entries"][1]["canonical_markdown_path"] = (
            "planning/Outside.md")
        self.write_yaml(self.global_map, document)
        result = self.validate()
        self.assert_error(result, "outside its declared layer")

    def test_map_canonical_entry_cannot_use_runtime_namespace(self):
        runtime_page = self.root / ".cambium/runtime-page.md"
        runtime_page.write_text("# Runtime projection\n", encoding="utf-8")
        document = self.load_yaml(self.global_map)
        document["entries"][1]["canonical_markdown_path"] = (
            ".cambium/runtime-page.md")
        self.write_yaml(self.global_map, document)
        self.assert_error(self.validate(), "may not be inside .cambium")

    def test_dependency_references_explicit_entries(self):
        document = self.load_yaml(self.global_map)
        document["typed_dependencies"][0]["upstream_entry_id"] = "NOPE"
        self.write_yaml(self.global_map, document)
        self.assert_error(self.validate(), "unknown upstream Entry ID")

    def test_dependency_cannot_be_self_edge(self):
        document = self.load_yaml(self.global_map)
        document["typed_dependencies"][0]["downstream_entry_id"] = "E-A"
        self.write_yaml(self.global_map, document)
        self.assert_error(self.validate(), "must differ")

    def test_unknown_relation_type_is_rejected(self):
        document = self.load_yaml(self.global_map)
        document["typed_dependencies"][0]["relation_type"] = "related-to"
        self.write_yaml(self.global_map, document)
        self.assert_error(self.validate(), "unknown relation_type")

    def test_extra_field_is_rejected(self):
        document = self.load_yaml(self.global_map)
        document["entries"][0]["queue_order"] = 1
        self.write_yaml(self.global_map, document)
        self.assert_error(self.validate(), "unsupported field(s): queue_order")

    def test_wrong_container_type_is_rejected(self):
        document = self.load_yaml(self.global_map)
        document["entries"] = "not-a-list"
        self.write_yaml(self.global_map, document)
        self.assert_error(self.validate(), "must be a list")


class CheckCorpusPlanMatrixGapTests(CorpusPlanFixture):
    def test_matrix_capability_id_is_unique(self):
        document = self.load_yaml(self.matrix)
        document["capabilities"].append(dict(document["capabilities"][0]))
        self.write_yaml(self.matrix, document)
        self.assert_error(self.validate(), "duplicate Capability ID")

    def test_matrix_level_must_be_declared_by_profile(self):
        document = self.load_yaml(self.matrix)
        document["capabilities"][0]["current_level"] = "Unknown"
        self.write_yaml(self.matrix, document)
        self.assert_error(self.validate(), "unknown current level")

    def test_matrix_priority_is_closed_set(self):
        document = self.load_yaml(self.matrix)
        document["capabilities"][0]["priority"] = "urgent"
        self.write_yaml(self.matrix, document)
        self.assert_error(self.validate(), "exactly P0, P1, or P2")

    def test_matrix_canonical_path_must_be_in_global_map(self):
        (self.root / "Other").mkdir()
        (self.root / "Other/C.md").write_text("# C\n", encoding="utf-8")
        document = self.load_yaml(self.matrix)
        document["capabilities"][0]["canonical_markdown_paths"] = [
            "Topics/A.md", "Other/C.md"]
        self.write_yaml(self.matrix, document)
        self.assert_error(self.validate(), "not covered by any linked")

    def test_matrix_map_entry_id_must_exist(self):
        document = self.load_yaml(self.matrix)
        document["capabilities"][0]["map_entry_ids"] = ["E-A", "NOPE"]
        self.write_yaml(self.matrix, document)
        self.assert_error(self.validate(), "unknown Global Map Entry ID")

    def test_nonlowest_current_level_requires_evidence(self):
        document = self.load_yaml(self.matrix)
        document["capabilities"][0]["evidence_paths"] = []
        self.write_yaml(self.matrix, document)
        self.assert_error(self.validate(), "requires evidence")

    def test_below_target_requires_gap_id(self):
        document = self.load_yaml(self.matrix)
        document["capabilities"][0]["gap_ids"] = []
        self.write_yaml(self.matrix, document)
        result = self.validate()
        self.assert_error(result, "below target requires")

    def test_gap_status_is_closed_set(self):
        document = self.load_yaml(self.gaps)
        document["gaps"][0]["status"] = "active"
        self.write_yaml(self.gaps, document)
        self.assert_error(self.validate(), "invalid status")

    def test_matrix_gap_reference_must_exist(self):
        document = self.load_yaml(self.matrix)
        document["capabilities"][0]["gap_ids"] = ["G-NOPE"]
        self.write_yaml(self.matrix, document)
        self.assert_error(self.validate(), "unknown Gap ID")

    def test_gap_and_matrix_links_are_bidirectional(self):
        matrix = self.load_yaml(self.matrix)
        matrix["capabilities"].append({
            "capability_id": "C-2", "capability": "Describe A.",
            "priority": "P1", "map_entry_ids": ["E-A"],
            "canonical_markdown_paths": ["Topics/A.md"],
            "current_level": "Core", "target_level": "Core",
            "evidence_paths": ["Topics/A.md"], "gap_ids": [],
        })
        self.write_yaml(self.matrix, matrix)
        gaps = self.load_yaml(self.gaps)
        gaps["gaps"][0]["capability_ids"].append("C-2")
        self.write_yaml(self.gaps, gaps)
        self.assert_error(self.validate(), "does not link back")

    def test_gap_requires_explicit_statement_and_close_condition(self):
        document = self.load_yaml(self.gaps)
        document["gaps"][0]["gap_statement"] = ""
        self.write_yaml(self.gaps, document)
        self.assert_error(self.validate(), "must be non-empty")
        document = self.load_yaml(self.gaps)
        document["gaps"][0]["gap_statement"] = "Missing support."
        document["gaps"][0]["close_condition"] = ""
        self.write_yaml(self.gaps, document)
        self.assert_error(self.validate(), "must be non-empty")

    def test_unpromoted_gap_cannot_claim_coverage_path(self):
        document = self.load_yaml(self.gaps)
        document["gaps"][0]["status"] = "confirmed"
        self.write_yaml(self.gaps, document)
        self.assert_error(self.validate(), "must use Promoted Coverage path None")

    def test_promoted_gap_requires_initialized_runtime(self):
        shutil.rmtree(self.root / ".cambium")
        result = self.validate("profiles/test-profile/profile.md")
        self.assert_error(result, "requires initialized canonical runtime")

    def test_promoted_gap_requires_coverage_row(self):
        coverage_path = self.root / ".cambium/state/coverage_ledger.yaml"
        coverage = kblib.load_yaml_file(coverage_path)
        coverage["pages"] = [row for row in coverage["pages"]
                             if row["path"] != "Topics/B.md"]
        coverage_path.write_text(kblib.canonical_yaml(coverage),
                                 encoding="utf-8")
        result = self.validate()
        self.assertTrue(result["errors"])
        self.assertTrue(any(
            "Coverage row" in error["details"] or
            error["check"] == "runtime"
            for error in result["errors"]), result["errors"])

    def test_resolved_gap_retains_current_evidence(self):
        document = self.load_yaml(self.gaps)
        document["gaps"][0]["status"] = "resolved"
        document["gaps"][0]["evidence_paths"] = []
        self.write_yaml(self.gaps, document)
        self.assert_error(self.validate(),
                          "resolved gap requires at least one retained evidence")

    def test_unknown_candidate_owner_is_rejected(self):
        document = self.load_yaml(self.gaps)
        document["gaps"][0]["candidate_owner_entry_id"] = "NOPE"
        self.write_yaml(self.gaps, document)
        self.assert_error(self.validate(), "unknown candidate owner Entry ID")

    def test_null_candidate_owner_is_allowed(self):
        document = self.load_yaml(self.gaps)
        document["gaps"][0]["candidate_owner_entry_id"] = None
        self.write_yaml(self.gaps, document)
        self.assertEqual([], self.validate()["errors"])

    def test_runtime_evidence_is_rejected_in_matrix_and_gap(self):
        runtime_evidence = self.root / ".cambium/evidence.json"
        runtime_evidence.write_text("{}\n", encoding="utf-8")
        matrix = self.load_yaml(self.matrix)
        matrix["capabilities"][0]["evidence_paths"] = [
            ".cambium/evidence.json"]
        self.write_yaml(self.matrix, matrix)
        self.assert_error(self.validate(), "may not be inside .cambium")
        self.write_yaml(self.matrix, kblib.parse_yaml_subset(MATRIX))
        gaps = self.load_yaml(self.gaps)
        gaps["gaps"][0]["evidence_paths"] = [".cambium/evidence.json"]
        self.write_yaml(self.gaps, gaps)
        self.assert_error(self.validate(), "may not be inside .cambium")

    def test_matrix_wrong_list_type_is_rejected(self):
        document = self.load_yaml(self.matrix)
        document["capabilities"][0]["map_entry_ids"] = "E-A"
        self.write_yaml(self.matrix, document)
        self.assert_error(self.validate(), "must be a list")


class PromotedGapHandoffTests(unittest.TestCase):
    def reconcile(self, disposition, next_batch=None, queue_items=None):
        result = {"errors": []}
        runtime = {
            "errors": [],
            "coverage": {"pages": [{
                "path": "Topics/C.md",
                "coverage_disposition": disposition,
                "next_batch": next_batch,
            }]},
            "queue": {"required_queue": queue_items or []},
        }
        outcome = check_corpus_plan._reconcile_promotion(
            "Topics/C.md", runtime, "G-OPTIONAL", result)
        return result, outcome

    def test_optional_promoted_gap_needs_coverage_but_no_queue(self):
        result, outcome = self.reconcile("optional")
        self.assertEqual([], result["errors"])
        self.assertEqual("optional",
                         outcome["coverage"]["coverage_disposition"])
        self.assertIsNone(outcome["queue_item"])

    def test_nonrequired_promoted_gap_rejects_next_batch(self):
        result, _ = self.reconcile("deferred", next_batch="B3")
        self.assertTrue(any(
            "must not declare next_batch" in error["details"]
            for error in result["errors"]), result["errors"])

    def test_nonrequired_promoted_gap_rejects_nonterminal_queue_projection(self):
        item = {
            "id": "B3", "state": "queued", "manifest": ["Topics/C.md"],
        }
        result, _ = self.reconcile("excluded", queue_items=[item])
        self.assertTrue(any(
            "must not appear in a nonterminal Queue" in error["details"]
            for error in result["errors"]), result["errors"])

    def test_completed_required_promoted_gap_needs_no_live_queue(self):
        result, outcome = self.reconcile("required")
        self.assertEqual([], result["errors"])
        self.assertIsNone(outcome["queue_item"])

    def test_unfinished_required_promoted_gap_matches_next_batch(self):
        item = {
            "id": "B3", "state": "open", "manifest": ["Topics/C.md"],
        }
        result, outcome = self.reconcile(
            "required", next_batch="B3", queue_items=[item])
        self.assertEqual([], result["errors"])
        self.assertEqual("B3", outcome["queue_item"]["id"])


if __name__ == "__main__":
    unittest.main()
