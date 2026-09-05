"""Shared current-contract Profile adoption transaction fixture."""

import contextlib
import hashlib
import io
import json
import shutil
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

import Tools.governance.profile.apply_profile_adoption as apply_profile_adoption
import Tools.governance.profile.check_profile as check_profile
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.governance.profile.scaffold_profile as scaffold_profile
import Tools.governance.standards.standards_state as standards_state
import Tools.platform.common.kblib as kblib
import Tools.platform.distribution.module_boundary_facts as module_boundary_facts
import Tools.platform.distribution.upstream_identity as upstream_identity
import Tools.tests.support.profile_load_fixture as profile_load_fixture
from Tools.tests.support.profile_contract_fixture import write_profile_document
from Tools.tests.support.profile_template_fixture import (
    ORIENTATION,
    TEMPLATE,
    fill_profile,
    fill_scaffolded_profile,
)


REPOSITORY = Path(__file__).resolve().parents[3]
TOOLS = REPOSITORY / "Tools"
GOVERNANCE = "kernel/K00 Standards Control/03 Standards Governance.md"
PROFILE_ID = "cand"
MANIFEST = "profiles/%s/%s" % (
    PROFILE_ID, profile_layout_contract.PROFILE_MANIFEST_NAME)
PLAN_RELATIVE = "adoption-plans/PA-001.yaml"
UPSTREAM_REF = "HEAD"
UPSTREAM_REVISION = upstream_identity.resolve_revision(REPOSITORY, UPSTREAM_REF)


def _copy_tree_bytes(source, target):
    """Clone one test checkpoint without invoking repository-copy helpers."""
    source = Path(source)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_symlink():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(path.readlink())
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    return target


def build_writer_checkpoint(target):
    """Build an already-authorized Profile checkpoint for writer tests.

    Profile parsing, typed-closure construction, and the real derived
    producers belong to their own Contract/E2E owners.  This checkpoint keeps
    only the bytes the adoption writer binds and the two producer entrypoint
    identities it requires before entering its transaction.
    """
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    governance = target / GOVERNANCE
    governance.parent.mkdir(parents=True, exist_ok=True)
    governance.write_bytes((REPOSITORY / GOVERNANCE).read_bytes())
    profile = target / "profiles" / PROFILE_ID
    profile.mkdir(parents=True)
    write_profile_document(profile, {
        "schema_version": 1, "profile_id": PROFILE_ID,
        "slots": {"corpus-planning": {
            "applicability": {"state": "not-applicable",
                              "reason": "Confirmed writer checkpoint."}}},
    })
    tools = target / "Tools"
    tools.mkdir()
    for script in ("compose_vocab.py", "compose_page_contract.py"):
        (tools / script).write_text(
            "# Current producer identity; execution is owned by its suite.\n",
            encoding="utf-8",
        )
    return target


def clone_writer_checkpoint(source, target):
    """Materialize one byte-exact local writer checkpoint."""
    return _copy_tree_bytes(source, target)


def _writer_profile_bytes(root):
    root = Path(root)
    return (root / MANIFEST).read_bytes()


def writer_evaluation_of(root):
    """Return the authorized typed-Profile handoff consumed by the writer."""
    digest = hashlib.sha256(_writer_profile_bytes(root)).hexdigest()
    snapshot = "sha256:" + digest
    contract = "sha256:" + hashlib.sha256(
        ("contract:" + digest).encode("ascii")).hexdigest()
    inputs = "sha256:" + hashlib.sha256(
        ("inputs:" + digest).encode("ascii")).hexdigest()
    metadata = "sha256:" + hashlib.sha256(
        ("metadata:" + digest).encode("ascii")).hexdigest()
    summary = {
        "receipt_id": "audit-check_profile-writer-%s" % digest[:20],
        "receipt_type_id": check_profile.GATE_RECEIPT_TYPE_ID,
        "check": check_profile.GATE_CHECK,
        "target": MANIFEST,
        "result": "pass",
        "details": "authorized typed Profile writer checkpoint",
        "checked_at": "2026-08-31T00:00:00Z",
        "tool": check_profile.TOOL,
        "tool_version": check_profile.TOOL_VERSION,
        "invalidated_by": None,
        "gate_id": check_profile.GATE_ID,
        "dimension": check_profile.GATE_DIMENSION,
        "selected_profile_manifest": MANIFEST,
        "profile_snapshot_sha256": snapshot,
        "profile_contract_fingerprint": contract,
        "profile_load_inputs_sha256": inputs,
        "metadata_execution_contract_fingerprint": metadata,
    }
    return SimpleNamespace(
        authorized=True,
        findings=(),
        exit_code=0,
        output="",
        profile_snapshot_sha256=snapshot,
        profile_contract_fingerprint=contract,
        profile_load_inputs_sha256=inputs,
        summary_receipt=summary,
    )


def writer_initial_plan(root, **overrides):
    """Bind one already-authorized writer checkpoint to an initial plan."""
    return initial_plan(root, evaluation=writer_evaluation_of(root),
                        **overrides)


