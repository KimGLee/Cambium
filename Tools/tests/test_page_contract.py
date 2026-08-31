"""Owner-focused tests for the current page-contract compiler and gate.

Pure predicates and the compiler's closed merge contract are exercised in
process. The adjacent compiler-to-checker seam starts from one typed local
admission checkpoint.
"""

import contextlib
import io
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

import Tools.governance.control.metadata_execution_contract as \
    metadata_execution_contract
import Tools.governance.profile.profile_admission as profile_admission
import Tools.knowledge.metadata.check_page_contract as check_page_contract
import Tools.knowledge.metadata.compose_page_contract as compose_page_contract
import Tools.knowledge.metadata.metadata_property_state as \
    metadata_property_state
from Tools.platform.common import reporting


APPLICABILITY_BASE = """schema_version: 1
fields:
  type:
    mode: required
    shape: nonempty-string
  depth:
    mode: optional
    shape: nonempty-string
  authoring_status:
    mode: projection
    shape: nonempty-string
  learning_status:
    mode: user-owned
    shape: nonempty-string
  coverage_disposition:
    mode: projection
    shape: nonempty-string
  deferred_reason:
    mode: conditional
    shape: nonempty-string
    condition:
      all:
        - field: coverage_disposition
          in:
            - deferred
  aliases:
    mode: optional
    shape: list-of-strings
  last_verified:
    mode: optional
    shape: date
  last_content_modified:
    mode: optional
    shape: date
  last_reviewed:
    mode: conditional
    shape: date
    condition:
      all:
        - field: authoring_status
          in:
            - reviewed
  review_by:
    mode: derived
    shape: date
    persisted: false
  boundary:
    mode: optional
    shape: delegated
    delegate: boundary-contract
"""

SOURCES_ROLE_BASE = """schema_version: 1
role: sources
default_titles:
  - Sources
applicability:
  condition:
    any:
      - field: depth
        in:
          - core
          - system
binding_satisfies:
  fields:
    - evidence_sources
  directions:
    - expression-to-canonical
"""

RELATIONSHIP_BASE = """schema_version: 1
relationships:
  source_url:
    mode: conditional
    condition:
      all:
        - field: type
          in:
            - source-note
    direction: page-to-external
    target: external-original
    shape: url
  evidence_sources:
    mode: optional
    direction: evidence-input
    target:
      - source-note
    shape: list-of-paths
"""

VOCAB = """schema_version: 1
frontmatter_extensions:
  fields: []
"""

CONTRACT_DEFAULTS = """schema_version: 1
applicability:
  state: kernel-defaults
applicability_differences: []
extension_fields: []
relationship_extensions: []
section_roles: []
"""

CONTRACT_CONFIGURED = """schema_version: 1
applicability:
  state: configured
applicability_differences:
  - field: last_verified
    mode: required
extension_fields:
  - field: card_binding
    mode: optional
    shape: path
    owner: "scope.md"
relationship_extensions: []
section_roles: []
"""


class StaticAdmission:
    """Compiler input adapter containing only typed immutable slot bytes."""

    def __init__(self, root):
        self.root = str(root)
        self.active_state_repo_path = None
        self.manifest_repo_path = "profile/profile.md"
        self.contract = SimpleNamespace(
            profile_repo_dir="profile", extension_gates=())
        self.evaluation = SimpleNamespace(
            profile_snapshot_sha256="sha256:" + "1" * 64,
            profile_contract_fingerprint="sha256:" + "2" * 64,
            profile_load_inputs_sha256="sha256:" + "3" * 64,
        )
        self.slot_paths = {
            compose_page_contract.METADATA_SLOT:
                str(root / "profile/metadata-contract.yaml"),
            compose_page_contract.VOCAB_SLOT:
                str(root / "profile/vocabulary-extensions.yaml"),
        }
        self.slot_bytes = {
            name: Path(path).read_bytes()
            for name, path in self.slot_paths.items()
        }

    def slot_path(self, name):
        return self.slot_paths.get(name)

    def slot_text(self, name):
        value = self.slot_bytes.get(name)
        return None if value is None else value.decode("utf-8")


