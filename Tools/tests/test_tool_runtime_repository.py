from Tools.platform.repository.repository import repository_source_root
import hashlib
import os
import pathlib
import sys
import tempfile
from types import SimpleNamespace
import unittest


TOOLS = pathlib.Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from Tools.platform.repository import repository
from Tools.platform.repository import path_contract


class RepositoryMechanicsTests(unittest.TestCase):
    @staticmethod
    def _target_snapshot(*, exists=True, repository_path="A.md",
                         missing_components=(), parent_repository_path="",
                         parent_dev=None, parent_ino=None, data=b"A\n"):
        return SimpleNamespace(
            exists=exists,
            repository_path=repository_path,
            missing_components=tuple(missing_components),
            parent_repository_path=parent_repository_path,
            parent_dev=parent_dev,
            parent_ino=parent_ino,
            dev=1 if exists else None,
            ino=2 if exists else None,
            mode=0o100644 if exists else None,
            nlink=1 if exists else None,
            size=len(data) if exists else None,
            mtime_ns=3 if exists else None,
            ctime_ns=4 if exists else None,
            data=data if exists else None,
        )

    def test_repository_source_root_uses_calling_tools_module(self):
        source = os.path.join(os.sep, "example", "repo", "Tools", "unit.py")
        self.assertEqual(
            os.path.join(os.sep, "example", "repo"),
            repository.repository_source_root(source),
        )

    def test_canonical_relative_path_applies_shared_shape_and_constraints(self):
        self.assertEqual(
            "Tools/example.py",
            path_contract.canonical_repository_relative_path(
                "Tools/example.py", "module", prefix="Tools/",
                suffix=".py"),
        )
        for value in ("", " Tools/example.py", "/Tools/example.py",
                      "Tools/../example.py"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                path_contract.canonical_repository_relative_path(
                    value, "module")

    def test_relative_slash_path_containment_does_not_admit_neighbors(self):
        self.assertTrue(repository.relative_path_is_within("Card", "Card"))
        self.assertTrue(repository.relative_path_is_within(
            "Card/R01.md", "Card"))
        self.assertFalse(repository.relative_path_is_within(
            "Card-old/R01.md", "Card"))
        self.assertTrue(repository.relative_path_is_within_any(
            "Read Set/R01.md", ("Card", "Read Set")))

    def test_repository_source_root_canonicalizes_explicit_root(self):
        with tempfile.TemporaryDirectory() as root:
            value = os.path.join(root, "nested", os.pardir)
            self.assertEqual(
                os.path.realpath(root),
                repository.repository_source_root("unused.py", value),
            )

    def test_file_bytes_sha256_hashes_exact_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "artifact.bin")
            payload = b"one\x00two\n"
            with open(path, "wb") as handle:
                handle.write(payload)
            self.assertEqual(
                "sha256:" + hashlib.sha256(payload).hexdigest(),
                repository.file_bytes_sha256(path),
            )

    def test_repository_relative_spelling_preserves_projection_semantics(self):
        with tempfile.TemporaryDirectory() as root:
            inside = os.path.join(root, "Tools", "compiled", "artifact.json")
            outside = os.path.join(os.path.dirname(root), "outside.json")
            self.assertEqual(
                "Tools/compiled/artifact.json",
                repository.repository_relative_spelling(root, inside),
            )
            self.assertEqual(
                os.path.abspath(outside),
                repository.repository_relative_spelling(root, outside),
            )
            self.assertEqual(
                os.path.abspath(root),
                repository.repository_relative_spelling(root, root),
            )

    def test_repository_input_snapshot_binds_canonical_path_and_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            nested = os.path.join(root, "kernel")
            os.mkdir(nested)
            path = os.path.join(nested, "contract.yaml")
            payload = b"schema_version: 1\n"
            with open(path, "wb") as handle:
                handle.write(payload)

            relative, snapshot = repository.repository_input_snapshot(
                root, os.path.join("kernel", "contract.yaml"), "contract")

            self.assertEqual("kernel/contract.yaml", relative)
            self.assertEqual(relative, snapshot.repository_path)
            self.assertEqual(payload, snapshot.data)

    def test_repository_input_snapshot_rejects_outside_path(self):
        with tempfile.TemporaryDirectory() as root:
            with tempfile.NamedTemporaryFile() as outside:
                with self.assertRaisesRegex(
                        ValueError, "contract path escapes the repository"):
                    repository.repository_input_snapshot(
                        root, outside.name, "contract")

    def test_existing_target_comparison_binds_identity_stat_and_bytes(self):
        before = self._target_snapshot()
        same = self._target_snapshot()
        changed = self._target_snapshot(data=b"B\n")
        missing = self._target_snapshot(
            exists=False, missing_components=("A.md",),
            parent_repository_path="", parent_dev=1, parent_ino=2)

        self.assertTrue(repository.same_existing_target_snapshot(before, same))
        self.assertFalse(
            repository.same_existing_target_snapshot(before, changed))
        self.assertFalse(
            repository.same_existing_target_snapshot(missing, missing))

    def test_repository_existing_comparison_also_binds_logical_path(self):
        before = self._target_snapshot(repository_path="A.md")
        renamed = self._target_snapshot(repository_path="B.md")

        self.assertTrue(
            repository.same_existing_target_snapshot(before, renamed))
        self.assertFalse(
            repository.same_existing_repository_target_snapshot(
                before, renamed))

    def test_missing_target_comparison_binds_tail_and_parent_identity(self):
        before = self._target_snapshot(
            exists=False, repository_path="Future/Nested.md",
            missing_components=("Future", "Nested.md"),
            parent_repository_path="", parent_dev=1, parent_ino=2)
        same = self._target_snapshot(
            exists=False, repository_path="Future/Nested.md",
            missing_components=("Future", "Nested.md"),
            parent_repository_path="", parent_dev=1, parent_ino=2)
        moved_parent = self._target_snapshot(
            exists=False, repository_path="Future/Nested.md",
            missing_components=("Future", "Nested.md"),
            parent_repository_path="", parent_dev=1, parent_ino=3)

        self.assertTrue(repository.same_missing_target_snapshot(before, same))
        self.assertFalse(
            repository.same_missing_target_snapshot(before, moved_parent))
        self.assertFalse(repository.same_missing_target_snapshot(
            self._target_snapshot(), self._target_snapshot()))

    def test_resolve_markdown_reference_is_suffix_tolerant_and_root_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            page = os.path.join(root, "A.md")
            pathlib.Path(page).write_text("# A\n", encoding="utf-8")
            self.assertEqual(
                page,
                repository.resolve_markdown_reference(root, "A"),
            )
            self.assertEqual(
                page,
                repository.resolve_markdown_reference(root, "A.md"),
            )
            self.assertIsNone(
                repository.resolve_markdown_reference(root, "../A.md"),
            )

    def test_path_is_within_any_includes_roots_and_descendants(self):
        roots = [os.path.join(os.sep, "repo", "ignored")]
        self.assertTrue(repository.path_is_within_any(roots[0], roots))
        self.assertTrue(repository.path_is_within_any(
            os.path.join(roots[0], "page.md"), roots))
        self.assertFalse(repository.path_is_within_any(
            os.path.join(os.sep, "repo", "ignored-neighbor"), roots))


if __name__ == "__main__":
    unittest.main()
