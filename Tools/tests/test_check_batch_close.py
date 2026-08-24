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
import metadata_execution_contract
import profile_admission
from profile_fixture import install_loadable_profile


# ---------------------------------------------------------------------------
# Scenario templates.
#
# Every test in this file used to walk the same applied-batch lifecycle in
# setUp -- copy the fixture tree, install the Profile and its registered
# verifier, admit B1 through ready/open/merge-ready, apply the Delta -- and
# many then ran one production close just to read its receipts.  Each distinct
# lifecycle is now walked exactly once per process into a template tree below.
# Tests that only read the walked state share the template directly; tests
# that mutate any byte start from a private `shutil.copytree` copy of it.
# The tools take the repository root from argv, so a copied root behaves
# identically; a tree copy costs milliseconds where the walk it replaces
# costs seconds of durable-write ceremony on every test.
# ---------------------------------------------------------------------------


class CheckBatchCloseTests(unittest.TestCase):
    """The fixture language every scenario class below shares.

    This is the original test class's helper set, unchanged; only the test
    methods moved out, into the scenario classes.  It keeps its walking
    setUp/tearDown and its name because test_quota_exception_lifecycle and
    test_reviewed_era_lifecycle subclass it for these helpers (both override
    setUp with their own trees, and the quota module inherits this tearDown).
    It defines no test methods, so discovery collects nothing from it here
    or in the modules that import it.
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        self.build_repository_fixture()
        self.prepare_applied_batch()

    def tearDown(self):
        self.temporary.cleanup()

    def build_repository_fixture(self):
        """Lay down the fixture tree and Profile the old setUp built."""
        shutil.copytree(FIXTURE, self.root)
        for name in ("deltas", "receipts", "reports"):
            (self.root / ".cambium" / name).mkdir(exist_ok=True)
        self.install_profile_and_tools()

    def reset_applied_batch(self, prepare_profile):
        """Rebuild the fixture when a test changes Profile-owned inputs.

        Current apply_delta/1.6 content evidence binds the exact authorized
        Profile it ran under.  Tests for a later close-time Profile condition
        must therefore install that condition *before* applying the Delta;
        mutating Profile bytes after apply would correctly make the owner
        evidence stale and never reach the close behavior under test.
        """
        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        self.build_repository_fixture()
        prepare_profile()
        self.prepare_applied_batch()

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

    def close_validation_kwargs(self, runtime, consistency, *, historical=False):
        item = runtime["items_by_id"]["B1"]
        view = runtime["_profile_authorized_view"]
        contract = metadata_execution_contract.\
            load_metadata_execution_contract(self.root)
        values = {
            "item_id": "B1",
            "root": self.root,
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
            "manifest": item["manifest"],
            "selected_profile_manifest":
                runtime["queue"]["selected_profile_manifest"],
            "profile_snapshot_sha256": view["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                view["profile_contract_fingerprint"],
            "profile_load_inputs_sha256":
                view["profile_load_inputs_sha256"],
            "metadata_execution_contract_fingerprint":
                contract.contract_fingerprint,
            "authorized_profile_contract": view["_contract"],
            "authorized_metadata_contract": contract,
            "current_repository_snapshot_sha256":
                kblib.repository_snapshot_sha256(self.root),
            "historical": historical,
        }
        return values

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

    @staticmethod
    def output_value(output, name):
        prefix = name + "="
        return next(line[len(prefix):] for line in output.splitlines()
                    if line.startswith(prefix))

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
        completed = self.batch_close()
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


class _ScenarioWalker(CheckBatchCloseTests):
    """Assertion-capable driver that walks a template scenario once.

    It defines no test methods, so discovery collects nothing from it; it
    exists so the walk can run the same helpers, with the same assertions,
    that the tests ran when each walked its own tree.
    """

    def _walk(self):
        raise NotImplementedError("never scheduled as a test")

    @classmethod
    def at(cls, root):
        walker = cls("_walk")
        walker.root = root
        return walker


def _build_base(walker, inherited):
    walker.build_repository_fixture()


def _build_applied(walker, inherited):
    walker.prepare_applied_batch()
    return {"delta_apply_receipt": walker.delta_apply_receipt}


def _build_closed(walker, inherited):
    completed = walker.batch_close()
    walker.assertEqual(0, completed.returncode, completed.stdout)
    return {"close_code": completed.returncode,
            "close_stdout": completed.stdout}


# Current apply_delta/1.6 content evidence binds the exact authorized Profile
# it ran under, so a close-time Profile condition must be installed *before*
# the Delta applies; these two variants bake the Corpus Planning slot in at
# the only point in the walk where it can take effect.
def _build_applied_inactive(walker, inherited):
    walker.install_inactive_corpus_plan()
    walker.prepare_applied_batch()
    return {"delta_apply_receipt": walker.delta_apply_receipt}


def _build_applied_configured(walker, inherited):
    walker.install_configured_corpus_plan()
    walker.prepare_applied_batch()
    return {"delta_apply_receipt": walker.delta_apply_receipt}


_TEMPLATE_PARENTS = {
    "base": None,
    "applied": "base",
    "closed": "applied",
    "applied-inactive": "base",
    "applied-configured": "base",
}
_TEMPLATE_BUILDERS = {
    "base": _build_base,
    "applied": _build_applied,
    "closed": _build_closed,
    "applied-inactive": _build_applied_inactive,
    "applied-configured": _build_applied_configured,
}
# name -> (TemporaryDirectory holder, template root, artifacts).  The holder
# reference keeps each template alive for the whole process; TemporaryDirectory
# finalizers remove the trees at interpreter exit.
_TEMPLATES = {}


def _template(name):
    """Return (root, artifacts) for ``name``, walking it on first use."""
    if name not in _TEMPLATES:
        holder = tempfile.TemporaryDirectory()
        root = Path(holder.name) / "repo"
        artifacts = {}
        parent = _TEMPLATE_PARENTS[name]
        if parent is not None:
            parent_root, parent_artifacts = _template(parent)
            artifacts.update(parent_artifacts)
            shutil.copytree(parent_root, root)
        walker = _ScenarioWalker.at(root)
        artifacts.update(_TEMPLATE_BUILDERS[name](walker, artifacts) or {})
        _TEMPLATES[name] = (holder, root, artifacts)
    _holder, root, artifacts = _TEMPLATES[name]
    return root, artifacts


class _TemplateBackedCase(CheckBatchCloseTests):
    """A test class whose tree starts at a named scenario template."""

    TEMPLATE = None
    # Only a class whose every test is read-only may share the template tree
    # itself; everything else gets a private copy per test.
    SHARE_TEMPLATE = False

    def setUp(self):
        template_root, self.scenario = _template(self.TEMPLATE)
        if self.SHARE_TEMPLATE:
            self.temporary = None
            self.root = template_root
        else:
            self.temporary = tempfile.TemporaryDirectory()
            self.root = Path(self.temporary.name) / "repo"
            shutil.copytree(template_root, self.root)
        if "delta_apply_receipt" in self.scenario:
            self.delta_apply_receipt = self.scenario["delta_apply_receipt"]

    def tearDown(self):
        if self.temporary is not None:
            self.temporary.cleanup()


class CorpusPlanInactiveTests(_TemplateBackedCase):
    # Shared scenario: the applied batch walked once with the Corpus Planning
    # slot installed as not-applicable before the Delta applied.  Both tests
    # only run in-process checks over the walked tree -- the corpus-plan
    # close check builds its receipt in memory and writes nothing, and the
    # runtime edits stay inside per-test dicts -- so the class shares the
    # template tree itself.
    TEMPLATE = "applied-inactive"
    SHARE_TEMPLATE = True

    def test_manifest_hit_requires_current_corpus_plan_child(self):
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


class CorpusPlanConfiguredViewTests(_TemplateBackedCase):
    # Shared scenario: the applied batch walked once with a configured
    # Corpus Planning slot and its bound planning artifacts installed before
    # the Delta applied.  The one test here evaluates the authorized view
    # in-process and writes nothing, so it reads the template tree directly.
    TEMPLATE = "applied-configured"
    SHARE_TEMPLATE = True

    def test_one_authorized_view_drives_corpus_scan_and_quota_overrides(self):
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


class CorpusPlanConfiguredCloseTests(_TemplateBackedCase):
    # Private copies of the configured-plan template: the test runs the
    # production close itself, which appends receipts, so it may not touch
    # the tree the read-only class above shares.
    TEMPLATE = "applied-configured"

    def test_configured_corpus_plan_child_is_consumed_by_batch_close(self):
        completed = self.batch_close()
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
        current_kwargs = self.close_validation_kwargs(runtime, consistency)
        current_kwargs.update({
            "corpus_plan_required": True,
            "corpus_plan_triggers": ["manifest"],
        })
        errors = check_queue.close_gate_receipt_errors(
            runtime["current_receipt_catalog"], close_gate,
            **current_kwargs)
        self.assertEqual([], errors)

        historical_catalog = {
            receipt_id: (path, copy.deepcopy(receipt))
            for receipt_id, (path, receipt)
            in runtime["current_receipt_catalog"].items()
        }
        for _path, receipt in historical_catalog.values():
            if receipt.get("tool") == check_batch_close.TOOL:
                receipt["tool_version"] = "1.6.0"
                if receipt.get("check") == "batch_global_review_attestation":
                    # A 1.6.0-era attestation carried the full inline
                    # disposition list; simulating that era from a compact
                    # 1.9.0 body must restore the legacy shape from the
                    # externalized evidence the compact writer produced.
                    evidence_rows = []
                    evidence_path = receipt.get("candidate_evidence_path")
                    if evidence_path:
                        evidence_rows = [
                            json.loads(line)
                            for line in (self.root / evidence_path)
                            .read_text(encoding="utf-8").splitlines()
                            if line.strip()
                        ]
                    receipt["candidate_dispositions"] = evidence_rows
                    receipt["accepted_candidate_ids"] = [
                        row["candidate_id"] for row in evidence_rows]
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


class VocabCompileOrderTests(_TemplateBackedCase):
    # Private walk from the base template: the subject is the order of the
    # walk itself -- the vocab artifact compiled under Profile A, the Profile
    # changed, and only then the batch applied -- so the batch admission and
    # the close both run inside the test and nothing here can be shared.
    TEMPLATE = "base"

    def test_batch_rejects_vocab_compiled_before_profile_change(self):
        """The closed list cannot reuse Profile A's vocabulary under B."""
        extension = self.root / \
            "profiles/test-profile/vocabulary-extensions.yaml"
        extension.write_text(
            extension.read_text(encoding="utf-8").replace(
                "  fixture: stable", "  fixture: slow"),
            encoding="utf-8")
        self.prepare_applied_batch()

        completed = self.batch_close()

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("vocab-artifact-stale", completed.stdout)
        self.assertIn("does not match the selected Profile", completed.stdout)


