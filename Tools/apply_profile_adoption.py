#!/usr/bin/env python3
"""Sole no-task-runtime R09 Profile-adoption transaction writer.

The restricted-YAML plan binds unchanged K00/03 rule bytes, the absent or
current canonical adopter Standards state, upstream identity, and one exact
passing `profile-load` evaluation. Initial adoption creates
`.cambium/governance/standards_state.yaml`; a pre-task revision advances it.
Both append `.cambium/receipts/standards-adoptions.jsonl`, then regenerate
vocabulary, page-contract, Card, and interface projections. K00/03 and Cards
never store the chronological adoption register.

Every touched byte is staged and recoverable. Any task runtime under
`.cambium/state/` redirects the caller to `adopt_standards.py`; governance and
receipt namespaces alone do not constitute a task runtime.

Dry-run is the default; `--apply` performs the transaction.  Exit codes
follow the writer convention: 0 = success (dry-run or applied), 1 = refusal
or failure.

Usage: python3 Tools/apply_profile_adoption.py <root> --plan <path>
       [--apply] [--json] [--receipts PATH]
"""

import errno
import json
import os
import re
import shutil
import subprocess
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_profile
import kblib
import standards_state

TOOL = "apply_profile_adoption"
TOOL_VERSION = "2.0.0"
# Consumed gate identity (K00/12 Stable Gate ID Registry); this tool registers
# no Gate ID of its own and `check_profile` remains the sole producer.
PROFILE_LOAD_GATE_ID = check_profile.GATE_ID

GOVERNANCE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
SIZE_REGISTER_PATH = (
    "kernel/K00 Standards Control/16 Leaf Module Size Register.md"
)
CARDS_DIR = "kernel/Cards"
VOCAB_ARTIFACT = "Tools/vocab.yaml"
PAGE_CONTRACT_ARTIFACT = "Tools/page_contract.yaml"
RUNTIME_NAMESPACE = ".cambium"
RECEIPT_RELATIVE = ".cambium/receipts/standards-adoptions.jsonl"

STAGING_PREFIX = ".r09-adoption-"
JOURNAL_NAME = "journal.json"
BACKUP_DIR = "backup"

SENTINEL = "TODO(profile-adoption)"
BRANCH_INITIAL = "initial-adoption"
BRANCH_REVISION = "profile-revision"
PLAN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
SHA_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")

PLAN_FIELDS = frozenset((
    "schema_version", "plan_id", "branch",
    "standards_version_after", "standards_status_after",
    "standards_effective_date_after", "selected_profile_manifest_after",
    "standards_version_before", "selected_profile_manifest_before",
    "change_summary", "changed_predicates", "adoption_requirement",
    "k00_03_sha256_before", "profile_snapshot_sha256_after",
    "profile_contract_fingerprint_after", "profile_load_inputs_sha256_after",
    "standards_state_sha256_before", "upstream_source_ref",
    "upstream_revision_id",
))

# The four producer steps, in README "Adopt Cambium" step-4 order.  Each entry
# is (step name, script under <root>/Tools, extra arguments builder).
COMPOSER_STEPS = (
    ("compose-vocab", "compose_vocab.py",
     lambda root, plan: []),
    ("compose-page-contract", "compose_page_contract.py",
     lambda root, plan: ["--root", root]),
    ("stamp-set-version", "stamp_cards.py",
     lambda root, plan: [root, "--set-version",
                         plan["standards_version_after"],
                         "--acknowledge-compiled"]),
    ("stamp-check", "stamp_cards.py",
     lambda root, plan: [root, "--check"]),
)


class AdoptionRefusal(Exception):
    """A deterministic validation refusal; nothing was written."""


class TransactionError(Exception):
    """A failure inside the apply transaction; triggers full restoration."""


# ---------------------------------------------------------------------------
# Plan loading and validation
# ---------------------------------------------------------------------------


def _string_field(plan, field):
    value = plan.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdoptionRefusal(
            "plan field %s must be a non-empty string; found %r"
            % (field, value))
    return value


