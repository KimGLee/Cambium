"""Owner, projection, interview and empty-candidate joins for Profile v1.

These tests evaluate real CUE constraints against explicit snapshots. They
never copy a semantic schema into a template, parse Markdown forms, publish
a receipt, infer user confirmation, or modify adopter selection.
"""

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Tools.governance.profile.profile_codec import loads_profile, dumps_profile
from Tools.governance.profile.profile_cue import validate_profile
from Tools.governance.profile import profile_cue, profile_layout_contract
from Tools.governance.profile.profile_schema_projection import (
    check_profile_schema_projections,
    main as projection_main,
    project_profile_document,
    project_profile_schema,
)
from Tools.platform.common import kblib

INTERFACE = "kernel/K00 Standards Control/profile-interface.yaml"
ENCODING = "Tools/governance/profile/profile-encoding.yaml"


def _read_yaml(relative):
    return kblib.parse_yaml_subset((ROOT / relative).read_text(encoding="utf-8"))


def _strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


class TemplateParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.interface = _read_yaml(INTERFACE)
        cls.encoding = _read_yaml(ENCODING)
        cls.kernel_sources = {
            entry["path"]: (ROOT / entry["path"]).read_bytes()
            for entry in cls.encoding["cue_sources"]
        }
        cls.encoding_sources = {
            path: (ROOT / path).read_bytes()
            for path in cls.encoding["encoding_cue_sources"]
        }
        cls.sources = {**cls.kernel_sources, **cls.encoding_sources}
        cls.snapshot = {
            **cls.sources,
            INTERFACE: (ROOT / INTERFACE).read_bytes(),
            ENCODING: (ROOT / ENCODING).read_bytes(),
            **{
                path: (ROOT / path).read_bytes()
                for path in cls.encoding["registry_references"].values()
            },
        }
        cls.examples = [
            loads_profile((ROOT / "profiles/examples" / name / "profile.toml").read_bytes())
            for name in ("agent-atlas", "worked-planning")
        ]

    def assert_valid(self, document, *, draft=False):
        result = validate_profile(document, self.sources, draft=draft)
        self.assertTrue(result.valid, "\n".join(result.diagnostics))

    def assert_invalid(self, document, *, draft=False):
        result = validate_profile(document, self.sources, draft=draft)
        self.assertFalse(result.valid, "an invalid candidate passed the real owner contract")

    def _vet_kernel_object(self, value, definition):
        """Exercise Kernel objects directly without the Tool document wrapper."""
        binary = os.environ.get("CAMBIUM_CUE") or shutil.which("cue")
        self.assertIsNotNone(binary, "these ownership tests require the real pinned CUE")
        with tempfile.TemporaryDirectory(prefix="cambium-kernel-semantic-") as temporary:
            directory = Path(temporary)
            filenames = []
            for index, (_relative, data) in enumerate(sorted(self.kernel_sources.items())):
                name = "semantic_%d.cue" % index
                (directory / name).write_bytes(data)
                filenames.append(name)
            (directory / "value.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            return subprocess.run(
                [binary, "vet", "-c", "-d", definition, *filenames, "value.json"],
                cwd=directory, capture_output=True, text=True, timeout=30)

    def test_kernel_semantic_objects_validate_without_document_encoding(self):
        kernel_interface = self.kernel_sources[
            "kernel/K00 Standards Control/profile-interface.cue"].decode("utf-8")
        self.assertNotIn("#ProfileDraft:", kernel_interface)
        self.assertNotIn("schema_version", kernel_interface)
        self.assertNotIn("profile_id:", kernel_interface)
        self.assertNotIn("slots:", kernel_interface)
        definition = self.interface["semantic_definition"]
        result = self._vet_kernel_object(self.examples[0]["slots"], definition)
        self.assertEqual(result.returncode, 0, result.stderr)
        wrapped = self._vet_kernel_object(self.examples[0], definition)
        self.assertNotEqual(wrapped.returncode, 0)
        invalid = copy.deepcopy(self.examples[0]["slots"])
        invalid["registered-scan-registry"]["scan_registrations"][0]["scan_id"] = "Bad_Scan"
        self.assertNotEqual(self._vet_kernel_object(invalid, definition).returncode, 0)

    def test_tool_encoding_can_change_without_changing_domain_rules(self):
        changed_bytes = self.snapshot[ENCODING].replace(
            b"document_schema_version: 1", b"document_schema_version: 2").replace(
            b"slot_container: slots", b"slot_container: answers")
        changed_encoding = kblib.parse_yaml_subset(changed_bytes.decode("utf-8"))
        sources = dict(self.kernel_sources)
        for path in self.encoding_sources:
            sources[path] = project_profile_document(changed_bytes, self.snapshot[INTERFACE])
        document = copy.deepcopy(self.examples[1])
        document["schema_version"] = changed_encoding["document_schema_version"]
        document[changed_encoding["slot_container"]] = document.pop("slots")
        result = validate_profile(document, sources)
        self.assertTrue(result.valid, "\n".join(result.diagnostics))
        self.assertFalse(validate_profile(document, self.sources).valid)
        document["answers"]["priority-rubric"]["priority_quota"]["items"][0]["maximum_share"] = 2
        self.assertFalse(validate_profile(document, sources).valid)
        self.assertEqual(self.kernel_sources, {path: sources[path] for path in self.kernel_sources})

    def test_directory_identity_is_tool_layout_not_kernel_slot_policy(self):
        document = copy.deepcopy(self.examples[1])
        document["profile_id"] = "Readable identity, not a directory slug"
        self.assert_valid(document)
        with self.assertRaises(profile_layout_contract.ProfileLayoutError):
            profile_layout_contract.parse_profile_manifest_path(
                "profiles/" + document["profile_id"] + "/profile.toml")

    def test_projection_cli_checks_and_regenerates_only_declared_views(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entries = [entry for entry in self.encoding["cue_sources"] if "projection_of" in entry]
            inputs = {ENCODING, INTERFACE, *(entry["projection_of"] for entry in entries)}
            paths = inputs | {entry["path"] for entry in entries} | set(self.encoding_sources)
            for relative in paths:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            owners_before = {relative: (root / relative).read_bytes() for relative in inputs}
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(projection_main(["--root", str(root), "--check"]), 0)
                stale = root / entries[0]["path"]
                expected = stale.read_bytes()
                stale.write_bytes(expected + b"// edited projection\n")
                self.assertEqual(projection_main(["--root", str(root), "--check"]), 1)
                self.assertEqual(projection_main(["--root", str(root), "--write"]), 0)
                self.assertEqual(stale.read_bytes(), expected)
                self.assertEqual(projection_main(["--root", str(root), "--check"]), 0)
                stale.unlink()
                stale.symlink_to(ROOT / entries[0]["path"])
                self.assertEqual(projection_main(["--root", str(root), "--write"]), 1)
            self.assertIn("stale Profile schema projections", errors.getvalue())
            self.assertIn("symlink in projection path", errors.getvalue())
            self.assertEqual(owners_before, {relative: (root / relative).read_bytes() for relative in inputs})

    def test_kernel_declares_owners_and_tool_resolves_exact_contract_membership(self):
        self.assertNotIn("cue_sources", self.interface)
        self.assertNotIn("projection_of", self.interface)
        self.assertNotIn("cue_definitions", self.interface)
        self.assertEqual(self.interface["semantic_definition"], "#ProfileSlots")
        self.assertEqual(self.encoding["cue_definitions"],
                         {"profile": "#Profile", "draft": "#ProfileDraft"})
        self.assertTrue(self.encoding_sources)
        self.assertFalse(set(self.kernel_sources) & set(self.encoding_sources))
        self.assertTrue(all(path.startswith("Tools/") for path in self.encoding_sources))
        self.assertEqual(self.encoding["interface_id"], self.interface["interface_id"])
        owners = {item["contract_id"]: item["semantic_owner"]
                  for item in self.interface["contracts"]}
        sources = self.encoding["cue_sources"]
        self.assertEqual(len(owners), len(self.interface["contracts"]))
        self.assertEqual(set(owners), {item["contract_id"] for item in sources})
        self.assertEqual(len(sources), len({item["path"] for item in sources}))
        self.assertEqual(len(sources), len({item["contract_id"] for item in sources}))
        self.assertTrue(all(owners.values()))
        for value in _strings(self.interface):
            self.assertFalse(value.startswith(("kernel/", "Tools/", "profiles/")), value)
            self.assertFalse(value.endswith((".cue", ".yaml", ".toml", ".md")), value)
        for source in sources:
            with self.subTest(contract=source["contract_id"]):
                self.assertNotIn("semantic_owner", source)
                self.assertTrue(source["path"].endswith(".cue"))
                self.assertNotIn("..", Path(source["path"]).parts)
                self.assertIn(b"package profile", self.sources[source["path"]])
                if "projection_of" in source:
                    owner = kblib.parse_yaml_subset(self.snapshot[source["projection_of"]].decode("utf-8"))
                    self.assertEqual(owner.get("contract_id", owner.get("registry_id")),
                                     source["contract_id"])
                    self.assertEqual(owner["semantic_owner"], owners[source["contract_id"]])
        for role, identity in self.interface["registry_references"].items():
            owner = kblib.parse_yaml_subset(self.snapshot[self.encoding["registry_references"][role]].decode("utf-8"))
            self.assertEqual(identity, owner.get("contract_id", owner.get("registry_id")))

    def test_all_generated_projections_match_the_same_owner_snapshot(self):
        check_profile_schema_projections(self.encoding, self.snapshot)
        expected_document = project_profile_document(self.snapshot[ENCODING], self.snapshot[INTERFACE])
        for actual in self.encoding_sources.values():
            self.assertEqual(actual, expected_document)
        for source in self.encoding["cue_sources"]:
            if "projection_of" in source:
                expected = project_profile_schema(
                    source["projection_of"], self.snapshot[source["projection_of"]])
                self.assertEqual(expected, self.sources[source["path"]])

    def test_encoding_projection_cannot_drift_from_either_snapshot_owner(self):
        for path in (INTERFACE, ENCODING, *self.encoding_sources):
            with self.subTest(source=path):
                changed = dict(self.snapshot)
                changed[path] += b"\n// edited\n" if path.endswith(".cue") else b"\n# edited\n"
                with self.assertRaisesRegex(ValueError, "stale Profile encoding projection"):
                    check_profile_schema_projections(self.encoding, changed)
                missing = dict(self.snapshot)
                del missing[path]
                with self.assertRaises(KeyError):
                    check_profile_schema_projections(self.encoding, missing)

    def test_metadata_condition_members_follow_original_owner_not_text_projection(self):
        owner_path = self.encoding["registry_references"]["metadata_profile_contract"]
        owner = kblib.parse_yaml_subset(self.snapshot[owner_path].decode("utf-8"))
        self.assertEqual(owner["condition"]["in_shape"], "nonempty-list")
        # This is an independent check through the retained K08 evaluator,
        # not a second expected schema copied from the CUE generator.
        for member in (1, True, "", {"x": "y"}, ["nested"], None):
            with self.subTest(member=member):
                document = copy.deepcopy(self.examples[0])
                entry = document["slots"]["metadata-contract"]["extension_fields"][1]
                entry["condition"] = {"all": [{"field": "type", "in": [member]}]}
                issues = kblib.validate_metadata_contract_shape(
                    document["slots"]["metadata-contract"], contract=owner)
                self.assertEqual(issues, [])
                self.assert_valid(document)
        entry["condition"]["all"][0]["in"] = []
        self.assertTrue(kblib.validate_metadata_contract_shape(
            document["slots"]["metadata-contract"], contract=owner))
        self.assert_invalid(document)

    def test_stale_or_handwritten_projection_and_missing_owner_fail_closed(self):
        entry = next(item for item in self.encoding["cue_sources"] if "projection_of" in item)
        with self.subTest(change="owner bytes"):
            changed = dict(self.snapshot)
            changed[entry["projection_of"]] += b"\n# changed owner snapshot\n"
            with self.assertRaises(ValueError):
                check_profile_schema_projections(self.encoding, changed)
        with self.subTest(change="generated bytes"):
            changed = dict(self.snapshot)
            changed[entry["path"]] += b"\n// a parallel handwritten edit\n"
            with self.assertRaises(ValueError):
                check_profile_schema_projections(self.encoding, changed)
        with self.subTest(change="missing owner"):
            changed = dict(self.snapshot)
            del changed[entry["projection_of"]]
            with self.assertRaises(KeyError):
                check_profile_schema_projections(self.encoding, changed)

    def test_empty_template_is_a_draft_without_policy_or_adoption_state(self):
        template = loads_profile((ROOT / "profiles/_template/profile.toml").read_bytes())
        self.assertEqual(template, {"schema_version": 1, "slots": {}})
        self.assert_valid(template, draft=True)
        self.assert_invalid(template)
        manifest = _read_yaml("profiles/template-files.yaml")
        directory = ROOT / manifest["source"]
        copied = set(manifest["copy"])
        orientation = set(manifest["orientation_not_copied"])
        actual = {str(path.relative_to(directory)) for path in directory.rglob("*")
                  if path.is_file()}
        self.assertEqual(copied | orientation, actual)
        self.assertFalse(copied & orientation)
        self.assertIn("profile.toml", copied)
        self.assertIn("README.md", orientation)
        self.assertFalse(any(path.endswith((
            "profile.md", "scope-and-architecture.md", "metadata-contract.yaml",
            "vocabulary-extensions.yaml", "rendering-contract.yaml")) for path in copied))

    def test_interview_uses_semantic_paths_and_covers_every_registered_slot(self):
        interview = _read_yaml("profiles/interview.yaml")
        slots = {item["slot_id"] for item in self.interface["slots"]}
        reached = set()
        questions = interview["core_pack"] + interview["expansion_packs"]
        self.assertEqual(interview["profile_document"], self.encoding["entrypoint"])
        for question in questions:
            if "binds_slot" in question:
                self.assertIn(question["binds_slot"], slots)
                reached.add(question["binds_slot"])
            paths = [item["path"] for item in question.get("maps_to", ())]
            self.assertEqual(len(paths), len(set(paths)), question.get("id", question.get("slot")))
            for target in question.get("maps_to", ()):
                self.assertEqual(set(target), {"path"})
                parts = target["path"].split(".")
                if parts == ["profile_id"]:
                    continue
                self.assertGreaterEqual(len(parts), 2)
                self.assertEqual(parts[0], "slots")
                self.assertIn(parts[1], slots)
                reached.add(parts[1])
                for example in self.examples:
                    node = example
                    for part in parts:
                        self.assertIsInstance(node, dict, target["path"])
                        self.assertIn(part, node, target["path"])
                        node = node[part]
        self.assertEqual(reached, slots)
        for rewrite in interview["self_path_rewrites"]:
            self.assertNotIn("file", rewrite)
            self.assertNotIn("cell", rewrite)
            self.assertTrue(rewrite["path"].startswith("slots."))

    def test_examples_obey_current_contracts_without_becoming_template_defaults(self):
        slots = {item["slot_id"] for item in self.interface["slots"]}
        for example in self.examples:
            with self.subTest(profile=example["profile_id"]):
                self.assertEqual(set(example["slots"]), slots)
                self.assert_valid(example)
                self.assertEqual(loads_profile(dumps_profile(example)), example)
        worked = self.examples[1]
        self.assertEqual(worked["execution_default_overrides"]["concurrency_cap"], 1)
        self.assertIs(type(worked["execution_default_overrides"]["concurrency_cap"]), int)
        quotas = worked["slots"]["priority-rubric"]["priority_quota"]["items"]
        self.assertEqual({row["priority"]: row["maximum_share"] for row in quotas},
                         {"P0": 0.1, "P1": 0.3})

    def test_previous_identifier_namespaces_remain_closed(self):
        base = self.examples[0]
        invalid_cases = [
            ("judgment id", "audit-dimension-registry", "judgment_items", "item_id", "Mixed_ID"),
            ("scan id", "registered-scan-registry", "scan_registrations", "scan_id", "bad_scan"),
        ]
        for label, slot, collection, field, value in invalid_cases:
            with self.subTest(case=label):
                document = copy.deepcopy(base)
                document["slots"][slot][collection][0][field] = value
                self.assert_invalid(document)
        document = copy.deepcopy(base)
        document["slots"]["role-registry"]["extension_roles"] = {
            "mode": "configured",
            "items": [{"role_id": "Bad_Role", "actor": "User", "responsibility": "Review."}],
        }
        self.assert_invalid(document)
        document = copy.deepcopy(base)
        document["slots"]["expression-layer-entry"]["registered_artifacts"]["items"][0]["artifact_id"] = "Bad_Artifact"
        self.assert_invalid(document)

    def test_audit_targets_come_from_owner_and_cannot_repeat(self):
        for targets, valid in (
            (["review"], True), (["receipt"], True),
            (["review", "receipt"], True), (["receipt", "review"], True),
            (["review", "review"], False), (["receipt", "receipt", "review"], False),
            (["unknown"], False), ([], False),
        ):
            with self.subTest(targets=targets):
                document = copy.deepcopy(self.examples[0])
                document["slots"]["audit-dimension-registry"]["extension_dimensions"] = {
                    "mode": "configured",
                    "items": [{"dimension_id": "domain_quality", "targets": targets,
                               "meaning": "A bounded domain judgment."}],
                }
                (self.assert_valid if valid else self.assert_invalid)(document)
        document["slots"]["audit-dimension-registry"]["extension_dimensions"]["items"][0].update(
            dimension_id="domain-quality", targets=["review"])
        self.assert_invalid(document)

    def test_field_gate_and_expression_token_shapes_preserve_old_domains(self):
        # This exercises the record contract only. Capability and authority
        # references receive their separate checks in the Profile linker.
        document = copy.deepcopy(self.examples[1])
        bindings = self.encoding["capability_bindings"]
        gate = {
            "gate_id": "P:worked-planning:ready",
            "owner_ref": "corpus-plan-structure",
            "blocked_transition": "mark-ready",
            "pass_authority_role_id": "gatekeeper",
            "applicability": "The declared field requires review.",
            "vocabulary_field": "review_status",
            "completion_values": ["ready"],
            "judgment_item_id": document["slots"]["audit-dimension-registry"]["judgment_items"][0]["item_id"],
            "producer_kind": "manual-attestation",
            "producer_capability": bindings["producer_capability_by_kind"]["manual-attestation"],
            "receipt_schema": bindings["receipt_schema_by_kind"]["manual-attestation"],
            "consumer_capability": bindings["profile_extension_enum_writer_capability"],
        }
        document["slots"]["routing-and-gate-registry"]["extension_gates"] = {
            "mode": "configured", "items": [gate],
        }
        self.assert_valid(document)
        for field, value in (
            ("gate_id", "ordinary-gate"), ("blocked_transition", "bad_transition"),
            ("vocabulary_field", "bad-field"), ("completion_values", ["MixedCase"]),
            ("completion_values", ["ready", "ready"]),
        ):
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(document)
                changed["slots"]["routing-and-gate-registry"]["extension_gates"]["items"][0][field] = value
                self.assert_invalid(changed)
        for fields in (["bad-field"], ["canonical_bindings", "canonical_bindings"]):
            changed = copy.deepcopy(self.examples[0])
            changed["slots"]["expression-layer-entry"]["registered_artifacts"]["items"][0]["metadata_fields"] = fields
            self.assert_invalid(changed)

    def test_batch_receipt_schema_preserves_the_existing_closed_domain(self):
        document = copy.deepcopy(self.examples[1])
        item_id = document["slots"]["audit-dimension-registry"]["judgment_items"][0]["item_id"]
        row = {
            "judgment_item_id": item_id, "target_selector": "each-manifest-page",
            "trigger": "before-merge-ready", "producer_kind": "manual-attestation",
            "receipt_schema": "page-batch-judgment-v2", "pass_authority_role_id": "gatekeeper",
        }
        document["slots"]["routing-and-gate-registry"]["batch_review_requirements"] = {
            "mode": "configured", "items": [row],
        }
        self.assert_valid(document)
        row["receipt_schema"] = "invented-receipt-v99"
        self.assert_invalid(document)

    def test_fixed_role_and_priority_sets_cannot_be_lost_during_encoding(self):
        document = copy.deepcopy(self.examples[1])
        placements = document["slots"]["profile-scope"]["placement_layer_registrations"]
        del placements[-1]
        self.assert_invalid(document)
        document = copy.deepcopy(self.examples[1])
        placements = document["slots"]["profile-scope"]["placement_layer_registrations"]
        placements[-1]["role_id"] = placements[0]["role_id"]
        self.assert_invalid(document)
        document = copy.deepcopy(self.examples[1])
        document["slots"]["priority-rubric"]["priority_quota"]["items"].pop()
        self.assert_invalid(document)
        document = copy.deepcopy(self.examples[1])
        quota = document["slots"]["priority-rubric"]["priority_quota"]["items"]
        quota[1]["priority"] = quota[0]["priority"]
        self.assert_invalid(document)

    def test_no_hidden_activation_default_or_unknown_answer_field(self):
        for field, value in (("active", True), ("confirmed", True), ("current_selection", "example")):
            with self.subTest(field=field):
                document = copy.deepcopy(self.examples[1])
                document[field] = value
                self.assert_invalid(document)
        document = copy.deepcopy(self.examples[1])
        document["slots"]["profile-scope"]["unknown_policy"] = "not an admitted field"
        self.assert_invalid(document)
        document = copy.deepcopy(self.examples[1])
        document["slots"]["corpus-planning"]["artifact_bindings"].pop("global_map")
        self.assert_invalid(document)
        document = copy.deepcopy(self.examples[1])
        document["slots"]["source-policy"]["domain_comparison_rules"]["mode"] = "none"
        self.assert_invalid(document)

    def test_natural_language_round_trips_without_becoming_executable_or_empty(self):
        document = copy.deepcopy(self.examples[1])
        text = '中文 policy\nEnglish "quote" | `literal`\nA condition remains a human judgment.'
        document["slots"]["profile-scope"]["goal"]["statement"] = text
        self.assert_valid(document)
        roundtrip = loads_profile(dumps_profile(document))
        self.assertEqual(roundtrip["slots"]["profile-scope"]["goal"]["statement"], text)
        for empty in ("", "   ", "\t\n", "\u3000"):
            document["slots"]["profile-scope"]["goal"]["statement"] = empty
            self.assert_invalid(document)

    def test_cue_resolver_accepts_builtin_syntax_and_refuses_external_imports(self):
        """Tool execution isolation uses the real CUE parser, not source scanning."""
        for index, declaration in enumerate((
                'import "strings"', 'import\t"strings"',
                'import (\n // owner dependency\n "strings"\n)')):
            source = 'package profile\n%s\n#Profile: {value: strings.MinRunes(1)}\n' % declaration
            result = validate_profile({"value": 'import "example.invalid/not-code"'}, {
                "isolation/builtin-%d.cue" % index: source,
            })
            self.assertTrue(result.valid, "\n".join(result.diagnostics))
        for index, declaration in enumerate((
                'import "unavailable.invalid/remote"',
                'import\t"unavailable.invalid/remote"',
                'import (\n\t"unavailable.invalid/remote"\n)')):
            source = 'package profile\n%s\n#Profile: {value: remote.#Value}\n' % declaration
            result = validate_profile({"value": "literal"}, {
                "isolation/external-%d.cue" % index: source,
            })
            self.assertFalse(result.valid)
            self.assertIn("imports are unavailable", "\n".join(result.diagnostics))

    def test_cue_execution_has_private_config_cache_and_no_ambient_controls(self):
        """This checks Tool process settings, not Profile acceptance obligations."""
        original_run = kblib.run_cambium_subprocess
        evaluations = []

        def inspect_run(command, **kwargs):
            if command[1] == "vet":
                directory = Path(kwargs["cwd"])
                environment = kwargs["env"]
                self.assertEqual(environment["CUE_REGISTRY"], "none")
                self.assertEqual(Path(environment["CUE_CACHE_DIR"]), directory / "cache")
                self.assertEqual(Path(environment["CUE_CONFIG_DIR"]), directory / "config")
                self.assertNotIn("CUE_EXPERIMENT", environment)
                self.assertNotIn("CUE_DEBUG", environment)
                self.assertEqual(list((directory / "cue.mod").iterdir()), [])
                self.assertFalse((directory / "cache").exists())
                self.assertFalse((directory / "config").exists())
                self.assertEqual(len(command[5:]), 2)
                self.assertTrue(command[5].startswith("owner_"))
                self.assertEqual(command[6], "candidate.json")
                evaluations.append(directory)
            return original_run(command, **kwargs)

        with mock.patch.dict(os.environ, {
                "CUE_REGISTRY": "unavailable.invalid",
                "CUE_CACHE_DIR": "/ambient/cache", "CUE_CONFIG_DIR": "/ambient/config",
                "CUE_EXPERIMENT": "ambient", "CUE_DEBUG": "ambient"}), \
                mock.patch.object(kblib, "run_cambium_subprocess", side_effect=inspect_run):
            for index in range(2):
                result = validate_profile({"value": index}, {
                    "isolation/environment-%d.cue" % index: "package profile\n#Profile: {value: int}\n",
                })
                self.assertTrue(result.valid, "\n".join(result.diagnostics))
        self.assertEqual(len(evaluations), 2)
        self.assertNotEqual(evaluations[0], evaluations[1])
        self.assertTrue(all(not directory.exists() for directory in evaluations))

    def test_cue_temporary_workspace_cannot_import_an_ancestor_module(self):
        original_temporary_directory = tempfile.TemporaryDirectory
        with original_temporary_directory(prefix="cambium-cue-parent-test-") as temporary:
            parent = Path(temporary)
            (parent / "cue.mod").mkdir()
            (parent / "cue.mod/module.cue").write_text(
                'module: "example.invalid/ambient@v0"\nlanguage: version: "v0.17.1"\n',
                encoding="utf-8")
            (parent / "dependency").mkdir()
            (parent / "dependency/value.cue").write_text(
                'package dependency\n#Value: "outside snapshot"\n', encoding="utf-8")

            def nested_workspace(**kwargs):
                return original_temporary_directory(dir=parent, **kwargs)

            with mock.patch.object(profile_cue.tempfile, "TemporaryDirectory", side_effect=nested_workspace):
                result = validate_profile({"value": "outside snapshot"}, {
                    "isolation/ancestor.cue": 'package profile\n'
                    'import "example.invalid/ambient/dependency"\n'
                    '#Profile: {value: dependency.#Value}\n',
                })
            self.assertFalse(result.valid)
            self.assertIn("imports are unavailable", "\n".join(result.diagnostics))

    def test_cue_shared_process_boundary_retains_but_does_not_consume_descriptors(self):
        """CUE success is not an acknowledgement of Cambium path consumption."""
        original_run = subprocess.run
        launches = []
        ack_read, ack_write = os.pipe()
        try:
            with tempfile.TemporaryFile() as retained:
                retained.write(b"not a CUE input")
                retained.flush()
                descriptor = retained.fileno()

                def inspect_launch(command, **kwargs):
                    self.assertIn(descriptor, kwargs["pass_fds"])
                    self.assertIn(ack_write, kwargs["pass_fds"])
                    self.assertEqual(kwargs["env"]["CAMBIUM_PATH_CAPABILITIES"], "opaque to CUE")
                    self.assertEqual(kwargs["env"]["CAMBIUM_PATH_CAPABILITIES_ACK_FD"], str(ack_write))
                    launches.append(command)
                    return original_run(command, **kwargs)

                with mock.patch.object(kblib, "inherited_path_capability_subprocess", return_value={
                        "pass_fds": (descriptor, ack_write),
                        "env_overrides": {
                            "CAMBIUM_PATH_CAPABILITIES": "opaque to CUE",
                            "CAMBIUM_PATH_CAPABILITIES_ACK_FD": str(ack_write),
                        }}), mock.patch.object(kblib.subprocess, "run", side_effect=inspect_launch):
                    result = validate_profile({"value": "explicit JSON only"}, {
                        "isolation/descriptors.cue": "package profile\n#Profile: {value: string}\n",
                    })
                self.assertTrue(result.valid, "\n".join(result.diagnostics))
                self.assertTrue(any(command[1] == "vet" for command in launches))
                retained.seek(0)
                self.assertEqual(retained.read(), b"not a CUE input")
                os.set_blocking(ack_read, False)
                with self.assertRaises(BlockingIOError):
                    os.read(ack_read, 1)
        finally:
            os.close(ack_read)
            os.close(ack_write)


if __name__ == "__main__":
    unittest.main()