class ClosedBundleReadTests(_TemplateBackedCase):
    # Shared scenario: the applied batch carried through one production
    # close, walked once into the "closed" template with the producer's
    # stdout kept as an artifact.  Every test here replays validation over
    # the recorded bundle with in-process validators and per-test copies of
    # the receipt catalog, and writes nothing, so the class shares the
    # template tree itself.
    TEMPLATE = "closed"
    SHARE_TEMPLATE = True

    def test_1_10_history_never_acquires_page_review_requirements(self):
        self.assertEqual(0, self.scenario["close_code"],
                         self.scenario["close_stdout"])
        close_gate = self.output_value(
            self.scenario["close_stdout"], "close_gate_receipt")
        consistency = self.output_value(
            self.scenario["close_stdout"], "queue_consistency_receipt")
        runtime = check_queue.validate_runtime(self.root)
        catalog = {
            receipt_id: (path, copy.deepcopy(receipt))
            for receipt_id, (path, receipt)
            in runtime["current_receipt_catalog"].items()
        }
        for _path, receipt in catalog.values():
            if receipt.get("tool") == check_batch_close.TOOL:
                receipt["tool_version"] = "1.10.0"
        aggregate = catalog[close_gate][1]
        aggregate.pop("page_review_receipts")
        aggregate.pop("page_review_receipt_count")
        aggregate.pop("page_review_receipt_set_sha256")
        aggregate.pop("metadata_execution_contract_fingerprint")
        kwargs = self.close_validation_kwargs(
            runtime, consistency, historical=True)
        self.assertEqual([], check_queue.close_gate_receipt_errors(
            catalog, close_gate, **kwargs))

    def test_current_page_review_subgraph_rejects_missing_extra_and_drift(self):
        self.assertEqual(0, self.scenario["close_code"],
                         self.scenario["close_stdout"])
        close_gate = self.output_value(
            self.scenario["close_stdout"], "close_gate_receipt")
        consistency = self.output_value(
            self.scenario["close_stdout"], "queue_consistency_receipt")
        runtime = check_queue.validate_runtime(self.root)
        base_catalog = runtime["current_receipt_catalog"]
        kwargs = self.close_validation_kwargs(runtime, consistency)
        with mock.patch.object(
                check_queue.metadata_execution_contract,
                "load_metadata_execution_contract",
                side_effect=AssertionError(
                    "validator must reuse the authorized contract")):
            self.assertEqual([], check_queue.close_gate_receipt_errors(
                base_catalog, close_gate, **kwargs))

        aggregate = base_catalog[close_gate][1]
        frozen_semantics = {
            base_catalog[receipt_id][1]["target"]:
                base_catalog[receipt_id][1]["semantic_content_sha256"]
            for receipt_id in aggregate["page_review_receipts"]
        }
        frozen_kwargs = dict(kwargs)
        frozen_kwargs["authorized_page_semantic_fingerprints"] = \
            frozen_semantics
        with mock.patch.object(
                check_queue.kblib, "repository_target_snapshot",
                side_effect=AssertionError(
                    "same-transaction validation must not re-read pages")), \
                mock.patch.object(
                    check_queue.project_page_state,
                    "semantic_content_fingerprint",
                    side_effect=AssertionError(
                        "same-transaction validation must reuse frozen page "
                        "semantics")):
            self.assertEqual([], check_queue.close_gate_receipt_errors(
                base_catalog, close_gate, **frozen_kwargs))

        for name, supplied, expected in (
                ("missing-target", {}, "targets do not equal the exact manifest"),
                ("extra-target", {
                    **frozen_semantics,
                    "Topics/B.md": "sha256:" + "a" * 64,
                }, "targets do not equal the exact manifest"),
                ("bad-sha", {
                    target: "not-a-sha256" for target in frozen_semantics
                }, "have invalid values")):
            with self.subTest(authorized_frozen_map=name):
                invalid_kwargs = dict(kwargs)
                invalid_kwargs["authorized_page_semantic_fingerprints"] = \
                    supplied
                errors = check_queue.close_gate_receipt_errors(
                    base_catalog, close_gate, **invalid_kwargs)
                self.assertTrue(
                    any(expected in error for error in errors), errors)

        def copied_catalog():
            return {
                receipt_id: (path, copy.deepcopy(receipt))
                for receipt_id, (path, receipt) in base_catalog.items()
            }

        cases = []

        missing = copied_catalog()
        missing_aggregate = missing[close_gate][1]
        missing_aggregate["page_review_receipts"] = []
        cases.append(("missing", missing, "do not equal exact manifest"))

        extra = copied_catalog()
        extra_aggregate = extra[close_gate][1]
        source_id = extra_aggregate["page_review_receipts"][0]
        extra_id = "audit-page-review-extra-current-era"
        extra_child = copy.deepcopy(extra[source_id][1])
        extra_child["receipt_id"] = extra_id
        extra_child["target"] = "Topics/B.md"
        extra[extra_id] = (extra[source_id][0], extra_child)
        extra_ids = sorted(extra_aggregate["page_review_receipts"] + [extra_id])
        extra_aggregate["page_review_receipts"] = extra_ids
        extra_aggregate["page_review_receipt_count"] = len(extra_ids)
        extra_aggregate["page_review_receipt_set_sha256"] = \
            check_batch_close._receipt_id_set_sha256(extra_ids)
        cases.append(("extra", extra, "do not equal exact manifest"))

        wrong_target = copied_catalog()
        target_aggregate = wrong_target[close_gate][1]
        target_child = wrong_target[
            target_aggregate["page_review_receipts"][0]][1]
        target_child["target"] = "Topics/B.md"
        cases.append(("wrong-target", wrong_target,
                      "do not equal exact manifest"))

        wrong_hash = copied_catalog()
        hash_aggregate = wrong_hash[close_gate][1]
        wrong_hash[hash_aggregate["page_review_receipts"][0]][1][
            "semantic_content_sha256"] = "sha256:" + "f" * 64
        cases.append(("wrong-hash", wrong_hash,
                      "does not match the authorized current page content"))

        wrong_date = copied_catalog()
        date_aggregate = wrong_date[close_gate][1]
        wrong_date[date_aggregate["page_review_receipts"][0]][1][
            "reviewed_on"] = "1999-01-01"
        cases.append(("wrong-date", wrong_date,
                      "must equal its own checked_at UTC date"))

        wrong_contract = copied_catalog()
        contract_aggregate = wrong_contract[close_gate][1]
        wrong_contract[contract_aggregate["page_review_receipts"][0]][1][
            "metadata_execution_contract_fingerprint"] = \
                "sha256:" + "e" * 64
        cases.append(("wrong-contract", wrong_contract,
                      "metadata_execution_contract_fingerprint"))

        wrong_distinction = copied_catalog()
        distinction_aggregate = wrong_distinction[close_gate][1]
        distinction_aggregate["page_review_receipts"] = [close_gate]
        distinction_aggregate["page_review_receipt_count"] = 1
        distinction_aggregate["page_review_receipt_set_sha256"] = \
            check_batch_close._receipt_id_set_sha256([close_gate])
        cases.append(("child-not-distinct", wrong_distinction,
                      "must use receipt IDs distinct"))

        for name, catalog, expected in cases:
            with self.subTest(name=name):
                errors = check_queue.close_gate_receipt_errors(
                    catalog, close_gate, **kwargs)
                self.assertTrue(any(expected in error for error in errors),
                                errors)

    def test_simple_batch_close_receipt_must_bind_explicit_null_work_spec(self):
        self.assertEqual(0, self.scenario["close_code"],
                         self.scenario["close_stdout"])
        close_gate = self.output_value(
            self.scenario["close_stdout"], "close_gate_receipt")
        consistency = self.output_value(
            self.scenario["close_stdout"], "queue_consistency_receipt")
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
        self.assertEqual(0, self.scenario["close_code"],
                         self.scenario["close_stdout"])
        close_gate = self.output_value(
            self.scenario["close_stdout"], "close_gate_receipt")
        consistency = self.output_value(
            self.scenario["close_stdout"], "queue_consistency_receipt")
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


