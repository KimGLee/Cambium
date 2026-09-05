"""Shared ``profile-load`` admission for Profile-dependent tools.

This module is deliberately a thin consumer adapter.  ``check_profile`` owns
Profile authorization and ``profile_contract`` owns the typed dependency
graph.  Gate checkers and artifact producers call :func:`admit_profile` once,
then consume the immutable slot and record values from that evaluation.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
import os

import Tools.governance.profile.check_profile as check_profile
import Tools.governance.profile.profile_contract as profile_contract
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.platform.common.kblib as kblib
import Tools.governance.standards.standards_state as standards_state


PROFILE_SCOPE_SLOT = profile_contract.PROFILE_SCOPE_SLOT


@dataclass(frozen=True)
class ProfileAdmission:
    """One authorized and snapshot-bound Profile view."""

    root: str
    evaluation: check_profile.ProfileLoadEvaluation
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

    @property
    def source_path(self):
        """The manifest source for diagnostics, not a slot read interface."""
        return os.path.join(self.root, *self.manifest_repo_path.split("/"))

    def slot(self, slot_name):
        """Return one immutable slot by its registered ID or display name."""
        return self.contract.slot(slot_name)

    def slot_document(self, slot_name):
        """Return a defensive plain-data projection for domain validators."""
        return self.contract.slot_document(slot_name)

    def value(self, slot_name, *keys):
        """Read a named field from the admitted typed slot without IO."""
        value = self.slot(slot_name)
        for key in keys:
            if not isinstance(value, Mapping) or key not in value:
                raise KeyError((slot_name,) + keys)
            value = value[key]
        return value

    def record(self, slot_name, collection, record_id, *, id_field="id"):
        """Read one record by stable identity from an explicit collection.

        Collection names may be a string or a tuple of field names. Missing
        or ambiguous IDs fail instead of falling back to positional lookup.
        """
        keys = (collection,) if isinstance(collection, str) else tuple(collection)
        records = self.value(slot_name, *keys)
        if isinstance(records, Mapping):
            if record_id not in records:
                raise KeyError(record_id)
            return records[record_id]
        if not isinstance(records, tuple):
            raise TypeError("record collection must be a typed mapping or tuple")
        matches = tuple(item for item in records
                        if isinstance(item, Mapping) and
                        item.get(id_field) == record_id)
        if not matches:
            raise KeyError(record_id)
        if len(matches) != 1:
            raise ValueError("record identity %r is ambiguous" % record_id)
        return matches[0]


def scope_directories(admission):
    """Project corpus directories from the admitted structured scope slot."""
    scope, error = require_slot(admission, PROFILE_SCOPE_SLOT)
    if error:
        return [], [error]
    layers = scope["logical_architecture"]
    directories = sorted({
        directory for layer in layers for directory in layer["directories"]
    })
    if not directories:
        return [], ["Profile Scope has no Logical Architecture directories"]
    return directories, []


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

    profile_snapshot = evaluation.profile_snapshot
    if (not isinstance(profile_snapshot, kblib.RepositoryTreeSnapshot) or
            profile_snapshot.sha256 != evaluation.profile_snapshot_sha256):
        return None, [
            "profile-load did not expose the immutable Profile snapshot "
            "that authorized its typed contract"
        ]
    return ProfileAdmission(
        root=root,
        evaluation=evaluation,
        active_state=MappingProxyType(dict(active_state or {})),
        active_state_repo_path=active_state_repo_path,
        active_state_sha256=active_state_sha256,
    ), []


def contract_from_admitted_view(root, view):
    """Read the exact model paired with an existing in-process Gate result.

    This checks identity only: it does no IO, repeats no Gate, and never
    turns compilation validity into approval. Transaction owners separately
    rebind currency at their established before/after boundaries.
    """
    if not isinstance(view, Mapping):
        raise ValueError("runtime has no admitted Profile view")
    evaluation = view.get("_evaluation")
    admission, errors = admission_from_evaluation(root, evaluation)
    if errors:
        raise ValueError("; ".join(errors))
    if (view.get("_contract") is not evaluation.contract or
            view.get("_profile_snapshot") is not evaluation.profile_snapshot or
            view.get("_metadata_execution_contract") is not evaluation.metadata_execution_contract):
        raise ValueError("Profile view does not reuse the exact Gate result objects")
    expected = {
        "selected_profile_manifest": admission.manifest_repo_path,
        "metadata_execution_contract_fingerprint":
            evaluation.metadata_execution_contract.contract_fingerprint,
    }
    expected.update({name: getattr(evaluation, name)
                     for name in profile_contract.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS})
    if any(view.get(name) != value for name, value in expected.items()):
        raise ValueError("Profile view public identity differs from its Gate result")
    return admission.contract


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


def admit_profile_manifest(root, manifest, *, evaluation=None):
    """Admit an explicitly bound manifest, optionally reusing its Gate result.

    A compiled model is never accepted as authorization. This adapter neither
    chooses an active Profile nor confirms or adopts candidate answers.
    """
    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    try:
        profile_layout_contract.parse_profile_manifest_path(manifest)
    except (TypeError, ValueError) as exc:
        return None, ["invalid Profile manifest identity: %s" % exc]
    if evaluation is None:
        try:
            evaluation = check_profile.evaluate_profile_load(
                os.path.join(root, os.path.dirname(manifest)), root=root,
                receipt_identity=None)
        except (OSError, UnicodeError, ValueError) as exc:
            return None, ["cannot evaluate profile-load: %s" % exc]
    admission, errors = admission_from_evaluation(root, evaluation)
    if errors:
        return None, errors
    if admission.manifest_repo_path != manifest:
        return None, ["profile-load evaluation selects a different manifest"]
    errors = currency_errors(admission)
    return (None, errors) if errors else (admission, [])


def require_slot(admission, slot_name):
    """Return an immutable slot value and error, never a filesystem path."""
    if admission is None:
        return None, "Profile slot access requires an authorized admission"
    try:
        value = admission.slot(slot_name)
    except (KeyError, ValueError) as exc:
        return None, "authorized Profile has no %r slot: %s" % (slot_name, exc)
    if value is None:
        return None, "authorized Profile has no %r slot" % slot_name
    return value, None


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
        _snapshots, current_inputs = admission.evaluation.rebind_normative_inputs(
            admission.root)
    except (OSError, ValueError) as exc:
        return ["cannot re-bind canonical profile-load inputs: %s" % exc]
    if current_inputs != admission.evaluation.profile_load_inputs_sha256:
        return [
            "canonical profile-load inputs changed after admission; rerun "
            "against one stable rule interface"
        ]
    try:
        current = admission.evaluation.rebind_profile_snapshot(
            admission.root).sha256
    except (OSError, ValueError) as exc:
        return ["cannot re-bind the admitted Profile snapshot: %s" % exc]
    if current != admission.profile_snapshot_sha256:
        return [
            "selected Profile changed after profile-load admission; rerun "
            "against one stable Profile snapshot"
        ]
    return []