def load_plan(root, plan_argument):
    """Resolve, parse, and shape-check one repository-contained plan."""
    if not isinstance(plan_argument, str) or not plan_argument.strip():
        raise AdoptionRefusal("--plan must name a plan file")
    if os.path.isabs(plan_argument):
        relative = os.path.relpath(
            os.path.realpath(plan_argument), root).replace(os.sep, "/")
        if relative.startswith(".."):
            raise AdoptionRefusal(
                "--plan must stay inside the repository root: %s"
                % plan_argument)
    else:
        relative = plan_argument.replace(os.sep, "/")
    try:
        path = kblib.repository_path(root, relative, must_exist=True,
                                     reject_symlink=True)
    except (OSError, ValueError) as exc:
        raise AdoptionRefusal("cannot resolve --plan %s: %s"
                              % (plan_argument, exc))
    if not relative.endswith(".yaml"):
        raise AdoptionRefusal("--plan must be a restricted-YAML .yaml file")
    parts = relative.split("/")
    if RUNTIME_NAMESPACE in parts:
        raise AdoptionRefusal(
            "--plan must not live under %s/" % RUNTIME_NAMESPACE)
    if parts[0] == "kernel":
        raise AdoptionRefusal(
            "--plan must not live under kernel/; the transaction writes "
            "there and the plan is its input, not its output")
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise AdoptionRefusal("adoption plan is not UTF-8: %s" % exc)
    if SENTINEL in text:
        raise AdoptionRefusal(
            "adoption plan still carries the unfilled sentinel %s; replace "
            "every sentinel before preparing the transaction" % SENTINEL)
    try:
        plan = kblib.parse_yaml_subset(text)
    except kblib.YamlSubsetError as exc:
        raise AdoptionRefusal("adoption plan is not restricted YAML: %s" % exc)
    if not isinstance(plan, dict):
        raise AdoptionRefusal("adoption plan top level must be a mapping")
    missing = sorted(PLAN_FIELDS - set(plan))
    extra = sorted(set(plan) - PLAN_FIELDS)
    if missing or extra:
        raise AdoptionRefusal(
            "adoption plan must contain exactly the closed field set; "
            "missing=%s extra=%s" % (missing, extra))
    validate_plan_values(plan, relative)
    return path, relative, raw, plan


def validate_plan_values(plan, plan_relative):
    if plan.get("schema_version") != 2 or \
            type(plan.get("schema_version")) is not int:
        raise AdoptionRefusal("plan schema_version must be integer 2")
    plan_id = _string_field(plan, "plan_id")
    if not PLAN_ID_RE.fullmatch(plan_id):
        raise AdoptionRefusal(
            "plan_id %r must fully match [A-Za-z0-9][A-Za-z0-9._-]*"
            % plan_id)
    branch = _string_field(plan, "branch")
    if branch not in (BRANCH_INITIAL, BRANCH_REVISION):
        raise AdoptionRefusal(
            "plan branch must be %s or %s; found %r"
            % (BRANCH_INITIAL, BRANCH_REVISION, branch))
    version_after = _string_field(plan, "standards_version_after")
    for field in ("standards_version_after", "standards_status_after",
                  "standards_effective_date_after",
                  "selected_profile_manifest_after", "change_summary"):
        value = _string_field(plan, field)
        if "|" in value or "\n" in value or "{{" in value:
            raise AdoptionRefusal(
                "plan field %s must be one instantiated scalar value "
                "value (no `|`, newline, or `{{`): %r" % (field, value))
    if plan["standards_status_after"] != "approved":
        raise AdoptionRefusal(
            "standards_status_after must be exactly `approved`; this writer "
            "records only an approved adopter state")
    if not DATE_RE.fullmatch(plan["standards_effective_date_after"]):
        raise AdoptionRefusal(
            "standards_effective_date_after must be an ISO date YYYY-MM-DD; "
            "found %r" % plan["standards_effective_date_after"])
    manifest = plan["selected_profile_manifest_after"]
    parts = manifest.split("/")
    if (len(parts) != 3 or parts[0] != "profiles" or
            parts[2] != "profile.md" or not parts[1] or
            parts[1].startswith("_")):
        raise AdoptionRefusal(
            "selected_profile_manifest_after must be exactly "
            "profiles/<profile-id>/profile.md naming a selectable profile; "
            "found %r" % manifest)
    if plan_relative.startswith("profiles/%s/" % parts[1]):
        raise AdoptionRefusal(
            "--plan must stay outside the candidate Profile directory so "
            "the plan cannot mutate the package whose snapshot it binds")
    if plan.get("changed_predicates") != []:
        raise AdoptionRefusal(
            "changed_predicates must be an empty list: no runtime exists, so "
            "no task state can consume a changed predicate; a revision with "
            "changed predicates against an existing runtime is an "
            "active-task adoption and belongs to Tools/adopt_standards.py")
    if plan.get("adoption_requirement") != "none":
        raise AdoptionRefusal(
            "adoption_requirement must be exactly `none` for the no-runtime "
            "writer; an active-task requirement belongs to "
            "Tools/adopt_standards.py")
    for field in ("k00_03_sha256_before", "profile_snapshot_sha256_after",
                  "profile_contract_fingerprint_after",
                  "profile_load_inputs_sha256_after"):
        value = _string_field(plan, field)
        if not SHA_RE.fullmatch(value):
            raise AdoptionRefusal(
                "plan field %s must be one canonical sha256:<hex> "
                "fingerprint; found %r" % (field, value))
    source = plan.get("upstream_source_ref")
    revision = plan.get("upstream_revision_id")
    if (source is None) != (revision is None):
        raise AdoptionRefusal(
            "upstream_source_ref and upstream_revision_id must both be null "
            "or both be non-empty")
    if source is not None:
        _string_field(plan, "upstream_source_ref")
        _string_field(plan, "upstream_revision_id")
    before_version = plan.get("standards_version_before")
    before_manifest = plan.get("selected_profile_manifest_before")
    if branch == BRANCH_INITIAL:
        if before_version is not None or before_manifest is not None:
            raise AdoptionRefusal(
                "initial-adoption declares the absent before-identity with "
                "an explicit null pair; found standards_version_before=%r "
                "selected_profile_manifest_before=%r"
                % (before_version, before_manifest))
        if plan.get("standards_state_sha256_before") is not None:
            raise AdoptionRefusal(
                "initial-adoption requires standards_state_sha256_before: null")
    else:
        for field in ("standards_version_before",
                      "selected_profile_manifest_before"):
            _string_field(plan, field)
        if before_version == version_after:
            raise AdoptionRefusal(
                "profile-revision must bump standards_version: before and "
                "after are both %r (changing the selected profile "
                "manifest or its content always requires a bump)" %
                version_after)
        state_sha = _string_field(plan, "standards_state_sha256_before")
        if not SHA_RE.fullmatch(state_sha):
            raise AdoptionRefusal(
                "standards_state_sha256_before must be a SHA-256")


