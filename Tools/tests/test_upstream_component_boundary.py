"""Ownership tests for the current upstream component distribution boundary."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS.parent) not in sys.path:
    sys.path.insert(0, str(TOOLS.parent))

import Tools.platform.distribution.upstream_component_boundary as boundary  # noqa: E402
from Tools.tests.support.upstream_component_boundary_fixture import (  # noqa: E402
    BOUNDARY_TEXT,
    SYNTHETIC_REVISION,
    SyntheticUpstreamSnapshot,
    build_real_git_pair,
    write_component_tree,
)


CHECKER = TOOLS / "check_upstream_components.py"


class DistributionBoundaryContractTests(unittest.TestCase):
    def test_distribution_only_contract_is_closed_and_cannot_omit_owners(self):
        declared = boundary._distribution_only_paths(
            (TOOLS.parent / boundary.DISTRIBUTION_BOUNDARY_PATH).read_bytes())
        self.assertEqual(tuple(sorted(set(declared))), declared)
        self.assertTrue(boundary._may_be_omitted(
            "Tools/tests/example.py", declared))
        for required in boundary.IMMUTABLE_FILE_PATHS:
            self.assertFalse(boundary._may_be_omitted(required, declared))

        invalid_documents = (
            BOUNDARY_TEXT + "unexpected: true\n",
            """schema_version: 1
distribution_only:
  - path: Tools/tests/
    reason: ""
""",
            """schema_version: 1
distribution_only:
  - path: Tools/tests/
    reason: "first"
  - path: Tools/tests/
    reason: "duplicate"
""",
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(boundary.ComponentBoundaryError):
                    boundary._distribution_only_paths(
                        document.encode("utf-8"))

    def test_manifest_projection_accepts_only_one_clean_report(self):
        row = boundary.ComponentRow(
            path="Card/owner.md",
            git_blob_oid="b" * 40,
            sha256="sha256:" + "c" * 64,
            presence="present",
        )
        clean = boundary.ComponentBoundaryReport(
            upstream_revision_id=SYNTHETIC_REVISION,
            distribution_boundary_sha256="sha256:" + "d" * 64,
            rows=(row,),
            errors=(),
        )
        rendered = boundary.manifest_text(clean)
        self.assertIn(
            "# upstream_revision_id: %s" % SYNTHETIC_REVISION,
            rendered)
        self.assertTrue(rendered.endswith(
            "Card/owner.md\t%s\t%s\tpresent\n" %
            (row.git_blob_oid, row.sha256)))

        failing = boundary.ComponentBoundaryReport(
            upstream_revision_id=clean.upstream_revision_id,
            distribution_boundary_sha256=clean.distribution_boundary_sha256,
            rows=(),
            errors=("required component is missing: Card/owner.md",),
        )
        with self.assertRaisesRegex(
                boundary.ComponentBoundaryError, "failing byte boundary"):
            boundary.manifest_text(failing)


class UpstreamComponentEvaluatorContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = SyntheticUpstreamSnapshot()

    def adopter(self, name):
        adopter = self.root / name
        write_component_tree(adopter)
        return adopter

    def test_current_snapshot_allows_only_upstream_declared_omissions(self):
        adopter = self.adopter("current")
        (adopter / "profiles/adopter/local.yaml").write_text(
            "adopter: value\n", encoding="utf-8")
        report = self.snapshot.evaluate(adopter)
        self.assertEqual((), report.errors)
        self.assertEqual(SYNTHETIC_REVISION, report.upstream_revision_id)
        self.assertEqual(
            ["Tools/tests/distribution_test.py"],
            [row.path for row in report.rows
             if row.presence == "omitted-distribution-only"])

    def test_drift_and_namespace_matrix_fails_closed(self):
        def changed(root):
            (root / "Card/owner.md").write_text(
                "changed\n", encoding="utf-8")

        def missing(root):
            (root / "Read Set/owner.md").unlink()

        def local_allowlist(root):
            (root / "Card/owner.md").unlink()
            (root / boundary.DISTRIBUTION_BOUNDARY_PATH).write_text(
                BOUNDARY_TEXT +
                "  - path: Card/\n    reason: \"local exception\"\n",
                encoding="utf-8")

        def changed_distribution_only(root):
            path = root / "Tools/tests/distribution_test.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("changed\n", encoding="utf-8")

        def unregistered(root):
            (root / "Tools/local_override.py").write_text(
                "override = True\n", encoding="utf-8")

        cases = [
            ("changed", changed,
             "component bytes differ from upstream: Card/owner.md"),
            ("missing", missing,
             "required component is missing: Read Set/owner.md"),
            ("local-allowlist", local_allowlist,
             "required component is missing: Card/owner.md"),
            ("changed-distribution-only", changed_distribution_only,
             "component bytes differ from upstream: "
             "Tools/tests/distribution_test.py"),
            ("unregistered", unregistered,
             "unregistered file in immutable component: "
             "Tools/local_override.py"),
        ]
        if hasattr(os, "symlink"):
            def symlink(root):
                target = root / "Card/owner.md"
                original = self.root / "original-card.md"
                original.write_bytes(
                    self.snapshot.source["Card/owner.md"])
                target.unlink()
                os.symlink(original, target)

            cases.append((
                "symlink", symlink, "unsafe component Card/owner.md:"))

        for name, mutate, expected in cases:
            with self.subTest(case=name):
                adopter = self.adopter(name)
                mutate(adopter)
                report = self.snapshot.evaluate(adopter)
                self.assertTrue(
                    any(error.startswith(expected) for error in report.errors),
                    report.errors)


class UpstreamComponentCliIntegrationTests(unittest.TestCase):
    def test_public_cli_evaluates_one_real_snapshot_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            upstream, adopter, revision = build_real_git_pair(temporary)
            completed = subprocess.run(
                [
                    sys.executable, str(CHECKER), str(adopter),
                    "--upstream-root", str(upstream),
                    "--revision", revision,
                    "--write-manifest", "--json",
                ],
                text=True, capture_output=True, check=False)
            self.assertEqual(
                0, completed.returncode,
                completed.stdout + completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual("PASS", result["result"])
            self.assertEqual(revision, result["upstream_revision_id"])
            manifest = adopter / boundary.DEFAULT_MANIFEST_PATH
            self.assertIn(
                "# upstream_revision_id: %s" % revision,
                manifest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
