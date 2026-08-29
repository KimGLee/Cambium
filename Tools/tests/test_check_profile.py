"""Profile admission checks in ``check_profile.py``.

Covers the execution-default override registry and the end-to-end typed
``profile-load`` Gate, including the transitive dependency closure that keeps
one selected Profile from consuming another Profile's runtime-active cells,
plus the closed mechanical/semantic-unresolved classification map behind
``--json`` structured diagnostics.
"""

import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "Tools/check_profile.py"
EXECUTION_DEFAULTS = (
    REPOSITORY / "kernel/K00 Standards Control/execution-defaults-base.yaml"
)
PLACEHOLDER_DEFAULTS = (
    REPOSITORY / "Tools/schemas/execution_defaults.template.yaml"
)
sys.path.insert(0, str(REPOSITORY / "Tools"))
sys.path.insert(0, str(REPOSITORY / "Tools/tests"))
import kblib  # noqa: E402
import check_queue  # noqa: E402
import corpus_planning_contract  # noqa: E402
import metadata_execution_contract  # noqa: E402
import profile_contract  # noqa: E402
import test_profile_onboarding_status as profile_fixture  # noqa: E402


def capability_implementation_paths():
    document = kblib.parse_yaml_subset(
        (REPOSITORY / "Tools/operation-capabilities.yaml").read_text(
            encoding="utf-8"))
    return metadata_execution_contract.capability_implementation_paths(
        document)

MANIFEST_HEAD = (
    "# Profile\n\n"
    "## Profile Identity\n\n"
    "- `profile_id`: `sample`\n\n"
    "## Implemented Slots\n\n"
    "## Execution Default Overrides\n\n"
    "| Override item ID from the registry | Non-default profile value |\n"
    "|---|---|\n"
)


class ExecutionDefaultOverrideTests(unittest.TestCase):
    """Each case runs the real checker against a one-row override table."""

    def run_check(self, override_rows, execution_defaults=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            for source, relative in (
                    (REPOSITORY / profile_contract.PROFILE_INTERFACE_PATH,
                     profile_contract.PROFILE_INTERFACE_PATH),
                    (PLACEHOLDER_DEFAULTS,
                     "Tools/schemas/execution_defaults.template.yaml"),
                    (REPOSITORY / "Tools/operation-capabilities.yaml",
                     "Tools/operation-capabilities.yaml"),
                    (REPOSITORY / "Tools/runtime_paths.py",
                     "Tools/runtime_paths.py"),
                    (REPOSITORY / profile_contract.SCAN_CAPABILITY_PATH,
                     profile_contract.SCAN_CAPABILITY_PATH),
                    (REPOSITORY / "Tools/check_residual_content.py",
                     "Tools/check_residual_content.py"),
                    (REPOSITORY /
                     "Tools/compiled/metadata-execution-contract.json",
                     "Tools/compiled/metadata-execution-contract.json"),
                    (REPOSITORY /
                     "kernel/K08 Metadata and Status/metadata-authority-base.yaml",
                     "kernel/K08 Metadata and Status/metadata-authority-base.yaml"),
                    (REPOSITORY /
                     profile_contract.KERNEL_APPLICABILITY_PATH,
                     profile_contract.KERNEL_APPLICABILITY_PATH),
                    (REPOSITORY /
                     profile_contract.KERNEL_RELATIONSHIP_PATH,
                     profile_contract.KERNEL_RELATIONSHIP_PATH),
                    (REPOSITORY /
                     profile_contract.AUDIT_DIMENSION_BASE_PATH,
                     profile_contract.AUDIT_DIMENSION_BASE_PATH),
                    (REPOSITORY /
                     corpus_planning_contract.CORPUS_PLANNING_CONTRACT_PATH,
                     corpus_planning_contract.CORPUS_PLANNING_CONTRACT_PATH),
                    (REPOSITORY / check_queue.STANDARDS_GATE_REGISTRY_PATH,
                     check_queue.STANDARDS_GATE_REGISTRY_PATH)):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            for relative in capability_implementation_paths():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPOSITORY / relative, target)
            profile_dir = root / "profiles/sample"
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.md").write_text(
                MANIFEST_HEAD + override_rows, encoding="utf-8")
            registry = (
                root /
                "kernel/K00 Standards Control/execution-defaults-base.yaml")
            registry.parent.mkdir(parents=True, exist_ok=True)
            if execution_defaults is not None:
                registry.write_text(execution_defaults, encoding="utf-8")
            else:
                shutil.copy2(EXECUTION_DEFAULTS, registry)
            receipts = root / "receipts.jsonl"
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(profile_dir),
                 "--root", str(root),
                 "--receipts", str(receipts)],
                text=True, capture_output=True, check=False)
            written = []
            if receipts.exists():
                written = [json.loads(line) for line in
                           receipts.read_text(encoding="utf-8").splitlines()
                           if line.strip()]
            return completed, written

    def override_checks(self, receipts):
        return {r["check"] for r in receipts
                if r["result"] == "fail" and r["check"].startswith("override-")}

    # ---- the closed set now comes from the kernel registry ----

    def test_kernel_registry_supplies_the_closed_overridable_set(self):
        _, receipts = self.run_check("| `concurrency_cap` | `5` |\n")
        self.assertNotIn("override-item-unknown",
                         self.override_checks(receipts))

    def test_item_outside_the_kernel_registry_is_rejected(self):
        _, receipts = self.run_check("| `not_an_item` | `5` |\n")
        self.assertIn("override-item-unknown", self.override_checks(receipts))

    def test_constitutional_item_stays_rejected_after_the_move(self):
        _, receipts = self.run_check(
            "| `terminal_audit.round_cap` | `4` |\n")
        self.assertIn("override-constitutional-item",
                      self.override_checks(receipts))

    def test_missing_kernel_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            for source, relative in (
                    (REPOSITORY / profile_contract.PROFILE_INTERFACE_PATH,
                     profile_contract.PROFILE_INTERFACE_PATH),
                    (PLACEHOLDER_DEFAULTS,
                     "Tools/schemas/execution_defaults.template.yaml")):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            profile_dir = root / "profiles/sample"
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.md").write_text(
                MANIFEST_HEAD, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(profile_dir),
                 "--root", str(root)],
                text=True, capture_output=True, check=False)
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("canonical profile-load input", completed.stdout)

    # ---- value domain ----

    def test_positive_integer_domain_accepts_a_positive_integer(self):
        _, receipts = self.run_check("| `concurrency_cap` | `5` |\n")
        self.assertEqual(set(), self.override_checks(receipts))

    def test_positive_integer_domain_rejects_zero_negative_and_non_numeric(self):
        for value in ("0", "-1", "2.5", "many"):
            with self.subTest(value=value):
                _, receipts = self.run_check(
                    "| `concurrency_cap` | `%s` |\n" % value)
                self.assertIn("override-value-domain",
                              self.override_checks(receipts))

    SHARE_REGISTRY = (
        "schema_version: 1\n"
        "overridable:\n"
        "  - item: \"concurrency_cap\"\n"
        "    owner: \"kernel/K13 Task Runtime and Execution Control/"
        "10 Batch Admission Transitions and Serial Integration.md\"\n"
        "  - item: \"fixture.share\"\n"
        "    owner: \"kernel/K00 Standards Control/"
        "07 Effort Tiering and Priority Quota.md\"\n"
        "    value_domain: \"percent-share-under-100\"\n"
        "constitutional: []\n"
    )

    def test_share_domain_accepts_bare_and_suffixed_percentages(self):
        for value in ("20", "20%", "0", "99.9%", "12.5%"):
            with self.subTest(value=value):
                _, receipts = self.run_check(
                    "| `fixture.share` | `%s` |\n" % value,
                    execution_defaults=self.SHARE_REGISTRY)
                self.assertEqual(set(), self.override_checks(receipts))

    def test_share_domain_rejects_out_of_range_and_non_numeric(self):
        for value in ("120%", "-5", "a lot"):
            with self.subTest(value=value):
                _, receipts = self.run_check(
                    "| `fixture.share` | `%s` |\n" % value,
                    execution_defaults=self.SHARE_REGISTRY)
                self.assertIn("override-value-domain",
                              self.override_checks(receipts))

    def test_a_share_of_the_whole_corpus_is_rejected_on_both_quota_items(self):
        """The named degenerate value: in 0..100, but it empties `P2`.

        Its owner keeps a remainder class outside the quota and demotes what
        exceeds the quota, so a share of the whole corpus states an empty
        class and leaves nothing able to exceed it.
        """
        for value in ("100", "100%", "100.0"):
            with self.subTest(value=value):
                _, receipts = self.run_check(
                    "| `fixture.share` | `%s` |\n" % value,
                    execution_defaults=self.SHARE_REGISTRY)
                self.assertIn("override-value-domain",
                              self.override_checks(receipts))

    def test_the_registry_names_a_domain_the_checker_implements(self):
        """Registry and checker are updated together, per the unknown path."""
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import check_profile
        import kblib
        registry = kblib.load_yaml_file(EXECUTION_DEFAULTS)
        named = {entry["item"]: entry.get("value_domain")
                 for entry in registry["overridable"]}
        # priority_quota.* is retired from this registry: the standing quota
        # truth lives in the Priority Rubric slot's Priority Quota block, so
        # a manifest still carrying the old rows fails as an unknown item.
        self.assertNotIn("priority_quota.P0", named)
        self.assertNotIn("priority_quota.P1", named)
        for item, domain in named.items():
            if domain is not None:
                self.assertIn(domain, check_profile.VALUE_DOMAINS, item)

    def test_item_without_a_registered_domain_is_left_to_its_owner(self):
        _, receipts = self.run_check("| `batch_size.S` | `whatever` |\n")
        self.assertEqual(set(), self.override_checks(receipts))

    def test_unimplemented_domain_name_is_reported_not_ignored(self):
        registry = (
            "schema_version: 1\n"
            "overridable:\n"
            "  - item: \"concurrency_cap\"\n"
            "    owner: \"kernel/K13 Task Runtime and Execution Control/"
            "10 Batch Admission Transitions and Serial Integration.md\"\n"
            "    value_domain: \"prime-number\"\n"
            "constitutional: []\n"
        )
        _, receipts = self.run_check("| `concurrency_cap` | `5` |\n",
                                     execution_defaults=registry)
        self.assertIn("override-value-domain-unknown",
                      self.override_checks(receipts))

    def test_domain_failure_names_the_owner_module(self):
        _, receipts = self.run_check(
            "| `fixture.share` | `120%` |\n",
            execution_defaults=self.SHARE_REGISTRY)
        details = [r["details"] for r in receipts
                   if r["check"] == "override-value-domain"]
        self.assertEqual(1, len(details), receipts)
        self.assertIn("07 Effort Tiering and Priority Quota.md", details[0])

    def test_empty_and_redundant_rows_keep_their_own_checks(self):
        _, receipts = self.run_check("| `concurrency_cap` |  |\n")
        self.assertIn("override-choice-empty", self.override_checks(receipts))
        _, receipts = self.run_check(
            "| `concurrency_cap` | `use-kernel-default` |\n")
        self.assertIn("override-redundant-default",
                      self.override_checks(receipts))


