import io
import copy
import json
import shlex
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import check_batch_close
import check_queue
import compose_vocab
import kblib
import profile_admission
from profile_fixture import install_loadable_profile


class CheckBatchCloseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        for name in ("deltas", "receipts", "reports"):
            (self.root / ".cambium" / name).mkdir(exist_ok=True)
        self.install_profile_and_tools()
        self.prepare_applied_batch()

    def tearDown(self):
        self.temporary.cleanup()

    def run_tool(self, name, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS / name), str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def install_profile_and_tools(self):
        install_loadable_profile(self.root)
        manifest = self.root / "profiles/test-profile/profile.md"
        manifest_text = manifest.read_text(encoding="utf-8")
        manifest.write_text(
            manifest_text.replace(
                "- `Audit Dimension Registry`: `slots.md`",
                "- `Audit Dimension Registry`: "
                "`registries/audit-dimensions.md`",
            ).replace(
                "- `Registered Scan Registry`: `slots.md`",
                "- `Registered Scan Registry`: "
                "`registries/registered-scans.md`",
            ),
            encoding="utf-8",
        )
        audit_registry = manifest.parent / "registries/audit-dimensions.md"
        audit_registry.parent.mkdir(parents=True)
        audit_registry.write_text(
            "# Audit Dimension Registry\n\n"
            "## Extension Dimensions\n\n"
            "- Registration: None\n\n"
            "| Dimension ID | Target list(s): `review`, `receipt`, or "
            "`review + receipt` | Meaning |\n"
            "|---|---|---|\n\n"
            "## Judgment Items\n\n"
            "| Stable Judgment Item ID | Base or registered receipt "
            "Dimension ID | Exact kernel audit-layer name | Bounded audit "
            "object one run proves | Evidence role: `emits`, `consumes`, "
            "or `triggers` | Predicate owner (repo-relative path; optional "
            "`#heading`) |\n"
            "|---|---|---|---|---|---|\n"
            "| `fixture-item` | `coverage_and_integration` | `Batch Review` "
            "| The fixture scan candidates have accepted dispositions. | "
            "`emits` | `profiles/test-profile/registries/"
            "audit-dimensions.md#Fixture Predicate` |\n\n"
            "## Fixture Predicate\n\n"
            "The fixture verifier reports residual candidates.\n",
            encoding="utf-8",
        )
        registry = manifest.parent / "registries/registered-scans.md"
        registry.write_text(
            "# Registered Scan Registry\n\n## Scan Registrations\n\n"
            "| Stable Scan ID | Activation role | Whole-corpus scope/root | "
            "Deterministic verifier command/path | Candidate predicate/boundary | "
            "Judgment Item ID reference |\n"
            "|---|---|---|---|---|---|\n"
            "| `fixture-residuals` | `K12/09 item 6 — residual-content scan` | "
            "Whole repository | `python3 Tools/fixture_residual.py . "
            "--scan-id fixture-residuals` | candidate-only | `fixture-item` |\n",
            encoding="utf-8",
        )
        tools = self.root / "Tools"
        tools.mkdir(exist_ok=True)
        (tools / "schemas").mkdir(exist_ok=True)
        shutil.copy2(TOOLS / "kblib.py", tools / "kblib.py")
        (tools / "fixture_residual.py").write_text(
            "#!/usr/bin/env python3\n"
            "import argparse, hashlib, json, os, sys\n"
            "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
            "import kblib\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('root')\n"
            "p.add_argument('--scan-id', required=True)\n"
            "p.add_argument('--receipts')\n"
            "p.add_argument('--positive-controls-only', action='store_true')\n"
            "a=p.parse_args()\n"
            "def classify(text):\n"
            "    return text.startswith('residual:')\n"
            "controls=('residual:alpha','residual:beta')\n"
            "if not all(classify(item) for item in controls):\n"
            "    raise SystemExit(1)\n"
            "control_bytes=json.dumps(controls,separators=(',',':')).encode()\n"
            "control_fp='sha256:' + hashlib.sha256(control_bytes).hexdigest()\n"
            "config_fp='sha256:' + hashlib.sha256(b'fixture-config-v1').hexdigest()\n"
            "r=kblib.make_receipt('fixture_residual','1.0.0',"
            "'residual-content-summary',a.root,'pass',"
            "('fixture controls passed' if a.positive_controls_only else "
            "'fixture production scan passed'),1)\n"
            "r['scan_id']=a.scan_id\n"
            "r['config_fingerprint']=config_fp\n"
            "r['positive_control_result']='passed'\n"
            "r['positive_control_mode']='production-classifier'\n"
            "r['positive_control_count']=len(controls)\n"
            "r['positive_control_fingerprint']=control_fp\n"
            "kblib.write_receipts(a.receipts,[r])\n",
            encoding="utf-8",
        )
        vocab_base = (
            "kernel/K08 Metadata and Status/vocabulary-base.yaml")
        (self.root / vocab_base).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TOOLS.parent / vocab_base, self.root / vocab_base)
        profile_manifest = self.root / "profiles/test-profile/profile.md"
        profile_manifest.write_text(
            profile_manifest.read_text(encoding="utf-8").replace(
                "- `Vocabulary Extensions`: `slots.md`",
                "- `Vocabulary Extensions`: `vocabulary-extensions.yaml`"),
            encoding="utf-8")
        (profile_manifest.parent / "vocabulary-extensions.yaml").write_text(
            "schema_version: 1\n"
            "frontmatter_extensions:\n"
            "  fields: []\n"
            "fields:\n"
            "volatility_defaults:\n"
            "  fixture: stable\n",
            encoding="utf-8")
        admission, admission_errors = profile_admission.admit_profile(
            self.root, profile_manifest.parent)
        self.assertEqual([], admission_errors)
        rendered, _vocab, compile_errors = compose_vocab.compiled_artifact(
            self.root, admission)
        self.assertEqual([], compile_errors)
        (tools / "vocab.yaml").write_text(rendered, encoding="utf-8")

    def queue(self):
        return kblib.load_yaml_file(self.root / check_queue.QUEUE_PATH)

    def transition(self, transition, *evidence):
        queue = self.queue()
        completed = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", transition,
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--apply", *evidence,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)

    def prepare_applied_batch(self):
        ready_path = ".cambium/receipts/ready.jsonl"
        ready = self.run_tool(
            "check_queue.py", "--require-ready", "B1",
            "--receipts", ready_path)
        self.assertEqual(0, ready.returncode, ready.stdout)
        ready_id = json.loads((self.root / ready_path).read_text(
            encoding="utf-8"))["receipt_id"]
        self.transition("open", "--gate-receipt", ready_id)

        page = kblib.make_receipt(
            "fixture_page", "0.9.0", "page_review", "Topics/A.md", "pass",
            "fixture historical page evidence", 1)
        batch = kblib.make_receipt(
            check_queue.MANUAL_ATTESTATION_TOOL,
            check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
            check_queue.BATCH_REVIEW_CHECK, "B1", "pass",
            "fixture current in-batch review authorization", 1)
        batch.update({
            "gate_id": check_queue.BATCH_REVIEW_GATE_ID,
            "task_id": "fixture-task",
            "batch_id": "B1",
            "delta_page_receipt_ids": [page["receipt_id"]],
        })
        kblib.write_receipts(
            self.root / ".cambium/receipts/batch.jsonl", [page, batch])
        delta_relative = ".cambium/deltas/B1.yaml"
        delta = {
            "batch": "B1",
            "generated_at": "2026-08-05T00:00:00Z",
            "pages": [{
                "path": "Topics/A.md",
                "authoring_status": "reviewed",
                "gate_receipts": [page["receipt_id"]],
            }],
            "open_gaps_added": [],
            "open_gaps_closed": [],
            "next_batch_updates": [],
            "watermark_advance": None,
        }
        (self.root / delta_relative).write_text(
            kblib.canonical_yaml(delta), encoding="utf-8")
        self.transition(
            "merge-ready", "--delta-path", delta_relative,
            "--batch-receipt", batch["receipt_id"])

        applied_path = ".cambium/receipts/applied.jsonl"
        applied = subprocess.run(
            [
                sys.executable, str(TOOLS / "apply_delta.py"),
                check_queue.COVERAGE_PATH, delta_relative,
                "--root", str(self.root),
                "--expected-coverage-sha256",
                kblib.sha256_file(self.root / check_queue.COVERAGE_PATH),
                "--expected-queue-sha256",
                kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
                "--actor-role", "integrator", "--receipts", applied_path,
                "--apply",
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, applied.returncode, applied.stdout)
        self.delta_apply_receipt = json.loads(
            (self.root / applied_path).read_text(encoding="utf-8"))[
                "receipt_id"]

    def batch_close(self, *extra):
        return self.run_tool(
            "check_batch_close.py", "--batch", "B1",
            "--integrator", "fixture-integrator",
            "--reviewer", "fixture-reviewer",
            "--review-attestation",
            "I reviewed the exact listed candidates and merged snapshot.",
            *extra,
        )

    def install_inactive_corpus_plan(self):
        manifest = self.root / "profiles/test-profile/profile.md"
        (manifest.parent / "corpus-planning.yaml").write_text(
            "schema_version: 1\n"
            "applicability:\n"
            "  state: not-applicable\n"
            "  reason: bounded fixture batch has no corpus-wide planning decision\n"
            "artifact_bindings:\n"
            "  global_map: null\n"
            "  capability_matrix: null\n"
            "  gap_register: null\n"
            "capability_scale: []\n"
            "pass_authority:\n"
            "  role_id: null\n"
            "  decision_scope_id: null\n",
            encoding="utf-8")

    def install_configured_corpus_plan(self):
        manifest = self.root / "profiles/test-profile/profile.md"
        text = manifest.read_text(encoding="utf-8")
        manifest.write_text(
            text.replace(
                "- `Profile Scope`: `slots.md`",
                "- `Profile Scope`: `scope-and-architecture.md`",
            ).replace(
                "- `Role Registry`: `slots.md`",
                "- `Role Registry`: `roles.md`",
            ),
            encoding="utf-8",
        )
        (manifest.parent / "scope-and-architecture.md").write_text(
            "# Scope And Architecture\n\n## Logical Architecture\n\n"
            "| Stable Layer ID | Repository-relative directories | "
            "Single layer responsibility |\n|---|---|---|\n"
            "| `L1` | `Topics` | Canonical fixture topics. |\n",
            encoding="utf-8")
        (manifest.parent / "roles.md").write_text(
            "# Role Registry\n\n## Process Roles\n\n"
            "| Kernel role | Bound actor or system ID/name |\n|---|---|\n"
            "| `stopper` | Fixture authority |\n",
            encoding="utf-8")
        (manifest.parent / "corpus-planning.yaml").write_text(
            "schema_version: 1\n"
            "applicability:\n  state: configured\n  reason: null\n"
            "artifact_bindings:\n"
            "  global_map: planning/global-map.yaml\n"
            "  capability_matrix: planning/capability-matrix.yaml\n"
            "  gap_register: planning/gap-register.yaml\n"
            "capability_scale:\n"
            "  - rank: 0\n    value: Missing\n"
            "    predicate: No canonical owner exists.\n"
            "    target_eligible: false\n"
            "  - rank: 1\n    value: Core\n"
            "    predicate: Core explanation has accepted evidence.\n"
            "    target_eligible: true\n"
            "pass_authority:\n  role_id: stopper\n"
            "  decision_scope_id: corpus-plan-semantic-acceptance\n",
            encoding="utf-8")
        planning = self.root / "planning"
        planning.mkdir()
        (planning / "global-map.yaml").write_text(
            "schema_version: 1\nentries:\n"
            "  - entry_id: E-A\n    layer_id: L1\n"
            "    canonical_markdown_path: Topics/A.md\n"
            "    single_responsibility: Own topic A.\n"
            "  - entry_id: E-B\n    layer_id: L1\n"
            "    canonical_markdown_path: Topics/B.md\n"
            "    single_responsibility: Own topic B.\n"
            "typed_dependencies:\n"
            "  - edge_id: D-1\n    upstream_entry_id: E-A\n"
            "    downstream_entry_id: E-B\n"
            "    relation_type: prerequisite-for\n",
            encoding="utf-8")
        (planning / "capability-matrix.yaml").write_text(
            "schema_version: 1\ncapabilities:\n"
            "  - capability_id: C-1\n"
            "    capability: Explain the fixture topic path.\n"
            "    priority: P0\n    map_entry_ids: [E-A, E-B]\n"
            "    canonical_markdown_paths: [Topics/A.md, Topics/B.md]\n"
            "    current_level: Core\n    target_level: Core\n"
            "    evidence_paths: [Topics/A.md]\n    gap_ids: []\n",
            encoding="utf-8")
        (planning / "gap-register.yaml").write_text(
            "schema_version: 1\ngaps: []\n", encoding="utf-8")

    def test_manifest_hit_requires_current_corpus_plan_child(self):
        self.install_inactive_corpus_plan()
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        item = dict(next(row for row in runtime["queue"]["required_queue"]
                         if row["id"] == "B1"))
        item["manifest"] = ["profiles/test-profile/corpus-planning.yaml"]
        snapshot = kblib.repository_snapshot_sha256(self.root)
        outcome = check_batch_close._corpus_plan_close_check(
            self.root, runtime, item, snapshot)
        self.assertTrue(outcome["required"])
        self.assertEqual(["manifest"], outcome["triggers"])
        self.assertEqual([], outcome["errors"])
        self.assertEqual("pass", outcome["receipt"]["result"])
        self.assertEqual("not-applicable",
                         outcome["receipt"]["corpus_plan_applicability"])

    def test_r13_cannot_close_with_not_applicable_corpus_plan(self):
        self.install_inactive_corpus_plan()
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        runtime["progress"]["contract"]["selected_route_ids"] = ["R13"]
        item = next(row for row in runtime["queue"]["required_queue"]
                    if row["id"] == "B1")
        outcome = check_batch_close._corpus_plan_close_check(
            self.root, runtime, item,
            kblib.repository_snapshot_sha256(self.root))
        self.assertTrue(outcome["required"])
        self.assertEqual(["R13"], outcome["triggers"])
        self.assertTrue(any("applicability.state=configured" in error
                            for error in outcome["errors"]), outcome)
        self.assertIsNone(outcome["receipt"])

    def test_configured_corpus_plan_child_is_consumed_by_batch_close(self):
        self.install_configured_corpus_plan()
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, completed.returncode, completed.stdout)
        close_gate = self.output_value(completed.stdout, "close_gate_receipt")
        consistency = self.output_value(
            completed.stdout, "queue_consistency_receipt")
        rows = [
            json.loads(line)
            for line in (self.root / ".cambium/receipts/batch-close.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        close = next(row for row in rows
                     if row.get("receipt_id") == close_gate)
        self.assertTrue(close["corpus_plan_required"])
        self.assertEqual(["manifest"], close["corpus_plan_triggers"])
        child = next(row for row in rows
                     if row.get("receipt_id") == close["corpus_plan_receipt"])
        self.assertEqual("check_corpus_plan", child["tool"])
        self.assertEqual("1.7.0", child["tool_version"])
        self.assertEqual("configured", child["corpus_plan_applicability"])
        runtime = check_queue.validate_runtime(self.root)
        item = runtime["items_by_id"]["B1"]
        errors = check_queue.close_gate_receipt_errors(
            runtime["current_receipt_catalog"], close_gate,
            item_id="B1", task_id=runtime["queue"]["task_id"],
            queue_revision=runtime["queue"]["queue_revision"],
            queue_state_revision=runtime["queue"]["state_revision"],
            required_queue_sha256=runtime["queue_sha256"],
            coverage_ledger_sha256=runtime["coverage_sha256"],
            progress_ledger_sha256=runtime["progress_sha256"],
            delta_sha256=item["delta_sha256"],
            queue_consistency_receipt=consistency,
            delta_apply_receipt=self.delta_apply_receipt,
            work_spec_path=item["work_spec_path"],
            work_spec_sha256=item["work_spec_sha256"],
            selected_profile_manifest=runtime["queue"][
                "selected_profile_manifest"],
            corpus_plan_required=True,
            corpus_plan_triggers=["manifest"],
            current_repository_snapshot_sha256=
                kblib.repository_snapshot_sha256(self.root),
        )
        self.assertEqual([], errors)

        historical_catalog = {
            receipt_id: (path, copy.deepcopy(receipt))
            for receipt_id, (path, receipt)
            in runtime["current_receipt_catalog"].items()
        }
        for _path, receipt in historical_catalog.values():
            if receipt.get("tool") == check_batch_close.TOOL:
                receipt["tool_version"] = "1.6.0"
        historical_kwargs = {
            "item_id": "B1",
            "task_id": runtime["queue"]["task_id"],
            "queue_revision": runtime["queue"]["queue_revision"],
            "queue_state_revision": runtime["queue"]["state_revision"],
            "required_queue_sha256": runtime["queue_sha256"],
            "coverage_ledger_sha256": runtime["coverage_sha256"],
            "progress_ledger_sha256": runtime["progress_sha256"],
            "delta_sha256": item["delta_sha256"],
            "queue_consistency_receipt": consistency,
            "delta_apply_receipt": self.delta_apply_receipt,
            "work_spec_path": item["work_spec_path"],
            "work_spec_sha256": item["work_spec_sha256"],
            "selected_profile_manifest": runtime["queue"][
                "selected_profile_manifest"],
            "corpus_plan_required": True,
            "corpus_plan_triggers": ["manifest"],
            "historical": True,
        }
        mismatched = check_queue.close_gate_receipt_errors(
            historical_catalog, close_gate, **historical_kwargs)
        self.assertTrue(any(
            "tool_version='1.7.0', expected '1.6.0'" in error
            for error in mismatched), mismatched)

        historical_catalog[close["corpus_plan_receipt"]][1][
            "tool_version"] = "1.6.0"
        self.assertEqual([], check_queue.close_gate_receipt_errors(
            historical_catalog, close_gate, **historical_kwargs))

    def test_one_authorized_view_drives_corpus_scan_and_quota_overrides(self):
        self.install_configured_corpus_plan()
        view, errors = check_queue.profile_load_authorized_view(
            self.root, "profiles/test-profile/profile.md")
        self.assertEqual([], errors)
        runtime = check_queue.validate_runtime(
            self.root, authorized_profile_view=view)
        self.assertEqual([], runtime["errors"])
        item = runtime["items_by_id"]["B1"]

        with mock.patch.object(
                check_batch_close.check_profile, "evaluate_profile_load",
                side_effect=AssertionError(
                    "shared batch admission must suppress producer reruns")):
            corpus = check_batch_close._corpus_plan_close_check(
                self.root, runtime, item,
                kblib.repository_snapshot_sha256(self.root),
                authorized_profile_view=view)
            evaluation = check_batch_close._profile_evaluation(
                self.root, runtime, authorized_profile_view=view)

        self.assertEqual([], corpus["errors"])
        self.assertIs(view["_evaluation"], evaluation)
        self.assertEqual((15.0, 35.0),
                         check_batch_close._priority_quotas(evaluation))

    def test_batch_rejects_vocab_compiled_before_profile_change(self):
        """The closed list cannot reuse Profile A's vocabulary under B."""
        extension = self.root / \
            "profiles/test-profile/vocabulary-extensions.yaml"
        extension.write_text(
            extension.read_text(encoding="utf-8").replace(
                "  fixture: stable", "  fixture: slow"),
            encoding="utf-8")

        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("vocab-artifact-stale", completed.stdout)
        self.assertIn("does not match the selected Profile", completed.stdout)

    @staticmethod
    def output_value(output, name):
        prefix = name + "="
        return next(line[len(prefix):] for line in output.splitlines()
                    if line.startswith(prefix))

    def test_production_cli_generates_bundle_consumed_by_close(self):
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, completed.returncode, completed.stdout)
        consistency = self.output_value(
            completed.stdout, "queue_consistency_receipt")
        close_gate = self.output_value(completed.stdout, "close_gate_receipt")
        delta_apply = self.output_value(completed.stdout,
                                       "delta_apply_receipt")
        self.assertEqual(self.delta_apply_receipt, delta_apply)
        close_records = [json.loads(line) for line in
                         (self.root / ".cambium/receipts/batch-close.jsonl")
                         .read_text(encoding="utf-8").splitlines()]
        own_records = [record for record in close_records
                       if record.get("tool") == check_batch_close.TOOL]
        self.assertTrue(own_records)
        self.assertEqual(
            {check_batch_close.TOOL_VERSION},
            {record.get("tool_version") for record in own_records})
        self.assertEqual(
            {check_batch_close.GATE_ID},
            {record.get("gate_id") for record in own_records})
        consistency_record = next(
            record for record in close_records
            if record.get("receipt_id") == consistency)
        self.assertEqual("check_queue", consistency_record["tool"])
        self.assertEqual(check_queue.TOOL_VERSION,
                         consistency_record["tool_version"])
        self.assertEqual("consistency",
                         consistency_record["queue_check_mode"])
        self.assertEqual(
            kblib.repository_snapshot_sha256(self.root),
            consistency_record["repository_snapshot_sha256"])
        close_record = next(
            record for record in close_records
            if record.get("receipt_id") == close_gate)
        self.assertIn("work_spec_path", close_record)
        self.assertIn("work_spec_sha256", close_record)
        self.assertIsNone(close_record["work_spec_path"])
        self.assertIsNone(close_record["work_spec_sha256"])
        self.transition(
            "closed", "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply)
        self.assertEqual("closed", self.queue()["required_queue"][0]["state"])
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def test_closed_bundle_snapshot_survives_a_checker_version_bump(self):
        """K12/10 producer-era identity: a sealed close bundle's Queue
        consistency snapshot is not re-judged against the current
        check_queue constant after an upgrade."""
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, completed.returncode, completed.stdout)
        consistency = self.output_value(
            completed.stdout, "queue_consistency_receipt")
        self.transition(
            "closed", "--gate-receipt", consistency,
            "--close-gate-receipt",
            self.output_value(completed.stdout, "close_gate_receipt"),
            "--delta-apply-receipt",
            self.output_value(completed.stdout, "delta_apply_receipt"))
        receipts = self.root / ".cambium/receipts/batch-close.jsonl"
        text = receipts.read_text(encoding="utf-8")
        needle = '"tool_version": "%s"' % check_queue.TOOL_VERSION
        self.assertIn(needle, text)
        receipts.write_text(
            text.replace(needle, '"tool_version": "0.9.0"'),
            encoding="utf-8")
        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"])

    def test_profile_example_vocabulary_is_outside_the_vocab_member(self):
        """A shipped example instance's own vocabulary values must not fail
        the adopter's close: profiles/ is control plane, so the vocab member
        excludes it like kernel/Cards (the defect only appeared on a real
        adopter's first close)."""
        foreign = self.root / "profiles/examples/foreign/corpus/Case.md"
        foreign.parent.mkdir(parents=True, exist_ok=True)
        foreign.write_text(
            "---\ntype: service-case\npriority: P9\n---\n# Foreign Case\n",
            encoding="utf-8")
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertNotIn("service-case", completed.stdout)

    def test_complex_work_spec_stability_guard_detects_byte_change(self):
        relative = ".cambium/work_specs/B1.yaml"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = (
            "---\nschema_version: 1\nbatch_id: B1\nmanifest:\n"
            "  - Topics/A.md\n---\n\n# Work\n"
        )
        path.write_text(text, encoding="utf-8")
        item = {
            "work_spec_path": relative,
            "work_spec_sha256": kblib.sha256_file(path),
        }
        check_batch_close._assert_work_spec_unchanged(self.root, item)
        path.write_text(text + "changed\n", encoding="utf-8")
        with self.assertRaisesRegex(
                check_batch_close.ReceiptPublicationUncertain,
                "Batch Work Spec changed"):
            check_batch_close._assert_work_spec_unchanged(self.root, item)

    def test_simple_batch_close_receipt_must_bind_explicit_null_work_spec(self):
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, completed.returncode, completed.stdout)
        close_gate = self.output_value(completed.stdout, "close_gate_receipt")
        consistency = self.output_value(
            completed.stdout, "queue_consistency_receipt")
        runtime = check_queue.validate_runtime(self.root)
        item = runtime["items_by_id"]["B1"]

        for mode in ("missing", "forged"):
            with self.subTest(mode=mode):
                catalog = {
                    receipt_id: (path, dict(receipt))
                    for receipt_id, (path, receipt) in
                    runtime["receipt_catalog"].items()
                }
                receipt = catalog[close_gate][1]
                if mode == "missing":
                    receipt.pop("work_spec_path", None)
                    receipt.pop("work_spec_sha256", None)
                else:
                    receipt["work_spec_path"] = \
                        ".cambium/work_specs/forged.yaml"
                    receipt["work_spec_sha256"] = "sha256:" + "a" * 64
                errors = check_queue.close_gate_receipt_errors(
                    catalog, close_gate,
                    item_id="B1", task_id=runtime["queue"]["task_id"],
                    queue_revision=runtime["queue"]["queue_revision"],
                    queue_state_revision=runtime["queue"]["state_revision"],
                    required_queue_sha256=runtime["queue_sha256"],
                    coverage_ledger_sha256=runtime["coverage_sha256"],
                    progress_ledger_sha256=runtime["progress_sha256"],
                    delta_sha256=item["delta_sha256"],
                    queue_consistency_receipt=consistency,
                    delta_apply_receipt=self.delta_apply_receipt,
                    work_spec_path=None, work_spec_sha256=None,
                )
                self.assertTrue(any("work_spec_" in error
                                    for error in errors), errors)

    def test_close_evidence_from_prior_work_spec_binding_is_not_reusable(self):
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, completed.returncode, completed.stdout)
        close_gate = self.output_value(completed.stdout, "close_gate_receipt")
        consistency = self.output_value(
            completed.stdout, "queue_consistency_receipt")
        runtime = check_queue.validate_runtime(self.root)
        item = runtime["items_by_id"]["B1"]
        errors = check_queue.close_gate_receipt_errors(
            runtime["receipt_catalog"], close_gate,
            item_id="B1", task_id=runtime["queue"]["task_id"],
            queue_revision=runtime["queue"]["queue_revision"],
            queue_state_revision=runtime["queue"]["state_revision"],
            required_queue_sha256=runtime["queue_sha256"],
            coverage_ledger_sha256=runtime["coverage_sha256"],
            progress_ledger_sha256=runtime["progress_sha256"],
            delta_sha256=item["delta_sha256"],
            queue_consistency_receipt=consistency,
            delta_apply_receipt=self.delta_apply_receipt,
            work_spec_path=".cambium/work_specs/B1.yaml",
            work_spec_sha256="sha256:" + "a" * 64,
        )
        self.assertTrue(any("work_spec_path" in error or
                            "work_spec_sha256" in error
                            for error in errors), errors)

    def test_resume_recovers_published_bundle_when_producer_stdout_is_lost(self):
        published = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, published.returncode, published.stdout)
        consistency = self.output_value(
            published.stdout, "queue_consistency_receipt")
        close_gate = self.output_value(published.stdout, "close_gate_receipt")

        # Deliberately recover from durable state only.  None of the values
        # parsed from the producer stdout are supplied to the resume command.
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        expected_action = "close-applied-batch:B1:%s:%s:%s" % (
            consistency, close_gate, self.delta_apply_receipt)
        self.assertIn(
            "batch_close_recovery.status=ready-to-close batch=B1",
            resumed.stdout)
        self.assertIn(
            "batch_close_recovery.queue_consistency_receipt=%s" %
            consistency, resumed.stdout)
        self.assertIn(
            "batch_close_recovery.close_gate_receipt=%s" % close_gate,
            resumed.stdout)
        self.assertIn(
            "batch_close_recovery.delta_apply_receipt=%s" %
            self.delta_apply_receipt, resumed.stdout)
        self.assertIn("next_action=%s" % expected_action, resumed.stdout)

        command = next(
            line.split("=", 1)[1]
            for line in resumed.stdout.splitlines()
            if line.startswith(
                "  batch_close_recovery.update_queue_command="))
        closed = subprocess.run(
            shlex.split(command), cwd=str(TOOLS.parent), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, closed.returncode, closed.stdout)
        self.assertEqual("closed", self.queue()["required_queue"][0]["state"])
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def test_resume_requires_close_gate_when_only_apply_receipt_exists(self):
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("batch_close_recovery.status=gate-required batch=B1",
                      resumed.stdout)
        self.assertIn("batch_close_recovery.update_queue_command=none",
                      resumed.stdout)
        self.assertIn("next_action=run-batch-close-gate:B1",
                      resumed.stdout)

    def test_resume_rejects_close_bundle_after_repository_snapshot_changes(self):
        published = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, published.returncode, published.stdout)
        close_gate = self.output_value(published.stdout, "close_gate_receipt")
        topic = self.root / "Topics/A.md"
        topic.write_text(
            topic.read_text(encoding="utf-8") + "\nchanged after gate\n",
            encoding="utf-8")

        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("batch_close_recovery.status=gate-required batch=B1",
                      resumed.stdout)
        self.assertIn("batch_close_recovery.compatible=none stale=%s" %
                      close_gate, resumed.stdout)
        self.assertIn("next_action=run-batch-close-gate:B1",
                      resumed.stdout)

    def test_resume_selects_latest_of_multiple_current_close_bundles(self):
        first = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, first.returncode, first.stdout)
        first_close = self.output_value(first.stdout, "close_gate_receipt")
        time.sleep(1.1)
        second = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, second.returncode, second.stdout)
        second_consistency = self.output_value(
            second.stdout, "queue_consistency_receipt")
        second_close = self.output_value(second.stdout, "close_gate_receipt")

        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn(
            "batch_close_recovery.compatible=%s,%s stale=none" %
            (first_close, second_close), resumed.stdout)
        self.assertIn(
            "batch_close_recovery.close_gate_receipt=%s" % second_close,
            resumed.stdout)
        self.assertIn(
            "next_action=close-applied-batch:B1:%s:%s:%s" % (
                second_consistency, second_close, self.delta_apply_receipt),
            resumed.stdout)

    def set_override_rows(self, rows):
        manifest = self.root / "profiles/test-profile/profile.md"
        text = manifest.read_text(encoding="utf-8")
        head, _, _ = text.partition("\n## Execution Default Overrides\n")
        manifest.write_text(
            head + "\n## Execution Default Overrides\n\n"
            "| Override item ID from the registry | Non-default profile value |\n"
            "|---|---|\n" + rows, encoding="utf-8")
        return {"queue": {
            "selected_profile_manifest": "profiles/test-profile/profile.md",
        }}

    def set_quota_section(self, body):
        """Rewrite the synthetic rubric's Priority Quota section."""
        rubric = self.root / "profiles/test-profile/slots.md"
        text = rubric.read_text(encoding="utf-8")
        head, _, _ = text.partition("\n## Priority Quota\n")
        rubric.write_text(head + "\n## Priority Quota\n" + body,
                          encoding="utf-8")
        return {"queue": {
            "selected_profile_manifest": "profiles/test-profile/profile.md",
        }}

    def resolved_quotas(self, runtime):
        return check_batch_close._priority_quotas(
            check_batch_close._profile_evaluation(self.root, runtime))

    def test_priority_quotas_read_the_rubric_slot(self):
        """K00/07: the standing quota truth lives in the Priority Rubric.

        The retired priority_quota.* override rows are rejected upstream by
        profile-load as unknown registry items, so the one long-lived source
        is the slot this consumer reads through the same kblib reader the
        Gate validated with.
        """
        runtime = self.set_quota_section("\n- Registration: None\n")
        self.assertEqual((15.0, 35.0), self.resolved_quotas(runtime))
        runtime = self.set_quota_section(
            "\n- Registration: Configured\n\n"
            "| Class | Maximum corpus share | Rationale |\n"
            "|---|---|---|\n"
            "| `P0` | `20%` | foundational density |\n"
            "| `P1` | `40` | applied breadth |\n")
        self.assertEqual((20.0, 40.0), self.resolved_quotas(runtime))

    def test_a_retired_override_row_fails_profile_load(self):
        """The old carrier is rejected at the Gate, not silently ignored."""
        runtime = self.set_override_rows(
            "| `priority_quota.P0` | `20%` |\n")
        with self.assertRaises(ValueError) as caught:
            check_batch_close._profile_evaluation(self.root, runtime)
        self.assertIn("not in the closed overridable registry",
                      str(caught.exception))

    def test_the_two_quota_shares_may_not_consume_the_corpus_together(self):
        """K00/07: the two shares together stay strictly below 100.

        Each value passes its own per-value form (60 < 100), so only the
        joint bound can catch the pair; it now lives in the shared slot
        reader, so profile-load and this consumer refuse identically.
        """
        runtime = self.set_quota_section(
            "\n- Registration: Configured\n\n"
            "| Class | Maximum corpus share | Rationale |\n"
            "|---|---|---|\n"
            "| `P0` | `60` | dense |\n"
            "| `P1` | `60` | broad |\n")
        with self.assertRaises(ValueError) as caught:
            self.resolved_quotas(runtime)
        self.assertIn("strictly below 100", str(caught.exception))

    def test_a_malformed_quota_registration_fails_closed(self):
        for body, expected in (
                ("\n- Registration: Configured\n\n"
                 "| Class | Maximum corpus share | Rationale |\n"
                 "|---|---|---|\n"
                 "| `P0` | `many` | words |\n"
                 "| `P1` | `40` | applied |\n",
                 "not a number"),
                ("\n- Registration: Configured\n\n"
                 "| Class | Maximum corpus share | Rationale |\n"
                 "|---|---|---|\n"
                 "| `P0` | `20` | dense |\n",
                 "missing P1"),
                ("\n- Registration: Sometimes\n", "invalid"),
                ("\n- Registration: None\n\n"
                 "| Class | Maximum corpus share | Rationale |\n"
                 "|---|---|---|\n"
                 "| `P0` | `20` | left behind |\n",
                 "active quota rows behind"),
        ):
            with self.subTest(expected=expected):
                runtime = self.set_quota_section(body)
                with self.assertRaises(ValueError) as caught:
                    self.resolved_quotas(runtime)
                self.assertIn(expected, str(caught.exception))

    def test_quota_and_scan_share_one_authorized_profile_revision(self):
        runtime = self.set_quota_section(
            "\n- Registration: Configured\n\n"
            "| Class | Maximum corpus share | Rationale |\n"
            "|---|---|---|\n"
            "| `P0` | `20%` | dense |\n"
            "| `P1` | `35` | applied |\n")
        evaluation = check_batch_close._profile_evaluation(self.root, runtime)
        rubric = self.root / "profiles/test-profile/slots.md"
        rubric.write_text(
            rubric.read_text(encoding="utf-8").replace(
                "| `P0` | `20%` | dense |",
                "| `P0` | `80%` | dense |"),
            encoding="utf-8")

        self.assertEqual(
            (20.0, 35.0), check_batch_close._priority_quotas(evaluation))
        command, expected = check_batch_close._profile_scan_command(
            self.root, evaluation)
        self.assertIn("--scan-id", command)
        self.assertEqual("fixture-residuals", expected["scan_id"])

    def test_override_reader_ignores_fenced_examples_and_other_sections(self):
        manifest_text = (
            "# Profile\n\n"
            "## Execution Default Overrides\n\n"
            "```text\n"
            "| `concurrency_cap` | `99` |\n"
            "```\n\n"
            "| Override item ID from the registry | Non-default profile value |\n"
            "|---|---|\n"
            "| `concurrency_cap` | `7` |\n"
            "| `maintenance.incoming_retarget_divisor` | `a \\| b` |\n\n"
            "## Implemented Slots\n\n"
            "| `priority_quota.P0` | `99` |\n"
        )
        self.assertEqual(
            {"concurrency_cap": "7",
             "maintenance.incoming_retarget_divisor": "a | b"},
            kblib.profile_execution_default_overrides(manifest_text))

    def test_candidates_require_exact_id_or_type_disposition(self):
        completed = self.batch_close()
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("lack an explicit ID/type disposition", completed.stdout)
        self.assertIn("type=check_vocab:frontmatter-missing", completed.stdout)
        records = []
        for path in (self.root / ".cambium/receipts").glob("*.jsonl"):
            records.extend(json.loads(line) for line in path.read_text(
                encoding="utf-8").splitlines() if line.strip())
        attempts = [record for record in records
                    if record.get("tool") == "check_batch_close"]
        self.assertEqual(1, len(attempts))
        self.assertEqual("fail", attempts[0]["result"])
        self.assertNotIn("closed_list_evidence", attempts[0])
        self.assertFalse((self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_plain_json_and_scalar_json_fences_are_not_graph_inputs(self):
        ordinary = self.root / "application-data.json"
        ordinary.write_text("42", encoding="utf-8")
        example = self.root / "JSON Example.md"
        example.write_text(
            "# JSON Example\n\n```json\n42\n```\n", encoding="utf-8")

        first, first_json = check_batch_close._markdown_graph_projection(
            self.root)
        first_check = check_batch_close._graph_and_basename_check(self.root)
        ordinary.write_text('"a different scalar"', encoding="utf-8")
        example.write_text(
            "# JSON Example\n\n```json\n\"changed\"\n```\n", encoding="utf-8")
        second, second_json = check_batch_close._markdown_graph_projection(
            self.root)
        second_check = check_batch_close._graph_and_basename_check(self.root)

        self.assertEqual(first, second)
        self.assertEqual(first_json, second_json)
        self.assertEqual(first_check["details"], second_check["details"])
        self.assertEqual([], first_check["errors"])
        self.assertEqual([], second_check["errors"])
        self.assertNotIn("application-data.json", first_json)

    def test_graph_projection_is_stable_and_duplicate_basename_is_candidate(self):
        for directory in ("z-last", "a-first"):
            path = self.root / directory / "Same.md"
            path.parent.mkdir()
            path.write_text("# Same\n", encoding="utf-8")
        source = self.root / "Graph Source.md"
        source.write_text(
            "# Graph Source\n\n[[z-last/Same]] [[Missing]] [[Same]]\n",
            encoding="utf-8")

        first, first_json = check_batch_close._markdown_graph_projection(
            self.root)
        second, second_json = check_batch_close._markdown_graph_projection(
            self.root)
        result = check_batch_close._graph_and_basename_check(self.root)

        self.assertEqual(first, second)
        self.assertEqual(first_json, second_json)
        self.assertEqual(
            sorted(node["path"] for node in first["nodes"]),
            [node["path"] for node in first["nodes"]])
        self.assertEqual(
            ["z-last/Same"],
            [edge["resolved_target"] for edge in first["resolved_edges"]
             if edge["source"] == "Graph Source"])
        self.assertEqual(
            ["ambiguous", "missing"],
            sorted(edge["status"] for edge in first["unresolved_edges"]
                   if edge["source"] == "Graph Source"))
        self.assertEqual([], result["errors"])
        duplicate = next(
            candidate for candidate in result["candidates"]
            if candidate["check"] == "duplicate-markdown-basename" and
            candidate["target"] == "Same.md")
        self.assertIn("a-first/Same.md", duplicate["details"])
        self.assertIn("z-last/Same.md", duplicate["details"])

    def test_same_reviewer_and_integrator_fail_before_receipts(self):
        completed = self.run_tool(
            "check_batch_close.py", "--batch", "B1",
            "--integrator", "same", "--reviewer", "same",
            "--review-attestation", "Independent review statement.")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("must use different declared labels", completed.stdout)
        self.assertFalse((self.root / ".cambium/receipts/batch-close.jsonl").exists())

    def test_custom_registered_verifier_without_config_remains_legal(self):
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])

        evaluation = check_batch_close._profile_evaluation(self.root, runtime)
        command, expected = check_batch_close._profile_scan_command(
            self.root, evaluation)

        self.assertEqual(sys.executable, command[0])
        self.assertEqual(
            str((self.root / "Tools/fixture_residual.py").resolve()),
            command[1])
        self.assertEqual(str(self.root.resolve()), command[2])
        self.assertNotIn("--config", command)
        self.assertEqual({"scan_id": "fixture-residuals"}, expected)

    def test_registered_foreign_config_is_rejected_before_verifier_launch(self):
        foreign = self.root / "profiles/foreign/scan-config.yaml"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("schema_version: 1\n", encoding="utf-8")
        registry = (
            self.root /
            "profiles/test-profile/registries/registered-scans.md"
        )
        source = registry.read_text(encoding="utf-8")
        registry.write_text(source.replace(
            "--scan-id fixture-residuals`",
            "--scan-id fixture-residuals "
            "--config profiles/foreign/scan-config.yaml`",
            1,
        ), encoding="utf-8")

        verifier = self.root / "Tools/fixture_residual.py"
        marker = self.root / "Tools/fixture-residual-launched"
        source = verifier.read_text(encoding="utf-8")
        verifier.write_text(source.replace(
            "import kblib\n",
            "import kblib\n"
            "open(os.path.join(os.path.dirname(__file__), "
            "'fixture-residual-launched'), 'w', encoding='utf-8').write("
            "'launched')\n",
            1,
        ), encoding="utf-8")

        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("profiles/foreign/scan-config.yaml", completed.stdout)
        self.assertFalse(marker.exists(), completed.stdout)

    def test_missing_non_registry_slot_blocks_scan_before_verifier_launch(self):
        # A valid Audit/Scan subgraph is not sufficient runtime authority.
        # Batch close must consume the complete profile-load result, including
        # the other eleven interface slots, before compiling item 6.
        (self.root / "profiles/test-profile/slots.md").unlink()

        verifier = self.root / "Tools/fixture_residual.py"
        marker = self.root / "Tools/fixture-residual-launched"
        source = verifier.read_text(encoding="utf-8")
        verifier.write_text(source.replace(
            "import kblib\n",
            "import kblib\n"
            "open(os.path.join(os.path.dirname(__file__), "
            "'fixture-residual-launched'), 'w', encoding='utf-8').write("
            "'launched')\n",
            1,
        ), encoding="utf-8")

        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("slot-binding-unresolved", completed.stdout)
        self.assertFalse(marker.exists(), completed.stdout)

    def test_registered_check_cannot_mutate_around_a_self_reported_pass(self):
        script = self.root / "Tools/fixture_residual.py"
        script.write_text(
            script.read_text(encoding="utf-8") +
            "open(os.path.join(a.root,'MUTATED.txt'),'w',encoding='utf-8')"
            ".write('changed during gate')\n",
            encoding="utf-8",
        )
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("repository content changed while the Closed List ran",
                      completed.stdout)
        records = [json.loads(line) for line in
                   (self.root / ".cambium/receipts/batch-close.jsonl")
                   .read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, len(records))
        self.assertEqual("fail", records[0]["result"])
        self.assertNotIn("closed_list_evidence", records[0])

    def test_registered_blind_pass_without_positive_control_evidence_fails(self):
        script = self.root / "Tools/fixture_residual.py"
        source = script.read_text(encoding="utf-8")
        for line in (
                "r['positive_control_result']='passed'\n",
                "r['positive_control_mode']='production-classifier'\n",
                "r['positive_control_count']=len(controls)\n",
                "r['positive_control_fingerprint']=control_fp\n"):
            source = source.replace(line, "")
        script.write_text(source, encoding="utf-8")
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn(
            "positive_control_result=passed", completed.stdout)
        records = [json.loads(line) for line in
                   (self.root / ".cambium/receipts/batch-close.jsonl")
                   .read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, len(records))
        self.assertEqual("fail", records[0]["result"])
        self.assertNotIn("closed_list_evidence", records[0])

    def test_registered_positive_control_invocation_failure_fails(self):
        script = self.root / "Tools/fixture_residual.py"
        source = script.read_text(encoding="utf-8").replace(
            "a=p.parse_args()\n",
            "a=p.parse_args()\n"
            "if a.positive_controls_only:\n"
            "    raise SystemExit(1)\n")
        script.write_text(source, encoding="utf-8")
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("positive-control invocation", completed.stdout)
        self.assertIn("checker exited 1", completed.stdout)

    def test_registered_control_and_production_binding_mismatch_fails(self):
        script = self.root / "Tools/fixture_residual.py"
        source = script.read_text(encoding="utf-8").replace(
            "r['config_fingerprint']=config_fp\n",
            "r['config_fingerprint']=(('sha256:' + 'f'*64) "
            "if a.positive_controls_only else config_fp)\n")
        script.write_text(source, encoding="utf-8")
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn(
            "positive-control and production summaries disagree on "
            "config_fingerprint", completed.stdout)

    def test_registered_verifier_cannot_self_report_a_foreign_scan_id(self):
        script = self.root / "Tools/fixture_residual.py"
        source = script.read_text(encoding="utf-8").replace(
            "r['scan_id']=a.scan_id\n",
            "r['scan_id']='foreign-scan'\n")
        script.write_text(source, encoding="utf-8")

        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn(
            "expected 'fixture-residuals' from the admitted Profile contract",
            completed.stdout)

    def test_candidate_production_receipts_do_not_replace_bound_summary(self):
        summary = {
            "tool": "fixture_residual",
            "tool_version": "1.0.0",
            "check": "residual-content-summary",
            "scan_id": "fixture-residuals",
            "config_fingerprint": "sha256:" + "b" * 64,
            "positive_control_result": "passed",
            "positive_control_mode": "production-classifier",
            "positive_control_count": 2,
            "positive_control_fingerprint": "sha256:" + "c" * 64,
            "result": "pass",
        }
        candidate = {
            "tool": "fixture_residual",
            "tool_version": "1.0.0",
            "check": "residual-content-candidate",
            "result": "candidate",
        }
        self.assertEqual(
            [], check_batch_close._positive_control_binding_errors(
                {"receipts": [dict(summary)]},
                {"receipts": [candidate, dict(summary)]}))

    def test_both_invocations_must_match_admitted_config_bytes(self):
        summary = {
            "tool": "fixture_residual",
            "tool_version": "1.0.0",
            "check": "residual-content-summary",
            "scan_id": "fixture-residuals",
            "config_fingerprint": "sha256:" + "d" * 64,
            "positive_control_result": "passed",
            "positive_control_mode": "production-classifier",
            "positive_control_count": 2,
            "positive_control_fingerprint": "sha256:" + "c" * 64,
            "result": "pass",
        }

        errors = check_batch_close._positive_control_binding_errors(
            {"receipts": [dict(summary)]},
            {"receipts": [dict(summary)]},
            expected_binding={
                "scan_id": "fixture-residuals",
                "config_fingerprint": "sha256:" + "e" * 64,
            })

        self.assertEqual(2, len(errors), errors)
        self.assertTrue(all(
            "config_fingerprint" in error and
            "admitted Profile contract" in error for error in errors))

    def _install_authoritative_state_mutating_verifier(self, exit_code):
        script = self.root / "Tools/fixture_residual.py"
        script.write_text(
            script.read_text(encoding="utf-8") +
            "with open(os.path.join(a.root,'.cambium/state/"
            "coverage_ledger.yaml'),'a',encoding='utf-8') as fh:\n"
            "    fh.write('\\n')\n" +
            ("raise SystemExit(%d)\n" % exit_code if exit_code else ""),
            encoding="utf-8",
        )

    def _assert_state_mutating_verifier_is_uncertain(self, exit_code):
        self._install_authoritative_state_mutating_verifier(exit_code)
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn(
            "authoritative state changed while the Closed List ran",
            completed.stdout)
        self.assertIn(
            "[RECOVERY] writer lock retained", completed.stdout)
        self.assertTrue(
            (self.root / ".cambium/tmp/state-writer.lock").is_dir())
        self.assertFalse(
            (self.root / ".cambium/receipts/batch-close.jsonl").exists())

    def test_failing_verifier_that_mutates_state_preserves_runtime_lock(self):
        self._assert_state_mutating_verifier_is_uncertain(1)

    def test_passing_verifier_that_mutates_state_preserves_runtime_lock(self):
        self._assert_state_mutating_verifier_is_uncertain(0)

    def test_uncertain_append_preserves_runtime_lock(self):
        target = self.root / ".cambium/receipts/uncertain.jsonl"
        receipt = kblib.make_receipt(
            "fixture", "1", "fixture", ".", "pass", "fixture", 1)
        with self.assertRaises(check_batch_close.ReceiptPublicationUncertain):
            with kblib.runtime_write_lock(self.root):
                with mock.patch.object(
                        kblib, "write_receipts_observed",
                        return_value=("uncertain", OSError("partial"), None)):
                    check_batch_close._append_receipts(target, [receipt])
        self.assertTrue((self.root / ".cambium/tmp/state-writer.lock").is_dir())

    def test_crashed_pass_bundle_recovery_detects_later_content_change(self):
        program = r'''
import os
import sys

sys.path.insert(0, sys.argv[1])
import check_batch_close

real_append = check_batch_close._append_receipts

def append_then_crash(path, receipts):
    real_append(path, receipts)
    if len(receipts) > 1:
        os._exit(23)

check_batch_close._append_receipts = append_then_crash
raise SystemExit(check_batch_close.main([
    sys.argv[2], "--batch", "B1",
    "--integrator", "fixture-integrator",
    "--reviewer", "fixture-reviewer",
    "--review-attestation",
    "I reviewed the exact listed candidates and merged snapshot.",
    "--accept-candidate-type", "check_vocab:frontmatter-missing",
]))
'''
        crashed = subprocess.run(
            [sys.executable, "-c", program, str(TOOLS), str(self.root)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(23, crashed.returncode, crashed.stdout)
        self.assertTrue(
            (self.root / ".cambium/tmp/state-writer.lock").is_dir())

        unchanged = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, unchanged.returncode, unchanged.stdout)
        self.assertIn("batch_close_recovery.status=writer-lock batch=none",
                      unchanged.stdout)
        self.assertIn("batch_close_recovery.update_queue_command=none",
                      unchanged.stdout)
        self.assertIn("next_action=reconcile-interrupted-write",
                      unchanged.stdout)
        self.assertIn('"matching_receipt": true', unchanged.stdout)
        self.assertIn(
            '"repository_snapshot": {"current_sha256": "sha256:',
            unchanged.stdout,
        )
        self.assertIn('"status": "matching"', unchanged.stdout)

        topic = self.root / "Topics/A.md"
        topic.write_text(
            topic.read_text(encoding="utf-8") +
            "\nchanged after interrupted close evidence\n",
            encoding="utf-8",
        )
        changed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, changed.returncode, changed.stdout)
        self.assertIn('"matching_receipt": false', changed.stdout)
        self.assertIn('"status": "semantic-mismatch"', changed.stdout)
        self.assertIn(
            '"mismatched_fields": '
            '["current_repository_snapshot_sha256"]',
            changed.stdout,
        )
        self.assertIn('"status": "changed"', changed.stdout)
        self.assertIn("next_action=reconcile-interrupted-write",
                      changed.stdout)


if __name__ == "__main__":
    unittest.main()
