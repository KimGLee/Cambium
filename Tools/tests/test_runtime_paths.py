"""Owned tests for the current adopter-runtime path registry."""

import ast
from pathlib import Path
import re
import tempfile
import unittest

import Tools.execution.task_runtime.runtime_paths as runtime_paths


TOOLS = Path(__file__).resolve().parents[1]
RUNTIME_PATH_LITERAL = re.compile(r"\.cambium(?:/[^\s]+)*\Z")
STABLE_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


def _within(path, namespace):
    return path == namespace or path.startswith(namespace + "/")


class RuntimePathRegistryContractTests(unittest.TestCase):
    """Contract: one current closed registry owns every physical spelling."""

    def test_registry_is_unique_closed_and_instance_local(self):
        objects = runtime_paths.RUNTIME_OBJECTS
        self.assertTrue(objects)
        self.assertEqual(len(objects), len({entry.path for entry in objects.values()}))
        self.assertEqual(
            set(runtime_paths.CATEGORY_ROOTS),
            {entry.category for entry in objects.values()})

        for object_id, entry in objects.items():
            with self.subTest(runtime_object_id=object_id):
                self.assertRegex(object_id, STABLE_ID)
                self.assertTrue(_within(entry.path, runtime_paths.RUNTIME_ROOT))
                self.assertTrue(any(
                    _within(entry.path, root)
                    for root in runtime_paths.roots_for(entry.category)
                ))

        cold = [
            entry for entry in objects.values()
            if _within(entry.path, runtime_paths.RECEIPT_COLD_ROOT)
        ]
        self.assertTrue(cold)
        self.assertLessEqual(
            {entry.category for entry in cold},
            {runtime_paths.EVIDENCE, runtime_paths.RECOVERY})

        self.assertLessEqual(
            runtime_paths.PRE_TASK_REQUIRED_FILE_OBJECT_IDS,
            runtime_paths.PRE_TASK_FILE_OBJECT_IDS)
        self.assertLessEqual(
            runtime_paths.PRE_TASK_FILE_OBJECT_IDS, set(objects))
        self.assertEqual(
            {objects[object_id].path
             for object_id in runtime_paths.PRE_TASK_FILE_OBJECT_IDS},
            runtime_paths.PRE_TASK_FILE_PATHS)
        self.assertEqual(
            tuple(
                path[len(runtime_paths.RUNTIME_ROOT) + 1:]
                for path in runtime_paths.TASK_RUNTIME_ROOTS),
            runtime_paths.TASK_RUNTIME_DIRECTORIES)

    def test_resolution_accepts_only_exact_current_identities(self):
        root_reference = runtime_paths.path_reference_for("runtime-root")
        self.assertEqual(runtime_paths.RUNTIME_ROOT, root_reference.path)
        self.assertEqual("namespace", root_reference.constraint)

        for object_id, entry in runtime_paths.RUNTIME_OBJECTS.items():
            with self.subTest(runtime_object_id=object_id):
                self.assertEqual(entry.path, runtime_paths.path_for(object_id))
                reference = runtime_paths.path_reference_for(object_id)
                self.assertEqual(object_id, reference.runtime_path_id)
                self.assertEqual(entry.path, reference.path)
                for candidate in (
                        entry.path, object_id.upper(), object_id + "-v0"):
                    with self.assertRaises(KeyError):
                        runtime_paths.path_for(candidate)
                    with self.assertRaises(KeyError):
                        runtime_paths.path_reference_for(candidate)

    def test_dynamic_children_require_a_registered_namespace_and_safe_leaf(self):
        directory_entries = {
            object_id: entry
            for object_id, entry in runtime_paths.RUNTIME_OBJECTS.items()
            if object_id.endswith("-root")
        }
        self.assertTrue(directory_entries)
        for object_id, entry in directory_entries.items():
            with self.subTest(runtime_object_id=object_id):
                self.assertEqual(
                    entry.path + "/leaf.yaml",
                    runtime_paths.child_path(entry.path, "leaf.yaml"))

        file_entry = next(
            entry for object_id, entry in runtime_paths.RUNTIME_OBJECTS.items()
            if not object_id.endswith("-root"))
        with self.assertRaisesRegex(ValueError, "registered runtime namespace"):
            runtime_paths.child_path(file_entry.path, "leaf.yaml")
        with self.assertRaisesRegex(ValueError, "registered runtime namespace"):
            runtime_paths.child_path(
                runtime_paths.RUNTIME_ROOT + "/unregistered", "leaf.yaml")
        for segment in ("", ".", "..", "nested/file", "nested\\file"):
            with self.subTest(segment=segment):
                with self.assertRaises(ValueError):
                    runtime_paths.child_path(runtime_paths.DELTA_ROOT, segment)

    def test_production_consumers_do_not_redeclare_runtime_path_spellings(self):
        violations = []
        owner = TOOLS / "execution/task_runtime/runtime_paths.py"
        for path in sorted(TOOLS.rglob("*.py")):
            if path == owner or "tests" in path.parts or "compiled" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            if runtime_paths.RUNTIME_ROOT not in source:
                continue
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and
                        isinstance(node.value, str) and
                        RUNTIME_PATH_LITERAL.fullmatch(node.value)):
                    violations.append(
                        "%s:%d:%s" % (
                            path.relative_to(TOOLS.parent),
                            node.lineno,
                            node.value,
                        ))
        self.assertEqual([], violations)


class RuntimeDirectoryIntegrationTests(unittest.TestCase):
    """Integration: a producer can materialize only a current safe root."""

    def test_directory_materialization_requires_existing_safe_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)

            absent = base / "absent"
            absent.mkdir()
            with self.assertRaisesRegex(ValueError, "must exist"):
                runtime_paths.ensure_directory(absent, "derived-root")

            current = base / "current"
            (current / runtime_paths.RUNTIME_ROOT).mkdir(parents=True)
            created = Path(runtime_paths.ensure_directory(
                current, "derived-root"))
            self.assertEqual(
                (current / runtime_paths.DERIVED_ROOT).resolve(),
                created.resolve())
            self.assertEqual(
                created,
                Path(runtime_paths.ensure_directory(
                    current, "derived-root")))
            with self.assertRaises(KeyError):
                runtime_paths.ensure_directory(current, "derived-root-v0")

            unsafe = base / "unsafe"
            (unsafe / runtime_paths.RUNTIME_ROOT).mkdir(parents=True)
            outside = base / "outside"
            outside.mkdir()
            (unsafe / runtime_paths.DERIVED_ROOT).symlink_to(
                outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink or file"):
                runtime_paths.ensure_directory(unsafe, "derived-root")


if __name__ == "__main__":
    unittest.main()