# ---------------------------------------------------------------------------
# Root and state validation
# ---------------------------------------------------------------------------


def find_runtime_namespace(root):
    """Return the first task-runtime state namespace, or None.

    Governance state and adoption receipts may exist before a task runtime;
    their `.cambium/` parent is not itself evidence that a task exists.
    """
    for current, directories, files in os.walk(root):
        directories[:] = sorted(
            name for name in directories
            if name != ".git" and not name.startswith(STAGING_PREFIX))
        if (os.path.basename(current) == "state" and
                os.path.basename(os.path.dirname(current)) == RUNTIME_NAMESPACE):
            return os.path.relpath(
                os.path.dirname(current),
                root).replace(os.sep, "/")
    return None


def require_tools(root):
    for _step, script, _args in COMPOSER_STEPS:
        path = os.path.join(root, "Tools", script)
        if not os.path.isfile(path):
            raise AdoptionRefusal(
                "root does not carry the Tools distribution the transaction "
                "drives: missing Tools/%s" % script)


def read_governance(root):
    path = kblib.repository_path(root, GOVERNANCE_PATH, must_exist=True,
                                 reject_symlink=True)
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise AdoptionRefusal("%s is not UTF-8: %s" % (GOVERNANCE_PATH, exc))
    return path, raw, text


def read_current_state(root):
    """Return current adopter state and bytes, or the absent initial state."""
    absolute = os.path.join(root, *standards_state.STATE_PATH.split("/"))
    if not os.path.lexists(absolute):
        return None, None
    state, view, errors = standards_state.snapshot(root)
    if errors:
        raise AdoptionRefusal("current adopter Standards state is invalid: %s" %
                              "; ".join(errors))
    with open(absolute, "rb") as handle:
        raw = handle.read()
    if kblib.sha256_bytes(raw) != view["active_standards_sha256"]:
        raise AdoptionRefusal("current adopter Standards state changed while read")
    return state, raw


def check_branch_state(plan, state):
    """The plan's branch must match absent/present adopter state."""
    if plan["branch"] == BRANCH_INITIAL:
        if state is None:
            return
        raise AdoptionRefusal(
            "branch initial-adoption requires absent adopter Standards state; "
            "a current state already exists")
    if state is None:
        raise AdoptionRefusal(
            "branch profile-revision requires an existing adopter Standards "
            "state; use initial-adoption first")
    for plan_field, state_field in (
            ("standards_version_before", "standards_version"),
            ("selected_profile_manifest_before",
             "selected_profile_manifest")):
        if plan[plan_field] != state.get(state_field):
            raise AdoptionRefusal(
                "plan %s=%r does not match current adopter state %s=%r"
                % (plan_field, plan[plan_field], state_field,
                   state.get(state_field)))


def evaluate_candidate(root, plan):
    """One canonical `profile-load` evaluation of the exact candidate.

    The admission judgment is `check_profile.evaluate_profile_load` and
    nothing else: no partial check is reimplemented here, and a candidate
    the canonical producer does not authorize is refused verbatim.
    """
    manifest = plan["selected_profile_manifest_after"]
    profile_dir = os.path.join(root, *os.path.dirname(manifest).split("/"))
    evaluation = check_profile.evaluate_profile_load(
        profile_dir, root=root,
        receipt_identity={"selected_profile_manifest": manifest})
    if not evaluation.authorized:
        findings = "; ".join(
            "%s %s" % (finding.get("check"), finding.get("target"))
            for finding in evaluation.findings[:8]) or "no findings emitted"
        raise AdoptionRefusal(
            "candidate Profile failed the canonical %s Gate "
            "(check_profile %s, exit %d): %s"
            % (PROFILE_LOAD_GATE_ID, check_profile.TOOL_VERSION,
               evaluation.exit_code, findings))
    for plan_field, observed in (
            ("profile_snapshot_sha256_after",
             evaluation.profile_snapshot_sha256),
            ("profile_contract_fingerprint_after",
             evaluation.profile_contract_fingerprint),
            ("profile_load_inputs_sha256_after",
             evaluation.profile_load_inputs_sha256)):
        if plan[plan_field] != observed:
            raise AdoptionRefusal(
                "candidate Profile drifted after plan preparation: plan "
                "%s=%s but the current canonical evaluation yields %s; "
                "re-prepare the plan against the exact bytes to adopt"
                % (plan_field, plan[plan_field], observed))
    summary = dict(evaluation.summary_receipt)
    if summary.get("selected_profile_manifest") != manifest:
        raise AdoptionRefusal(
            "canonical evaluation bound manifest %r, not the plan's %r"
            % (summary.get("selected_profile_manifest"), manifest))
    return evaluation


