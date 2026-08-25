"""Shared ``profile-load`` admission for Profile-dependent tools.

This module is deliberately a thin consumer adapter.  ``check_profile`` owns
Profile authorization and ``profile_contract`` owns the typed dependency
graph.  Gate checkers and artifact producers call :func:`admit_profile` once,
then consume only the ``manifest-slot`` edges exposed by that authorized
evaluation instead of parsing ``profile.md`` again.
"""

from dataclasses import dataclass
from types import MappingProxyType
import os

import check_profile
import kblib
import standards_state


def _profile_load_inputs_sha256(root):
    """Project the core producer's canonical input binding for currency."""
    _snapshots, fingerprint = \
        check_profile.canonical_profile_load_inputs(root)
    return fingerprint


@dataclass(frozen=True)
class ProfileAdmission:
    """One authorized and snapshot-bound Profile view."""

    root: str
    evaluation: check_profile.ProfileLoadEvaluation
    slot_paths: object
    slot_bytes: object
    active_state: object
    active_state_repo_path: object
    active_state_sha256: object

    @property
    def contract(self):
        return self.evaluation.contract

    @property
    def manifest_repo_path(self):
        return self.contract.manifest_repo_path

    @property
    def profile_id(self):
        return self.evaluation.profile_id

    @property
    def profile_snapshot_sha256(self):
        return self.evaluation.profile_snapshot_sha256

    def slot_path(self, slot_name):
        """Return one Profile slot's canonical absolute path, or ``None``."""
        return self.slot_paths.get(slot_name)

    def slot_text(self, slot_name):
        """Return strict UTF-8 text from the admitted snapshot bytes."""
        value = self.slot_bytes.get(slot_name)
        if value is None:
            return None
        return value.decode("utf-8", errors="strict")


def _evaluation_errors(evaluation):
    errors = []
    for finding in evaluation.findings:
        errors.append(
            "profile-load %s [%s]: %s" % (
                finding.get("check", "failure"),
                finding.get("target", "<unknown>"),
                finding.get("details", "Profile admission failed"),
            )
        )
    if not errors:
        detail = next(
            (line.strip() for line in reversed(evaluation.output.splitlines())
             if line.strip()),
            "profile-load did not emit an authorized pass summary",
        )
        errors.append("profile-load exited %d: %s" % (
            evaluation.exit_code, detail))
    return errors


def admission_from_evaluation(root, evaluation, *, active_state=None,
                              active_state_repo_path=None,
                              active_state_sha256=None):
    """Adapt one already-authorized core evaluation for slot consumers."""
    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    if (not isinstance(evaluation, check_profile.ProfileLoadEvaluation) or
            not evaluation.authorized):
        return None, [
            "Profile admission requires one authorized profile-load "
            "evaluation"
        ]
    contract = evaluation.contract
    if os.path.realpath(contract.root) != root:
        return None, [
            "profile-load evaluation belongs to a different repository root"
        ]

    slots = {}
    edge_paths = {}
    for edge in contract.dependency_edges:
        if edge.kind != "manifest-slot":
            continue
        if edge.owner_id in slots:
            return None, [
                "profile-load returned duplicate typed slot edge for %r" %
                edge.owner_id
            ]
        slots[edge.owner_id] = os.path.join(
            contract.root, *edge.path.split("/"))
        edge_paths[edge.owner_id] = edge.path

    profile_snapshot = evaluation.profile_snapshot
    if (not isinstance(profile_snapshot, kblib.RepositoryTreeSnapshot) or
            profile_snapshot.sha256 != evaluation.profile_snapshot_sha256):
        return None, [
            "profile-load did not expose the immutable Profile snapshot "
            "that authorized its typed contract"
        ]
    slot_bytes = {}
    for slot_name, relative in edge_paths.items():
        try:
            slot_bytes[slot_name] = profile_snapshot.read_bytes(relative)
        except FileNotFoundError:
            return None, [
                "admitted typed slot %r is absent from the materialized "
                "Profile snapshot" % slot_name
            ]

    return ProfileAdmission(
        root=root,
        evaluation=evaluation,
        slot_paths=MappingProxyType(slots),
        slot_bytes=MappingProxyType(slot_bytes),
        active_state=MappingProxyType(dict(active_state or {})),
        active_state_repo_path=active_state_repo_path,
        active_state_sha256=active_state_sha256,
    ), []


