"""Kernel leaf-size machine contract and budget acceptance tests."""

import copy
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import Tools.platform.common.kblib as kblib
import Tools.platform.distribution.check_kernel_size as check_kernel_size


LEAF_PATH = "kernel/K01 Demo/01 Big.md"


def policy_document():
    return {
        "schema_version": 1,
        "policy_id": "kernel-leaf-size-v1",
        "kernel_root": "kernel",
        "leaf_path_regex":
            r"kernel/K[0-9]{2} [^/]+/[0-9]{2} .+[.]md",
        "engineering_record": "Tools/kernel-size-exceptions.md",
        "target_bytes": 5 * 1024,
        "soft_cap_bytes": 6 * 1024,
        "exceptions": [{
            "path": LEAF_PATH,
            "measured_bytes": 6500,
            "growth_cap_bytes": 7 * 1024,
            "record_id": "EXC-001",
        }],
        "outside_cap": [],
    }


def compiled_policy(*, exceptions=None, outside=None):
    return {
        "target_bytes": 5 * 1024,
        "soft_cap_bytes": 6 * 1024,
        "leaf_re": re.compile(
            r"kernel/K[0-9]{2} [^/]+/[0-9]{2} .+[.]md\Z"),
        "exceptions": exceptions or {},
        "outside_cap": outside or {},
    }


def exception_row(*, measured=6500, cap=7 * 1024):
    return {
        "path": LEAF_PATH,
        "measured_bytes": measured,
        "growth_cap_bytes": cap,
        "record_id": "EXC-001",
    }


class KernelSizePolicyContractTests(unittest.TestCase):

    def test_closed_machine_contract_accepts_valid_and_rejects_invalid_forms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "Tools"
            tools.mkdir()
            policy_path = root / check_kernel_size.POLICY_PATH
            record_path = tools / "kernel-size-exceptions.md"
            record_path.write_text(
                "| `EXC-001` | [[kernel/K01 Demo/01 Big\\|Big]] | "
                "bounded exception | split follow-up |\n",
                encoding="utf-8")

            valid = policy_document()
            policy_path.write_text(
                kblib.canonical_yaml(valid), encoding="utf-8")
            loaded = check_kernel_size.load_policy(root)
            self.assertEqual(5 * 1024, loaded["target_bytes"])
            self.assertEqual(6 * 1024, loaded["soft_cap_bytes"])
            self.assertEqual({LEAF_PATH}, set(loaded["exceptions"]))

            invalid = []
            extra = copy.deepcopy(valid)
            extra["surplus"] = True
            invalid.append((extra, "closed contract"))

            duplicate = copy.deepcopy(valid)
            duplicate["exceptions"].append(dict(
                duplicate["exceptions"][0], record_id="EXC-002"))
            invalid.append((duplicate, "registered more than once"))

            overlap = copy.deepcopy(valid)
            overlap["outside_cap"] = [{
                "path": LEAF_PATH, "record_id": "OUT-001"}]
            invalid.append((overlap, "both exception and outside-cap"))

            over_cap = copy.deepcopy(valid)
            over_cap["exceptions"][0]["measured_bytes"] = 8 * 1024
            invalid.append((over_cap, "measurement exceeds"))

            non_leaf = copy.deepcopy(valid)
            non_leaf["exceptions"][0]["path"] = "kernel/K01 Demo.md"
            invalid.append((non_leaf, "not a numbered Kernel leaf"))

            for document, expected in invalid:
                with self.subTest(expected=expected):
                    policy_path.write_text(
                        kblib.canonical_yaml(document), encoding="utf-8")
                    with self.assertRaisesRegex(
                            check_kernel_size.KernelSizePolicyError,
                            expected):
                        check_kernel_size.load_policy(root)


class KernelSizeBudgetPredicateTests(unittest.TestCase):

    def test_measurement_matrix_has_one_deterministic_disposition(self):
        exception = exception_row()
        outside = {LEAF_PATH: {
            "path": LEAF_PATH, "record_id": "OUT-001"}}
        cases = (
            ("within-soft-cap", {LEAF_PATH: 100}, compiled_policy(),
             0, 0, None),
            ("undeclared-soft-cap", {LEAF_PATH: 6 * 1024 + 1},
             compiled_policy(), 0, 1, "soft cap"),
            ("recorded-exception", {LEAF_PATH: 6500},
             compiled_policy(exceptions={LEAF_PATH: exception}),
             0, 0, None),
            ("measurement-drift", {LEAF_PATH: 6501},
             compiled_policy(exceptions={LEAF_PATH: exception}),
             0, 1, "re-measurement"),
            ("growth-cap-breach", {LEAF_PATH: 7 * 1024 + 1},
             compiled_policy(exceptions={LEAF_PATH: exception}),
             1, 1, "growth cap"),
            ("outside-cap", {LEAF_PATH: 20 * 1024},
             compiled_policy(outside=outside), 0, 0, None),
            ("registered-missing", {},
             compiled_policy(exceptions={LEAF_PATH: exception}),
             1, 0, "not a current numbered Kernel leaf"),
        )
        for name, measured, policy, error_count, candidate_count, phrase \
                in cases:
            with self.subTest(name=name), mock.patch.object(
                    check_kernel_size, "discover_leaf_sizes",
                    return_value=measured):
                errors, candidates, summary = check_kernel_size.evaluate(
                    "unused", policy)
                self.assertEqual(error_count, len(errors))
                self.assertEqual(candidate_count, len(candidates))
                self.assertEqual(len(measured), summary["leaf_count"])
                self.assertEqual(error_count, summary["error_count"])
                self.assertEqual(candidate_count,
                                 summary["candidate_count"])
                if phrase:
                    self.assertIn(phrase, "\n".join(errors + candidates))


class KernelSizeCliIntegrationTests(unittest.TestCase):

    def test_minimal_repository_reports_one_numbered_leaf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            leaf = root / LEAF_PATH
            leaf.parent.mkdir(parents=True)
            leaf.write_bytes(b"x" * 100)
            tools = root / "Tools"
            tools.mkdir()
            document = policy_document()
            document["exceptions"] = []
            (root / check_kernel_size.POLICY_PATH).write_text(
                kblib.canonical_yaml(document), encoding="utf-8")
            (tools / "kernel-size-exceptions.md").write_text(
                "# No active exceptions\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                code = check_kernel_size.main([str(root), "--json"])

        self.assertEqual(0, code)
        payload = json.loads(output.getvalue())
        self.assertEqual(1, payload["leaf_count"])
        self.assertEqual(0, payload["exception_count"])
        self.assertEqual(0, payload["outside_cap_count"])
        self.assertEqual([], payload["errors"])
        self.assertEqual([], payload["candidates"])


if __name__ == "__main__":
    unittest.main()