# ---------------------------------------------------------------------------
# After-image construction
# ---------------------------------------------------------------------------



def build_commit_stub(plan, transaction_id):
    identity = {
        "standards_version": plan["standards_version_after"],
        "selected_profile_manifest": plan["selected_profile_manifest_after"],
    }
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "profile_adoption", plan["plan_id"], "pass",
        "R09 %s committed: %s -> %s; %s" % (
            plan["branch"],
            plan["standards_version_before"] or "(uninstantiated)",
            plan["standards_version_after"],
            plan["selected_profile_manifest_after"]),
        1, identity=identity)
    receipt["transaction_id"] = transaction_id
    return receipt


# ---------------------------------------------------------------------------
# Staging, journal, restoration
# ---------------------------------------------------------------------------


def staging_directory(root, plan_id):
    return os.path.join(root, STAGING_PREFIX + plan_id)


def existing_stagings(root):
    return sorted(
        name for name in os.listdir(root)
        if name.startswith(STAGING_PREFIX) and
        os.path.isdir(os.path.join(root, name)))


def read_journal(root, staging_name):
    path = os.path.join(root, staging_name, JOURNAL_NAME)
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise AdoptionRefusal(
            "interrupted adoption staging %s has no readable journal (%s); "
            "reconcile it manually before any new adoption"
            % (staging_name, exc))


def write_journal(staging, journal):
    kblib.atomic_write_text(
        os.path.join(staging, JOURNAL_NAME),
        json.dumps(journal, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        validator=json.loads)


def touched_paths(root):
    """Every repo-relative path the transaction may write, sorted."""
    paths = [standards_state.STATE_PATH, RECEIPT_RELATIVE,
             VOCAB_ARTIFACT, PAGE_CONTRACT_ARTIFACT]
    cards_dir = os.path.join(root, *CARDS_DIR.split("/"))
    for current, directories, files in os.walk(cards_dir):
        directories.sort()
        for name in sorted(files):
            relative = os.path.relpath(
                os.path.join(current, name), root).replace(os.sep, "/")
            paths.append(relative)
    return sorted(set(paths))


def prepare_staging(root, plan_relative, plan_sha, plan):
    """Create the staging tree with backups and the initial journal."""
    staging = staging_directory(root, plan["plan_id"])
    os.mkdir(staging)
    backups = {}
    for relative in touched_paths(root):
        absolute = os.path.join(root, *relative.split("/"))
        if os.path.isfile(absolute):
            with open(absolute, "rb") as handle:
                data = handle.read()
            backup = os.path.join(staging, BACKUP_DIR, *relative.split("/"))
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            with open(backup, "xb") as handle:
                handle.write(data)
            backups[relative] = {"existed": True,
                                 "sha256": kblib.sha256_bytes(data)}
        else:
            backups[relative] = {"existed": False, "sha256": None}
    journal = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "plan_id": plan["plan_id"],
        "plan_path": plan_relative,
        "plan_sha256": plan_sha,
        "branch": plan["branch"],
        "status": "prepared",
        "steps": [],
        "backups": backups,
        "restore_verified": None,
        "receipts_path": None,
        "receipts": None,
    }
    write_journal(staging, journal)
    return staging, journal


