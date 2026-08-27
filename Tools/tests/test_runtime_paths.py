"""Runtime paths have one typed Tool-side registry.

The registry owns physical spelling and lifecycle classification only. Object
schemas, transition rules, authorization, and current values remain with their
existing owners.
"""

import sys
import tempfile
import unittest
import ast
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import compose_page_contract  # noqa: E402
import compose_vocab  # noqa: E402
import check_proof  # noqa: E402
import init_state  # noqa: E402
import kblib  # noqa: E402
import project_page_state  # noqa: E402
import runtime_paths  # noqa: E402
import seal_receipts  # noqa: E402
import standards_state  # noqa: E402
import upstream_component_boundary  # noqa: E402
from queue_runtime import canon  # noqa: E402


class RuntimePathRegistryTests(unittest.TestCase):
    def test_every_registered_path_is_unique_and_instance_local(self):
        paths = [entry.path for entry in runtime_paths.RUNTIME_OBJECTS.values()]

        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all(path.startswith(".cambium/") for path in paths))

    def test_categories_are_closed_and_all_used(self):
        expected = {
            runtime_paths.CANONICAL_STATE,
            runtime_paths.BOUND_INPUT,
            runtime_paths.EVIDENCE,
            runtime_paths.RECOVERY,
            runtime_paths.TRANSIENT,
            runtime_paths.DERIVED_PROJECTION,
        }

        self.assertEqual(expected, set(runtime_paths.CATEGORY_ROOTS))
        self.assertEqual(
            expected,
            {entry.category for entry in runtime_paths.RUNTIME_OBJECTS.values()},
        )

    def test_durable_lock_and_journal_objects_are_not_transient(self):
        recovery_objects = (
            "state-writer-lock",
            "state-writer-owner",
            "page-state-recovery-journal",
            "receipt-append-free",
            "receipt-append-held",
            "receipt-seal-journal",
            "receipt-cold-pending-root",
        )

        self.assertTrue(all(
            runtime_paths.category_for(object_id) == runtime_paths.RECOVERY
            for object_id in recovery_objects
        ))

    def test_current_consumers_use_the_registered_canonical_paths(self):
        self.assertEqual(runtime_paths.QUEUE_PATH, canon.QUEUE_PATH)
        self.assertEqual(runtime_paths.COVERAGE_PATH, canon.COVERAGE_PATH)
        self.assertEqual(runtime_paths.PROGRESS_PATH, canon.PROGRESS_PATH)
        self.assertEqual(runtime_paths.WATERMARK_PATH, canon.WATERMARK_PATH)
        self.assertEqual(
            runtime_paths.ACTIVE_STANDARDS_PATH, standards_state.STATE_PATH)
        self.assertEqual(
            runtime_paths.VOCAB_ARTIFACT_PATH, compose_vocab.DEFAULT_OUTPUT)
        self.assertEqual(
            runtime_paths.PAGE_CONTRACT_ARTIFACT_PATH,
            compose_page_contract.DEFAULT_OUTPUT,
        )
        self.assertEqual(
            runtime_paths.UPSTREAM_COMPONENT_MANIFEST_PATH,
            upstream_component_boundary.DEFAULT_MANIFEST_PATH,
        )
        self.assertEqual(runtime_paths.QUEUE_PATH, kblib.RUNTIME_QUEUE_PATH)
        self.assertEqual(
            runtime_paths.RECEIPT_COLD_ROOT, kblib.RECEIPT_COLD_PREFIX)
        self.assertEqual(
            runtime_paths.RECEIPT_SEAL_JOURNAL_PATH,
            kblib.RECEIPT_COLD_JOURNAL_PATH,
        )
        self.assertEqual(
            runtime_paths.RECEIPT_APPEND_FREE_PATH,
            kblib.RECEIPT_APPEND_FREE_PATH,
        )
        self.assertEqual(
            runtime_paths.RECEIPT_APPEND_HELD_PATH,
            kblib.RECEIPT_APPEND_HELD_PATH,
        )
        self.assertEqual(
            runtime_paths.ACTIVE_STANDARDS_PATH,
            check_proof.ACTIVE_STATE_PATH,
        )
        self.assertEqual(
            runtime_paths.COVERAGE_PATH,
            check_proof.CANONICAL_COVERAGE_PATH,
        )
        self.assertEqual(
            runtime_paths.QUEUE_PATH,
            check_proof.CANONICAL_QUEUE_PATH,
        )
        self.assertEqual(
            runtime_paths.PROGRESS_PATH,
            check_proof.CANONICAL_PROGRESS_PATH,
        )
        self.assertEqual(
            runtime_paths.RECEIPT_ROOT, seal_receipts.RECEIPTS_ROOT)
        self.assertEqual(
            runtime_paths.RECEIPT_COLD_PENDING_ROOT,
            seal_receipts.COLD_PENDING_PREFIX,
        )
        self.assertEqual(
            runtime_paths.SEAL_RECEIPT_PATH,
            seal_receipts.SEAL_RECEIPTS_PATH,
        )
        self.assertEqual(
            Path(runtime_paths.PAGE_STATE_RECOVERY_JOURNAL_PATH).name,
            project_page_state.JOURNAL_NAME,
        )

    def test_receipt_protection_basenames_are_registry_projections(self):
        expected = {
            Path(path).name
            for path in (
                runtime_paths.QUEUE_TRANSITION_RECEIPT_PATH,
                runtime_paths.STANDARDS_ADOPTION_RECEIPT_PATH,
                runtime_paths.CONTRACT_AMENDMENT_RECEIPT_PATH,
                runtime_paths.AMENDMENT_RECEIPT_PATH,
                runtime_paths.SEAL_RECEIPT_PATH,
            )
        }

        self.assertEqual(expected, seal_receipts.NEVER_SEAL_BASENAMES)

    def test_path_reference_projection_covers_root_and_object_identities(self):
        root_reference = runtime_paths.path_reference_for("runtime-root")

        self.assertEqual("runtime-root", root_reference.runtime_path_id)
        self.assertEqual("namespace", root_reference.constraint)
        self.assertEqual(runtime_paths.RUNTIME_ROOT, root_reference.path)
        for object_id, entry in runtime_paths.RUNTIME_OBJECTS.items():
            with self.subTest(runtime_path_id=object_id):
                reference = runtime_paths.path_reference_for(object_id)

                self.assertEqual(object_id, reference.runtime_path_id)
                self.assertEqual(entry.path, reference.path)

        with self.assertRaisesRegex(KeyError, "unknown runtime path reference"):
            runtime_paths.path_reference_for("not-registered")

    def test_agent_interface_runtime_paths_use_owner_source_identities(self):
        """Policy names the registry owner instead of copying its paths."""
        policy = kblib.parse_yaml_subset(
            (TOOLS / "agent-interface-policy.yaml").read_text(
                encoding="utf-8"))
        defaults = {
            row["argument"]: row
            for row in policy["path_defaults"]
        }
        overrides = {
            (row["tool"], row["argument"]): row
            for row in policy["path_overrides"]
        }

        self.assertEqual(
            "receipt-root", defaults["receipts"]["runtime_path_id"])
        self.assertNotIn("value", defaults["receipts"])
        expected = {
            ("check_boundary_contract", "contract"):
                "effective-page-contract",
            ("check_page_contract", "contract"):
                "effective-page-contract",
            ("render_boundary_projection", "contract"):
                "effective-page-contract",
            ("check_proof", "ledger"): "coverage-ledger",
            ("check_proof", "progress_ledger"):
                "progress-ledger",
            ("check_vocab", "vocab"): "effective-vocabulary",
            ("compile_queue", "output"): "runtime-root",
            ("render_queue", "output"): "report-root",
            ("update_queue", "delta_path"): "delta-root",
        }
        for key, runtime_path_id in expected.items():
            with self.subTest(capability="%s.%s" % key):
                row = overrides[key]

                self.assertEqual(runtime_path_id, row["runtime_path_id"])
                self.assertNotIn("value", row)
                self.assertEqual(
                    runtime_path_id,
                    runtime_paths.path_reference_for(
                        runtime_path_id).runtime_path_id,
                )

        runtime_literals = [
            row["value"]
            for row in policy["path_defaults"] + policy["path_overrides"]
            if isinstance(row.get("value"), str) and (
                row["value"] == runtime_paths.RUNTIME_ROOT or
                row["value"].startswith(runtime_paths.RUNTIME_ROOT + "/")
            )
        ]
        self.assertEqual([], runtime_literals)

    def test_recovery_and_seal_consumers_do_not_redeclare_path_basenames(self):
        targets = {
            TOOLS / "seal_receipts.py": {
                Path(runtime_paths.QUEUE_TRANSITION_RECEIPT_PATH).name,
                Path(runtime_paths.STANDARDS_ADOPTION_RECEIPT_PATH).name,
                Path(runtime_paths.CONTRACT_AMENDMENT_RECEIPT_PATH).name,
                Path(runtime_paths.AMENDMENT_RECEIPT_PATH).name,
                Path(runtime_paths.SEAL_RECEIPT_PATH).name,
            },
            TOOLS / "project_page_state.py": {
                Path(runtime_paths.PAGE_STATE_RECOVERY_JOURNAL_PATH).name,
            },
        }
        findings = []
        for path, forbidden in targets.items():
            tree = ast.parse(
                path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and
                        isinstance(node.value, str) and
                        node.value in forbidden):
                    findings.append(
                        "%s:%d:%s" % (path.name, node.lineno, node.value))

        self.assertEqual([], findings)

    def test_conceptual_recovery_category_creates_no_empty_namespace(self):
        self.assertNotIn("recovery", runtime_paths.TASK_RUNTIME_DIRECTORIES)
        self.assertFalse(any(
            entry.path == ".cambium/recovery" or
            entry.path.startswith(".cambium/recovery/")
            for entry in runtime_paths.RUNTIME_OBJECTS.values()
        ))

    def test_directory_helper_cannot_instantiate_an_adopter(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "must exist"):
                runtime_paths.ensure_directory(root, "derived-root")

    def test_directory_helper_creates_only_registered_child_namespace(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, ".cambium").mkdir()

            created = runtime_paths.ensure_directory(root, "derived-root")

            self.assertEqual(
                Path(root, runtime_paths.DERIVED_ROOT).resolve(),
                Path(created).resolve(),
            )
            self.assertTrue(Path(created).is_dir())

    def test_dynamic_children_cannot_escape_the_registered_namespace(self):
        self.assertEqual(
            runtime_paths.DELTA_ROOT + "/B-001.yaml",
            runtime_paths.child_path(runtime_paths.DELTA_ROOT, "B-001.yaml"),
        )
        for segment in ("", ".", "..", "nested/file", "nested\\file"):
            with self.subTest(segment=segment):
                with self.assertRaises(ValueError):
                    runtime_paths.child_path(
                        runtime_paths.DELTA_ROOT, segment)
        with self.assertRaisesRegex(ValueError, "registered runtime"):
            runtime_paths.child_path(
                runtime_paths.RUNTIME_ROOT + "/unregistered", "leaf.yaml")

    def test_task_runtime_directories_are_derived_from_registered_roots(self):
        self.assertEqual(
            tuple(
                path[len(runtime_paths.RUNTIME_ROOT) + 1:]
                for path in runtime_paths.TASK_RUNTIME_ROOTS
            ),
            runtime_paths.TASK_RUNTIME_DIRECTORIES,
        )
        self.assertTrue(all(
            path in {
                entry.path
                for entry in runtime_paths.RUNTIME_OBJECTS.values()
            }
            for path in runtime_paths.TASK_RUNTIME_ROOTS
        ))

    def test_initializer_projects_state_documents_from_registered_objects(self):
        expected = {
            Path(path).name: path
            for path in (
                runtime_paths.COVERAGE_PATH,
                runtime_paths.QUEUE_PATH,
                runtime_paths.PROGRESS_PATH,
            )
        }

        self.assertEqual(expected, init_state._STATE_DOCUMENT_PATH_BY_NAME)
        self.assertEqual(
            frozenset(expected), init_state._STATE_DOCUMENT_NAMES)
        self.assertEqual(
            Path(runtime_paths.QUEUE_PATH).name,
            init_state._QUEUE_DOCUMENT_NAME,
        )

    def test_initializer_has_no_private_runtime_object_spelling(self):
        """The initializer may project paths, but cannot redeclare them."""
        path = TOOLS / "init_state.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden = {
            Path(runtime_paths.COVERAGE_PATH).name,
            Path(runtime_paths.QUEUE_PATH).name,
            Path(runtime_paths.PROGRESS_PATH).name,
            Path(runtime_paths.STATE_WRITER_LOCK_PATH).name,
            Path(runtime_paths.STATE_WRITER_OWNER_PATH).name,
            runtime_paths.ACTIVE_STANDARDS_PATH[
                len(runtime_paths.RUNTIME_ROOT) + 1:
            ],
        }
        findings = [
            "%d:%s" % (node.lineno, node.value)
            for node in ast.walk(tree)
            if (isinstance(node, ast.Constant) and
                isinstance(node.value, str) and
                node.value in forbidden)
        ]

        self.assertEqual([], findings)

    def test_initializer_maps_registered_paths_into_a_staged_runtime(self):
        with tempfile.TemporaryDirectory() as staging:
            self.assertEqual(
                str(Path(staging, "state", Path(runtime_paths.QUEUE_PATH).name)),
                init_state._runtime_namespace_path(
                    staging, runtime_paths.QUEUE_PATH),
            )
            with self.assertRaisesRegex(ValueError, "path below"):
                init_state._runtime_namespace_path(
                    staging, "outside/runtime.yaml")

    def test_initializer_extends_governance_with_registered_runtime_paths(self):
        with tempfile.TemporaryDirectory() as root:
            active_state = Path(root, runtime_paths.ACTIVE_STANDARDS_PATH)
            active_state.parent.mkdir(parents=True)
            active_state.write_text("schema_version: 1\n", encoding="utf-8")
            documents = {
                name: "schema_version: 1\n"
                for name in init_state._STATE_DOCUMENT_NAMES
            }
            observations = []

            def before_publication():
                observations.append(
                    not Path(root, runtime_paths.STATE_ROOT).exists())

            def after_publication():
                observations.append(all(
                    Path(root, path).is_file()
                    for path in init_state._STATE_DOCUMENT_PATH_BY_NAME.values()
                ))
                observations.append(
                    Path(root, runtime_paths.STATE_WRITER_LOCK_PATH).is_dir())

            init_state.publish_runtime_into_governance_namespace(
                root,
                documents,
                pre_publish_validator=before_publication,
                post_publish_validator=after_publication,
                lock_operation={"tool": "runtime-path-registry-test"},
            )

            self.assertEqual([True, True, True], observations)
            self.assertTrue(active_state.is_file())
            self.assertFalse(
                Path(root, runtime_paths.STATE_WRITER_LOCK_PATH).exists())
            self.assertFalse(Path(root, runtime_paths.DERIVED_ROOT).exists())

    def test_production_python_has_no_runtime_root_literal_outside_registry(self):
        """Physical spelling belongs only to runtime_paths.py.

        Human-facing module/function/class docstrings may explain the existing
        layout.  Executable constants, defaults, diagnostics, and path building
        must import the registry so they cannot drift independently.
        """
        violations = []
        for path in sorted(TOOLS.rglob("*.py")):
            if path == TOOLS / "runtime_paths.py":
                continue
            if "tests" in path.parts or "compiled" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            docstrings = set()
            for owner in ast.walk(tree):
                body = getattr(owner, "body", None)
                if not isinstance(body, list) or not body:
                    continue
                first = body[0]
                if (isinstance(first, ast.Expr) and
                        isinstance(first.value, ast.Constant) and
                        isinstance(first.value.value, str)):
                    docstrings.add(id(first.value))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and
                        isinstance(node.value, str) and
                        ".cambium" in node.value and
                        id(node) not in docstrings):
                    violations.append(
                        "%s:%d: %r" % (
                            path.relative_to(TOOLS.parent),
                            node.lineno,
                            node.value,
                        ))
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