class ShippedRegistryTests(unittest.TestCase):
    """The two registries must stay split the way the licensing record says."""

    def test_placeholder_registry_no_longer_carries_the_rule_blocks(self):
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import kblib
        placeholders = kblib.load_yaml_file(PLACEHOLDER_DEFAULTS)
        self.assertNotIn("overridable", placeholders)
        self.assertNotIn("constitutional", placeholders)
        self.assertIn("reserved_profile_ids", placeholders)
        self.assertIn("unfilled_sentinel", placeholders)

    def test_kernel_registry_carries_both_closed_sets_with_owners(self):
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import kblib
        registry = kblib.load_yaml_file(EXECUTION_DEFAULTS)
        items = [entry["item"] for entry in registry["overridable"]]
        self.assertEqual([
            "concurrency_cap",
            "batch_size.S", "batch_size.M", "batch_size.L",
            "maintenance.unselected_rounds_before_log_only",
            "maintenance.incoming_retarget_divisor",
        ], items)
        self.assertEqual(
            ["substantive_review.round_cap", "terminal_audit.round_cap"],
            [entry["item"] for entry in registry["constitutional"]])
        for entry in registry["overridable"] + registry["constitutional"]:
            self.assertTrue(str(entry["owner"]).startswith("kernel/"), entry)
            self.assertTrue(
                (REPOSITORY / entry["owner"]).is_file(), entry["owner"])

    def test_profile_load_registry_version_matches_the_producer(self):
        import check_profile
        registry = kblib.load_yaml_file(
            REPOSITORY / "kernel/K00 Standards Control/control-registry.yaml")
        rows = [row for row in registry.get("gates", [])
                if row.get("gate_id") == check_profile.GATE_ID]
        self.assertEqual(1, len(rows), rows)
        self.assertEqual(check_profile.TOOL, rows[0].get("tool"))
        self.assertEqual(check_profile.TOOL_VERSION,
                         rows[0].get("tool_version"))