class ClosedBundleConsumerTests(_TemplateBackedCase):
    # Private copies of the "closed" template: each test consumes the walked
    # close bundle -- transitioning B1 to closed, editing receipts or pages,
    # or publishing a second bundle -- so each starts from its own copy and
    # reads the producer stdout from the template artifacts.
    TEMPLATE = "closed"

    def test_production_cli_generates_bundle_consumed_by_close(self):
        self.assertEqual(0, self.scenario["close_code"],
                         self.scenario["close_stdout"])
        consistency = self.output_value(
            self.scenario["close_stdout"], "queue_consistency_receipt")
        close_gate = self.output_value(
            self.scenario["close_stdout"], "close_gate_receipt")
        delta_apply = self.output_value(self.scenario["close_stdout"],
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
        self.assertEqual(1, close_record["page_review_receipt_count"])
        self.assertEqual(
            sorted(close_record["page_review_receipts"]),
            close_record["page_review_receipts"])
        self.assertEqual(
            check_batch_close._receipt_id_set_sha256(
                close_record["page_review_receipts"]),
            close_record["page_review_receipt_set_sha256"])
        page_review = next(
            record for record in close_records
            if record.get("receipt_id") ==
            close_record["page_review_receipts"][0])
        self.assertEqual("page_review_acceptance", page_review["check"])
        self.assertEqual("Topics/A.md", page_review["target"])
        self.assertEqual(
            page_review["checked_at"][:10], page_review["reviewed_on"])
        self.assertRegex(
            page_review["semantic_content_sha256"],
            r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            close_record["metadata_execution_contract_fingerprint"],
            page_review["metadata_execution_contract_fingerprint"])
        for field in (
                "selected_profile_manifest", "profile_snapshot_sha256",
                "profile_contract_fingerprint",
                "profile_load_inputs_sha256"):
            self.assertEqual(close_record[field], page_review[field])
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
        self.assertEqual(0, self.scenario["close_code"],
                         self.scenario["close_stdout"])
        consistency = self.output_value(
            self.scenario["close_stdout"], "queue_consistency_receipt")
        self.transition(
            "closed", "--gate-receipt", consistency,
            "--close-gate-receipt",
            self.output_value(
                self.scenario["close_stdout"], "close_gate_receipt"),
            "--delta-apply-receipt",
            self.output_value(
                self.scenario["close_stdout"], "delta_apply_receipt"))
        receipts = self.root / ".cambium/receipts/batch-close.jsonl"
        text = receipts.read_text(encoding="utf-8")
        needle = '"tool_version": "%s"' % check_queue.TOOL_VERSION
        self.assertIn(needle, text)
        receipts.write_text(
            text.replace(needle, '"tool_version": "0.9.0"'),
            encoding="utf-8")
        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"])

    def test_resume_recovers_published_bundle_when_producer_stdout_is_lost(self):
        self.assertEqual(0, self.scenario["close_code"],
                         self.scenario["close_stdout"])
        consistency = self.output_value(
            self.scenario["close_stdout"], "queue_consistency_receipt")
        close_gate = self.output_value(
            self.scenario["close_stdout"], "close_gate_receipt")

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

    def test_resume_rejects_close_bundle_after_repository_snapshot_changes(self):
        self.assertEqual(0, self.scenario["close_code"],
                         self.scenario["close_stdout"])
        close_gate = self.output_value(
            self.scenario["close_stdout"], "close_gate_receipt")
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
        # The first bundle is the template's walked close; the sleep keeps
        # the second bundle's second-granularity timestamps strictly later,
        # exactly as it kept two in-test closes apart before.
        self.assertEqual(0, self.scenario["close_code"],
                         self.scenario["close_stdout"])
        first_close = self.output_value(
            self.scenario["close_stdout"], "close_gate_receipt")
        time.sleep(1.1)
        second = self.batch_close()
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


class AppliedBatchReadTests(_TemplateBackedCase):
    # Shared scenario: the plain applied batch, walked once.  The one test
    # here resolves the registered scan command from the authorized Profile
    # view entirely in-process and writes nothing, so it reads the template
    # tree directly.
    TEMPLATE = "applied"
    SHARE_TEMPLATE = True

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


class QuotaRubricSlotTests(_TemplateBackedCase):
    # Private copies of the applied template: every test rewrites the
    # Profile manifest or the rubric slot before reading the quota policy,
    # so each starts from its own copy.
    TEMPLATE = "applied"

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


class CandidateGraphTests(_TemplateBackedCase):
    # Private copies of the applied template: every test plants extra pages
    # or files in the corpus before projecting the graph or running its own
    # close over the changed content.
    TEMPLATE = "applied"

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
        completed = self.batch_close()
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertNotIn("service-case", completed.stdout)

    def test_candidates_require_exact_id_or_type_disposition(self):
        duplicate = self.root / "Other/A.md"
        duplicate.parent.mkdir()
        duplicate.write_text("# A duplicate basename\n", encoding="utf-8")
        completed = self.batch_close()
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("fresh candidate(s) lack an explicit ID/type disposition",
                      completed.stdout)
        self.assertIn(
            "type=check_batch_close:duplicate-markdown-basename",
            completed.stdout)
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

    def test_durable_selector_is_expanded_into_current_exact_evidence(self):
        duplicate = self.root / "Other/A.md"
        duplicate.parent.mkdir()
        duplicate.write_text("# A duplicate basename\n", encoding="utf-8")
        completed = self.batch_close(
            "--accept-while-unchanged-type",
            "check_batch_close:duplicate-markdown-basename")
        self.assertEqual(0, completed.returncode, completed.stdout)
        attestation_id = self.output_value(
            completed.stdout, "reviewer_attestation_receipt")
        records = []
        for path in (self.root / ".cambium/receipts").glob("*.jsonl"):
            records.extend(json.loads(line) for line in path.read_text(
                encoding="utf-8").splitlines() if line.strip())
        attestation = next(row for row in records
                           if row.get("receipt_id") == attestation_id)
        self.assertEqual("exact-carry-v1",
                         attestation["candidate_protocol"])
        self.assertEqual(0, attestation["carried_candidate_count"])
        self.assertEqual(1, attestation["fresh_candidate_count"])
        evidence = [json.loads(line) for line in (
            self.root / attestation["candidate_evidence_path"]
        ).read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(1, len(evidence))
        self.assertEqual("accept-while-unchanged",
                         evidence[0]["disposition"])
        self.assertRegex(evidence[0]["observation_sha256"],
                         r"^sha256:[0-9a-f]{64}$")

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


class RegisteredScanTests(_TemplateBackedCase):
    # Private copies of the applied template: every test poisons the
    # registered verifier, its registration row, or the Profile's slot
    # bindings before running its own close, so nothing here can share a
    # tree -- the poisoned walk is the subject.
    TEMPLATE = "applied"

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

        completed = self.batch_close()

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

        completed = self.batch_close()

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
        completed = self.batch_close()
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
        completed = self.batch_close()
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
        completed = self.batch_close()
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
        completed = self.batch_close()
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

        completed = self.batch_close()

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn(
            "expected 'fixture-residuals' from the admitted Profile contract",
            completed.stdout)


class CloseCeremonyGuardTests(_TemplateBackedCase):
    # Private copies of the applied template: the write ceremony itself is
    # the subject here -- CAS checks around the append, retained writer
    # locks, interrupted producers, and the recovery surface over their
    # durable leavings -- so every walk below stays inside its own test.
    TEMPLATE = "applied"

    def test_manifest_page_identity_and_bytes_are_cas_checked_before_append(self):
        page = self.root / "Topics/A.md"
        original = page.read_text(encoding="utf-8")
        real_assert = check_batch_close._assert_manifest_pages_unchanged
        injected = {"done": False}

        def change_before_first_cas(root, frozen, *, uncertain=False):
            if not injected["done"]:
                injected["done"] = True
                page.write_text(original + "\nconcurrent edit\n", encoding="utf-8")
            return real_assert(root, frozen, uncertain=uncertain)

        output = io.StringIO()
        with mock.patch.object(
                check_batch_close, "_assert_manifest_pages_unchanged",
                side_effect=change_before_first_cas), redirect_stdout(output):
            code = check_batch_close.main([
                str(self.root), "--batch", "B1",
                "--integrator", "fixture-integrator",
                "--reviewer", "fixture-reviewer",
                "--review-attestation",
                "I reviewed the exact listed candidates and merged snapshot.",
            ])
        self.assertEqual(1, code, output.getvalue())
        self.assertTrue(injected["done"])
        self.assertIn("manifest page changed before review evidence publication",
                      output.getvalue())
        attempts = [
            json.loads(line)
            for line in (self.root / ".cambium/receipts/batch-close.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(1, len(attempts))
        self.assertEqual("fail", attempts[0]["result"])
        self.assertEqual("batch_close_gate", attempts[0]["check"])
        self.assertFalse(any(
            row.get("check") == "page_review_acceptance"
            for row in attempts))

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

    def test_resume_requires_close_gate_when_only_apply_receipt_exists(self):
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("batch_close_recovery.status=gate-required batch=B1",
                      resumed.stdout)
        self.assertIn("batch_close_recovery.update_queue_command=none",
                      resumed.stdout)
        self.assertIn("next_action=run-batch-close-gate:B1",
                      resumed.stdout)

    def test_same_reviewer_and_integrator_fail_before_receipts(self):
        completed = self.run_tool(
            "check_batch_close.py", "--batch", "B1",
            "--integrator", "same", "--reviewer", "same",
            "--review-attestation", "Independent review statement.")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("must use different declared labels", completed.stdout)
        self.assertFalse((self.root / ".cambium/receipts/batch-close.jsonl").exists())

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


class PureFunctionTests(unittest.TestCase):
    # No scenario at all: these exercise pure functions over literal inputs
    # and never touch a repository tree.

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


if __name__ == "__main__":
    unittest.main()
