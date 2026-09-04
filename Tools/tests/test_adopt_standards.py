import copy
from contextlib import ExitStack, contextmanager, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"

import Tools.governance.standards.adopt_standards as adopt_standards
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.queue_runtime.adoption as queue_adoption
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
import Tools.execution.task_runtime.queue_runtime.revalidation as queue_revalidation
import Tools.execution.task_runtime.update_task as update_task
import Tools.knowledge.metadata.compose_page_contract as compose_page_contract
import Tools.knowledge.metadata.compose_vocab as compose_vocab
import Tools.platform.common.kblib as kblib
import Tools.governance.profile.profile_admission as profile_admission
import Tools.governance.standards.standards_state as standards_state
from Tools.tests.support.profile_fixture import install_loadable_profile
import Tools.platform.distribution.upstream_identity as upstream_identity


REPOSITORY = TOOLS.parent
UPSTREAM_REF = "HEAD"
ADOPTED_UPSTREAM_REVISION = upstream_identity.resolve_revision(
    REPOSITORY, UPSTREAM_REF)


def _current_contract_plan():
    """Return one complete current-schema plan without touching a repository."""
    digest = "sha256:" + "1" * 64
    revision = "a" * 40
    manifest = "profiles/test-profile/profile.md"
    return {
        "schema_version": 3,
        "adoption_id": "SA-CONTRACT",
        "task_id": "T-CONTRACT",
        "task_state_before": "paused",
        "contract_version_before": "c1",
        "contract_version_after": "c1",
        "upstream_revision_id_before": revision,
        "upstream_revision_id_after": revision,
        "standards_effective_date_after": "2026-08-31",
        "standards_state_sha256_before": digest,
        "selected_profile_manifest_before": manifest,
        "selected_profile_manifest_after": manifest,
        "governance_revision_ref":
            "kernel/K00 Standards Control/03 Standards Governance.md",
        "governance_revision_sha256": digest,
        "upstream_source_ref": "https://example.test/cambium.git",
        "standards_snapshot_sha256_after": digest,
        "profile_snapshot_sha256_after": digest,
        "profile_contract_fingerprint_after": digest,
        "profile_load_inputs_sha256_after": digest,
        "selected_route_ids_after": [],
        "selected_card_paths_after": [],
        "selected_profile_route_ids_after": [],
        "selected_read_sets_after": [],
        "loaded_module_paths_after": [],
        "queue_revision_before": 1,
        "queue_revision_after": 2,
        "queue_state_revision_before": 0,
        "coverage_sha256_before": digest,
        "required_queue_sha256_before": digest,
        "progress_sha256_before": digest,
        "changed_predicates": [],
        "invalidated_evidence": [],
        "invalidation_boundaries": [],
        "immediate_gate_reruns": ["required-queue-consistency"],
        "boundary_gate_reruns": [],
    }


# ---------------------------------------------------------------------------
# Scenario templates.
#
# The only repository-backed lifecycle is base -> paused -> adopted.  Each
# checkpoint is built once per process; mutating safety cases start from a
# private copy while the read-only happy path shares the adopted checkpoint.
# ---------------------------------------------------------------------------


