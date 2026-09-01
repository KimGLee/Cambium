"""Owned tests for the current metadata execution machine contract."""

import copy
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import Tools.governance.control.metadata_execution_contract as contract
import Tools.platform.common.kblib as kblib


REPOSITORY = Path(__file__).resolve().parents[2]


def _source_documents(root=REPOSITORY):
    authority = kblib.parse_yaml_subset(
        (root / contract.DEFAULT_AUTHORITY_PATH).read_text(encoding="utf-8"))
    capabilities = kblib.parse_yaml_subset(
        (root / contract.DEFAULT_CAPABILITIES_PATH).read_text(
            encoding="utf-8"))
    return authority, capabilities


def _normalized_capability(entry):
    """Independently normalize one registry row for semantic comparison."""
    normalized = copy.deepcopy(entry)
    for role in ("writers", "checkers", "consumers"):
        normalized[role] = sorted(normalized[role])
    normalized["operations"] = sorted(
        normalized["operations"],
        key=lambda operation: tuple(
            str(operation[key]) for key in sorted(operation)))
    return normalized


def _metadata_capabilities(document):
    """The metadata artifact consumes every current non-projection row."""
    return [
        entry for entry in document["capabilities"]
        if entry["kind"] != "projection"
    ]


def _implementation_paths(entries):
    paths = set()
    for entry in entries:
        paths.add(entry["implementation_owner"])
        if "invocation_owner" in entry:
            paths.add(entry["invocation_owner"])
        for role in ("writers", "checkers", "consumers"):
            paths.update(entry[role])
    return tuple(sorted(paths))


def _implementation_hashes(root, entries):
    return {
        path: kblib.sha256_file(root / path)
        for path in _implementation_paths(entries)
    }


def _compile(authority, capabilities, snapshots):
    return contract.compile_metadata_execution_document(
        authority, capabilities, implementation_snapshots=snapshots)


def _materialize_current_inputs(destination):
    authority, capabilities = _source_documents()
    for relative in (
            contract.DEFAULT_AUTHORITY_PATH,
            contract.DEFAULT_CAPABILITIES_PATH):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPOSITORY / relative).read_bytes())
    for relative in _implementation_paths(capabilities["capabilities"]):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPOSITORY / relative).read_bytes())
    (destination / "Tools/compiled").mkdir(parents=True, exist_ok=True)
    return authority, capabilities


def _run_contract_cli(*arguments):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = contract.main(list(arguments))
    return code, stdout.getvalue(), stderr.getvalue()