def admit_profile(root, override=None, *,
                  active_state_path=standards_state.STATE_PATH,
                  require_approved=False):
    """Return ``(admission, errors)`` for one complete Profile evaluation.

    ``override`` is a Profile directory used by explicit validation runs.  If
    absent, the selected manifest identity comes from the active Standards
    state and must equal the manifest identity authorized by ``profile-load``.
    No manifest slot is parsed here or by callers.
    """
    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    errors = []
    active_state = {}
    active_state_repo_path = None
    active_state_sha256 = None
    expected_manifest = None

    if override:
        profile_dir = os.fspath(override)
        if not os.path.isabs(profile_dir):
            profile_dir = os.path.join(root, profile_dir)
        relative = os.path.relpath(profile_dir, root).replace(os.sep, "/")
        if (kblib.inherited_path_capability(override, "snapshot") is not None
                or kblib.retained_tree_is_bound(relative)):
            try:
                kblib.repository_tree_snapshot(root, relative)
            except (OSError, ValueError) as exc:
                return None, ["--profile cannot bind its admitted directory: "
                              "%s" % exc]
        elif not os.path.isdir(profile_dir):
            return None, [
                "--profile does not name an existing directory: %s" %
                override
            ]
    else:
        if active_state_path != standards_state.STATE_PATH:
            return None, [
                "active_state_path must be the canonical adopter state %s; "
                "Kernel Markdown is not instance state" %
                standards_state.STATE_PATH]
        active_state, state_view, parse_errors = standards_state.snapshot(root)
        errors.extend("%s: %s" % (active_state_path, error)
                      for error in parse_errors)
        if state_view is not None:
            active_state_repo_path = state_view["active_standards_path"]
            active_state_sha256 = state_view["active_standards_sha256"]
        if active_state is None:
            return None, errors
        expected_manifest = active_state.get("selected_profile_manifest")
        if (not isinstance(expected_manifest, str) or
                not expected_manifest.strip() or
                "{{" in expected_manifest):
            errors.append(
                "no instantiated selected_profile_manifest; pass --profile "
                "for an explicit validation run"
            )
        if (require_approved and
                active_state.get("status") != "approved"):
            errors.append(
                "active Standards Status must be approved; found %r" %
                active_state.get("status")
            )
        if errors:
            return None, errors
        # This is selection only.  The manifest bytes and every slot binding
        # are read exactly once by evaluate_profile_load below.
        profile_dir = os.path.join(root, os.path.dirname(expected_manifest))

    try:
        evaluation = check_profile.evaluate_profile_load(
            profile_dir, root=root, receipt_identity=None)
    except (OSError, UnicodeError, ValueError) as exc:
        return None, ["cannot evaluate profile-load: %s" % exc]
    if not evaluation.authorized:
        return None, _evaluation_errors(evaluation)

    if active_state_repo_path is not None:
        try:
            state_after = kblib.repository_file_snapshot(
                root, active_state_repo_path, singly_linked=True)
        except (OSError, ValueError) as exc:
            return None, [
                "active Standards state became unreadable during "
                "profile-load: %s" % exc
            ]
        if state_after.sha256 != active_state_sha256:
            return None, [
                "active Standards state changed while profile-load was "
                "evaluating; rerun against one stable selection"
            ]

    contract = evaluation.contract
    if (expected_manifest is not None and
            contract.manifest_repo_path != expected_manifest):
        return None, [
            "profile-load authorized manifest %r, but the active Standards "
            "state selected %r" %
            (contract.manifest_repo_path, expected_manifest)
        ]

    return admission_from_evaluation(
        root, evaluation, active_state=active_state,
        active_state_repo_path=active_state_repo_path,
        active_state_sha256=active_state_sha256)


def require_slot(admission, slot_name):
    """Return ``(path, error)`` for one typed first-hop slot edge."""
    path = admission.slot_path(slot_name) if admission is not None else None
    if path is None:
        return None, (
            "authorized profile-load contract carries no typed %r slot edge"
            % slot_name
        )
    return path, None


def currency_errors(admission):
    """Fail if Profile bytes changed after the shared admission snapshot."""
    if admission.active_state_repo_path is not None:
        try:
            state_snapshot = kblib.repository_file_snapshot(
                admission.root, admission.active_state_repo_path,
                singly_linked=True)
            state_text = state_snapshot.read_text()
        except (OSError, UnicodeError, ValueError) as exc:
            return ["cannot re-bind the active Standards state: %s" % exc]
        if state_snapshot.sha256 != admission.active_state_sha256:
            return [
                "active Standards state changed after profile-load admission; "
                "rerun against one stable Profile selection"
            ]
        state, parse_errors = standards_state.parse(state_text)
        if parse_errors:
            return [
                "active Standards state became invalid after profile-load "
                "admission: %s" % "; ".join(parse_errors)
            ]
        if state.get("selected_profile_manifest") != \
                admission.manifest_repo_path:
            return [
                "active Standards state no longer selects the Profile "
                "authorized by profile-load"
            ]
    try:
        current_inputs = _profile_load_inputs_sha256(admission.root)
    except (OSError, ValueError) as exc:
        return ["cannot re-bind canonical profile-load inputs: %s" % exc]
    if current_inputs != admission.evaluation.profile_load_inputs_sha256:
        return [
            "canonical profile-load inputs changed after admission; rerun "
            "against one stable rule interface"
        ]
    try:
        current = kblib.repository_tree_sha256(
            admission.root, admission.contract.profile_repo_dir)
    except (OSError, ValueError) as exc:
        return ["cannot re-bind the admitted Profile snapshot: %s" % exc]
    if current != admission.profile_snapshot_sha256:
        return [
            "selected Profile changed after profile-load admission; rerun "
            "against one stable Profile snapshot"
        ]
    return []
