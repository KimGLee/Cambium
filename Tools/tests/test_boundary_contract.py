"""Page-boundary value, Gate Receipt, and checker/renderer seam tests."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import Tools.knowledge.metadata.compose_page_contract as compose_page_contract
import Tools.knowledge.structure.boundary_contract as boundary_contract
import Tools.knowledge.structure.check_boundary_contract as boundary_checker
import Tools.knowledge.structure.render_boundary_projection as boundary_renderer
import Tools.platform.common.kblib as kblib


CONTRACT_TEXT = """fields: {}
boundary_projection:
  labels:
    owns: Owned here
    excludes: Owned elsewhere
"""

ALPHA = """---
boundary:
  owns:
    - alpha-core
    - alpha-group:
        - alpha-sub
  excludes:
    - concern: beta-core
      owner: Domain/Beta
  goals:
    - Keep alpha coherent.
  non_goals:
    - Own beta.
---
# Alpha

<!-- boundary-projection:begin -->
<!-- boundary-projection:end -->
"""

BETA = """---
boundary:
  owns:
    - beta-core
---
# Beta
"""


def capture(callable_, *args, **kwargs):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), \
            contextlib.redirect_stderr(output):
        code = callable_(*args, **kwargs)
    return code, output.getvalue()


class _ContractSnapshot:

    sha256 = "sha256:" + "a" * 64

    def read_text(self):
        return CONTRACT_TEXT


class BoundaryValueContractTests(unittest.TestCase):

    def test_shape_slug_projection_and_invalid_matrix_share_one_owner(self):
        valid = kblib.parse_yaml_subset(
            kblib.extract_frontmatter(ALPHA))["boundary"]
        self.assertEqual([], kblib.validate_boundary_shape(valid))
        self.assertEqual(
            ["alpha-core", "alpha-group", "alpha-sub"],
            kblib.boundary_owned_slugs(valid))
        rendered = kblib.render_boundary_projection_lines(
            valid, {"owns": "Owned here", "excludes": "Owned elsewhere"})
        self.assertEqual(rendered,
                         kblib.render_boundary_projection_lines(
                             valid, {"owns": "Owned here",
                                     "excludes": "Owned elsewhere"}))
        self.assertEqual(kblib.BOUNDARY_PROJECTION_BEGIN, rendered[0])
        self.assertEqual(kblib.BOUNDARY_PROJECTION_END, rendered[-1])

        invalid = (
            {"owns": ["valid"], "surplus": []},
            {"owns": ["Bad_Slug"]},
            {"owns": ["same", "same"]},
            {"owns": ["same"], "excludes": [{
                "concern": "same", "owner": "Domain/Other"}]},
            {"owns": [{"group": []}]},
            {"owns": ["valid"], "goals": [""]},
        )
        for value in invalid:
            with self.subTest(value=value):
                self.assertTrue(kblib.validate_boundary_shape(value))


class BoundaryReceiptContractTests(unittest.TestCase):

    def test_current_receipt_identity_accepts_one_gate_and_rejects_drift(self):
        receipt = kblib.make_receipt(
            boundary_checker.TOOL,
            boundary_checker.TOOL_VERSION,
            boundary_checker.GATE_CHECK,
            "boundary-contract",
            "pass",
            "fixture",
            1,
            receipt_type_id=boundary_checker.RECEIPT_TYPE_ID)
        receipt["gate_id"] = boundary_checker.GATE_ID
        self.assertEqual([], boundary_checker.current_receipt_errors(receipt))

        mutations = (
            ("gate_id", "another-gate"),
            ("receipt_type_id", "another-receipt-type"),
            ("tool", "another-tool"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = dict(receipt)
                changed[field] = value
                self.assertTrue(
                    boundary_checker.current_receipt_errors(changed))


class BoundaryInterpretationContractTests(unittest.TestCase):

    def test_shared_frontmatter_marker_and_label_interpretation_is_closed(self):
        block, parse_ok = boundary_contract.boundary_block_from_text(ALPHA)
        self.assertTrue(parse_ok)
        self.assertEqual(
            ["alpha-core", "alpha-group", "alpha-sub"],
            kblib.boundary_owned_slugs(block),
        )
        self.assertEqual(
            (None, True),
            boundary_contract.boundary_block_from_text("# No frontmatter\n"),
        )
        self.assertEqual(
            (None, False),
            boundary_contract.boundary_block_from_text("---\n: bad\n---\n"),
        )

        labels, error = boundary_contract.projection_labels_from_text(
            CONTRACT_TEXT
        )
        self.assertIsNone(error)
        self.assertEqual("Owned here", labels["owns"])
        self.assertIsNone(
            boundary_contract.projection_labels_from_text("fields: []\n")[0]
        )

        self.assertEqual(
            (1, 3, None),
            boundary_contract.projection_marker_pair(
                ["before", kblib.BOUNDARY_PROJECTION_BEGIN, "body",
                 kblib.BOUNDARY_PROJECTION_END]
            ),
        )
        malformed = (
            [kblib.BOUNDARY_PROJECTION_END,
             kblib.BOUNDARY_PROJECTION_BEGIN],
            [kblib.BOUNDARY_PROJECTION_BEGIN,
             kblib.BOUNDARY_PROJECTION_BEGIN,
             kblib.BOUNDARY_PROJECTION_END],
        )
        for lines in malformed:
            with self.subTest(lines=lines):
                self.assertIsNotNone(
                    boundary_contract.projection_marker_pair(lines)[2]
                )


class BoundaryGateIntegrationTests(unittest.TestCase):

    def test_renderer_output_is_accepted_and_duplicate_ownership_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            domain = root / "Domain"
            domain.mkdir()
            alpha = domain / "Alpha.md"
            beta = domain / "Beta.md"
            alpha.write_text(ALPHA, encoding="utf-8")
            beta.write_text(BETA, encoding="utf-8")
            admission = SimpleNamespace(
                manifest_repo_path="profiles/fixture/profile.toml")
            snapshot = _ContractSnapshot()
            patches = (
                mock.patch.object(
                    boundary_checker.profile_admission, "admit_profile",
                    return_value=(admission, [])),
                mock.patch.object(
                    boundary_renderer.profile_admission, "admit_profile",
                    return_value=(admission, [])),
                mock.patch.object(
                    compose_page_contract, "admitted_artifact",
                    return_value=(snapshot, [])),
                mock.patch.object(
                    compose_page_contract, "artifact_currency_errors",
                    return_value=[]),
                mock.patch.object(
                    boundary_checker.profile_admission, "currency_errors",
                    return_value=[]),
                mock.patch.object(
                    boundary_renderer.profile_admission, "currency_errors",
                    return_value=[]),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                render_code, render_output = capture(
                    boundary_renderer.main,
                    [str(root), "--profile", "profiles/fixture",
                     "--contract", "contract.yaml", "--scope", "Domain",
                     "--apply"])
                accepted_code, accepted_output = capture(
                    boundary_checker.run,
                    str(root), "profiles/fixture", "contract.yaml",
                    "Domain", [], False, None)

                beta.write_text(
                    BETA.replace(
                        "    - beta-core",
                        "    - beta-core\n    - alpha-core"),
                    encoding="utf-8")
                advisory_code, advisory_output = capture(
                    boundary_checker.run,
                    str(root), "profiles/fixture", "contract.yaml",
                    "Domain", [], False, None)
                strict_code, strict_output = capture(
                    boundary_checker.run,
                    str(root), "profiles/fixture", "contract.yaml",
                    "Domain", [], True, None)

        self.assertEqual(0, render_code, render_output)
        self.assertEqual(0, accepted_code, accepted_output)
        self.assertEqual(2, advisory_code, advisory_output)
        self.assertIn("boundary-uniqueness", advisory_output)
        self.assertEqual(1, strict_code, strict_output)
        self.assertIn("boundary-uniqueness", strict_output)


if __name__ == "__main__":
    unittest.main()