@contextlib.contextmanager
def compiler_workspace(contract_text=CONTRACT_DEFAULTS):
    """Yield one typed compiler checkpoint with no adopter runtime."""
    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace)
        inputs = {
            "kernel/applicability-base.yaml": APPLICABILITY_BASE,
            "kernel/relationship-base.yaml": RELATIONSHIP_BASE,
            "kernel/sources-role-base.yaml": SOURCES_ROLE_BASE,
            "profile/metadata-contract.yaml": contract_text,
            "profile/vocabulary-extensions.yaml": VOCAB,
        }
        for relative, text in inputs.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        admission = StaticAdmission(root)
        yield root, admission


def compile_contract(contract_text, *, verify_repeat=False):
    """Compile fixture bytes without installing an adopter runtime."""
    with compiler_workspace(contract_text) as (root, admission):
        result = compose_page_contract.compiled_artifact(
            str(root), admission,
            base_path=str(root / "kernel/applicability-base.yaml"),
            rel_path=str(root / "kernel/relationship-base.yaml"),
            sources_role_path=str(root / "kernel/sources-role-base.yaml"),
        )
        if verify_repeat:
            repeated = compose_page_contract.compiled_artifact(
                str(root), admission,
                base_path=str(root / "kernel/applicability-base.yaml"),
                rel_path=str(root / "kernel/relationship-base.yaml"),
                sources_role_path=str(root / "kernel/sources-role-base.yaml"),
            )
            if result != repeated:
                raise AssertionError(
                    "identical admitted inputs did not compile deterministically")
        return result


class PageContractUnitTests(unittest.TestCase):
    def test_condition_predicate_handles_all_any_and_absence(self):
        cases = (
            ({"all": [{"field": "type", "in": ["concept"]}]},
             {"type": "concept"}, True),
            ({"all": [{"field": "type", "in": ["source-note"]}]},
             {"type": "concept"}, False),
            ({"any": [{"field": "depth", "in": ["core", "system"]}]},
             {"depth": "system"}, True),
            ({"all": [{"field": "review_by", "absent": True}]},
             {"review_by": ""}, True),
            (None, {}, False),
        )
        for condition, fields, expected in cases:
            with self.subTest(condition=condition, fields=fields):
                self.assertIs(
                    check_page_contract.condition_holds(condition, fields),
                    expected,
                )