def _atomic_write_bytes(path, data):
    """Byte-exact atomic replacement (restoration must not re-encode)."""
    parent = os.path.dirname(os.path.abspath(path))
    temporary = os.path.join(
        parent, ".r09-restore-%s-%d" % (os.path.basename(path), os.getpid()))
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        kblib.durable_replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def restore_from_staging(root, staging, journal):
    """Put back the pre-transaction bytes of every touched path.

    Returns a list of restoration failures; empty means the restoration was
    byte-verified: every backed-up file matches its recorded fingerprint,
    every file that did not exist is absent again, and no file the
    transaction may have created under kernel/Cards survives.
    """
    failures = []
    backups = journal.get("backups") or {}
    for relative in sorted(backups):
        record = backups[relative]
        absolute = os.path.join(root, *relative.split("/"))
        try:
            if record.get("existed"):
                backup = os.path.join(
                    staging, BACKUP_DIR, *relative.split("/"))
                with open(backup, "rb") as handle:
                    data = handle.read()
                _atomic_write_bytes(absolute, data)
            elif os.path.lexists(absolute):
                os.unlink(absolute)
        except (OSError, UnicodeError) as exc:
            failures.append("%s: %s" % (relative, exc))
    # Initial adoption may have created the governance/receipt directories
    # before a later producer failed. Remove only directories that are now
    # empty, so rollback restores the pre-adoption namespace shape without
    # touching any pre-existing history or state.
    for relative in (
            ".cambium/governance", ".cambium/receipts", ".cambium"):
        absolute = os.path.join(root, *relative.split("/"))
        if os.path.isdir(absolute) and not os.path.islink(absolute):
            try:
                os.rmdir(absolute)
            except OSError as exc:
                if exc.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                    failures.append("%s cleanup: %s" % (relative, exc))
    cards_dir = os.path.join(root, *CARDS_DIR.split("/"))
    if os.path.isdir(cards_dir):
        for current, directories, files in os.walk(cards_dir):
            directories.sort()
            for name in sorted(files):
                absolute = os.path.join(current, name)
                relative = os.path.relpath(
                    absolute, root).replace(os.sep, "/")
                if relative not in backups:
                    try:
                        os.unlink(absolute)
                    except OSError as exc:
                        failures.append(
                            "%s: cannot remove transaction-created file: %s"
                            % (relative, exc))
    for relative in sorted(backups):
        record = backups[relative]
        absolute = os.path.join(root, *relative.split("/"))
        if record.get("existed"):
            try:
                if kblib.sha256_file(absolute) != record.get("sha256"):
                    failures.append(
                        "%s bytes differ after restoration" % relative)
            except OSError as exc:
                failures.append("%s verification: %s" % (relative, exc))
        elif os.path.lexists(absolute):
            failures.append(
                "%s still exists after restoration but was absent before"
                % relative)
    for relative in (".cambium/governance", ".cambium/receipts", ".cambium"):
        absolute = os.path.join(root, *relative.split("/"))
        try:
            os.rmdir(absolute)
        except OSError:
            pass
    return failures


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------


def _run_step(command, cwd):
    """Run one producer step; kept module-level so tests can inject failure."""
    completed = subprocess.run(
        command, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False)
    return completed.returncode, completed.stdout


def _journal_step(staging, journal, step, status, detail=""):
    journal["steps"].append(
        {"step": step, "status": status, "detail": detail})
    write_journal(staging, journal)