def writer_revision_plan(root, **overrides):
    """Bind a changed authorized checkpoint to the current adopter state."""
    root = Path(root)
    plan = writer_initial_plan(root)
    plan.update({
        "plan_id": "PA-002",
        "branch": "profile-revision",
        "standards_effective_date_after": "2026-08-14",
        "upstream_revision_id_before": UPSTREAM_REVISION,
        "selected_profile_manifest_before": MANIFEST,
        "standards_state_sha256_before":
            kblib.sha256_file(root / standards_state.STATE_PATH),
        "change_summary":
            "Profile revision inside %s: confirmed bytes updated" % MANIFEST,
    })
    plan.update(overrides)
    return plan


def _writer_projection_bytes(root, script):
    profile_sha = hashlib.sha256(_writer_profile_bytes(root)).hexdigest()
    return kblib.canonical_yaml({
        "producer": Path(script).stem,
        "profile_checkpoint_sha256": "sha256:" + profile_sha,
    }).encode("utf-8")


def writer_step(command, cwd):
    """Model the adjacent deterministic producer handoff, not its internals."""
    script = next((
        Path(str(part)).name for part in command
        if str(part).endswith(("compose_vocab.py",
                               "compose_page_contract.py"))
    ), None)
    artifact = {
        "compose_vocab.py": apply_profile_adoption.VOCAB_ARTIFACT,
        "compose_page_contract.py":
            apply_profile_adoption.PAGE_CONTRACT_ARTIFACT,
    }.get(script)
    if artifact is None:
        return 2, "unexpected writer checkpoint producer command"
    path = Path(cwd) / artifact
    expected = _writer_projection_bytes(cwd, script)
    if "--check" in command:
        if path.is_file() and path.read_bytes() == expected:
            return 0, "current"
        return 2, "derived writer checkpoint is stale"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(expected)
    return 0, "written"


def _writer_adoption_history(root):
    """Read the exact current history bytes for writer read-back tests."""
    path = Path(root) / apply_profile_adoption.RECEIPT_RELATIVE
    catalog = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            catalog[row["receipt_id"]] = (
                apply_profile_adoption.RECEIPT_RELATIVE, row)
    return catalog, []


def run_writer_tool(root, *extra, plan=PLAN_RELATIVE, step_runner=None,
                    component_errors=()):
    """Run the current writer from an authorized local contract checkpoint."""
    if step_runner is None:
        step_runner = writer_step
    evaluation = lambda *_args, **_kwargs: writer_evaluation_of(root)
    buffer = io.StringIO()
    component_report = mock.Mock(
        upstream_revision_id=UPSTREAM_REVISION,
        errors=tuple(component_errors),
    )
    with contextlib.ExitStack() as stack:
        stack.enter_context(contextlib.redirect_stdout(buffer))
        stack.enter_context(mock.patch.object(
            apply_profile_adoption.upstream_component_boundary,
            "evaluate", return_value=component_report))
        stack.enter_context(mock.patch.object(
            apply_profile_adoption.check_profile,
            "evaluate_profile_load", side_effect=evaluation))
        stack.enter_context(mock.patch.object(
            apply_profile_adoption, "_run_step", side_effect=step_runner))
        stack.enter_context(mock.patch.object(
            apply_profile_adoption.adoption_lineage_contract,
            "load_adoption_history", side_effect=_writer_adoption_history))
        stack.enter_context(mock.patch.object(
            apply_profile_adoption.adoption_lineage_contract,
            "current_lineage_errors", return_value=[]))
        code = apply_profile_adoption.main([
            str(root),
            "--plan", plan,
            "--upstream-root", str(REPOSITORY),
            "--upstream-ref", UPSTREAM_REF,
            *extra,
        ])
    return code, buffer.getvalue()


def build_base(target):
    target = Path(target)
    target.mkdir(parents=True)
    shutil.copytree(REPOSITORY / "kernel", target / "kernel")
    shutil.copytree(REPOSITORY / "Card", target / "Card")
    shutil.copytree(REPOSITORY / "Read Set", target / "Read Set")
    (target / "profiles").mkdir()
    shutil.copyfile(REPOSITORY / "profiles" / "README.md", target / "profiles" / "README.md")
    (target / "Tools").mkdir()
    for relative in module_boundary_facts.shipped_modules(str(TOOLS)):
        copy = target / "Tools" / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TOOLS / relative, copy)
    shutil.copytree(REPOSITORY / "Tools" / "schemas", target / "Tools" / "schemas")
    profile_load_fixture.install_current_profile_load_inputs(target)
    profile = target / "profiles" / PROFILE_ID
    shutil.copytree(TEMPLATE, profile)
    for name in ORIENTATION:
        (profile / name).unlink()
    fill_profile(profile, PROFILE_ID)
    return target