class AdoptStandardsFixture:
    """Minimal fixture language for current adoption checkpoints."""

    GOVERNANCE = "kernel/K00 Standards Control/03 Standards Governance.md"
    PLAN = ".cambium/deltas/standards-adoptions/SA-001.yaml"
    RECEIPTS = ".cambium/receipts/standards-adoptions.jsonl"
    WRITER_BEFORE_REVISION = "0123456789abcdef0123456789abcdef01234567"
    WRITER_PROFILE = "profiles/writer-profile/profile.md"

    def build_repository_fixture(self):
        """Lay down the fixture tree the original setUp built per test."""
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        self.install_s_tier_audit_fixture()
        canonical_root = str(self.root.resolve())
        admission, admission_errors = profile_admission.admit_profile(
            canonical_root, require_approved=True)
        self.assertEqual([], admission_errors)
        vocab_text, _vocab, vocab_errors = compose_vocab.compiled_artifact(
            canonical_root, admission)
        self.assertEqual([], vocab_errors)
        vocab_path = self.root / compose_vocab.DEFAULT_OUTPUT
        vocab_path.parent.mkdir(parents=True, exist_ok=True)
        vocab_path.write_text(vocab_text, encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            code = compose_page_contract.main(["--root", str(self.root)])
        self.assertEqual(0, code, output.getvalue())
        governance = self.root / self.GOVERNANCE
        governance.parent.mkdir(parents=True, exist_ok=True)
        governance.write_text(
            "## Standards State And Adoption History\n\n"
            "Adopter state is external to the Kernel.\n",
            encoding="utf-8",
        )
        # ``install_loadable_profile`` installs the complete current
        # K00-owned YAML Control registry and its K12 registry dependency.
        # Tests must not recreate either machine contract as Markdown.

    def install_s_tier_audit_fixture(self):
        """Keep this Standards fixture outside unresolved M-review policy.

        These tests exercise Standards adoption, revalidation, and historical
        sealing; they do not make or inspect M-tier semantic judgments.  The
        current Kernel deliberately holds several M atoms whose acceptance
        selectors do not yet exist.  Treating the two synthetic ``# A``/``#
        B`` pages as S-tier therefore keeps this independent fixture honest:
        its one-page B1 still owes the registry-derived S sample and the full
        deterministic changed-scope closure, but it never manufactures an M
        verdict merely to reach the lifecycle edge under test.
        """
        for name in ("A", "B"):
            (self.root / ("Topics/%s.md" % name)).write_text(
                "---\n"
                "type: concept\n"
                "domain: general\n"
                "scope: shared\n"
                "level: basic\n"
                "depth: atomic\n"
                "priority: P2\n"
                "---\n"
                "# %s\n\n"
                "## Synthetic Residual\n\n"
                "Accepted-root liveness marker for the registered fixture "
                "scan.\n" % name,
                encoding="utf-8")

        coverage_path = self.root / queue_runtime.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        for page in coverage["pages"]:
            page["tier"] = "S"
            page["priority"] = "P2"
        coverage_path.write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        coverage_sha256 = kblib.sha256_file(coverage_path)

        progress_path = self.root / queue_runtime.PROGRESS_PATH
        progress = kblib.load_yaml_file(progress_path)
        checkpoint = progress.get("checkpoint") or {}
        if checkpoint.get("coverage_sha256") is not None:
            checkpoint["coverage_sha256"] = coverage_sha256
            progress_path.write_text(
                kblib.canonical_yaml(progress), encoding="utf-8")

        receipt_path = self.root / \
            ".cambium/receipts/task-transitions.jsonl"
        receipts = [
            json.loads(line) for line in
            receipt_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        initial = next(
            row for row in receipts
            if row.get("receipt_id") == "audit-fixture-initial-queue")
        initial["before_coverage_sha256"] = coverage_sha256
        initial["after_coverage_sha256"] = coverage_sha256
        initial["after_progress_sha256"] = kblib.sha256_file(progress_path)
        receipt_path.write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n"
                    for row in receipts),
            encoding="utf-8")

    def load(self, relative):
        return kblib.load_yaml_file(self.root / relative)

    def build_writer_checkpoint(self):
        """Create only the four current state documents the writer owns.

        Typed Profile admission, full runtime validation, and component-byte
        comparison are adjacent owners.  Their current handoffs are supplied
        by :meth:`writer_contract_context`; the transaction still performs
        its real state CAS, lock, append, rollback, and resulting-state read.
        """
        for relative in (
                queue_runtime.COVERAGE_PATH, queue_runtime.QUEUE_PATH,
                queue_runtime.PROGRESS_PATH, standards_state.STATE_PATH):
            (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
        (self.root / ".cambium/tmp").mkdir(parents=True, exist_ok=True)
        (self.root / ".cambium/receipts").mkdir(parents=True, exist_ok=True)
        governance = self.root / self.GOVERNANCE
        governance.parent.mkdir(parents=True, exist_ok=True)
        governance.write_text(
            "## Standards State And Adoption History\n\n"
            "Adopter state is external to the Kernel.\n",
            encoding="utf-8",
        )
        profile = self.root / self.WRITER_PROFILE
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(
            "# Authorized writer checkpoint\n", encoding="utf-8")

        coverage = {
            "schema_version": 2,
            "task_id": "writer-task",
            "upstream_revision_id": self.WRITER_BEFORE_REVISION,
            "selected_profile_manifest": self.WRITER_PROFILE,
            "pages": [],
            "batch_specs": [],
        }
        queue = {
            "schema_version": 2,
            "task_id": "writer-task",
            "scope_version": "s1",
            "queue_revision": 1,
            "state_revision": 0,
            "upstream_revision_id": self.WRITER_BEFORE_REVISION,
            "selected_profile_manifest": self.WRITER_PROFILE,
            "required_queue": [],
        }
        queue_text = kblib.canonical_yaml(queue)
        progress = {
            "schema_version": 2,
            "task_id": "writer-task",
            "task_state": "paused",
            "queue_revision": 1,
            "required_queue_sha256": kblib.sha256_bytes(queue_text),
            "standards_adoptions": [],
            "contract": {
                "contract_version": "c1",
                "upstream_revision_id": self.WRITER_BEFORE_REVISION,
                "selected_profile_manifest": self.WRITER_PROFILE,
                "selected_route_ids": [],
                "selected_card_paths": [],
                "selected_profile_route_ids": [],
                "selected_read_sets": [],
                "loaded_module_paths": [],
            },
        }
        standards = standards_state.next_state(
            None,
            effective_date="2026-08-30",
            selected_profile_manifest=self.WRITER_PROFILE,
            latest_adoption_receipt="audit-writer-before",
            upstream_source_ref="https://example.test/cambium.git",
            upstream_revision_id=self.WRITER_BEFORE_REVISION,
        )
        texts = {
            queue_runtime.COVERAGE_PATH: kblib.canonical_yaml(coverage),
            queue_runtime.QUEUE_PATH: queue_text,
            queue_runtime.PROGRESS_PATH: kblib.canonical_yaml(progress),
            standards_state.STATE_PATH: standards_state.canonical_text(
                standards),
        }
        for relative, text in texts.items():
            (self.root / relative).write_text(text, encoding="utf-8")
        self.writer_profile_evidence = {
            "selected_profile_manifest": self.WRITER_PROFILE,
            "profile_snapshot_sha256": "sha256:" + "2" * 64,
            "profile_contract_fingerprint": "sha256:" + "3" * 64,
            "profile_load_inputs_sha256": "sha256:" + "4" * 64,
        }
        write_plan = self.root / self.PLAN
        write_plan.parent.mkdir(parents=True, exist_ok=True)
        write_plan.write_text(
            kblib.canonical_yaml(self.writer_plan()), encoding="utf-8")

    def writer_plan(self):
        plan = _current_contract_plan()
        plan.update({
            "adoption_id": "SA-WRITER",
            "task_id": "writer-task",
            "task_state_before": "paused",
            "upstream_revision_id_before": self.WRITER_BEFORE_REVISION,
            "upstream_revision_id_after": ADOPTED_UPSTREAM_REVISION,
            "standards_state_sha256_before": kblib.sha256_file(
                self.root / standards_state.STATE_PATH),
            "selected_profile_manifest_before": self.WRITER_PROFILE,
            "selected_profile_manifest_after": self.WRITER_PROFILE,
            "governance_revision_sha256": kblib.sha256_file(
                self.root / self.GOVERNANCE),
            "standards_snapshot_sha256_after":
                kblib.repository_tree_sha256(self.root, "kernel"),
            "profile_snapshot_sha256_after":
                self.writer_profile_evidence["profile_snapshot_sha256"],
            "profile_contract_fingerprint_after":
                self.writer_profile_evidence[
                    "profile_contract_fingerprint"],
            "profile_load_inputs_sha256_after":
                self.writer_profile_evidence[
                    "profile_load_inputs_sha256"],
            "coverage_sha256_before": kblib.sha256_file(
                self.root / queue_runtime.COVERAGE_PATH),
            "required_queue_sha256_before": kblib.sha256_file(
                self.root / queue_runtime.QUEUE_PATH),
            "progress_sha256_before": kblib.sha256_file(
                self.root / queue_runtime.PROGRESS_PATH),
        })
        return plan

    def _writer_runtime_result(
            self, root, *, state_overrides=None,
            active_standards_state_override=None, **_kwargs):
        state_overrides = state_overrides or {}

        def document(relative):
            if relative in state_overrides:
                return copy.deepcopy(state_overrides[relative][1])
            return kblib.load_yaml_file(Path(root) / relative)

        coverage = document(queue_runtime.COVERAGE_PATH)
        queue = document(queue_runtime.QUEUE_PATH)
        progress = document(queue_runtime.PROGRESS_PATH)
        lock = Path(root) / ".cambium/tmp/state-writer.lock"
        return {
            "root": str(root),
            "errors": [],
            "coverage": coverage,
            "queue": queue,
            "progress": progress,
            "queue_path": str(Path(root) / queue_runtime.QUEUE_PATH),
            "coverage_sha256": kblib.sha256_bytes(
                kblib.canonical_yaml(coverage)),
            "queue_sha256": kblib.sha256_bytes(
                kblib.canonical_yaml(queue)),
            "progress_sha256": kblib.sha256_bytes(
                kblib.canonical_yaml(progress)),
            "remaining": len(queue.get("required_queue") or []),
            "receipt_catalog": {},
            "_writer_locks": [str(lock)] if lock.is_dir() else [],
        }

    def _writer_history(self, root):
        path = Path(root) / self.RECEIPTS
        catalog = {}
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                catalog[row["receipt_id"]] = (self.RECEIPTS, row)
        return catalog, []

    @contextmanager
    def writer_contract_context(self, *, profile_failure_phase=None,
                                component_failure_phase=None):
        def profile_evidence(_root, _plan, *, expected=None, phase):
            if phase == profile_failure_phase:
                raise ValueError(
                    "%s candidate Profile failed profile-load: injected "
                    "current-contract drift" % phase)
            evidence = copy.deepcopy(self.writer_profile_evidence)
            if expected is not None:
                self.assertEqual(expected, evidence)
            return evidence

        def components(_root, _upstream_root, revision_id, phase):
            if phase == component_failure_phase:
                raise ValueError(
                    "%s adopter immutable components differ from frozen "
                    "revision" % phase)
            return mock.Mock(
                upstream_revision_id=revision_id, errors=())

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                adopt_standards.runtime_validation, "validate_runtime",
                side_effect=self._writer_runtime_result))
            stack.enter_context(mock.patch.object(
                adopt_standards.queue_runtime,
                "delta_apply_write_barrier", return_value=None))
            stack.enter_context(mock.patch.object(
                adopt_standards.queue_runtime,
                "standards_adoption_plan_errors", return_value=[]))
            stack.enter_context(mock.patch.object(
                adopt_standards, "_after_profile_evidence",
                side_effect=profile_evidence))
            stack.enter_context(mock.patch.object(
                adopt_standards, "_require_upstream_components",
                side_effect=components))
            stack.enter_context(mock.patch.object(
                adopt_standards.adoption_lineage_contract,
                "load_adoption_history", side_effect=self._writer_history))
            yield

    def writer_prepare_result(self):
        with self.writer_contract_context():
            return adopt_standards._prepare_result(
                self.root, self.PLAN, REPOSITORY, UPSTREAM_REF)

    def writer_command(self, *, profile_failure_phase=None):
        stdout = io.StringIO()
        with self.writer_contract_context(
                profile_failure_phase=profile_failure_phase), \
                redirect_stdout(stdout):
            code = adopt_standards.main([
                str(self.root), "--plan", self.PLAN,
                "--upstream-root", str(REPOSITORY),
                "--upstream-ref", UPSTREAM_REF,
                "--apply", "--actor-role", "integrator",
            ])
        return code, stdout.getvalue()

    def pause(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = update_task.main([
                str(self.root), "--transition", "paused",
                "--checkpoint-summary", "pause before Standards adoption",
                "--expected-progress-sha256",
                kblib.sha256_file(self.root / queue_runtime.PROGRESS_PATH),
                "--expected-queue-sha256",
                kblib.sha256_file(self.root / queue_runtime.QUEUE_PATH),
                "--actor-role", "integrator", "--at",
                "2026-08-05T00:03:00Z", "--apply",
            ])
        self.assertEqual(0, code, output.getvalue())

    def plan(self, *, invalidated_receipt=None, overrides=None):
        # The live adopter state carries a full fixture commit identity. The
        # plan adopts the current upstream Git commit while K00/03 remains an
        # unchanged rules owner.
        queue = self.load(queue_runtime.QUEUE_PATH)
        progress = self.load(queue_runtime.PROGRESS_PATH)
        contract = progress["contract"]
        semantic = invalidated_receipt is not None
        profile_evidence, profile_errors = queue_runtime.profile_load_evidence(
            self.root, queue["selected_profile_manifest"])
        self.assertEqual([], profile_errors)
        plan = {
            "schema_version": 3,
            "adoption_id": "SA-001",
            "task_id": queue["task_id"],
            "task_state_before": progress["task_state"],
            "contract_version_before": contract["contract_version"],
            "contract_version_after": "c2" if semantic else
                contract["contract_version"],
            "upstream_revision_id_before": queue["upstream_revision_id"],
            "upstream_revision_id_after": ADOPTED_UPSTREAM_REVISION,
            "standards_effective_date_after": "2026-08-06",
            "standards_state_sha256_before": kblib.sha256_file(
                self.root / standards_state.STATE_PATH),
            "selected_profile_manifest_before":
                queue["selected_profile_manifest"],
            "selected_profile_manifest_after":
                queue["selected_profile_manifest"],
            "governance_revision_ref": self.GOVERNANCE,
            "governance_revision_sha256": kblib.sha256_file(
                self.root / self.GOVERNANCE),
            # The current source/revision identity pair is explicit; the
            # fixture corpus tracks a nominal upstream source so the closed
            # plan shape is exercised.
            "upstream_source_ref": "https://example.test/cambium.git",
            "standards_snapshot_sha256_after":
                kblib.repository_tree_sha256(self.root, "kernel"),
            "profile_snapshot_sha256_after":
                profile_evidence["profile_snapshot_sha256"],
            "profile_contract_fingerprint_after":
                profile_evidence["profile_contract_fingerprint"],
            "profile_load_inputs_sha256_after":
                profile_evidence["profile_load_inputs_sha256"],
            "selected_route_ids_after": copy.deepcopy(
                contract["selected_route_ids"]),
            "selected_card_paths_after": copy.deepcopy(
                contract["selected_card_paths"]),
            "selected_profile_route_ids_after": copy.deepcopy(
                contract["selected_profile_route_ids"]),
            "selected_read_sets_after": copy.deepcopy(
                contract["selected_read_sets"]),
            "loaded_module_paths_after": copy.deepcopy(
                contract["loaded_module_paths"]),
            "queue_revision_before": queue["queue_revision"],
            "queue_revision_after": queue["queue_revision"] + 1,
            "queue_state_revision_before": queue["state_revision"],
            "coverage_sha256_before": kblib.sha256_file(
                self.root / queue_runtime.COVERAGE_PATH),
            "required_queue_sha256_before": kblib.sha256_file(
                self.root / queue_runtime.QUEUE_PATH),
            "progress_sha256_before": kblib.sha256_file(
                self.root / queue_runtime.PROGRESS_PATH),
            "changed_predicates": [],
            "invalidated_evidence": [],
            "invalidation_boundaries": [],
            "immediate_gate_reruns": ["required-queue-consistency"],
            "boundary_gate_reruns": [],
        }
        if semantic:
            plan.update({
                "changed_predicates": [{
                    "predicate_id": "PRED-READY-001",
                    "owner_path": self.GOVERNANCE,
                    "change_kind": "modified",
                    "affected_gate_ids": ["required-queue-consistency"],
                }],
                "invalidated_evidence": [{
                    "receipt_id": invalidated_receipt,
                    "predicate_ids": ["PRED-READY-001"],
                    "dimension_ids": ["coverage_and_integration"],
                    "boundary_ids": ["INV-B1-READY"],
                    "reason_code": "predicate-changed",
                    "revalidation_scope_ids": ["B1"],
                }],
                "invalidation_boundaries": [{
                    "boundary_id": "INV-B1-READY",
                    "predicate_ids": ["PRED-READY-001"],
                    "target_kind": "batch",
                    "target_ids": ["B1"],
                    "required_gate_ids": ["required-queue-consistency"],
                }],
                "boundary_gate_reruns": ["required-queue-consistency"],
            })
        if overrides:
            plan.update(copy.deepcopy(overrides))
        path = self.root / self.PLAN
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
        return plan

    def _component_report(self, errors=()):
        return mock.Mock(
            upstream_revision_id=ADOPTED_UPSTREAM_REVISION,
            errors=tuple(errors),
        )

    def prepare_result(self):
        with mock.patch.object(
                adopt_standards.upstream_component_boundary, "evaluate",
                return_value=self._component_report()):
            return adopt_standards._prepare_result(
                self.root, self.PLAN, REPOSITORY, UPSTREAM_REF)

    def command(self, *, apply=False, actor="worker", component_errors=()):
        args = [str(self.root), "--plan", self.PLAN,
                "--upstream-root", str(REPOSITORY),
                "--upstream-ref", UPSTREAM_REF]
        if apply:
            args.extend(["--apply", "--actor-role", actor])
        stdout = io.StringIO()
        with redirect_stdout(stdout), mock.patch.object(
                adopt_standards.upstream_component_boundary, "evaluate",
                return_value=self._component_report(component_errors)):
            code = adopt_standards.main(args)
        return code, stdout.getvalue()

    def adoption_history_bytes(self):
        """Return the legal canonical-history baseline, including Profile adoption."""
        path = self.root / self.RECEIPTS
        return path.read_bytes() if path.exists() else None

    def standards_transaction_rows(self):
        """Select the latest Standards transaction and its linked Gate row."""
        path = self.root / self.RECEIPTS
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        transaction_rows = [
            row for row in rows
            if row.get("tool") == adopt_standards.TOOL and
            row.get("transaction_id")
        ]
        if not transaction_rows:
            return []
        transaction_id = transaction_rows[-1]["transaction_id"]
        transaction_rows = [
            row for row in transaction_rows
            if row["transaction_id"] == transaction_id
        ]
        linked_receipts = {
            receipt_id
            for row in transaction_rows
            for receipt_id in row.get("immediate_gate_receipts", [])
        }
        return [
            row for row in rows
            if (row.get("tool") == adopt_standards.TOOL and
                row.get("transaction_id") == transaction_id) or
            row.get("receipt_id") in linked_receipts
        ]

    def assert_committed_scenario(self):
        """The committed adoption this test consumes really applied clean."""
        self.assertEqual(0, self.scenario["apply_code"],
                         self.scenario["apply_output"])
        self.assertEqual(
            [], runtime_validation.validate_runtime(self.root)["errors"])

    READ_SET = "Read Set/R99 Fixture Read Set.md"
    CROSS_READ_SET = "Read Set/R98 Cross Referenced Read Set.md"
    PROFILE_READ_SET = "profiles/test-profile/P Supplemental Read Set.md"
    # A non-Read-Set target must not sit inside the closed canonical Read Set
    # declaration directory, where discovery intentionally treats every
    # Markdown file except the generated index as a declaration.
    READ_SET_INDEX = "kernel/K99 Fixture Family/Fixture Route Index.md"
    LEAF_DIRECT = "kernel/K99 Fixture Family/01 Direct Leaf.md"
    LEAF_NESTED = "kernel/K99 Fixture Family/02 Nested Leaf.md"
    LEAF_PROFILE = "kernel/K99 Fixture Family/03 Profile Leaf.md"
    LEAF_RELATED = "kernel/K99 Fixture Family/04 Related Only Leaf.md"
    ORDINARY_SELECTED = "profiles/test-profile/ordinary.md"
    BOUND_PROFILE_FILE = "profiles/test-profile/profile.md"
    BOUND_TOOL_FILE = "Tools/fixture_tool.py"
    def read_set_text(self, route_id, *, targets, read_sets,
                      document_type="read-set", trigger_note="None."):
        """Render one canonical machine Read Set fixture."""
        declaration = {
            "type": document_type,
            "schema_version": 1,
            "route_id": route_id,
            "activation_phase": "batch-preflight",
            "narrowable": True,
            "load_edges": [{
                "edge_id": "%s:start" % route_id,
                "kind": "required",
                "phase_id": "batch-preflight",
                "trigger_id": "route-selected",
                "targets": list(targets),
                "read_sets": list(read_sets),
            }],
        }
        return (
            "---\n%s---\n# %s Fixture Read Set\n\n"
            "## Purpose\n\nExercise the declared loading boundary.\n\n"
            "## Non-deterministic triggers\n\n%s\n" %
            (kblib.canonical_yaml(declaration), route_id, trigger_note))

    def write_boundary_fixture(self):
        """Lay down a cycle-safe kernel/profile Read Set closure."""
        for relative in (self.LEAF_DIRECT, self.LEAF_NESTED,
                         self.LEAF_PROFILE, self.LEAF_RELATED):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("## Purpose\n\nFixture leaf.\n", encoding="utf-8")
        index = self.root / self.READ_SET_INDEX
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(
            "---\ntype: route-index\n---\n\n## Purpose\n\nNot a Read Set.\n",
            encoding="utf-8")
        tool = self.root / self.BOUND_TOOL_FILE
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text("# Extra bound tool.\n", encoding="utf-8")

        read_set = self.root / self.READ_SET
        read_set.parent.mkdir(parents=True, exist_ok=True)
        read_set.write_text(
            self.read_set_text(
                "R99",
                targets=[self.LEAF_DIRECT, self.READ_SET_INDEX],
                # A top-level Read Set composes only top-level route IDs.
                # The selected Profile route is an independent closure root
                # resolved from selected_profile_route_ids_after.
                read_sets=["R98"],
                trigger_note=(
                    "The explanatory link [[%s|Related Only Leaf]] is not a "
                    "loading edge." % self.LEAF_RELATED[:-3])),
            encoding="utf-8")

        cross = self.root / self.CROSS_READ_SET
        cross.write_text(
            self.read_set_text(
                "R98", targets=[self.LEAF_NESTED], read_sets=["R99"]),
            encoding="utf-8")

        profile = self.root / self.PROFILE_READ_SET
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(
            self.read_set_text(
                "P:test-profile:supplemental",
                targets=[self.LEAF_PROFILE], read_sets=[],
                document_type="profile-read-set"),
            encoding="utf-8")

    def revalidation_result(self, **item):
        """A reduced resume context carrying one outstanding batch."""
        task_state = item.pop("task_state", "active")
        record = {"id": "B1", "order": 1, "state": "queued",
                  "hold_state": "none"}
        record.update(item)
        return {
            # Producer eligibility consumes the canonical K00 Gate registry;
            # the reduced context must therefore retain the repository root
            # that a full validate_runtime result always carries.
            "root": TOOLS.parent,
            "standards_revalidation_outstanding": {
                "B1": [{"adoption_id": "SA-001", "boundary_id": "INV-B1",
                        "required_gate_id": "batch-close"}]},
            "items_by_id": {"B1": record},
            "progress": {"task_state": task_state},
            "queue": {"required_queue": [{"id": "B1"}]},
        }


class _ScenarioWalker(AdoptStandardsFixture, unittest.TestCase):
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


def _build_adopted(walker, inherited):
    plan = walker.plan()
    state_paths = [walker.root / path for path in (
        queue_runtime.COVERAGE_PATH, queue_runtime.QUEUE_PATH,
        queue_runtime.PROGRESS_PATH)]
    state_before_dry_run = [path.read_bytes() for path in state_paths]
    history_before_dry_run = walker.adoption_history_bytes()
    dry_run_code, dry_run_output = walker.command()
    state_after_dry_run = [path.read_bytes() for path in state_paths]
    history_after_dry_run = walker.adoption_history_bytes()
    apply_code, apply_output = walker.command(
        apply=True, actor="integrator")
    walker.assertEqual(0, apply_code, apply_output)
    return {
        "plan": plan,
        "state_before_dry_run": state_before_dry_run,
        "dry_run_code": dry_run_code,
        "dry_run_output": dry_run_output,
        "state_after_dry_run": state_after_dry_run,
        "history_before_dry_run": history_before_dry_run,
        "history_after_dry_run": history_after_dry_run,
        "apply_code": apply_code,
        "apply_output": apply_output,
    }


# name -> (TemporaryDirectory holder, template root, artifacts).  The holder
# reference keeps each template alive for the whole process; TemporaryDirectory
# finalizers remove the trees at interpreter exit.
_TEMPLATES = {}


def _template(name):
    """Return (root, artifacts) for ``name``, walking it on first use."""
    if name != "adopted":
        raise ValueError("the current suite has only one adoption E2E")
    if name not in _TEMPLATES:
        holder = tempfile.TemporaryDirectory()
        root = Path(holder.name) / "repo"
        walker = _ScenarioWalker.at(root)
        walker.build_repository_fixture()
        walker.pause()
        artifacts = _build_adopted(walker, {})
        _TEMPLATES[name] = (holder, root, artifacts)
    _holder, root, artifacts = _TEMPLATES[name]
    return root, artifacts


class _TemplateBackedCase(AdoptStandardsFixture, unittest.TestCase):
    """A test class whose tree starts at a named scenario template."""

    TEMPLATE = None
    # Only a class whose every test is read-only may share the template tree
    # itself; everything else gets a private copy per test.
    SHARE_TEMPLATE = False

    def setUp(self):
        template_root, self.scenario = _template(self.TEMPLATE)
        if self.SHARE_TEMPLATE:
            self.tmp = None
            self.root = template_root
        else:
            self.tmp = tempfile.TemporaryDirectory()
            self.root = Path(self.tmp.name) / "repo"
            shutil.copytree(template_root, self.root)

    def tearDown(self):
        if self.tmp is not None:
            self.tmp.cleanup()


class WriterProjectionUnitTests(unittest.TestCase):
    """Pure writer-owned projections; no repository or receipt machinery."""

    def test_plan_identity_contains_only_current_non_version_identity(self):
        plan = _current_contract_plan()
        self.assertEqual({
            "task_id": "T-CONTRACT",
            "selected_profile_manifest": "profiles/test-profile/profile.md",
        }, adopt_standards._plan_identity(plan))

    def test_writer_guard_allows_only_adopter_owned_projection(self):
        before = {
            "coverage": {
                "upstream_revision_id": "before",
                "selected_profile_manifest": "profiles/before/profile.md",
                "pages": [{"path": "Topics/A.md"}],
            },
            "queue": {
                "upstream_revision_id": "before",
                "selected_profile_manifest": "profiles/before/profile.md",
                "queue_revision": 1,
                "state_revision": 7,
                "required_queue": [{"id": "B1"}],
            },
            "progress": {
                "standards_adoptions": [],
                "queue_revision": 1,
                "required_queue_sha256": "before",
                "task_state": "paused",
                "checkpoint": {"stable": True},
                "contract": {
                    "contract_version": "c1",
                    "upstream_revision_id": "before",
                    "selected_profile_manifest":
                        "profiles/before/profile.md",
                    "selected_route_ids": [],
                    "selected_card_paths": [],
                    "selected_profile_route_ids": [],
                    "selected_read_sets": [],
                    "loaded_module_paths": [],
                },
            },
            "standards": {
                "state_revision": 1,
                "upstream_revision_id": "before",
                "status": "current",
                "effective_date": "2026-08-01",
                "selected_profile_manifest":
                    "profiles/before/profile.md",
                "latest_adoption_receipt": "R0",
                "upstream_source_ref":
                    "https://example.test/cambium.git",
                "policy": "fixed",
            },
        }
        after = copy.deepcopy(before)
        after["coverage"].update({
            "upstream_revision_id": "after",
            "selected_profile_manifest": "profiles/after/profile.md",
        })
        after["queue"].update({
            "upstream_revision_id": "after",
            "selected_profile_manifest": "profiles/after/profile.md",
            "queue_revision": 2,
        })
        after["progress"].update({
            "standards_adoptions": [{"adoption_id": "SA-CONTRACT"}],
            "queue_revision": 2,
            "required_queue_sha256": "after",
        })
        after["progress"]["contract"].update({
            "contract_version": "c2",
            "upstream_revision_id": "after",
            "selected_profile_manifest": "profiles/after/profile.md",
            "loaded_module_paths": ["kernel/K00.md"],
        })
        after["standards"].update({
            "state_revision": 2,
            "upstream_revision_id": "after",
            "effective_date": "2026-08-31",
            "selected_profile_manifest": "profiles/after/profile.md",
            "latest_adoption_receipt": "R1",
        })
        adopt_standards._assert_only_permitted_changes(before, after)

        forbidden = {
            "coverage": lambda value: value["coverage"]["pages"].append(
                {"path": "Topics/B.md"}),
            "queue": lambda value: value["queue"]["required_queue"].append(
                {"id": "B2"}),
            "progress": lambda value: value["progress"].update(
                task_state="active"),
            "standards": lambda value: value["standards"].update(
                policy="changed"),
        }
        for name, mutate in forbidden.items():
            with self.subTest(document=name):
                candidate = copy.deepcopy(after)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    adopt_standards._assert_only_permitted_changes(
                        before, candidate)


class AdoptionPlanContractTests(unittest.TestCase):
    """Closed current-schema admission over in-memory plan objects."""

    def plan_errors(self, plan):
        return queue_runtime.standards_adoption_plan_errors(
            None, plan, validate_live_inputs=False)

    def test_current_shape_is_closed_and_requires_unambiguous_identity(self):
        plan = _current_contract_plan()
        self.assertEqual([], self.plan_errors(plan))
        cases = (
            ("invalid-schema", {"schema_version": None},
             "schema_version must be 3"),
            ("unknown-field", {"undeclared_identity": "value"},
             "unsupported field(s): undeclared_identity"),
            ("short-upstream-revision", {"upstream_revision_id_after": "v3"},
             "must be one full Git commit SHA"),
            ("missing-upstream-source", {"upstream_source_ref": None},
             "must name the adopted Cambium source"),
        )
        for label, changes, expected in cases:
            with self.subTest(case=label):
                candidate = copy.deepcopy(plan)
                candidate.update(changes)
                self.assertTrue(any(
                    expected in error for error in
                    self.plan_errors(candidate)),
                    self.plan_errors(candidate))

    def test_plan_order_revision_and_immediate_gate_are_exact(self):
        plan = _current_contract_plan()
        cases = (
            ({"selected_route_ids_after": ["z", "a"]},
             "selected_route_ids_after must be sorted"),
            ({"queue_revision_after": 3},
             "queue_revision_after must increment"),
            ({"immediate_gate_reruns": []},
             "immediate_gate_reruns must be exactly"),
        )
        for changes, expected in cases:
            with self.subTest(changes=changes):
                candidate = copy.deepcopy(plan)
                candidate.update(changes)
                errors = self.plan_errors(candidate)
                self.assertTrue(any(expected in error for error in errors),
                                errors)

    def test_profile_load_boundary_is_the_exact_candidate_admission(self):
        plan = _current_contract_plan()
        manifest = plan["selected_profile_manifest_after"]
        plan["contract_version_after"] = "c2"
        plan["changed_predicates"] = [{
            "predicate_id": "P-PROFILE",
            "owner_path": plan["governance_revision_ref"],
            "change_kind": "modified",
            "affected_gate_ids": ["profile-load"],
        }]
        plan["invalidation_boundaries"] = [{
            "boundary_id": "INV-PROFILE",
            "predicate_ids": ["P-PROFILE"],
            "target_kind": "profile-load",
            "target_ids": [manifest],
            "required_gate_ids": ["profile-load"],
        }]
        self.assertEqual([], self.plan_errors(plan))

        cases = (
            ("wrong-target", {"target_ids":
                ["profiles/test-profile/slots.md"]},
             "target_ids must contain only "
             "selected_profile_manifest_after"),
            ("missing-gate", {"required_gate_ids": []},
             "must require the profile-load Gate"),
            ("missing-predicate", {"predicate_ids": []},
             "must reference every changed predicate"),
        )
        for label, changes, expected in cases:
            with self.subTest(case=label):
                candidate = copy.deepcopy(plan)
                candidate["invalidation_boundaries"][0].update(changes)
                errors = self.plan_errors(candidate)
                self.assertTrue(any(expected in error for error in errors),
                                errors)


class RevalidationSelectionContractTests(AdoptStandardsFixture,
                                          unittest.TestCase):

    def test_resume_names_only_batches_the_current_producer_admits(self):
        registry = {
            "standards-revalidation": {
                "lifecycle_states": ("queued", "open"),
            },
        }
        cases = (
            ("queued-active", "queued", "none", "active", True),
            ("held-open-active", "open", "revalidation-required",
             "active", True),
            ("unheld-open", "open", "none", "active", False),
            ("merge-ready", "merge-ready", "none", "active", False),
            ("closed", "closed", "none", "active", False),
            ("paused", "queued", "none", "paused", False),
        )
        with mock.patch.object(
                queue_revalidation, "standards_gate_registry",
                return_value=(registry, [])):
            for label, state, hold, task_state, admitted in cases:
                with self.subTest(case=label):
                    result = self.revalidation_result(
                        state=state, hold_state=hold,
                        task_state=task_state)
                    reason = (
                        queue_runtime
                        .standards_revalidation_producer_eligibility(
                            result, "B1"))
                    self.assertEqual(admitted, reason is None)
                    actionable = (
                        queue_runtime.actionable_revalidation_batches(
                            result))
                    self.assertEqual(["B1"] if admitted else [], actionable)
                    action = queue_runtime.resume_next_action(result, [])
                    if admitted:
                        self.assertEqual(
                            "run-standards-revalidation:B1", action)
                    else:
                        self.assertNotEqual(
                            "run-standards-revalidation:B1", action)


class CorrectiveAdoptionBeforeImageTests(AdoptStandardsFixture,
                                         unittest.TestCase):
    """One local current-runtime seam for the K12/10 asymmetric boundary."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.build_repository_fixture()

    def test_new_profile_load_inputs_do_not_rebind_old_adoption_receipts(self):
        # Public release components are installed before adopt_standards can
        # run.  A byte change in their canonical Profile-load input closure
        # therefore creates a valid target view that the immutable before
        # Receipt could never have bound.
        contract = self.root / \
            "kernel/K00 Standards Control/profile-interface.yaml"
        contract.write_text(
            contract.read_text(encoding="utf-8") + "\n",
            encoding="utf-8")

        ordinary = runtime_validation.validate_runtime(self.root)
        self.assertIn(
            "does not bind current authorized Profile",
            "\n".join(ordinary["errors"]))

        corrective = runtime_validation.validate_runtime(
            self.root,
            allow_invalid_current_profile_for_corrective_adoption=True,
            allow_active_standards_mismatch_for_adoption=True)
        self.assertEqual([], corrective["errors"])
        self.assertIsNotNone(corrective["_profile_authorized_view"])


class BaseReadSetCheckpointTests(AdoptStandardsFixture,
                                 unittest.TestCase):
    """One adjacent Read Set closure -> adoption-plan seam."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        governance = self.root / self.GOVERNANCE
        governance.parent.mkdir(parents=True, exist_ok=True)
        governance.write_text("## Fixture governance\n", encoding="utf-8")
        profile = self.root / self.BOUND_PROFILE_FILE
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(
            "# Fixture Profile\n\n## Profile Identity\n\n"
            "- `profile_id`: `test-profile`\n",
            encoding="utf-8")
        schema = self.root / "Read Set/read-set.schema.yaml"
        schema.parent.mkdir(parents=True, exist_ok=True)
        schema.write_bytes(
            (REPOSITORY / "Read Set/read-set.schema.yaml").read_bytes())
        standards = standards_state.next_state(
            None,
            effective_date="2026-08-30",
            selected_profile_manifest=self.BOUND_PROFILE_FILE,
            latest_adoption_receipt="audit-read-set-before",
            upstream_source_ref="https://example.test/cambium.git",
            upstream_revision_id="a" * 40,
        )
        state = self.root / standards_state.STATE_PATH
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(
            standards_state.canonical_text(standards), encoding="utf-8")
        self.write_boundary_fixture()

    def live_plan_errors(self, plan):
        queue = {
            "task_id": plan["task_id"],
            "queue_revision": plan["queue_revision_before"],
            "state_revision": plan["queue_state_revision_before"],
            "required_queue": [],
        }
        progress = {
            "task_state": plan["task_state_before"],
            "contract": {
                "contract_version": plan["contract_version_before"],
                "selected_route_ids": [],
                "selected_card_paths": [],
                "selected_profile_route_ids": [],
                "selected_read_sets": [],
                "loaded_module_paths": [],
            },
        }
        evidence = {
            "selected_profile_manifest": self.BOUND_PROFILE_FILE,
            "profile_snapshot_sha256":
                plan["profile_snapshot_sha256_after"],
            "profile_contract_fingerprint":
                plan["profile_contract_fingerprint_after"],
            "profile_load_inputs_sha256":
                plan["profile_load_inputs_sha256_after"],
        }
        with mock.patch.object(
                queue_adoption, "profile_load_evidence",
                return_value=(evidence, [])), mock.patch.object(
                queue_adoption, "standards_gate_registry",
                return_value=({}, [])), mock.patch.object(
                queue_adoption, "standards_revalidation_capabilities",
                return_value=({}, [])):
            return queue_runtime.standards_adoption_plan_errors(
                self.root, plan, catalog={}, queue=queue,
                progress=progress, validate_live_inputs=True)

    def test_complete_declared_closure_accepts_route_bound_extra_paths(self):
        plan = _current_contract_plan()
        plan.update({
            "contract_version_after": "c2",
            "selected_profile_manifest_before": self.BOUND_PROFILE_FILE,
            "selected_profile_manifest_after": self.BOUND_PROFILE_FILE,
            "standards_state_sha256_before": kblib.sha256_file(
                self.root / standards_state.STATE_PATH),
            "governance_revision_sha256": kblib.sha256_file(
                self.root / self.GOVERNANCE),
            "standards_snapshot_sha256_after":
                kblib.repository_tree_sha256(self.root, "kernel"),
            "selected_profile_route_ids_after": [
                "P:test-profile:supplemental"],
            "selected_read_sets_after": sorted(
                (self.READ_SET, self.CROSS_READ_SET,
                 self.PROFILE_READ_SET)),
            "loaded_module_paths_after": sorted(
                (self.BOUND_PROFILE_FILE, self.BOUND_TOOL_FILE,
                 self.LEAF_DIRECT, self.LEAF_NESTED, self.LEAF_PROFILE,
                 self.READ_SET_INDEX)),
        })
        self.assertEqual([], self.live_plan_errors(plan))


class AdoptionTransactionE2ETests(_TemplateBackedCase):
    TEMPLATE = "adopted"
    SHARE_TEMPLATE = True

    def test_dry_run_then_apply_commits_one_current_transaction(self):
        plan = self.scenario["plan"]
        self.assertEqual(
            0, self.scenario["dry_run_code"],
            self.scenario["dry_run_output"])
        self.assertEqual(
            self.scenario["state_before_dry_run"],
            self.scenario["state_after_dry_run"])
        self.assertEqual(
            self.scenario["history_before_dry_run"],
            self.scenario["history_after_dry_run"])

        self.assert_committed_scenario()
        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual("paused", result["progress"]["task_state"])
        self.assertEqual(
            plan["queue_revision_after"],
            result["queue"]["queue_revision"])
        self.assertEqual(0, result["queue"]["state_revision"])

        record = result["progress"]["standards_adoptions"][0]
        self.assertEqual(
            plan["profile_contract_fingerprint_after"],
            record["profile_contract_fingerprint_after"])
        self.assertEqual(
            plan["profile_load_inputs_sha256_after"],
            record["profile_load_inputs_sha256_after"])
        rows = self.standards_transaction_rows()
        self.assertEqual(
            ["prepare", None, "commit"],
            [row.get("transaction_phase") for row in rows])
        adoption_rows = [
            row for row in rows
            if row.get("tool") == adopt_standards.TOOL
        ]
        self.assertEqual(
            {adopt_standards.TOOL_VERSION},
            {row.get("tool_version") for row in adoption_rows})
        self.assertEqual(
            {adopt_standards.GATE_ID},
            {row.get("gate_id") for row in adoption_rows})
        self.assertRegex(
            record["profile_contract_fingerprint_after"],
            r"^sha256:[0-9a-f]{64}$")

        # Profile closure invalidation and adoption-lineage interpretation
        # have their own Contract owners.  This sole E2E stops at the exact
        # current runtime after-image instead of mutating it into another
        # suite's failure case.


class AdoptionTransactionSafetyTests(AdoptStandardsFixture,
                                      unittest.TestCase):
    """Writer CAS and recovery from a local current-contract checkpoint."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.build_writer_checkpoint()

    def test_locked_prewrite_component_cas_rejects_drift(self):
        prepared = self.writer_prepare_result()
        state_paths = [self.root / path for path in (
            queue_runtime.COVERAGE_PATH, queue_runtime.QUEUE_PATH,
            queue_runtime.PROGRESS_PATH, standards_state.STATE_PATH)]
        before = [path.read_bytes() for path in state_paths]
        history_before = self.adoption_history_bytes()

        with self.writer_contract_context(
                component_failure_phase="locked pre-write"):
            with self.assertRaisesRegex(ValueError, "locked pre-write"):
                adopt_standards._commit_transaction(
                    prepared, self.root / self.RECEIPTS)

        self.assertEqual(
            before, [path.read_bytes() for path in state_paths])
        self.assertEqual(history_before, self.adoption_history_bytes())
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_final_append_drift_restores_state_and_keeps_recovery_lock(self):
        state_paths = [self.root / path for path in (
            queue_runtime.COVERAGE_PATH, queue_runtime.QUEUE_PATH,
            queue_runtime.PROGRESS_PATH)]
        before = [path.read_bytes() for path in state_paths]
        code, output = self.writer_command(
            profile_failure_phase="post-final-receipt")

        self.assertEqual(1, code, output)
        self.assertIn(
            "post-final-receipt candidate Profile failed", output)
        self.assertIn("recovery is incomplete", output)
        self.assertEqual(
            before, [path.read_bytes() for path in state_paths])
        rows = self.standards_transaction_rows()
        self.assertEqual(
            ["prepare", None, "commit", "abort"],
            [row.get("transaction_phase") for row in rows])
        lock = self.root / ".cambium/tmp/state-writer.lock"
        self.assertTrue(lock.is_dir())
        owner = json.loads(
            (lock / "owner.json").read_text(encoding="utf-8"))
        self.assertRegex(
            owner["operation"][
                "profile_contract_fingerprint_after"],
            r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(
            owner["operation"]["profile_load_inputs_sha256_after"],
            r"^sha256:[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
