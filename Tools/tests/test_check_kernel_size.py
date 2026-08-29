"""Tool-owned Kernel leaf-size policy and deterministic checker tests."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
SCRIPT = TOOLS / "check_kernel_size.py"

sys.path.insert(0, str(TOOLS))
import check_kernel_size  # noqa: E402
import kblib  # noqa: E402


def leaf(root, name, size):
    path = root / "kernel" / "K01 Demo" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def policy(exceptions=None, outside=None):
    return {
        "target_bytes": 5 * 1024,
        "soft_cap_bytes": 6 * 1024,
        "leaf_re": re.compile(
            r"kernel/K[0-9]{2} [^/]+/[0-9]{2} .+[.]md\Z"),
        "exceptions": exceptions or {},
        "outside_cap": outside or {},
    }


class ShippedPolicyTests(unittest.TestCase):
    def test_shipped_policy_is_closed_and_uses_the_preserved_budget(self):
        loaded = check_kernel_size.load_policy(REPOSITORY)

        self.assertEqual(5 * 1024, loaded["target_bytes"])
        self.assertEqual(6 * 1024, loaded["soft_cap_bytes"])
        self.assertEqual(22, len(loaded["exceptions"]))
        self.assertEqual(2, len(loaded["outside_cap"]))

    def test_every_machine_disposition_has_one_human_engineering_record(self):
        loaded = check_kernel_size.load_policy(REPOSITORY)
        expected = {
            row["record_id"]: path
            for path, row in {
                **loaded["exceptions"], **loaded["outside_cap"]}.items()
        }
        text = (TOOLS / "kernel-size-exceptions.md").read_text(
            encoding="utf-8")
        observed = {}
        for line in text.splitlines():
            match = re.match(r"^\| `(EXC|OUT)-([0-9]{3})` \|", line)
            if match is None:
                continue
            record_id = "%s-%s" % match.groups()
            self.assertNotIn(record_id, observed)
            observed[record_id] = line
        self.assertEqual(set(expected), set(observed))
        for record_id, path in expected.items():
            self.assertIn(path[:-3], observed[record_id])

    def test_shipped_tree_has_no_size_finding(self):
        errors, candidates, summary = check_kernel_size.evaluate(REPOSITORY)

        self.assertEqual([], errors)
        self.assertEqual([], candidates)
        self.assertGreater(summary["leaf_count"], 0)


class PolicyShapeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "Tools").mkdir()

    def write(self, document):
        path = self.root / check_kernel_size.POLICY_PATH
        path.write_text(kblib.canonical_yaml(document), encoding="utf-8")

    def base(self):
        return {
            "schema_version": 1,
            "policy_id": "kernel-leaf-size-v1",
            "kernel_root": "kernel",
            "leaf_path_regex":
                "kernel/K[0-9]{2} [^/]+/[0-9]{2} .+[.]md",
            "engineering_record": "Tools/kernel-size-exceptions.md",
            "target_bytes": 5 * 1024,
            "soft_cap_bytes": 6 * 1024,
            "exceptions": [],
            "outside_cap": [],
        }

    def exception(self, path="kernel/K01 Demo/01 Big.md"):
        return {
            "path": path,
            "measured_bytes": 7000,
            "growth_cap_bytes": 7 * 1024,
            "record_id": "EXC-001",
        }

    def test_unknown_top_level_field_fails_closed(self):
        document = self.base()
        document["whatever"] = True
        self.write(document)

        with self.assertRaisesRegex(
                check_kernel_size.KernelSizePolicyError, "extra"):
            check_kernel_size.load_policy(self.root)

    def test_duplicate_exception_path_fails_closed(self):
        document = self.base()
        document["exceptions"] = [self.exception(), dict(
            self.exception(), record_id="EXC-002")]
        self.write(document)

        with self.assertRaisesRegex(
                check_kernel_size.KernelSizePolicyError, "more than once"):
            check_kernel_size.load_policy(self.root)

    def test_exception_and_outside_cap_are_exclusive(self):
        document = self.base()
        document["exceptions"] = [self.exception()]
        document["outside_cap"] = [{
            "path": self.exception()["path"], "record_id": "OUT-001"}]
        self.write(document)

        with self.assertRaisesRegex(
                check_kernel_size.KernelSizePolicyError, "both exception"):
            check_kernel_size.load_policy(self.root)

    def test_recorded_measurement_cannot_already_exceed_the_cap(self):
        document = self.base()
        document["exceptions"] = [dict(
            self.exception(), measured_bytes=8 * 1024)]
        self.write(document)

        with self.assertRaisesRegex(
                check_kernel_size.KernelSizePolicyError,
                "measurement exceeds"):
            check_kernel_size.load_policy(self.root)

    def test_non_leaf_paths_are_rejected(self):
        document = self.base()
        document["exceptions"] = [self.exception("kernel/K01 Demo.md")]
        self.write(document)

        with self.assertRaisesRegex(
                check_kernel_size.KernelSizePolicyError, "not a numbered"):
            check_kernel_size.load_policy(self.root)

    def test_missing_engineering_record_fails_closed(self):
        self.write(self.base())

        with self.assertRaisesRegex(
                check_kernel_size.KernelSizePolicyError,
                "missing, unsafe, or unreadable"):
            check_kernel_size.load_policy(self.root)

    def test_empty_exception_follow_up_fails_closed(self):
        document = self.base()
        document["exceptions"] = [self.exception()]
        self.write(document)
        (self.root / "Tools/kernel-size-exceptions.md").write_text(
            "| `EXC-001` | [[kernel/K01 Demo/01 Big\\|Big]] | reason | |\n",
            encoding="utf-8")

        with self.assertRaisesRegex(
                check_kernel_size.KernelSizePolicyError,
                "empty rationale or follow-up"):
            check_kernel_size.load_policy(self.root)


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "kernel").mkdir()
        self.path = "kernel/K01 Demo/01 Big.md"

    def exception(self, measured, cap=7 * 1024):
        return {self.path: {
            "path": self.path,
            "measured_bytes": measured,
            "growth_cap_bytes": cap,
            "record_id": "EXC-001",
        }}

    def test_leaf_inside_soft_cap_needs_no_disposition(self):
        leaf(self.root, "01 Big.md", 100)

        errors, candidates, _summary = check_kernel_size.evaluate(
            self.root, policy())

        self.assertEqual([], errors)
        self.assertEqual([], candidates)

    def test_over_growth_cap_is_an_error(self):
        leaf(self.root, "01 Big.md", 7 * 1024 + 1)

        errors, candidates, _summary = check_kernel_size.evaluate(
            self.root, policy(self.exception(7000)))

        self.assertEqual(1, len(errors))
        self.assertIn("growth cap", errors[0])
        self.assertEqual(1, len(candidates))

    def test_undeclared_soft_cap_breach_is_a_candidate(self):
        leaf(self.root, "01 Big.md", 6 * 1024 + 1)

        errors, candidates, _summary = check_kernel_size.evaluate(
            self.root, policy())

        self.assertEqual([], errors)
        self.assertEqual(1, len(candidates))
        self.assertIn("soft cap", candidates[0])

    def test_measurement_drift_is_a_candidate(self):
        leaf(self.root, "01 Big.md", 6500)

        errors, candidates, _summary = check_kernel_size.evaluate(
            self.root, policy(self.exception(6400)))

        self.assertEqual([], errors)
        self.assertEqual(1, len(candidates))
        self.assertIn("re-measurement", candidates[0])

    def test_outside_cap_leaf_is_not_compared_with_the_soft_cap(self):
        leaf(self.root, "01 Big.md", 20 * 1024)
        outside = {self.path: {
            "path": self.path, "record_id": "OUT-001"}}

        errors, candidates, _summary = check_kernel_size.evaluate(
            self.root, policy(outside=outside))

        self.assertEqual([], errors)
        self.assertEqual([], candidates)

    def test_registered_missing_leaf_is_an_error(self):
        errors, _candidates, _summary = check_kernel_size.evaluate(
            self.root, policy(self.exception(7000)))

        self.assertEqual(1, len(errors))
        self.assertIn("not a current numbered Kernel leaf", errors[0])


class CommandTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        shutil.copytree(REPOSITORY / "kernel", root / "kernel")
        shutil.copytree(
            TOOLS, root / "Tools",
            ignore=shutil.ignore_patterns(
                "tests", "compiled", "__pycache__", "receipts"))
        return root

    def run_tool(self, root, *extra):
        return subprocess.run(
            [sys.executable, str(root / "Tools/check_kernel_size.py"),
             str(root), *extra], capture_output=True, text=True, check=False)

    def test_json_output_is_closed_over_the_same_result(self):
        root = self.fixture()

        result = self.run_tool(root, "--json")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(0, payload["error_count"])
        self.assertEqual(0, payload["candidate_count"])

    def test_missing_policy_fails_closed(self):
        root = self.fixture()
        (root / check_kernel_size.POLICY_PATH).unlink()

        result = self.run_tool(root)

        self.assertEqual(1, result.returncode)
        self.assertIn("[FAIL]", result.stdout)


if __name__ == "__main__":
    unittest.main()