class ProfileCliFixture(unittest.TestCase):
    """Shared temp-root fixture and helpers for the profile-load CLI."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self._copy_repository_file(profile_contract.PROFILE_INTERFACE_PATH)
        self._copy_repository_file(
            "Tools/schemas/execution_defaults.template.yaml")
        self._copy_repository_file(
            "kernel/K00 Standards Control/execution-defaults-base.yaml")
        self._copy_repository_file("Tools/operation-capabilities.yaml")
        self._copy_repository_file("Tools/runtime_paths.py")
        self._copy_repository_file(profile_contract.SCAN_CAPABILITY_PATH)
        self._copy_repository_file(
            "Tools/compiled/metadata-execution-contract.json")
        self._copy_repository_file(
            "kernel/K08 Metadata and Status/metadata-authority-base.yaml")
        self._copy_repository_file(
            profile_contract.KERNEL_APPLICABILITY_PATH)
        self._copy_repository_file(
            profile_contract.KERNEL_RELATIONSHIP_PATH)
        self._copy_repository_file(
            profile_contract.AUDIT_DIMENSION_BASE_PATH)
        self._copy_repository_file(
            corpus_planning_contract.CORPUS_PLANNING_CONTRACT_PATH)
        self._copy_repository_file(check_queue.STANDARDS_GATE_REGISTRY_PATH)
        self._copy_repository_file("Tools/check_residual_content.py")
        for relative in capability_implementation_paths():
            self._copy_repository_file(relative)
        self.original_profile = profile_fixture.fill_candidate(
            self.root, "base-profile")

    def _copy_repository_file(self, relative):
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY / relative, destination)

    def _replace_exact(self, path, old, new, count=None):
        text = path.read_text(encoding="utf-8")
        observed = text.count(old)
        if count is not None:
            self.assertEqual(count, observed, (path, old))
        else:
            self.assertGreater(observed, 0, (path, old))
        path.write_text(text.replace(old, new), encoding="utf-8")

    def _copied_profile(self, profile_id, self_owned=False):
        profile = self.root / "profiles" / profile_id
        shutil.copytree(self.original_profile, profile)
        self._replace_exact(
            profile / "profile.md",
            "- `profile_id`: `base-profile`",
            "- `profile_id`: `%s`" % profile_id,
            count=1)
        if self_owned:
            old_prefix = "profiles/base-profile"
            new_prefix = "profiles/%s" % profile_id
            for relative in (
                    "registries/audit-dimensions.md",
                    "registries/registered-scans.md"):
                self._replace_exact(
                    profile / relative, old_prefix, new_prefix)
        return profile

    def _run_check(self, profile, receipt_name, *extra_args):
        receipt_path = self.root / receipt_name
        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(profile),
             "--root", str(self.root), "--receipts", str(receipt_path),
             *extra_args],
            text=True, capture_output=True, check=False)
        receipts = []
        if receipt_path.exists():
            receipts = [
                json.loads(line)
                for line in receipt_path.read_text(
                    encoding="utf-8").splitlines()
                if line.strip()
            ]
        return completed, receipts

    def _checks(self, receipts, result="fail"):
        return [
            receipt["check"] for receipt in receipts
            if receipt["result"] == result
        ]

    def _profile_tree_state(self, profile):
        state = {}
        for path in sorted(profile.rglob("*")):
            relative = path.relative_to(profile).as_posix()
            if path.is_symlink():
                state[relative] = ("symlink", str(path.readlink()))
            elif path.is_dir():
                state[relative] = ("directory",)
            else:
                state[relative] = ("file", path.read_bytes())
        return state

    def _without_dynamic_receipt_fields(self, receipts):
        dynamic = {"receipt_id", "checked_at"}
        return [
            {key: value for key, value in receipt.items()
             if key not in dynamic}
            for receipt in receipts
        ]

class ProfileLoadCliTests(ProfileCliFixture):
    """End-to-end admission tests for the typed ``profile-load`` Gate."""

    STRUCTURE_WITH_DERIVED_ROLE = """schema_version: 2
applicability:
  state: configured
  reason: null
units:
  - id: U-NOTES
    kind: domain
    parent: null
    root: "Notes"
    entry:
      path: "Notes/Overview.md"
      expected_type: overview
    global_map_entry: null
    roles:
      sequence:
        mode: not-applicable
        reason: "No sequence."
      coverage:
        mode: derived
        generator_capability: structure-coverage-projection-v1
        inputs_owner: coverage-ledger
      quick_reference:
        mode: not-applicable
        reason: "No quick reference."
      expression:
        mode: not-applicable
        reason: "No expression layer."
