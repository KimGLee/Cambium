"""Vocabulary source-to-compiled-artifact identity and currentness tests."""

import copy
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.governance.profile.profile_contract as profile_contract
import Tools.platform.common.kblib as kblib
import Tools.knowledge.metadata.check_vocab as check_vocab
import Tools.knowledge.metadata.compose_vocab as compose_vocab


BASE_PATH = compose_vocab.DEFAULT_BASE
EXTENSION_PATH = "profiles/fixture/vocabulary-extensions.yaml"


def base_document():
    return {
        "schema_version": 1,
        "composition_policy": "append-only-profile-extensions",
        "fields": {
            "priority": {
                "owner": "fixture-priority-owner",
                "values": ["P0", "P1", "P2"],
            },
            "volatility": {
                "owner": "fixture-volatility-owner",
                "values": ["slow"],
            },
            "coverage_disposition": {
                "owner": "fixture-coverage-owner",
                "values": ["required"],
            },
        },
        "review_intervals_days": {"slow": 365},
    }


def extension_document():
    return {
        "schema_version": 1,
        "frontmatter_extensions": {"fields": []},
        "fields": {},
        "volatility_defaults": {"general": "slow"},
    }


class FixtureAdmission:

    def __init__(self, root, extension_bytes):
        self.root = str(Path(root).resolve())
        self.profile_id = "fixture"
        self.manifest_repo_path = "profiles/fixture/profile.md"
        self.slot_bytes = {"Vocabulary Extensions": extension_bytes}
        self.contract = profile_contract.ProfileContract(
            root=self.root,
            manifest_path=str(Path(self.root) / self.manifest_repo_path),
            manifest_repo_path=self.manifest_repo_path,
            profile_root=str(Path(self.root) / "profiles/fixture"),
            profile_repo_dir="profiles/fixture",
            audit_registry_path=None,
            scan_registry_path=None,
            routing_registry_path=None,
            extension_registration=None,
            extension_dimensions=(),
            judgment_items=(),
            registered_scans=(),
            extension_gate_registration=None,
            extension_gates=(),
            dependency_edges=(),
            source_cells=(),
            diagnostics=(),
            volatility_defaults=(("general", "slow"),),
        )
        self.evaluation = SimpleNamespace(
            profile_snapshot_sha256="sha256:" + "1" * 64,
            profile_contract_fingerprint="sha256:" + "2" * 64,
            profile_load_inputs_sha256="sha256:" + "3" * 64,
        )

    def slot_text(self, name):
        return self.slot_bytes[name].decode("utf-8")

    def slot_path(self, name):
        if name != "Vocabulary Extensions":
            return None
        return str(Path(self.root) / EXTENSION_PATH)


def install_sources(root):
    root = Path(root)
    base_bytes = kblib.canonical_yaml(base_document()).encode("utf-8")
    extension_bytes = kblib.canonical_yaml(
        extension_document()).encode("utf-8")
    base = root / BASE_PATH
    extension = root / EXTENSION_PATH
    base.parent.mkdir(parents=True, exist_ok=True)
    extension.parent.mkdir(parents=True, exist_ok=True)
    base.write_bytes(base_bytes)
    extension.write_bytes(extension_bytes)
    return base, extension, FixtureAdmission(root, extension_bytes)


class VocabularyArtifactIdentityContractTests(unittest.TestCase):

    def test_identity_is_deterministic_and_all_byte_drift_is_stale(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
                compose_vocab.profile_admission, "currency_errors",
                return_value=[]):
            root = Path(directory)
            base, extension, admission = install_sources(root)
            original_base = base.read_bytes()
            original_extension = extension.read_bytes()
            artifact = root / runtime_paths.VOCAB_ARTIFACT_PATH
            artifact.parent.mkdir(parents=True)

            first, first_projection, errors = compose_vocab.compiled_artifact(
                root, admission)
            second, second_projection, repeated_errors = \
                compose_vocab.compiled_artifact(root, admission)
            self.assertEqual([], errors)
            self.assertEqual([], repeated_errors)
            self.assertEqual(first, second)
            self.assertEqual(first_projection, second_projection)
            artifact.write_text(first, encoding="utf-8")
            snapshot, current_errors = compose_vocab.admitted_artifact(
                root, runtime_paths.VOCAB_ARTIFACT_PATH, admission)
            self.assertEqual([], current_errors)
            self.assertEqual(first.encode("utf-8"), snapshot.data)
            defaults_snapshot, defaults, defaults_errors = \
                compose_vocab.admitted_volatility_defaults(
                    root, runtime_paths.VOCAB_ARTIFACT_PATH, admission)
            self.assertEqual([], defaults_errors)
            self.assertEqual(snapshot.data, defaults_snapshot.data)
            self.assertEqual(snapshot.sha256, defaults_snapshot.sha256)
            self.assertEqual({"general": "slow"}, defaults)

            reordered = base_document()
            reordered["fields"] = {
                key: reordered["fields"][key]
                for key in reversed(tuple(reordered["fields"]))
            }
            mutations = (
                ("artifact-bytes", None, None,
                 first.encode("utf-8") + b"# drift\n"),
                ("base-bytes", original_base + b"# drift\n", None,
                 first.encode("utf-8")),
                ("extension-bytes", None,
                 original_extension + b"# drift\n", first.encode("utf-8")),
                ("base-field-order",
                 kblib.canonical_yaml(reordered).encode("utf-8"), None,
                 first.encode("utf-8")),
            )
            for name, changed_base, changed_extension, changed_artifact \
                    in mutations:
                with self.subTest(name=name):
                    base.write_bytes(changed_base or original_base)
                    extension.write_bytes(
                        changed_extension or original_extension)
                    admission.slot_bytes["Vocabulary Extensions"] = \
                        changed_extension or original_extension
                    artifact.write_bytes(changed_artifact)

                    stale = compose_vocab.artifact_currency_errors(
                        root, runtime_paths.VOCAB_ARTIFACT_PATH, admission)

                    self.assertTrue(stale)
                    self.assertTrue(any("does not match" in error
                                        for error in stale), stale)


class VocabularyComposeCheckIntegrationTests(unittest.TestCase):

    def test_small_compose_output_is_accepted_by_the_current_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _base, _extension, admission = install_sources(root)
            (root / ".cambium").mkdir()
            corpus = root / "corpus"
            corpus.mkdir()
            (corpus / "Page.md").write_text(
                "---\npriority: P2\n---\n\n# Page\n",
                encoding="utf-8")
            selected = (
                EXTENSION_PATH, admission.profile_id, [], admission)
            compose_output = io.StringIO()
            check_output = io.StringIO()

            with mock.patch.object(compose_vocab, "REPO_ROOT", str(root)), \
                    mock.patch.object(
                        compose_vocab, "active_extensions_selection",
                        return_value=selected), \
                    mock.patch.object(
                        compose_vocab.profile_admission, "currency_errors",
                        return_value=[]):
                with redirect_stdout(compose_output):
                    compose_code = compose_vocab.main([])
                with redirect_stdout(check_output):
                    check_code = check_vocab.main(
                        [str(root), "--scope", "corpus"],
                        authorized_admission=admission)

            artifact = root / runtime_paths.VOCAB_ARTIFACT_PATH
            artifact_exists = artifact.exists()

        self.assertEqual(0, compose_code, compose_output.getvalue())
        self.assertEqual(0, check_code, check_output.getvalue())
        self.assertTrue(artifact_exists)


if __name__ == "__main__":
    unittest.main()