def build_scaffolded_base(target):
    """Build the sole current-template scaffold -> Profile-load E2E input."""
    target = build_base(target)
    profile = target / "profiles" / PROFILE_ID
    shutil.rmtree(profile)
    shutil.copyfile(
        REPOSITORY / "profiles" / "template-files.yaml",
        target / "profiles" / "template-files.yaml",
    )
    shutil.copytree(TEMPLATE, target / "profiles" / "_template")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = scaffold_profile.main([
            str(target), "--profile-id=%s" % PROFILE_ID, "--apply",
        ])
    if code != 0:
        raise AssertionError(output.getvalue())
    fill_scaffolded_profile(profile, PROFILE_ID)
    evaluation = evaluation_of(target)
    return target, evaluation


def evaluation_of(root):
    root = Path(root)
    evaluation = check_profile.evaluate_profile_load(
        str(root / "profiles" / PROFILE_ID),
        root=str(root),
        receipt_identity={"selected_profile_manifest": MANIFEST},
    )
    if not evaluation.authorized:
        raise AssertionError(evaluation.output)
    return evaluation


def initial_plan(root, *, evaluation=None, **overrides):
    root = Path(root)
    if evaluation is None:
        evaluation = evaluation_of(root)
    plan = {
        "schema_version": 3,
        "plan_id": "PA-001",
        "branch": "initial-adoption",
        "upstream_revision_id_after": UPSTREAM_REVISION,
        "standards_status_after": "approved",
        "standards_effective_date_after": "2026-08-13",
        "selected_profile_manifest_after": MANIFEST,
        "upstream_revision_id_before": None,
        "selected_profile_manifest_before": None,
        "change_summary": "Initial adoption: selected %s; upstream https://example.test/corpus.git @ %s" % (MANIFEST, UPSTREAM_REVISION),
        "changed_predicates": [],
        "adoption_requirement": "none",
        "k00_03_sha256_before": kblib.sha256_file(root / GOVERNANCE),
        "standards_state_sha256_before": None,
        "upstream_source_ref": "https://example.test/corpus.git",
        "profile_snapshot_sha256_after": evaluation.profile_snapshot_sha256,
        "profile_contract_fingerprint_after": evaluation.profile_contract_fingerprint,
        "profile_load_inputs_sha256_after": evaluation.profile_load_inputs_sha256,
    }
    plan.update(overrides)
    return plan


def revision_plan(root, **overrides):
    root = Path(root)
    plan = initial_plan(root)
    plan.update(
        {
            "plan_id": "PA-002",
            "branch": "profile-revision",
            "upstream_revision_id_after": UPSTREAM_REVISION,
            "standards_effective_date_after": "2026-08-14",
            "upstream_revision_id_before": UPSTREAM_REVISION,
            "selected_profile_manifest_before": MANIFEST,
            "standards_state_sha256_before": kblib.sha256_file(root / standards_state.STATE_PATH)
            if (root / standards_state.STATE_PATH).exists()
            else "sha256:" + "0" * 64,
            "change_summary": "Profile revision inside %s: corpus-planning reason updated" % MANIFEST,
        }
    )
    plan.update(overrides)
    return plan


def write_plan(root, plan, relative=PLAN_RELATIVE):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
    return relative


def run_tool(root, *extra, plan=PLAN_RELATIVE, component_errors=(), component_reports=None):
    buffer = io.StringIO()
    component_report = mock.Mock(
        upstream_revision_id=UPSTREAM_REVISION, errors=tuple(component_errors)
    )
    if component_reports is None:
        component_patch = mock.patch.object(
            apply_profile_adoption.upstream_component_boundary,
            "evaluate",
            return_value=component_report,
        )
    else:
        component_patch = mock.patch.object(
            apply_profile_adoption.upstream_component_boundary,
            "evaluate",
            side_effect=list(component_reports),
        )
    with contextlib.redirect_stdout(buffer), component_patch:
        code = apply_profile_adoption.main(
            [
                str(root),
                "--plan",
                plan,
                "--upstream-root",
                str(REPOSITORY),
                "--upstream-ref",
                UPSTREAM_REF,
                *extra,
            ]
        )
    return code, buffer.getvalue()


def tree_state(root):
    state = {}
    for path in sorted(Path(root).rglob("*")):
        relative = path.relative_to(root).as_posix()
        if any(
            part.startswith(apply_profile_adoption.STAGING_PREFIX)
            for part in relative.split("/")
        ):
            continue
        if path.is_symlink():
            state[relative] = "symlink:%s" % path.readlink()
        elif path.is_dir():
            state[relative] = "dir"
        else:
            state[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return state


def governance_state(root):
    state, _view, errors = standards_state.snapshot(root)
    if errors:
        raise AssertionError(errors)
    return state


__all__ = [
    "GOVERNANCE",
    "MANIFEST",
    "PLAN_RELATIVE",
    "PROFILE_ID",
    "UPSTREAM_REF",
    "UPSTREAM_REVISION",
    "build_base",
    "build_scaffolded_base",
    "build_writer_checkpoint",
    "clone_writer_checkpoint",
    "evaluation_of",
    "governance_state",
    "initial_plan",
    "revision_plan",
    "run_tool",
    "run_writer_tool",
    "tree_state",
    "writer_evaluation_of",
    "writer_initial_plan",
    "writer_revision_plan",
    "writer_step",
    "write_plan",
]