support_layers: []
"""

    def _profile_with_derived_structure(self, profile_id):
        copied = self._copied_profile(profile_id, self_owned=True)
        (copied / "structure-registry.yaml").write_text(
            self.STRUCTURE_WITH_DERIVED_ROLE, encoding="utf-8")
        return copied

    def test_profile_load_resolves_structure_capability_and_runtime_owner(self):
        copied = self._profile_with_derived_structure(
            "structure-reference-notes")

        completed, receipts = self._run_check(
            copied, "structure-reference.jsonl")

        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("profile-check-summary",
                      self._checks(receipts, result="pass"))

    def test_profile_load_rejects_unknown_structure_projection_capability(self):
        copied = self._profile_with_derived_structure(
            "unknown-structure-capability-notes")
        self._replace_exact(
            copied / "structure-registry.yaml",
            "structure-coverage-projection-v1",
            "unregistered-structure-projection-v1", count=1)

        completed, receipts = self._run_check(
            copied, "unknown-structure-capability.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("structure-registry-capability",
                      self._checks(receipts))

    def test_profile_load_rejects_runtime_owner_not_bound_by_capability(self):
        copied = self._profile_with_derived_structure(
            "wrong-structure-owner-notes")
        self._replace_exact(
            copied / "structure-registry.yaml",
            "inputs_owner: coverage-ledger",
            "inputs_owner: progress-ledger", count=1)

        completed, receipts = self._run_check(
            copied, "wrong-structure-owner.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("structure-registry-input-owner",
                      self._checks(receipts))

    def test_renaming_only_profile_id_rejects_all_stale_foreign_edges(self):
        """Exact Issue #42 reproduction: the source Profile still exists."""
        copied = self._copied_profile("copied-notes")

        completed, receipts = self._run_check(copied, "issue-42.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        checks = self._checks(receipts)
        self.assertGreaterEqual(
            checks.count("scan-config-path-outside-profile"), 1, receipts)
        self.assertGreaterEqual(
            checks.count("predicate-owner-path-outside-profile"), 2,
            receipts)
        details = "\n".join(receipt["details"] for receipt in receipts)
        self.assertIn("profiles/base-profile", details)
        self.assertFalse(any(
            receipt["check"] == "profile-check-summary"
            for receipt in receipts))

    def test_self_owned_copy_emits_a_bound_profile_load_pass(self):
        copied = self._copied_profile("self-owned-notes", self_owned=True)

        completed, receipts = self._run_check(copied, "self-owned.jsonl")

        self.assertEqual(0, completed.returncode, completed.stdout)
        summaries = [
            receipt for receipt in receipts
            if receipt["check"] == "profile-check-summary"
        ]
        self.assertEqual(1, len(summaries), receipts)
        summary = summaries[0]
        manifest = "profiles/self-owned-notes/profile.md"
        self.assertEqual("pass", summary["result"])
        self.assertEqual("profile-load", summary["gate_id"])
        self.assertEqual("guidance_and_contract", summary["dimension"])
        self.assertEqual(manifest, summary["target"])
        self.assertEqual(manifest, summary["selected_profile_manifest"])
        self.assertRegex(
            summary["profile_snapshot_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(
            summary["profile_contract_fingerprint"],
            r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(
            summary["profile_load_inputs_sha256"],
            r"^sha256:[0-9a-f]{64}$")
        tools = str(REPOSITORY / "Tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import kblib
        import profile_contract
        contract = profile_contract.load_profile_contract(
            self.root, copied / "profile.md")
        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(contract.fingerprint,
                         summary["profile_contract_fingerprint"])
        self.assertEqual(
            14,
            len([edge for edge in contract.dependency_edges
                 if edge.kind == "manifest-slot"]))
        full_tree = kblib.repository_tree_snapshot(
            self.root, "profiles/self-owned-notes")
        self.assertEqual(
            full_tree.project(contract.profile_snapshot_paths).sha256,
            summary["profile_snapshot_sha256"])
        self.assertEqual(
            set(contract.profile_snapshot_paths),
            set(full_tree.project(contract.profile_snapshot_paths).files))

    def test_candidate_cli_receipt_does_not_mix_live_queue_identity(self):
        copied = self._copied_profile(
            "candidate-identity-notes", self_owned=True)
        queue = self.root / ".cambium/state/required_queue.yaml"
        queue.parent.mkdir(parents=True)
        queue.write_text(
            "task_id: live-task\n"
            "standards_version: live-v1\n"
            "selected_profile_manifest: "
            "profiles/base-profile/profile.md\n",
            encoding="utf-8",
        )

        completed, receipts = self._run_check(
            copied, "candidate-identity.jsonl")

        self.assertEqual(0, completed.returncode, completed.stdout)
        summary = next(
            receipt for receipt in receipts
            if receipt["check"] == "profile-check-summary")
        self.assertEqual(
            "profiles/candidate-identity-notes/profile.md",
            summary["selected_profile_manifest"])
        self.assertNotIn("task_id", summary)
        self.assertNotIn("standards_version", summary)

    def test_shared_evaluation_returns_one_authorized_contract_snapshot(self):
        """Programmatic consumers get the same pass summary and typed IR."""
        copied = self._copied_profile("api-notes", self_owned=True)
        tools = str(REPOSITORY / "Tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import check_profile

        queue = self.root / ".cambium/state/required_queue.yaml"
        queue.parent.mkdir(parents=True)
        queue.write_text(
            "task_id: live-task\n"
            "standards_version: live-v1\n"
            "selected_profile_manifest: "
            "profiles/api-notes/profile.md\n",
            encoding="utf-8",
        )

        evaluation = check_profile.evaluate_profile_load(
            copied, root=self.root, receipt_identity=None)

        self.assertTrue(evaluation.authorized, evaluation.findings)
        self.assertEqual(0, evaluation.exit_code)
        self.assertEqual((), evaluation.findings)
        self.assertEqual(
            evaluation.contract.manifest_repo_path,
            evaluation.summary_receipt["selected_profile_manifest"],
        )
        self.assertEqual(
            evaluation.profile_snapshot_sha256,
            evaluation.summary_receipt["profile_snapshot_sha256"],
        )
        self.assertEqual(
            evaluation.profile_contract_fingerprint,
            evaluation.summary_receipt["profile_contract_fingerprint"],
        )
        self.assertIsInstance(
            evaluation.metadata_execution_contract,
            metadata_execution_contract.CompiledMetadataExecutionContract)
        self.assertEqual(
            evaluation.metadata_execution_contract.contract_fingerprint,
            evaluation.summary_receipt[
                "metadata_execution_contract_fingerprint"],
        )
        # ``None`` is an explicit identity-free API evaluation, not a request
        # to infer identity from whatever Queue may happen to be on disk.
        self.assertNotIn("task_id", evaluation.summary_receipt)
        self.assertNotIn("standards_version", evaluation.summary_receipt)

        identity = {
            "task_id": "planned-task",
            "standards_version": "planned-v2",
            "selected_profile_manifest":
                "profiles/api-notes/profile.md",
        }
        injected = check_profile.evaluate_profile_load(
            copied, root=self.root, receipt_identity=identity)
        self.assertTrue(injected.authorized, injected.findings)
        self.assertEqual("planned-task", injected.summary_receipt["task_id"])
        self.assertEqual(
            "planned-v2", injected.summary_receipt["standards_version"])

    def test_shared_evaluation_never_exposes_partial_contract_as_authority(self):
        copied = self._copied_profile("api-broken-notes")
        tools = str(REPOSITORY / "Tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import check_profile

        evaluation = check_profile.evaluate_profile_load(
            copied, root=self.root, receipt_identity=None)

        self.assertFalse(evaluation.authorized)
        self.assertEqual(1, evaluation.exit_code)
        self.assertIsNone(evaluation.contract)
        self.assertIsNone(evaluation.summary_receipt)
        self.assertTrue(evaluation.findings)

    def test_shared_evaluation_never_calls_the_receipt_writer(self):
        copied = self._copied_profile("api-no-write", self_owned=True)
        tools = str(REPOSITORY / "Tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import check_profile

        with mock.patch.object(
                check_profile.kblib, "write_receipts",
                side_effect=AssertionError("receipt writer was called")):
            evaluation = check_profile.evaluate_profile_load(
                copied, root=self.root, receipt_identity=None)

        self.assertTrue(evaluation.authorized, evaluation.findings)

    def test_candidate_result_never_emits_a_profile_load_pass(self):
        copied = self._copied_profile("candidate-notes", self_owned=True)
        manifest = copied / "profile.md"
        self._replace_exact(
            manifest,
            "\n## Execution Default Overrides\n",
            "\n- `Experimental Guidance`: `inline`\n\n"
            "## Execution Default Overrides\n",
            count=1)
        with manifest.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n## Experimental Guidance\n\n"
                "This extension is deliberately outside the interface.\n")

        completed, receipts = self._run_check(copied, "candidate.jsonl")

        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("slot-not-in-interface",
                      self._checks(receipts, result="candidate"))
        self.assertFalse(any(
            receipt["check"] == "profile-check-summary"
            for receipt in receipts))

    def test_registered_gate_rejects_all_normative_input_substitutions(self):
        copied = self._copied_profile("input-substitution", self_owned=True)
        reduced_interface = self.root / "reduced-interface.yaml"
        reduced_interface.write_text(
            (self.root / profile_contract.PROFILE_INTERFACE_PATH).read_text(
                encoding="utf-8").replace(
                    "slot_id: priority-rubric", "slot_id: priority-rubric-hidden"),
            encoding="utf-8")
        custom_defaults = self.root / "custom-defaults.yaml"
        custom_defaults.write_text(
            "schema_version: 1\nunfilled_sentinel: OTHER\n"
            "reserved_profile_ids: []\n",
            encoding="utf-8")
        custom_execution = self.root / "custom-execution.yaml"
        custom_execution.write_text(
            "schema_version: 1\noverridable: []\nconstitutional: []\n",
            encoding="utf-8")

        cases = (
            ("--interface", reduced_interface),
            ("--defaults", custom_defaults),
            ("--execution-defaults", custom_execution),
        )
        for option, path in cases:
            with self.subTest(option=option):
                completed, receipts = self._run_check(
                    copied, "substitution-%s.jsonl" % option[2:],
                    option, str(path))
                self.assertEqual(1, completed.returncode, completed.stdout)
                self.assertIn(
                    "profile-load-noncanonical-input",
                    self._checks(receipts))
                self.assertFalse(any(
                    receipt["check"] == "profile-check-summary"
                    for receipt in receipts))

        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import check_profile
        evaluation = check_profile.evaluate_profile_load(
            copied, root=self.root, interface=reduced_interface,
            receipt_identity=None)
        self.assertFalse(evaluation.authorized)

    def test_fake_fence_closer_cannot_authorize_hidden_manifest_slots(self):
        copied = self._copied_profile("hidden-slots", self_owned=True)
        manifest = copied / "profile.md"
        text = manifest.read_text(encoding="utf-8")
        before, after = text.split("## Implemented Slots", 1)
        manifest.write_text(
            before + "```text\n```not-a-closing-fence\n"
            "## Implemented Slots" + after + "\n```\n",
            encoding="utf-8")

        completed, receipts = self._run_check(
            copied, "hidden-slots.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("profile-contract-slot-missing",
                      self._checks(receipts))
        self.assertFalse(any(
            receipt["check"] == "profile-check-summary"
            for receipt in receipts))

    def test_indented_commonmark_heading_ends_slot_authority(self):
        for spaces in (" ", "  ", "   "):
            with self.subTest(spaces=len(spaces)):
                profile_id = "indented-boundary-%d" % len(spaces)
                copied = self._copied_profile(profile_id, self_owned=True)
                manifest = copied / "profile.md"
                self._replace_exact(
                    manifest,
                    "- `Priority Rubric`: `priority-rubric.md`",
                    "%s# Outside Implemented Slots\n"
                    "- `Priority Rubric`: `priority-rubric.md`" % spaces,
                    count=1)

                completed, receipts = self._run_check(
                    copied, "%s.jsonl" % profile_id)

                self.assertEqual(1, completed.returncode, completed.stdout)
                self.assertIn("slot-unbound", self._checks(receipts))

    def test_literal_trailing_hash_does_not_name_slots_section(self):
        copied = self._copied_profile("hash-section", self_owned=True)
        manifest = copied / "profile.md"
        self._replace_exact(
            manifest, "## Implemented Slots", "## Implemented Slots#",
            count=1)

        completed, receipts = self._run_check(
            copied, "hash-section.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("slot-unbound", self._checks(receipts))

    def test_html_comment_line_cannot_supply_profile_identity(self):
        copied = self._copied_profile("comment-identity", self_owned=True)
        manifest = copied / "profile.md"
        self._replace_exact(
            manifest,
            "- `profile_id`: `comment-identity`",
            "<!-- hidden -->- `profile_id`: `comment-identity`",
            count=1)

        completed, receipts = self._run_check(
            copied, "comment-identity.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("profile-id-missing", self._checks(receipts))

    def test_indented_code_cannot_supply_profile_identity(self):
        copied = self._copied_profile("indented-identity", self_owned=True)
        manifest = copied / "profile.md"
        self._replace_exact(
            manifest,
            "- `profile_id`: `indented-identity`",
            "    - `profile_id`: `indented-identity`",
            count=1)

        completed, receipts = self._run_check(
            copied, "indented-identity.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("profile-id-missing", self._checks(receipts))

    def test_tab_expanded_indented_code_cannot_supply_profile_identity(self):
        copied = self._copied_profile("tab-identity", self_owned=True)
        manifest = copied / "profile.md"
        self._replace_exact(
            manifest,
            "- `profile_id`: `tab-identity`",
            "   \t- `profile_id`: `tab-identity`",
            count=1)

        completed, receipts = self._run_check(
            copied, "tab-identity.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("profile-id-missing", self._checks(receipts))

    def test_every_interface_slot_is_file_bound(self):
        copied = self._copied_profile("inline-slot", self_owned=True)
        manifest = copied / "profile.md"
        self._replace_exact(
            manifest,
            "- `Priority Rubric`: `priority-rubric.md`",
            "- `Priority Rubric`: `inline`",
            count=1)
        with manifest.open("a", encoding="utf-8") as handle:
            handle.write("\n## Priority Rubric\n\nInline substitute.\n")

        completed, receipts = self._run_check(copied, "inline-slot.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("slot-binding-inline", self._checks(receipts))
        self.assertFalse(any(
            receipt["check"] == "profile-check-summary"
            for receipt in receipts))

    def test_first_hop_slot_path_rejects_dot_segment_alias(self):
        copied = self._copied_profile("dot-slot", self_owned=True)
        manifest = copied / "profile.md"
        self._replace_exact(
            manifest,
            "- `Priority Rubric`: `priority-rubric.md`",
            "- `Priority Rubric`: `./priority-rubric.md`",
            count=1)

        completed, receipts = self._run_check(copied, "dot-slot.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("slot-binding-invalid", self._checks(receipts))

    def test_slot_binding_rejects_multiple_or_mixed_path_candidates(self):
        cases = (
            ("markdown-two",
             "[first](priority-rubric.md) or [second](source-policy.md)"),
            ("wiki-two",
             "[[priority-rubric.md]] or [[source-policy.md]]"),
            ("mixed-links",
             "[[priority-rubric.md]] [second](source-policy.md)"),
            ("inline-path", "inline or `priority-rubric.md`"),
        )
        for suffix, binding in cases:
            with self.subTest(binding=binding):
                profile_id = "ambiguous-%s" % suffix
                copied = self._copied_profile(profile_id, self_owned=True)
                manifest = copied / "profile.md"
                self._replace_exact(
                    manifest,
                    "- `Priority Rubric`: `priority-rubric.md`",
                    "- `Priority Rubric`: %s" % binding,
                    count=1)

                completed, receipts = self._run_check(
                    copied, "%s.jsonl" % profile_id)

                self.assertEqual(1, completed.returncode, completed.stdout)
                self.assertIn("slot-binding-invalid",
                              self._checks(receipts))
                self.assertFalse(any(
                    receipt["check"] == "profile-check-summary"
                    for receipt in receipts))

    def test_non_registry_slot_rejects_filesystem_case_alias(self):
        copied = self._copied_profile("case-slot", self_owned=True)
        alias = copied / "Structure-Registry.yaml"
        if not alias.exists():
            self.skipTest("filesystem is case-sensitive")
        manifest = copied / "profile.md"
        self._replace_exact(
            manifest,
            "- `Structure Registry`: `structure-registry.yaml`",
            "- `Structure Registry`: `Structure-Registry.yaml`",
            count=1)

        completed, receipts = self._run_check(copied, "case-slot.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("slot-binding-invalid", self._checks(receipts))

    def test_every_first_hop_slot_requires_strict_utf8(self):
        copied = self._copied_profile("binary-slot", self_owned=True)
        (copied / "priority-rubric.bin").write_bytes(b"\xff\xfe\x00")
        manifest = copied / "profile.md"
        self._replace_exact(
            manifest,
            "- `Priority Rubric`: `priority-rubric.md`",
            "- `Priority Rubric`: [binary](priority-rubric.bin)",
            count=1)

        completed, receipts = self._run_check(copied, "binary-slot.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("profile-contract-slot-unreadable",
                      self._checks(receipts))

    def test_slot_suffix_cannot_hide_unfilled_sentinel(self):
        copied = self._copied_profile("sentinel-slot", self_owned=True)
        (copied / "priority-rubric.bin").write_text(
            "TODO(profile)\n", encoding="utf-8")
        manifest = copied / "profile.md"
        self._replace_exact(
            manifest,
            "- `Priority Rubric`: `priority-rubric.md`",
            "- `Priority Rubric`: [priority](priority-rubric.bin)",
            count=1)

        completed, receipts = self._run_check(
            copied, "sentinel-slot.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("unfilled-placeholder", self._checks(receipts))
        self.assertFalse(any(
            receipt["check"] == "profile-check-summary"
            for receipt in receipts))

    def test_hidden_profile_text_cannot_hide_unfilled_sentinel(self):
        for profile_id, relative in (
                ("hidden-directory-sentinel", ".hidden/priority.md"),
                ("hidden-file-sentinel", ".priority.md")):
            with self.subTest(relative=relative):
                copied = self._copied_profile(profile_id, self_owned=True)
                hidden = copied / relative
                hidden.parent.mkdir(parents=True, exist_ok=True)
                hidden.write_text("TODO(profile)\n", encoding="utf-8")
                manifest = copied / "profile.md"
                self._replace_exact(
                    manifest,
                    "- `Priority Rubric`: `priority-rubric.md`",
                    "- `Priority Rubric`: `%s`" % relative,
                    count=1)

                completed, receipts = self._run_check(
                    copied, "%s.jsonl" % profile_id)

                self.assertEqual(1, completed.returncode, completed.stdout)
                self.assertIn("unfilled-placeholder", self._checks(receipts))

    def test_unbound_unknown_suffix_is_not_profile_authority(self):
        copied = self._copied_profile("unbound-sentinel", self_owned=True)
        (copied / "unbound.bin").write_bytes(
            b"opaque prefix\nTODO(profile)\nopaque suffix\n")

        completed, receipts = self._run_check(
            copied, "unbound-sentinel.jsonl")

        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertNotIn("unfilled-placeholder", self._checks(receipts))
        self.assertTrue(any(
            receipt["check"] == "profile-check-summary"
            for receipt in receipts))

    def test_unfilled_template_cannot_authorize_profile_load(self):
        template = self.root / "profiles/_template"
        shutil.copytree(REPOSITORY / "profiles/_template", template)

        completed, receipts = self._run_check(template, "template.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        checks = self._checks(receipts)
        self.assertIn("unfilled-placeholder", checks)
        self.assertIn("profile-id-invalid", checks)
        self.assertFalse(any(
            receipt["check"] == "profile-check-summary"
            for receipt in receipts))

    def test_missing_self_owned_scan_config_is_rejected_at_the_cli(self):
        copied = self._copied_profile("missing-config", self_owned=True)
        scans = copied / "registries/registered-scans.md"
        self._replace_exact(
            scans,
            "profiles/missing-config/scan-configs/"
            "residual-scan.yaml",
            "profiles/missing-config/scan-configs/absent.yaml",
            count=1)

        completed, receipts = self._run_check(copied, "missing.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("scan-config-path-invalid", self._checks(receipts))

    def test_symlinked_scan_config_cannot_escape_to_the_source_profile(self):
        copied = self._copied_profile("symlink-config", self_owned=True)
        config = copied / "scan-configs/residual-scan.yaml"
        config.unlink()
        config.symlink_to(
            self.original_profile / "scan-configs/residual-scan.yaml")

        completed, receipts = self._run_check(copied, "symlink.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("profile-snapshot-invalid", self._checks(receipts))

    def test_missing_predicate_heading_is_rejected_at_the_cli(self):
        copied = self._copied_profile("missing-heading", self_owned=True)
        owner = copied / "scope-and-architecture.md"
        self._replace_exact(
            owner, "## Foundation Depth Requirements",
            "## Renamed Foundation Requirements", count=1)

        completed, receipts = self._run_check(copied, "heading.jsonl")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("predicate-owner-heading-count",
                      self._checks(receipts))

    def test_unbound_profile_file_is_not_a_typed_text_dependency(self):
        copied = self._copied_profile("invalid-utf8", self_owned=True)
        (copied / "role-registry.md").write_bytes(b"# Roles\n\xff\n")

        completed, receipts = self._run_check(copied, "invalid-utf8.jsonl")

        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertNotIn("profile-text-unreadable", self._checks(receipts))

    def test_snapshot_identity_tracks_only_manifest_and_typed_closure(self):
        copied = self._copied_profile("closure-identity", self_owned=True)
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import check_profile

        first = check_profile.evaluate_profile_load(
            copied, root=self.root, receipt_identity=None)
        self.assertTrue(first.authorized, first.findings)

        unrelated = copied / "editor-cache.bin"
        unrelated.write_bytes(b"host state\x00TODO(profile)\xff")
        second = check_profile.evaluate_profile_load(
            copied, root=self.root, receipt_identity=None)
        self.assertTrue(second.authorized, second.findings)
        self.assertEqual(first.profile_snapshot_sha256,
                         second.profile_snapshot_sha256)
        self.assertNotIn(
            unrelated.relative_to(self.root).as_posix(),
            second.profile_snapshot.files)
        self.assertEqual(
            first.profile_snapshot_sha256,
            first.rebind_profile_snapshot(self.root).sha256)

        bound_slot = copied / "priority-rubric.md"
        bound_slot.write_text(
            bound_slot.read_text(encoding="utf-8") +
            "\n<!-- typed closure revision -->\n",
            encoding="utf-8")
        self.assertNotEqual(
            first.profile_snapshot_sha256,
            first.rebind_profile_snapshot(self.root).sha256)
        third = check_profile.evaluate_profile_load(
            copied, root=self.root, receipt_identity=None)
        self.assertTrue(third.authorized, third.findings)
        self.assertNotEqual(first.profile_snapshot_sha256,
                            third.profile_snapshot_sha256)

        transitive = copied / "scan-configs/residual-scan.yaml"
        transitive_repo_path = transitive.relative_to(self.root).as_posix()
        self.assertIn(transitive_repo_path, third.profile_snapshot.files)
        transitive.write_text(
            transitive.read_text(encoding="utf-8") +
            "\n# typed transitive dependency revision\n",
            encoding="utf-8")
        fourth = check_profile.evaluate_profile_load(
            copied, root=self.root, receipt_identity=None)
        self.assertTrue(fourth.authorized, fourth.findings)
        self.assertNotEqual(third.profile_snapshot_sha256,
                            fourth.profile_snapshot_sha256)

    def test_repeated_failure_is_deterministic_and_profile_tree_is_read_only(self):
        copied = self._copied_profile("stable-diagnostics")
        before = self._profile_tree_state(copied)

        first, first_receipts = self._run_check(copied, "stable-1.jsonl")
        middle = self._profile_tree_state(copied)
        second, second_receipts = self._run_check(copied, "stable-2.jsonl")
        after = self._profile_tree_state(copied)

        self.assertEqual(1, first.returncode, first.stdout)
        self.assertEqual(1, second.returncode, second.stdout)
        self.assertEqual(before, middle)
        self.assertEqual(before, after)
        self.assertEqual(
            self._without_dynamic_receipt_fields(first_receipts),
            self._without_dynamic_receipt_fields(second_receipts))

    def test_profile_contract_parses_one_immutable_tree_snapshot(self):
        copied = self._copied_profile("snapshot-aba", self_owned=True)
        scans = copied / "registries/registered-scans.md"
        original = scans.read_bytes()
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import check_profile
        import kblib
        import profile_contract
        before_tree = kblib.repository_tree_snapshot(
            self.root, "profiles/snapshot-aba")
        before_contract = profile_contract.load_profile_contract(
            self.root, copied / "profile.md", profile_snapshot=before_tree)
        self.assertTrue(before_contract.authorized,
                        before_contract.diagnostics)
        before = before_tree.project(
            before_contract.profile_snapshot_paths).sha256
        real_load = profile_contract.load_profile_contract

        def transient_swap(*args, **kwargs):
            text = original.decode("utf-8").replace(
                "base-profile-scratch-residuals", "transient-scan")
            scans.write_text(text, encoding="utf-8")
            try:
                return real_load(*args, **kwargs)
            finally:
                scans.write_bytes(original)

        with mock.patch.object(
                profile_contract, "load_profile_contract",
                side_effect=transient_swap):
            evaluation = check_profile.evaluate_profile_load(
                copied, root=self.root, receipt_identity=None)

        self.assertTrue(evaluation.authorized, evaluation.findings)
        self.assertEqual(
            "base-profile-scratch-residuals",
            evaluation.contract.required_scan.scan_id)
        self.assertEqual(before, evaluation.profile_snapshot_sha256)
        self.assertEqual(
            before,
            evaluation.rebind_profile_snapshot(self.root).sha256)
    def test_receipt_output_cannot_mutate_the_profile_snapshot(self):
        copied = self._copied_profile("receipt-boundary", self_owned=True)
        receipt_path = copied / "profile-load.jsonl"

        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(copied),
             "--root", str(self.root), "--receipts", str(receipt_path)],
            text=True, capture_output=True, check=False)

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("receipt output cannot be written inside",
                      completed.stdout)
        self.assertFalse(receipt_path.exists())


class FindingClassificationTests(unittest.TestCase):
    """The ``--json`` category map must stay a CLOSED dict over every code.

    The emittable set is collected by introspection of the three emitting
    sources -- ``check_profile.py``'s own ``add(...)`` literals, the kblib
    identity/shape validators it consumes, and ``profile_contract``'s
    diagnostics (literal plus the composed ``<prefix>-<shape>`` /
    ``<kind>-<failure>`` families) -- so adding a check anywhere without
    classifying it fails here rather than shipping an unclassified finding.
    """

    TOOLS = REPOSITORY / "Tools"

    @staticmethod
    def _literal_add_codes(tree):
        codes = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (func.attr if isinstance(func, ast.Attribute)
                    else func.id if isinstance(func, ast.Name) else None)
            if name != "add" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                codes.add(first.value)
        return codes

    def _check_profile_codes(self):
        tree = ast.parse(
            (self.TOOLS / "check_profile.py").read_text(encoding="utf-8"))
        return self._literal_add_codes(tree)

    def _kblib_passthrough_codes(self):
        """Codes check_profile forwards from kblib validators.

        ``profile_identity``, ``validate_structure_registry_shape``, and
        ``validate_metadata_contract_shape`` return ``(check, ...)`` tuples
        whose check literals all carry one of three closed name families;
        collecting the families from the source keeps this maintained-free.
        """
        source = (self.TOOLS / "kblib.py").read_text(encoding="utf-8")
        return set(re.findall(
            r'"((?:profile-id|structure-registry|metadata-contract)'
            r'-[a-z][a-z-]*)"', source))

    def _profile_contract_codes(self):
        """Every diagnostic check ``profile_contract`` can emit.

        Literal ``add("...")`` codes, plus the two composed families: the
        table-shape helpers (``section``/``table``/``cells``) format
        ``"%s-<shape>"`` with the section prefix their call sites pass, and
        ``profile_dependency`` formats ``"%s-<failure>"`` with the literal
        dependency kind.  Templates and prefixes/kinds are both read from
        the AST so a new prefix, kind, or template extends the set here
        automatically.
        """
        tree = ast.parse(
            (self.TOOLS / "profile_contract.py").read_text(encoding="utf-8"))
        codes = self._literal_add_codes(tree)
        # ``check = ("...-invalid" if ... else "...-unresolved")`` binds the
        # code before the add() call; collect the constants of any such
        # ``check`` assignment too.
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "check"
                    for target in node.targets):
                value = node.value
                branches = ((value.body, value.orelse)
                            if isinstance(value, ast.IfExp) else (value,))
                for branch in branches:
                    if isinstance(branch, ast.Constant) and \
                            isinstance(branch.value, str):
                        codes.add(branch.value)
        table_templates, dependency_templates = set(), set()
        prefixes, kinds = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                target = None
                if node.name in ("section", "table", "cells"):
                    target = table_templates
                elif node.name == "profile_dependency":
                    target = dependency_templates
                if target is not None:
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Constant) and \
                                isinstance(sub.value, str) and \
                                sub.value.startswith("%s-"):
                            target.add(sub.value[len("%s-"):])
            if isinstance(node, ast.Call) and \
                    isinstance(node.func, ast.Attribute) and node.args:
                if node.func.attr in ("section", "table", "cells"):
                    last = node.args[-1]
                    if isinstance(last, ast.Constant) and \
                            isinstance(last.value, str):
                        prefixes.add(last.value)
                if node.func.attr == "profile_dependency":
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and \
                            isinstance(first.value, str):
                        kinds.add(first.value)
        # A parse regression must not silently shrink the composed families.
        self.assertTrue(table_templates and dependency_templates)
        self.assertTrue(prefixes and kinds)
        codes.update("%s-%s" % (prefix, template)
                     for prefix in prefixes for template in table_templates)
        codes.update("%s-%s" % (kind, template)
                     for kind in kinds for template in dependency_templates)
        return codes

    def _emittable_codes(self):
        sys.path.insert(0, str(self.TOOLS))
        import check_profile
        codes = (self._check_profile_codes() |
                 self._kblib_passthrough_codes() |
                 self._profile_contract_codes())
        # profile-contract-sentinel is re-emitted as unfilled-placeholder;
        # the pass summary is a pass receipt, never a finding.
        codes.discard("profile-contract-sentinel")
        codes.discard(check_profile.GATE_CHECK)
        return codes

    def test_category_map_covers_exactly_the_emittable_codes(self):
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import check_profile

        emittable = self._emittable_codes()
        classified = set(check_profile.FINDING_CATEGORIES)

        self.assertEqual(
            sorted(emittable - classified), [],
            "emittable check codes without a category; classify them in "
            "check_profile.FINDING_CATEGORIES")
        self.assertEqual(
            sorted(classified - emittable), [],
            "classified codes the tool can no longer emit; remove them "
            "from check_profile.FINDING_CATEGORIES")

    def test_every_category_value_is_one_of_the_two_tokens(self):
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import check_profile

        self.assertEqual(
            {check_profile.MECHANICAL, check_profile.SEMANTIC_UNRESOLVED},
            set(check_profile.FINDING_CATEGORIES.values()))

    def test_pinned_semantic_and_mechanical_anchors(self):
        """The load-bearing calls: sentinels are open answers, paths are not."""
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import check_profile

        semantic = check_profile.SEMANTIC_UNRESOLVED
        mechanical = check_profile.MECHANICAL
        categories = check_profile.FINDING_CATEGORIES
        self.assertEqual(semantic, categories["unfilled-placeholder"])
        self.assertEqual(semantic, categories["override-choice-empty"])
        self.assertEqual(semantic, categories["slot-not-in-interface"])
        self.assertEqual(mechanical, categories["slot-binding-unresolved"])
        self.assertEqual(mechanical,
                         categories["profile-id-directory-mismatch"])
        self.assertEqual(
            mechanical, categories["predicate-owner-path-outside-profile"])
        # Unknown codes stay conservative: never auto-"fixed" by an agent.
        self.assertEqual(semantic,
                         check_profile.finding_category("not-a-real-check"))


class JsonDiagnosticsTests(ProfileCliFixture):
    """``--json`` structured diagnostics over the same CLI fixtures."""

    def _run_json(self, profile):
        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(profile),
             "--root", str(self.root), "--json"],
            text=True, capture_output=True, check=False)
        return completed, json.loads(completed.stdout)

    def test_json_is_one_object_with_categorized_findings(self):
        copied = self._copied_profile("json-broken-notes")

        completed, report = self._run_json(copied)

        self.assertEqual(1, completed.returncode)
        self.assertEqual("check_profile", report["tool"])
        self.assertEqual("fail", report["result"])
        self.assertEqual("profiles/json-broken-notes",
                         report["profile_dir"])
        self.assertTrue(report["findings"])
        for finding in report["findings"]:
            self.assertEqual(
                {"check", "target", "details", "category"},
                set(finding))
            self.assertIn(finding["category"],
                          ("mechanical", "semantic-unresolved"))
        checks = {finding["check"]: finding["category"]
                  for finding in report["findings"]}
        self.assertEqual(
            "mechanical", checks["scan-config-path-outside-profile"])

    def test_json_pass_has_no_findings_and_matching_exit(self):
        copied = self._copied_profile("json-pass-notes", self_owned=True)

        completed, report = self._run_json(copied)

        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertEqual("pass", report["result"])
        self.assertEqual([], report["findings"])

    def test_json_output_is_deterministic(self):
        copied = self._copied_profile("json-stable-notes")

        first, _ = self._run_json(copied)
        second, _ = self._run_json(copied)

        self.assertEqual(first.stdout, second.stdout)

    def test_sentinel_findings_are_semantic_unresolved(self):
        copied = self._copied_profile("json-sentinel-notes", self_owned=True)
        (copied / "priority-rubric.md").write_text(
            "TODO(profile)\n", encoding="utf-8")

        completed, report = self._run_json(copied)

        self.assertEqual(1, completed.returncode)
        sentinel_findings = [finding for finding in report["findings"]
                             if finding["check"] == "unfilled-placeholder"]
        self.assertTrue(sentinel_findings)
        for finding in sentinel_findings:
            self.assertEqual("semantic-unresolved", finding["category"])

    def test_human_output_is_unchanged_without_json(self):
        copied = self._copied_profile("json-human-notes")

        completed, _receipts = self._run_check(copied, "json-human.jsonl")

        self.assertEqual(1, completed.returncode)
        self.assertIn("[FAIL ", completed.stdout)
        self.assertNotIn('"findings"', completed.stdout)


if __name__ == "__main__":
    unittest.main()