class PageContractContractTests(unittest.TestCase):
    def test_compiled_contract_requires_a_nonempty_field_mapping(self):
        findings = reporting.FindingSet()
        fields, roles = check_page_contract.load_contract(
            "memory", findings,
            text="schema_version: 1\nfields:\n  type:\n"
                 "    mode: required\nsection_roles: {}\n",
        )
        self.assertEqual({"type"}, set(fields))
        self.assertEqual({}, roles)
        self.assertEqual([], findings.rows)

        empty_findings = reporting.FindingSet()
        fields, roles = check_page_contract.load_contract(
            "memory", empty_findings,
            text="schema_version: 1\nfields: {}\n",
        )
        self.assertIsNone(fields)
        self.assertIsNone(roles)
        self.assertEqual("fail", empty_findings.rows[0]["result"])
        self.assertIn("no fields mapping", empty_findings.rows[0]["details"])

    def test_shape_registry_enforces_scalars_and_reference_targets(self):
        scalar_cases = (
            ({"shape": "date"}, "soon", "YYYY-MM-DD"),
            ({"shape": "url"}, "Domain/Page.md", "external http(s)"),
            ({"shape": "list-of-strings"}, ["ok", ""],
             "list of nonempty strings"),
            ({"shape": "delegated"}, {"owns": ["Not_A_Slug"]}, None),
        )
        for spec, value, expected in scalar_cases:
            rows = []
            check_page_contract.check_shape(
                ".", "Domain/Page.md", "field", spec, value,
                lambda check, target, details: rows.append(
                    (check, target, details)),
            )
            with self.subTest(spec=spec, value=value):
                if expected is None:
                    self.assertEqual([], rows)
                else:
                    self.assertIn(expected, rows[0][2])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Domain").mkdir()
            (root / "Domain/Source.md").write_text(
                "---\ntype: source-note\n---\n# Source\n", encoding="utf-8")
            (root / "Domain/Other.md").write_text(
                "---\ntype: concept\n---\n# Other\n", encoding="utf-8")
            rows = []
            report = lambda check, target, details: rows.append(
                (check, target, details))
            spec = {"shape": "list-of-paths", "target": ["source-note"]}
            check_page_contract.check_shape(
                str(root), "Domain/Page.md", "evidence_sources", spec,
                ["Domain/Source"], report)
            self.assertEqual([], rows)
            check_page_contract.check_shape(
                str(root), "Domain/Page.md", "evidence_sources", spec,
                ["Domain/Other", "Domain/Ghost"], report)
            self.assertTrue(any("expected one of source-note" in row[2]
                                for row in rows))
            self.assertTrue(any("does not resolve inside the vault" in row[2]
                                for row in rows))

    def test_sources_role_has_one_acceptance_matrix(self):
        roles = {
            "sources": {
                "titles": ["Sources"],
                "applicability": {
                    "condition": {
                        "any": [{"field": "depth",
                                 "in": ["core", "system"]}],
                    },
                },
                "binding_satisfies": {
                    "fields": ["evidence_sources"],
                    "directions": ["expression-to-canonical"],
                },
            },
        }
        contract = {
            "evidence_sources": {"direction": "evidence-input"},
            "claim_binding": {"direction": "expression-to-canonical"},
        }
        cases = (
            ("# Deep\n\nBody.\n", {"depth": "core"}, 1,
             "owes the sources role"),
            ("# Deep\n\n## Sources\n\n- A\n", {"depth": "core"}, 0,
             None),
            ("# Deep\n", {"depth": "core", "evidence_sources": ["S"]},
             0, None),
            ("# Deep\n", {"depth": "core", "claim_binding": "C"}, 0,
             None),
            ("# Deep\n", {"depth": "survey"}, 0, None),
            ("# Deep\n\n## Sources\n\nA\n\n## Sources\n\nB\n",
             {"depth": "core"}, 1, "more than one"),
        )
        for text, fields, expected_count, expected_detail in cases:
            rows = []
            check_page_contract.check_sources_role(
                ".", "Domain/Deep.md", text, fields, contract, roles,
                lambda check, target, details: rows.append(
                    (check, target, details)),
            )
            with self.subTest(fields=fields, text=text):
                self.assertEqual(expected_count, len(rows))
                if expected_detail:
                    self.assertIn(expected_detail, rows[0][2])

    def test_compiler_composes_kernel_profile_and_role_closure(self):
        _first_text, first_contract, errors = compile_contract(
            CONTRACT_DEFAULTS, verify_repeat=True)
        _second_text, second_contract, second_errors = compile_contract(
            CONTRACT_DEFAULTS)
        self.assertEqual([], errors)
        self.assertEqual([], second_errors)
        self.assertEqual(first_contract, second_contract)
        self.assertEqual("required", first_contract["fields"]["type"]["mode"])
        self.assertEqual(
            "kernel-relationship",
            first_contract["fields"]["evidence_sources"]["origin"],
        )
        self.assertEqual(
            ["Sources"],
            first_contract["section_roles"]["sources"]["titles"],
        )

        _text, configured, errors = compile_contract(CONTRACT_CONFIGURED)
        self.assertEqual([], errors)
        self.assertEqual(
            "required", configured["fields"]["last_verified"]["mode"])
        self.assertEqual(
            "profile", configured["fields"]["card_binding"]["origin"])

    def test_compiler_rejects_non_tightening_unknown_and_duplicate_fields(self):
        cases = (
            (CONTRACT_CONFIGURED.replace(
                "  - field: last_verified\n    mode: required",
                "  - field: type\n    mode: conditional\n"
                "    condition:\n      all:\n        - field: type\n"
                "          in:\n            - concept"),
             "not a tightening"),
            (CONTRACT_CONFIGURED.replace(
                "field: last_verified", "field: unheard_of"),
             "does not name a kernel base field"),
            (CONTRACT_CONFIGURED.replace(
                "field: card_binding", "field: aliases"),
             "declared twice"),
        )
        for contract, expected in cases:
            _text, _compiled, errors = compile_contract(contract)
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in error for error in errors),
                                errors)