class MetadataExecutionSourceContractTests(unittest.TestCase):
    """Contract: source owners project exactly one executable authority."""

    @classmethod
    def setUpClass(cls):
        cls.authority, cls.capabilities = _source_documents()
        metadata_entries = _metadata_capabilities(cls.capabilities)
        cls.snapshots = _implementation_hashes(REPOSITORY, metadata_entries)
        cls.compiled = _compile(
            cls.authority, cls.capabilities, cls.snapshots)

    def test_compiler_projects_exact_kernel_and_registry_sources(self):
        artifact = self.compiled.artifact

        expected_rules = sorted(
            copy.deepcopy(self.authority["field_rules"]),
            key=lambda rule: (rule["field"], rule["transition"]))
        self.assertEqual(expected_rules, artifact["field_rules"])
        self.assertEqual(
            self.authority["temporal_order"], artifact["temporal_order"])

        expected_capabilities = sorted(
            (_normalized_capability(entry)
             for entry in _metadata_capabilities(self.capabilities)),
            key=lambda entry: (
                entry["kind"], entry["capability_id"],
                entry["capability_version"]))
        self.assertEqual(
            expected_capabilities, artifact["operation_capabilities"])
        self.assertEqual(
            [entry for entry in expected_capabilities
             if entry["kind"] == "writer"],
            artifact["writer_capabilities"])

        expected_implementations = [
            {"path": path, "sha256": self.snapshots[path]}
            for path in sorted(self.snapshots)
        ]
        self.assertEqual(
            expected_implementations, artifact["capability_implementations"])

        fingerprint_source = {
            key: copy.deepcopy(value)
            for key, value in artifact.items()
            if key != "contract_fingerprint"
        }
        self.assertEqual(
            kblib.sha256_bytes(
                kblib.canonical_json_bytes(fingerprint_source)),
            artifact["contract_fingerprint"])
        self.assertEqual(
            kblib.canonical_json_bytes(artifact) + b"\n",
            self.compiled.canonical_bytes)

    def test_declaration_order_does_not_change_contract_identity(self):
        authority = copy.deepcopy(self.authority)
        capabilities = copy.deepcopy(self.capabilities)
        authority["field_rules"].reverse()
        capabilities["capabilities"].reverse()
        for entry in capabilities["capabilities"]:
            for role in ("writers", "checkers", "consumers"):
                entry[role].reverse()
            entry["operations"].reverse()

        reordered = _compile(authority, capabilities, self.snapshots)

        self.assertEqual(
            self.compiled.contract_fingerprint,
            reordered.contract_fingerprint)
        self.assertEqual(
            self.compiled.canonical_bytes, reordered.canonical_bytes)

    def test_kernel_authority_mutation_matrix_fails_closed(self):
        cases = (
            ("duplicate-rule", "duplicate field transition rule"),
            ("unknown-key", "unknown keys: helpful_note"),
            ("missing-writer", "missing keys: writer_capability"),
            ("changed-temporal-order", "temporal_order"),
            ("incomplete-content-exclusions", "content-change exclusions"),
            ("unknown-reconcile-policy", "reconcile_policy is not registered"),
        )
        for case, expected in cases:
            with self.subTest(case=case):
                authority = copy.deepcopy(self.authority)
                if case == "duplicate-rule":
                    authority["field_rules"].append(
                        copy.deepcopy(authority["field_rules"][0]))
                elif case == "unknown-key":
                    authority["field_rules"][0]["helpful_note"] = "prose"
                elif case == "missing-writer":
                    del authority["field_rules"][0]["writer_capability"]
                elif case == "changed-temporal-order":
                    authority["temporal_order"] = list(reversed(
                        authority["temporal_order"]))
                elif case == "incomplete-content-exclusions":
                    rule = next(
                        row for row in authority["field_rules"]
                        if row["source_adapter"] ==
                        "content-change-event-v1")
                    rule["evidence_requirement"][
                        "excluded_change_classes"] = ["projection-only"]
                else:
                    authority["field_rules"][0]["reconcile_policy"] = \
                        "retired-copy-policy-v1"

                with self.assertRaisesRegex(
                        contract.MetadataExecutionContractError, expected):
                    _compile(authority, self.capabilities, self.snapshots)

    def test_capability_registry_mutation_matrix_fails_closed(self):
        cases = (
            ("retired-schema", "schema_version must be 3"),
            ("duplicate-id", "duplicate capability_id"),
            ("orphan-operation", "is unauthorized"),
            ("second-writer", "implemented more than once"),
            ("noncanonical-owner", "canonical Tools/\\*\\.py"),
            ("overlapping-role", "more than once"),
            ("unknown-projection-owner", "unknown runtime object"),
        )
        for case, expected in cases:
            with self.subTest(case=case):
                capabilities = copy.deepcopy(self.capabilities)
                entries = capabilities["capabilities"]
                writers = [entry for entry in entries
                           if entry["kind"] == "writer"]
                if case == "retired-schema":
                    capabilities["schema_version"] = 1
                elif case == "duplicate-id":
                    other = next(entry for entry in entries
                                 if entry["kind"] != "writer")
                    other["capability_id"] = writers[0]["capability_id"]
                elif case == "orphan-operation":
                    writers[0]["operations"].append({
                        "field": "orphan_field",
                        "transition": "owner-to-page-projection",
                        "source_adapter": "coverage-row-value-v1",
                    })
                elif case == "second-writer":
                    duplicate = copy.deepcopy(writers[0])
                    duplicate["capability_id"] = "second-writer-v1"
                    duplicate["operations"] = [
                        copy.deepcopy(writers[0]["operations"][0])]
                    entries.append(duplicate)
                elif case == "noncanonical-owner":
                    entries[0]["implementation_owner"] = "../outside.py"
                elif case == "overlapping-role":
                    entries[0]["consumers"].append(
                        entries[0]["implementation_owner"])
                else:
                    projection = next(
                        entry for entry in entries
                        if entry["kind"] == "projection")
                    projection["input_owners"] = ["unknown-runtime-object"]

                with self.assertRaisesRegex(
                        contract.MetadataExecutionContractError, expected):
                    _compile(self.authority, capabilities, self.snapshots)


class MetadataExecutionProjectionIntegrationTests(unittest.TestCase):
    """Integration: one generated projection tracks all live source inputs."""

    def test_compile_check_and_runtime_load_reject_stale_projection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            root.mkdir()
            _authority, capabilities = _materialize_current_inputs(root)
            args = ("--root", str(root))

            code, _stdout, stderr = _run_contract_cli(*args)
            self.assertEqual(0, code, stderr)
            artifact_path = root / contract.DEFAULT_COMPILED_PATH
            generated = artifact_path.read_bytes()

            code, _stdout, stderr = _run_contract_cli(*args, "--check")
            self.assertEqual(0, code, stderr)
            loaded = contract.load_metadata_execution_contract(root)
            self.assertEqual(generated, loaded.canonical_bytes)

            artifact_path.write_bytes(generated + b"\n")
            code, _stdout, _stderr = _run_contract_cli(*args, "--check")
            self.assertEqual(1, code)
            artifact_path.write_bytes(generated)

            implementation = root / _implementation_paths(
                _metadata_capabilities(capabilities))[0]
            implementation.write_bytes(
                implementation.read_bytes() + b"\n# current-source-drift\n")
            code, _stdout, _stderr = _run_contract_cli(*args, "--check")
            self.assertEqual(1, code)
            with self.assertRaisesRegex(
                    contract.MetadataExecutionContractError,
                    "stale relative to live authority"):
                contract.load_metadata_execution_contract(root)


if __name__ == "__main__":
    unittest.main()
