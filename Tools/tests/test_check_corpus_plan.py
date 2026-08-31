"""Owned tests for the current Corpus Planning checker.

The Profile envelope, Corpus Planning registry, acceptance writer, close gate,
and Terminal Proof have separate test owners. This suite owns only the checker
predicates, artifact relationships, promotion handoff, and one already-
authorized Profile/runtime checkpoint through the Receipt consumer. No test
constructs a Task or Batch lifecycle.
"""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from Tools.execution.planning import check_corpus_plan, corpus_planning_contract
from Tools.execution.task_runtime import queue_runtime
from Tools.platform.common import kblib
from Tools.tests.fixtures.contract.corpus_plan_objects import (
    CONFIGURED_SLOT,
    GAPS,
    GLOBAL_MAP,
    INACTIVE_SLOT,
    MANIFEST,
    MATRIX,
    ROLES,
    SCOPE,
)


PROFILE_MANIFEST = "profiles/test-profile/profile.md"
CORPUS_SLOT = "profiles/test-profile/corpus-planning.yaml"
PROFILE_SCOPE = "profiles/test-profile/scope-and-architecture.md"
ROLE_REGISTRY = "profiles/test-profile/roles.md"


def sha256_fixture(character):
    return "sha256:" + character * 64


class MinimalCorpusPlanFixture:
    """One minimal filesystem contract fixture shared by this test module.

    It contains only the exact Profile projection, planning artifacts, pages,
    and runtime byte bindings consumed by ``check_corpus_plan``. The
    authorized view and runtime result are supplied as already-validated
    checkpoints, so this fixture never adopts a Profile or builds Task/Queue/
    Batch history.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls._temporary.name).resolve()

    @classmethod
    def tearDownClass(cls):
        try:
            cls._temporary.cleanup()
        finally:
            super().tearDownClass()

    def setUp(self):
        super().setUp()
        for relative in (
                "profiles/test-profile", "planning", "Topics",
                ".cambium/state"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        for removable in ("Other", ".cambium/evidence.json"):
            candidate = self.root / removable
            if candidate.is_dir():
                shutil.rmtree(candidate)
            elif candidate.exists():
                candidate.unlink()
        for candidate in (
                self.root / "planning/Outside.md",
                self.root / ".cambium/runtime-page.md"):
            if candidate.exists():
                candidate.unlink()

        self.write_text(PROFILE_MANIFEST, MANIFEST)
        self.write_text(CORPUS_SLOT, CONFIGURED_SLOT)
        self.write_text(PROFILE_SCOPE, SCOPE)
        self.write_text(ROLE_REGISTRY, ROLES)
        self.write_text("planning/global-map.yaml", GLOBAL_MAP)
        self.write_text("planning/capability-matrix.yaml", MATRIX)
        self.write_text("planning/gap-register.yaml", GAPS)
        self.write_text("Topics/A.md", "# A\n")
        self.write_text("Topics/B.md", "# B\n")

        for relative, text in (
                (queue_runtime.COVERAGE_PATH, "coverage checkpoint\n"),
                (queue_runtime.QUEUE_PATH, "queue checkpoint\n"),
                (queue_runtime.PROGRESS_PATH, "progress checkpoint\n")):
            self.write_text(relative, text)

        self.runtime = {
            "errors": [],
            "current_receipt_catalog": {},
            "coverage": {"pages": [{
                "path": "Topics/B.md",
                "coverage_disposition": "required",
                "next_batch": "B2",
            }]},
            "queue": {
                "task_id": "TASK-1",
                "queue_revision": 1,
                "state_revision": 1,
                "selected_profile_manifest": PROFILE_MANIFEST,
                "required_queue": [{
                    "id": "B2",
                    "state": "open",
                    "manifest": ["Topics/B.md"],
                }],
            },
            "progress": {"contract": {
                "selected_profile_manifest": PROFILE_MANIFEST,
                "selected_route_ids": ["R13"],
            }},
            "coverage_sha256": self.file_sha(queue_runtime.COVERAGE_PATH),
            "queue_sha256": self.file_sha(queue_runtime.QUEUE_PATH),
            "progress_sha256": self.file_sha(queue_runtime.PROGRESS_PATH),
        }

    def write_text(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def file_sha(self, relative):
        return kblib.repository_file_snapshot(
            self.root, relative, singly_linked=True).sha256

    def profile_view(self, *, slot=CONFIGURED_SLOT, scope=SCOPE, roles=ROLES):
        files = {
            PROFILE_MANIFEST: MANIFEST.encode("utf-8"),
            CORPUS_SLOT: slot.encode("utf-8"),
            PROFILE_SCOPE: scope.encode("utf-8"),
            ROLE_REGISTRY: roles.encode("utf-8"),
        }
        snapshot = kblib.RepositoryTreeSnapshot(
            str(self.root), "profiles/test-profile",
            sha256_fixture("1"), files)
        return {
            "selected_profile_manifest": PROFILE_MANIFEST,
            "profile_snapshot_sha256": snapshot.sha256,
            "profile_contract_fingerprint": sha256_fixture("2"),
            "profile_load_inputs_sha256": sha256_fixture("3"),
            "_manifest_slot_paths": (
                ("Corpus Planning", CORPUS_SLOT),
                ("Profile Scope", PROFILE_SCOPE),
                ("Role Registry", ROLE_REGISTRY),
            ),
            "_profile_snapshot": snapshot,
        }

    def validate_current_plan(self):
        view = self.profile_view()
        with mock.patch.object(
                check_corpus_plan.queue_runtime,
                "authorized_profile_view_errors", return_value=[]), \
                mock.patch.object(
                    check_corpus_plan, "runtime",
                    return_value=self.runtime), \
                mock.patch.object(
                    check_corpus_plan, "_profile_view_currency_errors",
                    return_value=[]):
            return check_corpus_plan.validate_corpus_plan(
                self.root, profile=PROFILE_MANIFEST,
                authorized_profile_view=view)

    @property
    def global_map(self):
        return self.root / "planning/global-map.yaml"


class CorpusPlanObjectFixture:
    """In-memory artifacts for pure checker predicates."""

    root = Path("/repo")

    @property
    def profile_scope(self):
        return {
            "path": PROFILE_SCOPE,
            "layers": [{
                "id": "L1",
                "directories": [{
                    "value": "Topics",
                    "path": "/repo/Topics",
                }],
                "responsibility": "Canonical topic pages.",
            }],
        }

    @property
    def scale(self):
        return kblib.parse_yaml_subset(CONFIGURED_SLOT)["capability_scale"]

    @property
    def runtime(self):
        return {
            "errors": [],
            "coverage": {"pages": [{
                "path": "Topics/B.md",
                "coverage_disposition": "required",
                "next_batch": "B2",
            }]},
            "queue": {"required_queue": [{
                "id": "B2", "state": "open",
                "manifest": ["Topics/B.md"],
            }]},
        }

    @staticmethod
    def binding(relative, text):
        return {
            "value": relative,
            "_snapshot": kblib.RepositoryFileSnapshot(
                "/repo/" + relative, relative, text.encode("utf-8")),
        }

    @staticmethod
    def resolved_path(_root, raw, label, result, *, must_exist=True,
                      markdown=False, yaml_file=False, directory=False):
        del must_exist, directory
        if not isinstance(raw, str):
            check_corpus_plan._add_error(
                result, "path", label, "must be a string path")
            return None
        value = raw.strip().strip("`")
        if markdown and not value.lower().endswith(".md"):
            check_corpus_plan._add_error(
                result, "path", label, "must end with .md")
            return None
        if yaml_file and not value.lower().endswith(".yaml"):
            check_corpus_plan._add_error(
                result, "path", label, "must end with .yaml")
            return None
        return {"value": value, "path": "/repo/" + value}

    def profile_view(self, *, scope=SCOPE):
        snapshot = kblib.RepositoryTreeSnapshot(
            "/repo", "profiles/test-profile", sha256_fixture("1"), {
                PROFILE_MANIFEST: MANIFEST.encode("utf-8"),
                CORPUS_SLOT: CONFIGURED_SLOT.encode("utf-8"),
                PROFILE_SCOPE: scope.encode("utf-8"),
                ROLE_REGISTRY: ROLES.encode("utf-8"),
            })
        return {
            "selected_profile_manifest": PROFILE_MANIFEST,
            "_manifest_slot_paths": (
                ("Corpus Planning", CORPUS_SLOT),
                ("Profile Scope", PROFILE_SCOPE),
                ("Role Registry", ROLE_REGISTRY),
            ),
            "_profile_snapshot": snapshot,
        }

    def validate_artifacts(self, *, global_map=GLOBAL_MAP, matrix=MATRIX,
                           gaps=GAPS, scale=None, runtime=None):
        result = {"errors": []}
        with mock.patch.object(
                check_corpus_plan, "_resolve_path",
                side_effect=self.resolved_path):
            parsed_map = check_corpus_plan._validate_global_map(
                self.root,
                self.binding("planning/global-map.yaml", global_map),
                self.profile_scope, result)
            parsed_matrix = check_corpus_plan._validate_matrix(
                self.root,
                self.binding("planning/capability-matrix.yaml", matrix),
                self.scale if scale is None else scale,
                parsed_map, result)
            parsed_gaps = check_corpus_plan._validate_gap_register(
                self.root,
                self.binding("planning/gap-register.yaml", gaps),
                parsed_map, parsed_matrix,
                self.runtime if runtime is None else runtime, result)
        return {
            "errors": result["errors"],
            "global_map": parsed_map,
            "matrix": parsed_matrix,
            "gap_register": parsed_gaps,
        }

    @staticmethod
    def assert_error(result, fragment):
        messages = [error["details"] for error in result["errors"]]
        if not any(fragment in message for message in messages):
            raise AssertionError("%r not present in %r" % (fragment, messages))


class CorpusAcceptancePlanContractTests(unittest.TestCase):
    """The semantic-plan predicate owner, independent of its writer."""

    @staticmethod
    def result(current_level="Defensible"):
        return {
            "errors": [],
            "applicability": "configured",
            "runtime": {"errors": []},
            "slot": {
                "authorities": [{"role_id": "stopper"}],
                "scale": [
                    {"value": "Core", "rank": 1},
                    {"value": "Defensible", "rank": 2},
                ],
            },
            "matrix": {"capabilities": [{
                "id": "C-1",
                "current_level": current_level,
                "target_level": "Defensible",
            }]},
        }

    @staticmethod
    def plan(decision="accepted"):
        return {
            "schema_version": 1,
            "acceptance_id": "CPA-001",
            "authority_role_id": "stopper",
            "decision_scope_id": "corpus-plan-semantic-acceptance",
            "decisions": [{
                "capability_id": "C-1",
                "decision": decision,
                "rationale": "The authority confirmed the current evidence.",
            }],
        }

    def test_shape_authority_order_and_rank_are_one_owner_predicate(self):
        self.assertEqual(
            [], check_corpus_plan.acceptance_plan_errors(
                ".", self.plan(), self.result()))
        self.assertEqual(
            [], check_corpus_plan.acceptance_plan_errors(
                ".", self.plan("rejected"), self.result("Core")))

        cases = []
        wrong_role = self.plan()
        wrong_role["authority_role_id"] = "gatekeeper"
        cases.append((wrong_role, self.result(), "Profile-bound role"))
        missing_decisions = self.plan()
        missing_decisions["decisions"] = []
        cases.append((
            missing_decisions, self.result(),
            "every current Capability Matrix row"))
        cases.append((
            self.plan(), self.result("Core"), "below its target rank"))

        for plan, result, expected in cases:
            with self.subTest(expected=expected):
                errors = check_corpus_plan.acceptance_plan_errors(
                    ".", plan, result)
                self.assertTrue(
                    any(expected in error for error in errors), errors)

    def test_semantic_acceptance_status_closed_current_only_table(self):
        def result(applicability="configured", *, runtime=None, errors=None):
            return {
                "root": ".",
                "errors": list(errors or []),
                "applicability": applicability,
                "slot": {"authorities": [{"role_id": "stopper"}]},
                "runtime": runtime,
            }

        def receipt(receipt_id, outcome="pass", *, stale=False):
            return {
                "receipt_id": receipt_id,
                "tool": check_corpus_plan.SEMANTIC_ACCEPTANCE_TOOL,
                "check": check_corpus_plan.SEMANTIC_ACCEPTANCE_CHECK,
                "result": outcome,
                "checked_at": "2026-09-01T00:00:00Z",
                "_stale": stale,
            }

        def status(value):
            with mock.patch.object(
                    check_corpus_plan,
                    "semantic_acceptance_receipt_errors",
                    side_effect=lambda _root, row, **_kwargs: (
                        ["stale"] if row.get("_stale") else [])):
                return check_corpus_plan.semantic_acceptance_status(value)[
                    "status"]

        self.assertEqual("unavailable", status(result(runtime=None)))
        self.assertEqual("unavailable", status(result(runtime={
            "errors": ["invalid"], "current_receipt_catalog": {},
        })))
        self.assertEqual("unavailable", status(result(runtime={"errors": []})))
        self.assertEqual("not-applicable", status(result(
            applicability="not-applicable", runtime={
                "errors": [], "current_receipt_catalog": {},
            })))
        self.assertEqual("not-recorded", status(result(runtime={
            "errors": [], "current_receipt_catalog": {},
            "receipt_catalog": {"historical": receipt("historical")},
        })))
        self.assertEqual("current", status(result(runtime={
            "errors": [], "current_receipt_catalog": {
                "accepted": receipt("accepted"),
            },
        })))
        self.assertEqual("rejected", status(result(runtime={
            "errors": [], "current_receipt_catalog": {
                "rejected": receipt("rejected", "fail"),
            },
        })))
        self.assertEqual("stale", status(result(runtime={
            "errors": [], "current_receipt_catalog": {
                "stale": receipt("stale", stale=True),
            },
        })))
        self.assertEqual("ambiguous", status(result(runtime={
            "errors": [], "current_receipt_catalog": {
                "one": receipt("one"), "two": receipt("two"),
            },
        })))


class CorpusPlanPipelineIntegrationTests(
        MinimalCorpusPlanFixture, unittest.TestCase):
    def test_authorized_plan_projects_artifacts_receipt_and_stale_boundary(self):
        result = self.validate_current_plan()
        self.assertEqual([], result["errors"])
        self.assertEqual("configured", result["applicability"])
        self.assertEqual("B2",
                         result["gap_register"]["promotions"][0]
                         ["queue_item"]["id"])

        paths = set(check_corpus_plan.planning_artifact_paths(result))
        self.assertTrue({
            "planning/global-map.yaml", "Topics/A.md", "Topics/B.md",
        }.issubset(paths))
        required, triggers = check_corpus_plan.close_requirement(
            self.runtime,
            self.runtime["queue"]["required_queue"][0],
            result,
        )
        self.assertTrue(required)
        self.assertEqual(
            sorted(corpus_planning_contract.CLOSE_TRIGGERS), triggers)
        projection = check_corpus_plan.normalized_projection(
            result,
            repository_snapshot_sha256=
                kblib.repository_snapshot_sha256(self.root))
        self.assertTrue(projection["structural_reconciliation_valid"])
        self.assertEqual("not-recorded",
                         projection["semantic_acceptance"]["status"])

        with mock.patch.object(
                check_corpus_plan, "_profile_view_currency_errors",
                return_value=[]):
            receipt = check_corpus_plan.make_pass_receipt(result)
        self.assertEqual(
            [], check_corpus_plan.current_gate_receipt_errors(receipt))
        self.assertEqual(
            [], check_corpus_plan.pass_receipt_errors(
                self.root, receipt, expected_binding=receipt))

        self.global_map.write_bytes(
            self.global_map.read_bytes() + b"\n# changed bytes\n")
        with mock.patch.object(
                check_corpus_plan, "_profile_view_currency_errors",
                return_value=[]):
            with self.assertRaisesRegex(ValueError, "Global Map changed"):
                check_corpus_plan.receipt_binding(result)


class CorpusPlanSlotAdapterContractTests(
        CorpusPlanObjectFixture, unittest.TestCase):
    def validate_slot(self, text, *, view=None):
        result = {"profile_manifest": PROFILE_MANIFEST, "errors": []}
        def snapshot(_root, relative, singly_linked=True):
            del singly_linked
            return kblib.RepositoryFileSnapshot(
                "/repo/" + relative, relative, b"schema_version: 1\n")

        with mock.patch.object(
                check_corpus_plan, "_resolve_path",
                side_effect=self.resolved_path), mock.patch.object(
                    check_corpus_plan.kblib, "repository_file_snapshot",
                    side_effect=snapshot):
            slot = check_corpus_plan._validate_slot(
                text, CORPUS_SLOT, view or self.profile_view(),
                self.root, result)
        return result, slot

    def test_slot_adapter_enforces_paths_role_sentinels_and_inactive_shape(self):
        inactive_result, inactive = self.validate_slot(INACTIVE_SLOT)
        self.assertEqual([], inactive_result["errors"])
        self.assertEqual(("not-applicable", {}, []), (
            inactive["mode"], inactive["bindings"], inactive["authorities"]))

        cases = (
            (CONFIGURED_SLOT.replace(
                "planning/global-map.yaml",
                ".cambium/reports/global-map.yaml"),
             "may not be inside .cambium"),
            (CONFIGURED_SLOT.replace(
                "  role_id: stopper", "  role_id: unknown-role"),
             "not registered"),
            (CONFIGURED_SLOT.replace(
                "Core explanation has accepted evidence.", "TODO(profile)"),
             "must replace TODO(profile)"),
        )
        for text, expected in cases:
            with self.subTest(expected=expected):
                result, _slot = self.validate_slot(text)
                self.assert_error(result, expected)


class CorpusPlanProfileScopeContractTests(
        CorpusPlanObjectFixture, unittest.TestCase):
    def test_scope_projection_enforces_identity_and_directory_membership(self):
        duplicate = SCOPE.replace(
            "| `L1` | `Topics` | Canonical topic pages. |",
            "| `L1` | `Topics` | Canonical topic pages. |\n"
            "| `L1` | `Topics` | Duplicate topic pages. |",
        )
        result = {"profile_manifest": PROFILE_MANIFEST, "errors": []}
        with mock.patch.object(
                check_corpus_plan, "_resolve_path",
                side_effect=self.resolved_path):
            check_corpus_plan._validate_profile_scope(
                self.root, self.profile_view(scope=duplicate), result)
        self.assert_error(result, "duplicate Stable Layer ID")

        multiple = SCOPE.replace(
            "`Topics` | Canonical topic pages.",
            "`Topics`; `Other` | Canonical topic pages.")
        result = {"profile_manifest": PROFILE_MANIFEST, "errors": []}
        with mock.patch.object(
                check_corpus_plan, "_resolve_path",
                side_effect=self.resolved_path):
            scope = check_corpus_plan._validate_profile_scope(
                self.root, self.profile_view(scope=multiple), result)
        self.assertEqual([], result["errors"])
        self.assertEqual(
            ["Topics", "Other"],
            [row["value"] for row in scope["layers"][0]["directories"]])


class CheckCorpusPlanMapContractTests(
        CorpusPlanObjectFixture, unittest.TestCase):
    def test_global_map_closed_references_and_path_boundaries(self):
        cases = (
            (lambda value: value["entries"][1].__setitem__(
                "layer_id", "MISSING"), "unknown Layer ID"),
            (lambda value: value["entries"][1].__setitem__(
                "canonical_markdown_path", "planning/Outside.md"),
             "outside its declared layer"),
            (lambda value: value["entries"][1].__setitem__(
                "canonical_markdown_path", ".cambium/runtime-page.md"),
             "may not be inside .cambium"),
            (lambda value: value["typed_dependencies"][0].__setitem__(
                "upstream_entry_id", "NOPE"), "unknown upstream Entry ID"),
            (lambda value: value["typed_dependencies"][0].__setitem__(
                "downstream_entry_id", "E-A"), "must differ"),
            (lambda value: value["typed_dependencies"][0].__setitem__(
                "relation_type", "related-to"), "unknown relation_type"),
            (lambda value: value["entries"][0].__setitem__(
                "queue_order", 1), "unsupported field(s): queue_order"),
            (lambda value: value.__setitem__(
                "entries", "not-a-list"), "must be a list"),
        )
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                document = kblib.parse_yaml_subset(GLOBAL_MAP)
                mutate(document)
                self.assert_error(self.validate_artifacts(
                    global_map=kblib.canonical_yaml(document)), expected)


class CheckCorpusPlanMatrixGapContractTests(
        CorpusPlanObjectFixture, unittest.TestCase):
    def test_capability_matrix_closed_values_and_references(self):
        cases = (
            (lambda row, doc: doc["capabilities"].append(dict(row)),
             "duplicate Capability ID"),
            (lambda row, _doc: row.__setitem__(
                "current_level", "Unknown"), "unknown current level"),
            (lambda row, _doc: row.__setitem__(
                "priority", "urgent"), "exactly P0, P1, or P2"),
            (lambda row, _doc: row.__setitem__(
                "canonical_markdown_paths", ["Topics/A.md", "Other/C.md"]),
             "not covered by any linked"),
            (lambda row, _doc: row.__setitem__(
                "map_entry_ids", ["E-A", "NOPE"]),
             "unknown Global Map Entry ID"),
            (lambda row, _doc: row.__setitem__(
                "evidence_paths", []), "requires evidence"),
            (lambda row, _doc: row.__setitem__(
                "gap_ids", []), "below target requires"),
            (lambda row, _doc: row.__setitem__(
                "map_entry_ids", "E-A"), "must be a list"),
        )
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                document = kblib.parse_yaml_subset(MATRIX)
                mutate(document["capabilities"][0], document)
                self.assert_error(self.validate_artifacts(
                    matrix=kblib.canonical_yaml(document)), expected)

        scale = [dict(row) for row in self.scale]
        scale[-1]["target_eligible"] = False
        self.assert_error(
            self.validate_artifacts(scale=scale),
            "target level is not Target eligible",
        )

    def test_gap_register_closed_values_and_bidirectional_links(self):
        def add_unlinked_capability(_row, matrix, gap):
            matrix["capabilities"].append({
                "capability_id": "C-2", "capability": "Describe A.",
                "priority": "P1", "map_entry_ids": ["E-A"],
                "canonical_markdown_paths": ["Topics/A.md"],
                "current_level": "Core", "target_level": "Core",
                "evidence_paths": ["Topics/A.md"], "gap_ids": [],
            })
            gap["capability_ids"].append("C-2")

        cases = (
            (lambda row, _matrix, _gap: row.__setitem__(
                "status", "active"), "invalid status"),
            (lambda _row, matrix, _gap: matrix["capabilities"][0].__setitem__(
                "gap_ids", ["G-NOPE"]), "unknown Gap ID"),
            (add_unlinked_capability, "does not link back"),
            (lambda row, _matrix, _gap: row.__setitem__(
                "gap_statement", ""), "must be non-empty"),
            (lambda row, _matrix, _gap: row.__setitem__(
                "close_condition", ""), "must be non-empty"),
            (lambda row, _matrix, _gap: row.__setitem__(
                "status", "confirmed"), "must use Promoted Coverage path None"),
            (lambda row, _matrix, _gap: (
                row.__setitem__("status", "resolved"),
                row.__setitem__("evidence_paths", [])),
             "resolved gap requires at least one retained evidence"),
            (lambda row, _matrix, _gap: row.__setitem__(
                "candidate_owner_entry_id", "NOPE"),
             "unknown candidate owner Entry ID"),
        )
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                matrix = kblib.parse_yaml_subset(MATRIX)
                gaps = kblib.parse_yaml_subset(GAPS)
                row = gaps["gaps"][0]
                mutate(row, matrix, row)
                self.assert_error(self.validate_artifacts(
                    matrix=kblib.canonical_yaml(matrix),
                    gaps=kblib.canonical_yaml(gaps)), expected)

        gaps = kblib.parse_yaml_subset(GAPS)
        gaps["gaps"][0]["candidate_owner_entry_id"] = None
        self.assertEqual([], self.validate_artifacts(
            gaps=kblib.canonical_yaml(gaps))["errors"])

    def test_runtime_namespace_cannot_supply_planning_evidence(self):
        matrix = kblib.parse_yaml_subset(MATRIX)
        matrix["capabilities"][0]["evidence_paths"] = [
            ".cambium/evidence.json"]
        self.assert_error(
            self.validate_artifacts(matrix=kblib.canonical_yaml(matrix)),
            "may not be inside .cambium")

        gaps = kblib.parse_yaml_subset(GAPS)
        gaps["gaps"][0]["evidence_paths"] = [".cambium/evidence.json"]
        self.assert_error(
            self.validate_artifacts(gaps=kblib.canonical_yaml(gaps)),
            "may not be inside .cambium")


class PromotedGapConsumerUnitTests(unittest.TestCase):
    def test_current_promotion_resolves_exact_handoff_or_requires_runtime(self):
        runtime = {
            "errors": [],
            "coverage": {"pages": [{
                "path": "Topics/C.md",
                "coverage_disposition": "required",
                "next_batch": "B3",
            }]},
            "queue": {"required_queue": [{
                "id": "B3",
                "state": "open",
                "manifest": ["Topics/C.md"],
            }]},
        }
        result = {"errors": []}
        outcome = check_corpus_plan._reconcile_promotion(
            "Topics/C.md", runtime, "G-OPTIONAL", result)
        self.assertEqual([], result["errors"])
        self.assertEqual("B3", outcome["queue_item"]["id"])

        result = {"errors": []}
        outcome = check_corpus_plan._reconcile_promotion(
            "Topics/C.md", None, "G-OPTIONAL", result)
        self.assertIsNone(outcome["queue_item"])
        self.assertTrue(any(
            "requires initialized canonical runtime" in error["details"]
            for error in result["errors"]), result["errors"])


if __name__ == "__main__":
    unittest.main()