def run_acceptance(root, admission, contract_text, *, strict=False):
    """Run the checker from an already admitted typed contract checkpoint."""
    snapshot = SimpleNamespace(read_text=lambda: contract_text)
    output = io.StringIO()
    with (
            mock.patch.object(
                compose_page_contract, "admitted_artifact",
                return_value=(snapshot, [])),
            mock.patch.object(
                compose_page_contract, "artifact_currency_errors",
                return_value=[]),
            mock.patch.object(
                profile_admission, "currency_errors", return_value=[]),
            mock.patch.object(
                metadata_execution_contract,
                "load_metadata_execution_contract", return_value=object()),
            mock.patch.object(
                metadata_property_state, "profile_gate_projection_rules",
                return_value=()),
            contextlib.redirect_stdout(output)):
        code = check_page_contract.run(
            str(root), "profile", "compiled-page-contract.yaml",
            "Domain", (), strict, None,
            authorized_admission=admission,
        )
    return code, output.getvalue()


class PageContractAcceptanceTests(unittest.TestCase):
    def test_one_contract_matrix_owns_field_modes_and_unknown_closure(self):
        contract = """schema_version: 1
fields:
  type:
    mode: required
    shape: nonempty-string
  deferred_reason:
    mode: conditional
    shape: nonempty-string
    condition:
      all:
        - field: coverage_disposition
          in:
            - deferred
  coverage_disposition:
    mode: optional
    shape: nonempty-string
  aliases:
    mode: optional
    shape: list-of-strings
  review_by:
    mode: derived
    shape: date
    persisted: false
  internal_note:
    mode: forbidden
    shape: nonempty-string
section_roles: {}
"""
        pages = {
            "Good.md": "---\ntype: concept\n---\n# Good\n",
            "Missing.md": "---\naliases:\n  - valid\n---\n# Missing\n",
            "Conditional.md": (
                "---\ntype: concept\ncoverage_disposition: deferred\n"
                "---\n# Conditional\n"),
            "Empty.md": "---\ntype: concept\naliases: []\n---\n# Empty\n",
            "Derived.md": (
                "---\ntype: concept\nreview_by: 2026-01-01\n"
                "---\n# Derived\n"),
            "Forbidden.md": (
                "---\ntype: concept\ninternal_note: hidden\n"
                "---\n# Forbidden\n"),
            "Unknown.md": (
                "---\ntype: concept\nunregistered: value\n"
                "---\n# Unknown\n"),
        }
        with compiler_workspace() as (root, admission):
            domain = root / "Domain"
            domain.mkdir()
            for name, text in pages.items():
                (domain / name).write_text(text, encoding="utf-8")
            code, output = run_acceptance(root, admission, contract)

        self.assertEqual(2, code, output)
        for expected in (
                "Missing.md:type", "Conditional.md:deferred_reason",
                "Empty.md:aliases", "Derived.md:review_by",
                "Forbidden.md:internal_note", "Unknown.md:unregistered"):
            self.assertIn(expected, output)
        self.assertNotIn("Good.md:", output)


class PageContractIntegrationTests(unittest.TestCase):
    def test_compiled_contract_is_consumed_by_one_current_page_scan(self):
        with compiler_workspace() as (root, admission):
            text, _contract, errors = compose_page_contract.compiled_artifact(
                str(root), admission,
                base_path=str(root / "kernel/applicability-base.yaml"),
                rel_path=str(root / "kernel/relationship-base.yaml"),
                sources_role_path=str(
                    root / "kernel/sources-role-base.yaml"),
            )
            self.assertEqual([], errors)
            artifact = root / "compiled-page-contract.yaml"
            artifact.write_text(text, encoding="utf-8")
            domain = root / "Domain"
            domain.mkdir()
            (domain / "Page.md").write_text(
                "---\ntype: concept\n---\n# Page\n", encoding="utf-8")

            output = io.StringIO()
            with (
                    mock.patch.object(
                        profile_admission, "currency_errors",
                        return_value=[]),
                    mock.patch.object(
                        metadata_execution_contract,
                        "load_metadata_execution_contract",
                        return_value=object()),
                    mock.patch.object(
                        metadata_property_state,
                        "profile_gate_projection_rules", return_value=()),
                    contextlib.redirect_stdout(output)):
                code = check_page_contract.run(
                    str(root), "profile", str(artifact), "Domain", (),
                    False, None, authorized_admission=admission)

        self.assertEqual(0, code, output.getvalue())
        self.assertIn("scanned 1 page(s)", output.getvalue())
        self.assertIn("every scanned page satisfies", output.getvalue())


if __name__ == "__main__":
    unittest.main()