def build_receipts(prepared):
    """The two commit records: canonical Gate receipt plus commit receipt."""
    plan = prepared["plan"]
    summary = dict(prepared["evaluation"].summary_receipt)
    identity = {
        "standards_version": plan["standards_version_after"],
        "selected_profile_manifest":
            plan["selected_profile_manifest_after"],
    }
    commit = dict(prepared["commit_stub"])
    commit.update({
        "transaction_id": prepared["transaction_id"],
        "branch": plan["branch"],
        "plan_path": prepared["plan_relative"],
        "plan_sha256": prepared["plan_sha"],
        "standards_version_before": plan["standards_version_before"],
        "standards_version_after": plan["standards_version_after"],
        "standards_status_after": plan["standards_status_after"],
        "standards_effective_date_after":
            plan["standards_effective_date_after"],
        "selected_profile_manifest_before":
            plan["selected_profile_manifest_before"],
        "selected_profile_manifest_after":
            plan["selected_profile_manifest_after"],
        "k00_03_sha256_before": plan["k00_03_sha256_before"],
        "k00_03_sha256_after": plan["k00_03_sha256_before"],
        "standards_state_sha256_before":
            plan["standards_state_sha256_before"],
        "standards_state_sha256_after": prepared["state_after_sha"],
        "upstream_source_ref": plan["upstream_source_ref"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "profile_snapshot_sha256_after":
            plan["profile_snapshot_sha256_after"],
        "profile_contract_fingerprint_after":
            plan["profile_contract_fingerprint_after"],
        "profile_load_inputs_sha256_after":
            plan["profile_load_inputs_sha256_after"],
        "change_summary": plan["change_summary"],
        "changed_predicate_ids": [],
        "adoption_requirement": "none",
        # Consumed gate identity: the exact registered producer's receipt,
        # appended alongside this record; no new Gate ID is registered.
        "profile_load_gate_id": PROFILE_LOAD_GATE_ID,
        "profile_load_receipt_id": summary.get("receipt_id"),
    })
    return [summary, commit]


def commit_transaction(prepared):
    """Prepare, write, compose, verify, and publish -- or restore fully."""
    root = prepared["root"]
    plan = prepared["plan"]
    staging = staging_directory(root, plan["plan_id"])
    try:
        staging, journal = prepare_staging(
            root, prepared["plan_relative"], prepared["plan_sha"], plan)
    except Exception as exc:
        if os.path.isdir(staging):
            shutil.rmtree(staging)
        raise TransactionError(
            "transaction preparation failed before any repository write: %s"
            % exc)
    try:
        # Locked re-verification: the staging directory is the exclusive
        # writer token; re-check the exact before bytes behind it.
        live_sha = kblib.sha256_file(
            os.path.join(root, *GOVERNANCE_PATH.split("/")))
        if live_sha != plan["k00_03_sha256_before"]:
            raise TransactionError(
                "%s changed between validation and staging" % GOVERNANCE_PATH)
        live_state_path = os.path.join(
            root, *standards_state.STATE_PATH.split("/"))
        if plan["standards_state_sha256_before"] is None:
            if os.path.lexists(live_state_path):
                raise TransactionError(
                    "%s appeared between validation and staging" %
                    standards_state.STATE_PATH)
        elif (not os.path.isfile(live_state_path) or
              kblib.sha256_file(live_state_path) !=
              plan["standards_state_sha256_before"]):
            raise TransactionError(
                "%s changed between validation and staging" %
                standards_state.STATE_PATH)
        journal["status"] = "writing"
        write_journal(staging, journal)
        state_path = os.path.join(root, *standards_state.STATE_PATH.split("/"))
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        kblib.atomic_write_text(
            state_path, prepared["state_after_text"],
            validator=kblib.parse_yaml_subset)
        _journal_step(staging, journal, "write-standards-state", "done")
        for step, script, argument_builder in COMPOSER_STEPS:
            # -B: a producer step must not drop bytecode caches into the
            # adopter repository; after an abort the tree is byte-identical.
            command = [sys.executable, "-B",
                       os.path.join(root, "Tools", script)]
            command.extend(argument_builder(root, plan))
            code, output = _run_step(command, root)
            if code != 0:
                _journal_step(staging, journal, step, "failed",
                              output[-2000:])
                raise TransactionError(
                    "producer step %s (Tools/%s) exited %d:\n%s"
                    % (step, script, code, output.strip()[-2000:]))
            _journal_step(staging, journal, step, "done")
        # The producers ran against external bytes; re-run the canonical
        # profile-load producer so a candidate mutated during the
        # transaction cannot inherit the earlier pass.
        try:
            prepared["evaluation"] = evaluate_candidate(root, plan)
        except AdoptionRefusal as exc:
            raise TransactionError(str(exc))
        _journal_step(staging, journal, "reverify-profile-load", "done")
        receipts = build_receipts(prepared)
        journal["status"] = "committing"
        journal["receipts_path"] = prepared["receipts_path"]
        journal["receipts"] = receipts
        write_journal(staging, journal)
        os.makedirs(os.path.dirname(prepared["receipts_path"]), exist_ok=True)
        kblib.write_receipts(prepared["receipts_path"], receipts)
        journal["status"] = "committed"
        write_journal(staging, journal)
    except Exception as exc:
        failures = restore_from_staging(root, staging, journal)
        journal["restore_verified"] = not failures
        journal["failure"] = str(exc)
        journal["status"] = "aborted" if not failures else "restore-failed"
        write_journal(staging, journal)
        if failures:
            raise TransactionError(
                "adoption failed (%s) AND restoration is incomplete: %s; "
                "the staging journal %s/%s records the interrupted state -- "
                "reconcile manually before any new adoption"
                % (exc, "; ".join(failures),
                   os.path.basename(staging), JOURNAL_NAME))
        raise TransactionError(
            "adoption aborted: %s; every touched file was restored to its "
            "pre-transaction bytes (byte-verified) and the journal is "
            "marked aborted" % exc)
    shutil.rmtree(staging)
    return receipts


def recover_staging(root, staging_name, plan_sha, apply_mode, printer):
    """Handle one pre-existing staging directory for the same plan bytes.

    Returns "completed" when the interrupted transaction was already
    committed (the caller exits 0), or "retry" when the repository has been
    restored and a fresh transaction may proceed.
    """
    staging = os.path.join(root, staging_name)
    journal = read_journal(root, staging_name)
    if journal.get("plan_sha256") != plan_sha:
        raise AdoptionRefusal(
            "an interrupted adoption transaction exists at %s for different "
            "plan bytes (journal binds %s); complete or reconcile it with "
            "its own plan before starting another adoption"
            % (staging_name, journal.get("plan_sha256")))
    if not apply_mode:
        raise AdoptionRefusal(
            "an interrupted adoption transaction exists at %s (status %s); "
            "re-run with --apply and the same plan to recover it"
            % (staging_name, journal.get("status")))
    status = journal.get("status")
    if status == "restore-failed" or journal.get("restore_verified") is False:
        raise AdoptionRefusal(
            "the interrupted transaction at %s could not verify its "
            "restoration; reconcile it manually from %s/%s and the backups "
            "before any new adoption"
            % (staging_name, staging_name, BACKUP_DIR))
    if status == "committed":
        shutil.rmtree(staging)
        printer("recovered %s: the transaction had already committed; "
                "staging removed" % staging_name)
        return "completed"
    if status == "committing":
        receipts = journal.get("receipts") or []
        receipts_path = journal.get("receipts_path")
        if not receipts or not receipts_path:
            raise AdoptionRefusal(
                "the interrupted transaction at %s reached committing "
                "without recorded receipts; reconcile manually"
                % staging_name)
        try:
            with open(receipts_path, encoding="utf-8") as handle:
                present = handle.read()
        except OSError:
            present = ""
        missing = [receipt for receipt in receipts
                   if receipt.get("receipt_id") not in present]
        if missing:
            kblib.write_receipts(receipts_path, missing)
        shutil.rmtree(staging)
        printer("recovered %s: state was fully written; %d missing receipt "
                "record(s) appended; staging removed"
                % (staging_name, len(missing)))
        return "completed"
    # prepared/writing (interrupted mid-flight) or aborted (already
    # restored): put the before bytes back, verify, and allow a fresh
    # attempt with the identical plan.
    failures = restore_from_staging(root, staging, journal)
    if failures:
        journal["restore_verified"] = False
        journal["status"] = "restore-failed"
        write_journal(staging, journal)
        raise AdoptionRefusal(
            "recovery of %s could not verify its restoration: %s; "
            "reconcile manually before any new adoption"
            % (staging_name, "; ".join(failures)))
    shutil.rmtree(staging)
    printer("recovered %s: pre-transaction bytes restored (byte-verified); "
            "retrying the same plan" % staging_name)
    return "retry"


# ---------------------------------------------------------------------------
# Preparation shared by dry-run and apply
# ---------------------------------------------------------------------------


def resolve_receipts_path(root, plan_path, plan, receipts_argument):
    """Resolve the one canonical Standards-adoption history stream."""
    if receipts_argument:
        relative = os.fspath(receipts_argument).replace(os.sep, "/")
    else:
        relative = RECEIPT_RELATIVE
    if relative != RECEIPT_RELATIVE:
        raise AdoptionRefusal(
            "--receipts must be the canonical history stream %s" %
            RECEIPT_RELATIVE)
    try:
        return kblib.managed_repository_path(
            root, relative, ".cambium/receipts", suffixes=(".jsonl",),
            must_exist=False)
    except ValueError as exc:
        raise AdoptionRefusal("invalid --receipts destination: %s" % exc)


def prepare(root, plan_argument, receipts_argument):
    plan_path, plan_relative, plan_raw, plan = load_plan(root, plan_argument)
    plan_sha = kblib.sha256_bytes(plan_raw)
    receipts_path = resolve_receipts_path(root, plan_path, plan,
                                          receipts_argument)
    runtime = find_runtime_namespace(root)
    if runtime is not None:
        raise AdoptionRefusal(
            "a Cambium runtime exists at %s/; this writer serves only the "
            "no-runtime R09 branches and never edits runtime state. Use the "
            "active-task flow: prepare a K12/10 adoption plan under "
            ".cambium/deltas/standards-adoptions/ and apply it with "
            "Tools/adopt_standards.py" % runtime)
    require_tools(root)
    governance_path, governance_raw, _governance_text = read_governance(root)
    state, state_raw = read_current_state(root)
    check_branch_state(plan, state)
    live_sha = kblib.sha256_bytes(governance_raw)
    if live_sha != plan["k00_03_sha256_before"]:
        raise AdoptionRefusal(
            "current %s bytes (%s) do not match the plan's "
            "k00_03_sha256_before (%s); the governance file moved after the "
            "plan was prepared -- re-prepare the plan against the current "
            "bytes" % (GOVERNANCE_PATH, live_sha,
                       plan["k00_03_sha256_before"]))
    observed_state_sha = (
        kblib.sha256_bytes(state_raw) if state_raw is not None else None)
    if observed_state_sha != plan["standards_state_sha256_before"]:
        raise AdoptionRefusal(
            "current %s fingerprint %r does not match "
            "standards_state_sha256_before %r" % (
                standards_state.STATE_PATH, observed_state_sha,
                plan["standards_state_sha256_before"]))
    evaluation = evaluate_candidate(root, plan)
    transaction_id = "txn-%s-%s" % (plan["plan_id"], uuid.uuid4().hex)
    commit_stub = build_commit_stub(plan, transaction_id)
    state_after = standards_state.next_state(
        state,
        standards_version=plan["standards_version_after"],
        effective_date=plan["standards_effective_date_after"],
        selected_profile_manifest=plan["selected_profile_manifest_after"],
        latest_adoption_receipt=commit_stub["receipt_id"],
        upstream_source_ref=plan["upstream_source_ref"],
        upstream_revision_id=plan["upstream_revision_id"],
    )
    state_after_text = standards_state.canonical_text(state_after)
    return {
        "root": root,
        "plan": plan,
        "plan_path": plan_path,
        "plan_relative": plan_relative,
        "plan_sha": plan_sha,
        "receipts_path": receipts_path,
        "state": state,
        "state_after": state_after,
        "state_after_text": state_after_text,
        "state_after_sha": kblib.sha256_bytes(state_after_text),
        "commit_stub": commit_stub,
        "evaluation": evaluation,
        "transaction_id": transaction_id,
    }


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Apply one no-runtime R09 Profile adoption (initial "
                    "adoption or pre-runtime profile revision) from a "
                    "restricted-YAML plan")
    parser.add_argument("root", help="repository root (no task runtime may "
                                     "exist; governance state may exist)")
    parser.add_argument("--plan", required=True,
                        help="root-relative adoption plan "
                             "(schemas/profile_adoption_plan.template.yaml)")
    parser.add_argument("--apply", action="store_true",
                        help="perform the transaction; without it the "
                             "complete planned change is reported and "
                             "nothing is written")
    parser.add_argument("--json", action="store_true",
                        help="emit the plan/result as one JSON document")
    parser.add_argument("--receipts", default=None,
                        help="must be the canonical Standards history stream "
                             ".cambium/receipts/standards-adoptions.jsonl")
    args = parser.parse_args(argv)

    report = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "apply": bool(args.apply),
        "result": None,
        "error": None,
    }
    lines = []

    def say(message):
        if args.json:
            # Scheme A: JSON owns stdout, the human summary goes to stderr as
            # it is produced. It is not buffered into the payload -- five of
            # the six JSON exits keep the two apart, and this was the one that
            # did not.
            print(message, file=sys.stderr)
        else:
            print(message)

    def emit(exit_code):
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True,
                             indent=2))
        return exit_code

    def refuse(message):
        report["result"] = "refused"
        report["error"] = message
        if not args.json:
            print("[FAIL] %s; nothing was written" % message)
        return emit(1)

    root = os.path.realpath(os.path.abspath(args.root))
    if not os.path.isdir(root):
        return refuse("root is not an existing directory: %s" % args.root)

    # Interrupted-transaction handling comes before every state judgment:
    # a half-written adopter state must be recovered from its journal, never
    # re-diagnosed as a branch mismatch.
    try:
        plan_path, _rel, plan_raw, plan = load_plan(root, args.plan)
        plan_sha = kblib.sha256_bytes(plan_raw)
        for staging_name in existing_stagings(root):
            outcome = recover_staging(
                root, staging_name, plan_sha, args.apply, say)
            if outcome == "completed":
                report["result"] = "already-committed"
                say("[PASS] adoption for this exact plan was already "
                    "committed; recovery completed the cleanup")
                return emit(0)
        prepared = prepare(root, args.plan, args.receipts)
    except AdoptionRefusal as exc:
        return refuse(str(exc))
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        return refuse(str(exc))

    plan = prepared["plan"]
    report.update({
        "plan_id": plan["plan_id"],
        "branch": plan["branch"],
        "plan_path": prepared["plan_relative"],
        "plan_sha256": prepared["plan_sha"],
        "standards_version_before": plan["standards_version_before"],
        "standards_version_after": plan["standards_version_after"],
        "selected_profile_manifest_before":
            plan["selected_profile_manifest_before"],
        "selected_profile_manifest_after":
            plan["selected_profile_manifest_after"],
        "k00_03_sha256_before": plan["k00_03_sha256_before"],
        "k00_03_sha256_after": plan["k00_03_sha256_before"],
        "standards_state_sha256_before":
            plan["standards_state_sha256_before"],
        "standards_state_sha256_after": prepared["state_after_sha"],
        "profile_snapshot_sha256_after":
            plan["profile_snapshot_sha256_after"],
        "profile_contract_fingerprint_after":
            plan["profile_contract_fingerprint_after"],
        "profile_load_inputs_sha256_after":
            plan["profile_load_inputs_sha256_after"],
        "history_record": "append-only receipt",
        "receipts_path": os.path.relpath(
            prepared["receipts_path"], root).replace(os.sep, "/"),
    })

    say("R09 %s %s: %s -> %s" % (
        plan["branch"], plan["plan_id"],
        plan["standards_version_before"] or "(uninstantiated)",
        plan["standards_version_after"]))
    say("  selected_profile_manifest: %s -> %s" % (
        plan["selected_profile_manifest_before"] or "(uninstantiated)",
        plan["selected_profile_manifest_after"]))
    say("  normative Kernel binding %s: %s (unchanged)" % (
        GOVERNANCE_PATH, plan["k00_03_sha256_before"]))
    say("  %s: %r -> %s" % (
        standards_state.STATE_PATH,
        plan["standards_state_sha256_before"],
        prepared["state_after_sha"]))
    say("  history: append one transaction record; Kernel remains rules-only")
    say("  candidate profile-load: snapshot=%s contract=%s inputs=%s" % (
        plan["profile_snapshot_sha256_after"],
        plan["profile_contract_fingerprint_after"],
        plan["profile_load_inputs_sha256_after"]))
    say("  producer steps: %s" % ", ".join(
        step for step, _script, _args in COMPOSER_STEPS))
    say("  receipts: %s" % report["receipts_path"])

    if not args.apply:
        report["result"] = "dry-run"
        say("dry run; add --apply with unchanged plan/state bytes")
        return emit(0)

    try:
        receipts = commit_transaction(prepared)
    except (TransactionError, OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        report["result"] = "aborted"
        report["error"] = str(exc)
        if not args.json:
            print("[FAIL] %s" % exc)
        return emit(1)
    report["result"] = "committed"
    report["receipt_ids"] = [receipt["receipt_id"] for receipt in receipts]
    say("[PASS] R09 %s %s committed; transaction_id=%s; %d receipt(s) "
        "appended to %s" % (
            plan["branch"], plan["plan_id"], prepared["transaction_id"],
            len(receipts), report["receipts_path"]))
    return emit(0)


if __name__ == "__main__":
    sys.exit(main())
