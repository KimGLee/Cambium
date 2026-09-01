"""Which Profile and adopter-Standards view was admitted, and is it still it.

A run freezes a snapshot-bound view once and then re-checks that the bytes it
was admitted against have not moved underneath it.  Admission and currency
are separate questions and both are asked here, because a view that was valid
at admission and is stale now is the exact state a long transaction produces.
"""

from dataclasses import dataclass
import os

import Tools.governance.profile.check_profile as check_profile
import Tools.platform.common.kblib as kblib
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.governance.profile.profile_contract as profile_contract
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.governance.standards.standards_state as standards_state

from Tools.execution.task_runtime.queue_runtime.canon import SHA256_RE
from Tools.execution.task_runtime.queue_runtime.primitives import nonempty_string


EXPRESSION_LAYER_SLOT = "Expression Layer Entry"


@dataclass(frozen=True)
class _ProfileViewReadScope:
    """One outer validation's permission to read an admitted snapshot."""

    root: str
    profile_manifest: str
    authorized_view: dict


def _selected_profile_manifest_envelope_errors(profile):
    """Reject a selected-Profile reference outside the runtime envelope.

    This check is deliberately lexical: ordinary runtime admission must not
    read Profile bytes before the one authoritative ``profile-load`` producer
    binds them.  The smaller corrective-adoption guard below adds its own
    identity/sentinel reads because that explicit escape must remain usable
    when the current transitive closure is already invalid.
    """
    if not nonempty_string(profile):
        return ["selected_profile_manifest must be instantiated"]
    try:
        profile_layout_contract.validate_selectable_profile_manifest_path(
            profile)
    except profile_layout_contract.ProfileLayoutError as exc:
        return ["selected_profile_manifest %s" % exc]
    return []


def selected_profile_manifest_errors(root, profile):
    """Reject template/example/unfilled manifests as runtime identities.

    Full profile quality remains owned by ``check_profile.py``.  This small
    persistent guard enforces the mechanical facts a resumed Queue must never
    forget: the selected package is an adopter-owned profile ID, not a shipped
    form/example, and its identity/sentinel state is instantiated.
    """
    if not nonempty_string(profile):
        return ["selected_profile_manifest must be instantiated"]
    try:
        location = profile_layout_contract.parse_profile_manifest_path(profile)
    except profile_layout_contract.ProfileLayoutError:
        return ["selected_profile_manifest must be %s/<id>/%s" %
                (profile_layout_contract.PROFILES_DIRECTORY,
                 profile_layout_contract.PROFILE_MANIFEST_NAME)]
    if location.example:
        return ["selected_profile_manifest must be %s/<id>/%s" %
                (profile_layout_contract.PROFILES_DIRECTORY,
                 profile_layout_contract.PROFILE_MANIFEST_NAME)]
    errors = []
    profile_id = location.profile_id
    reserved = set(profile_layout_contract.RESERVED_PROFILE_IDS)
    sentinel = "TODO(profile)"
    defaults_path = os.path.join(
        os.path.realpath(os.path.abspath(root)),
        "Tools/schemas/execution_defaults.template.yaml",
    )
    if os.path.isfile(defaults_path):
        try:
            defaults = kblib.load_yaml_file(defaults_path)
            reserved.update(str(value) for value in
                            (defaults.get("reserved_profile_ids") or []))
            sentinel = str(defaults.get("unfilled_sentinel") or sentinel)
        except (OSError, ValueError, kblib.YamlSubsetError) as exc:
            errors.append("selected profile default registry is unreadable: %s" %
                          exc)
    if not location.selectable or profile_id in reserved:
        errors.append("selected_profile_manifest uses reserved/non-runnable "
                      "profile id %r" % profile_id)
    try:
        profile_snapshot = kblib.repository_tree_snapshot(
            root, os.path.dirname(profile))
        manifest_text = profile_snapshot.read_text(profile)
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append("selected_profile_manifest is unsafe or missing: %s" % exc)
        return errors
    _, identity_errors = kblib.profile_identity(
        manifest_text, profile_id, reserved)
    for _, details in identity_errors:
        errors.append("selected profile identity: %s" % details)
    try:
        hits, _, _ = check_profile.scan_sentinel(profile_snapshot, sentinel)
    except (OSError, UnicodeError) as exc:
        errors.append("selected profile cannot be scanned for unfilled "
                      "sentinels: %s" % exc)
    else:
        if hits:
            sample = ", ".join("%s:%d" % hit for hit in hits[:3])
            errors.append("selected profile is not runnable; unfilled sentinel "
                          "%r remains at %s" % (sentinel, sample))
    return errors


def profile_load_authorized_view(root, profile):
    """Run ``profile-load`` once and retain its snapshot-bound consumer view.

    The public evidence fields bind the selected manifest, complete Profile
    tree, and typed dependency graph.  ``_manifest_slot_paths`` is an internal
    projection of that *same* authorized contract; it lets runtime consumers
    locate a slot without reparsing the manifest under a later revision.

    ``evaluate_profile_load`` returns the Profile contract, compiled metadata
    contract, snapshot, fingerprints, and summary from one producer
    invocation.  Consumers must not reconstruct either contract in a second
    parse: doing so could pair the verdict for revision A with revision B's
    dependency graph or execution rules.
    """
    errors = _selected_profile_manifest_envelope_errors(profile)
    if errors or not nonempty_string(profile):
        return None, errors

    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    profile_dir = os.path.join(
        root, os.path.dirname(profile).replace("/", os.sep))
    try:
        evaluation = check_profile.evaluate_profile_load(
            profile_dir, root=root, receipt_identity=None)
    except (OSError, SystemExit, TypeError, UnicodeError, ValueError) as exc:
        errors.append("profile-load producer could not run: %s" % exc)
        return None, errors

    if not evaluation.authorized:
        findings = [
            "[%s %s] %s — %s" % (
                str(receipt.get("result", "fail")).upper(),
                receipt.get("check", "profile-load"),
                receipt.get("target", profile),
                receipt.get("details", "profile-load was not authorized"),
            )
            for receipt in evaluation.findings[:5]
        ]
        detail = "; ".join(findings) if findings else \
            "check_profile exited %d without an authorized contract" % \
            evaluation.exit_code
        errors.append("selected Profile failed profile-load: %s" % detail)
        return None, errors

    contract = evaluation.contract
    metadata_contract = evaluation.metadata_execution_contract
    summary = evaluation.summary_receipt
    if (not isinstance(contract,
                       check_profile.profile_contract.ProfileContract) or
            not contract.authorized):
        return None, ["profile-load pass exposed no authorized typed contract"]
    if not isinstance(summary, dict):
        return None, ["profile-load pass exposed no summary receipt"]
    if not isinstance(
            metadata_contract,
            metadata_execution_contract.CompiledMetadataExecutionContract):
        return None, ["profile-load pass exposed no authorized metadata "
                      "execution contract"]
    if contract.manifest_repo_path != profile:
        errors.append(
            "profile-load selected manifest %r, expected %r" %
            (contract.manifest_repo_path, profile))
    if summary.get("selected_profile_manifest") != profile:
        errors.append(
            "profile-load summary selected manifest %r, expected %r" %
            (summary.get("selected_profile_manifest"), profile))

    if errors:
        return None, errors
    snapshot = evaluation.profile_snapshot_sha256
    if (not isinstance(snapshot, str) or
            not SHA256_RE.fullmatch(snapshot)):
        return None, ["profile-load did not authorize a canonical Profile "
                      "snapshot fingerprint"]
    bound_snapshot = evaluation.profile_snapshot
    if (not isinstance(bound_snapshot, kblib.RepositoryTreeSnapshot) or
            bound_snapshot.sha256 != snapshot or
            os.path.realpath(bound_snapshot.root) != root or
            bound_snapshot.relative_directory != contract.profile_repo_dir):
        return None, ["profile-load did not expose the immutable Profile "
                      "snapshot that authorized its typed contract"]
    fingerprint = evaluation.profile_contract_fingerprint
    if (not isinstance(fingerprint, str) or
            not SHA256_RE.fullmatch(fingerprint)):
        return None, ["profile-load did not authorize a typed contract "
                      "fingerprint"]
    inputs_fingerprint = evaluation.profile_load_inputs_sha256
    if (not isinstance(inputs_fingerprint, str) or
            not SHA256_RE.fullmatch(inputs_fingerprint)):
        return None, ["profile-load did not bind its canonical normative "
                      "input bytes"]
    metadata_fingerprint = metadata_contract.contract_fingerprint
    if (not isinstance(metadata_fingerprint, str) or
            not SHA256_RE.fullmatch(metadata_fingerprint)):
        return None, ["profile-load authorized metadata contract has an "
                      "invalid fingerprint"]
    for field, expected in (
            ("profile_snapshot_sha256", snapshot),
            ("profile_contract_fingerprint", fingerprint),
            ("profile_load_inputs_sha256", inputs_fingerprint),
            ("metadata_execution_contract_fingerprint",
             metadata_fingerprint)):
        if summary.get(field) != expected:
            return None, ["profile-load summary %s differs from the "
                          "authorized evaluation" % field]

    slot_paths = {}
    for edge in contract.dependency_edges:
        if edge.kind != "manifest-slot":
            continue
        if (not nonempty_string(edge.owner_id) or
                not nonempty_string(edge.path)):
            return None, ["profile-load authorized a malformed manifest-slot "
                          "dependency edge"]
        if edge.owner_id in slot_paths:
            return None, ["profile-load authorized duplicate manifest-slot "
                          "dependency edges for %r" % edge.owner_id]
        slot_paths[edge.owner_id] = edge.path
    if EXPRESSION_LAYER_SLOT not in slot_paths:
        return None, ["profile-load authorized no manifest-slot dependency "
                      "edge for %s" % EXPRESSION_LAYER_SLOT]

    return {
        "selected_profile_manifest": profile,
        "profile_snapshot_sha256": snapshot,
        "profile_contract_fingerprint": fingerprint,
        "profile_load_inputs_sha256": inputs_fingerprint,
        "metadata_execution_contract_fingerprint": metadata_fingerprint,
        "_manifest_slot_paths": tuple(sorted(slot_paths.items())),
        "_contract": contract,
        "_metadata_execution_contract": metadata_contract,
        "_profile_snapshot": bound_snapshot,
        "_evaluation": evaluation,
    }, []


def public_profile_load_evidence(authorized_view):
    """Project an internal authorized view into durable evidence fields."""
    return {
        field: authorized_view[field]
        for field in profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS
    }


def active_standards_authorized_view(root, upstream_revision_id,
                                     selected_profile_manifest,
                                     state_override=None):
    """Return one immutable approved adopter-state view and its errors."""
    state, view, errors = standards_state.snapshot(
        root, override_text=state_override)
    errors = ["active Standards state: %s" % error for error in errors]
    if state is None:
        return None, errors
    if state.get("upstream_revision_id") != upstream_revision_id:
        errors.append(
            "runtime upstream_revision_id %r differs from active state %r" %
            (upstream_revision_id, state.get("upstream_revision_id")))
    if (state.get("selected_profile_manifest") !=
            selected_profile_manifest):
        errors.append(
            "runtime selected_profile_manifest %r differs from active "
            "state %r" %
            (selected_profile_manifest,
             state.get("selected_profile_manifest")))
    if errors:
        return None, errors
    return view, []



def active_standards_view_currency_errors(root, authorized_view,
                                          state_override=None):
    """Fail when current-state bytes no longer equal an authorized view."""
    if not isinstance(authorized_view, dict):
        return ["active Standards authorized view must be a mapping"]
    expected = authorized_view.get("active_standards_sha256")
    view, errors = active_standards_authorized_view(
        root, authorized_view.get("upstream_revision_id"),
        authorized_view.get("selected_profile_manifest"),
        state_override=state_override)
    if errors:
        return errors
    if view.get("active_standards_sha256") != expected:
        return [
            "active Standards state changed after identity admission; "
            "rerun against one stable state revision"
        ]
    return []


def profile_load_evidence(root, profile):
    """Run ``profile-load`` and return one stable, receipt-free identity.

    The returned mapping is deliberately an in-memory value, not a Gate
    receipt.  Standards adoption judges a candidate *after* Profile while the
    Required Queue still names the current Profile; publishing that candidate
    receipt into the current receipt catalog would therefore combine two
    different task identities.  The eventual selected task must produce its
    own ``profile-load`` receipt after the adoption commits.

    Slot consumers inside this module use the authorized-view API so
    their source paths come from the same producer invocation.  External
    callers receive only the three durable identity fields.
    """
    authorized_view, errors = profile_load_authorized_view(root, profile)
    if authorized_view is None:
        return None, errors
    return public_profile_load_evidence(authorized_view), errors


def profile_load_errors(root, profile):
    """Return the canonical ``profile-load`` admission failures.

    Default runtime consistency and every candidate after-image use this full
    producer.  :func:`selected_profile_manifest_errors` remains only as the
    smaller identity/sentinel check behind the explicit corrective-adoption
    escape, so a broken current closure can be replaced without weakening any
    ordinary reader, writer, or proposed state.
    """
    _authorized_view, errors = profile_load_authorized_view(root, profile)
    return errors


def profile_view_snapshot_error(root, authorized_view, phase):
    """Return a fail-closed error if an authorized view is no longer current."""
    manifest = authorized_view.get("selected_profile_manifest")
    expected = authorized_view.get("profile_snapshot_sha256")
    if (not nonempty_string(manifest) or not isinstance(expected, str) or
            not SHA256_RE.fullmatch(expected)):
        return "authorized Profile view has malformed snapshot identity"
    evaluation = authorized_view.get("_evaluation")
    if (not isinstance(evaluation, check_profile.ProfileLoadEvaluation) or
            not evaluation.authorized):
        return "authorized Profile view has no reusable profile-load evaluation"
    try:
        actual = evaluation.rebind_profile_snapshot(root).sha256
    except (OSError, ValueError) as exc:
        return ("selected Profile cannot be rebound %s Expression hub "
                "derivation: %s" % (phase, exc))
    if actual != expected:
        return ("selected Profile changed after profile-load authorization; "
                "snapshot mismatch %s Expression hub derivation" % phase)
    expected_inputs = authorized_view.get("profile_load_inputs_sha256")
    try:
        _snapshots, actual_inputs = \
            check_profile.canonical_profile_load_inputs(root)
    except (OSError, ValueError) as exc:
        return ("canonical profile-load inputs cannot be rebound %s "
                "Expression hub derivation: %s" % (phase, exc))
    if actual_inputs != expected_inputs:
        return ("canonical profile-load inputs changed after profile-load "
                "authorization; input mismatch %s Expression hub "
                "derivation" % phase)
    return None


def authorized_profile_view_errors(root, profile_manifest, authorized_view):
    """Validate one in-process view without rerunning ``profile-load``."""
    if not isinstance(authorized_view, dict):
        return ["authorized Profile view must be a mapping returned by "
                "profile_load_authorized_view"]
    errors = []
    if authorized_view.get("selected_profile_manifest") != profile_manifest:
        errors.append("authorized Profile view selects %r, not %r" % (
            authorized_view.get("selected_profile_manifest"),
            profile_manifest))
    snapshot = authorized_view.get("profile_snapshot_sha256")
    if not isinstance(snapshot, str) or not SHA256_RE.fullmatch(snapshot):
        errors.append("authorized Profile view has malformed snapshot identity")
    fingerprint = authorized_view.get("profile_contract_fingerprint")
    if (not isinstance(fingerprint, str) or
            not SHA256_RE.fullmatch(fingerprint)):
        errors.append("authorized Profile view has malformed typed-contract "
                      "fingerprint")
    inputs_fingerprint = authorized_view.get("profile_load_inputs_sha256")
    if (not isinstance(inputs_fingerprint, str) or
            not SHA256_RE.fullmatch(inputs_fingerprint)):
        errors.append("authorized Profile view has malformed canonical-input "
                      "fingerprint")
    metadata_fingerprint = authorized_view.get(
        "metadata_execution_contract_fingerprint")
    if (not isinstance(metadata_fingerprint, str) or
            not SHA256_RE.fullmatch(metadata_fingerprint)):
        errors.append("authorized Profile view has malformed metadata-contract "
                      "fingerprint")

    contract = authorized_view.get("_contract")
    contract_type = check_profile.profile_contract.ProfileContract
    if not isinstance(contract, contract_type) or not contract.authorized:
        errors.append("authorized Profile view has no authorized typed "
                      "contract object")
        contract = None
    elif os.path.realpath(contract.root) != \
            os.path.realpath(os.path.abspath(os.fspath(root))):
        errors.append("authorized Profile view belongs to a different "
                      "repository root")
    else:
        if contract.manifest_repo_path != profile_manifest:
            errors.append("authorized Profile contract selects %r, not %r" % (
                contract.manifest_repo_path, profile_manifest))
        if contract.profile_contract_fingerprint != fingerprint:
            errors.append("authorized Profile view fingerprint differs from "
                          "its typed contract")

    bound_snapshot = authorized_view.get("_profile_snapshot")
    if not isinstance(bound_snapshot, kblib.RepositoryTreeSnapshot):
        errors.append("authorized Profile view has no immutable Profile "
                      "snapshot object")
    else:
        expected_directory = os.path.dirname(profile_manifest)
        if (bound_snapshot.sha256 != snapshot or
                os.path.realpath(bound_snapshot.root) !=
                os.path.realpath(os.path.abspath(os.fspath(root))) or
                bound_snapshot.relative_directory != expected_directory):
            errors.append("authorized Profile immutable snapshot identity "
                          "differs from its public binding")

    evaluation = authorized_view.get("_evaluation")
    if (not isinstance(evaluation, check_profile.ProfileLoadEvaluation) or
            not evaluation.authorized):
        errors.append("authorized Profile view has no authorized evaluation "
                      "object")
    else:
        if (evaluation.contract is not contract or
                evaluation.profile_snapshot is not bound_snapshot):
            errors.append("authorized Profile evaluation objects differ from "
                          "its typed contract or immutable snapshot")
        for field in \
                profile_contract.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS:
            if getattr(evaluation, field) != authorized_view.get(field):
                errors.append("authorized Profile evaluation %s differs "
                              "from its public binding" % field)

    metadata_contract = authorized_view.get("_metadata_execution_contract")
    metadata_type = \
        metadata_execution_contract.CompiledMetadataExecutionContract
    if not isinstance(metadata_contract, metadata_type):
        errors.append("authorized Profile view has no compiled metadata "
                      "execution contract object")
    else:
        if metadata_contract.contract_fingerprint != metadata_fingerprint:
            errors.append("authorized Profile metadata contract fingerprint "
                          "differs from its public binding")
        if (isinstance(evaluation, check_profile.ProfileLoadEvaluation) and
                evaluation.metadata_execution_contract is not
                metadata_contract):
            errors.append("authorized Profile metadata contract differs from "
                          "its producer evaluation object")

    projected_pairs = ()
    try:
        projected_pairs = tuple(authorized_view["_manifest_slot_paths"])
        projected = dict(projected_pairs)
        if (len(projected) != len(projected_pairs) or
                any(not nonempty_string(key) or
                    not nonempty_string(value)
                    for key, value in projected_pairs)):
            raise ValueError("malformed or duplicate manifest-slot edge")
    except (KeyError, TypeError, ValueError):
        errors.append("authorized Profile view has no immutable manifest-slot "
                      "projection")
        projected = {}

    if contract is not None:
        contract_pairs = tuple(sorted(
            (edge.owner_id, edge.path)
            for edge in contract.dependency_edges
            if edge.kind == "manifest-slot"
        ))
        if projected_pairs != contract_pairs:
            errors.append("authorized Profile manifest-slot projection differs "
                          "from its typed contract")
    if not nonempty_string(projected.get(EXPRESSION_LAYER_SLOT)):
        errors.append("authorized Profile view has no %s path" %
                      EXPRESSION_LAYER_SLOT)

    if not errors:
        snapshot_error = profile_view_snapshot_error(
            root, authorized_view, "before")
        if snapshot_error:
            errors.append(snapshot_error)
    return errors


def open_profile_view_read_scope(root, profile_manifest, authorized_view):
    """CAS one Profile view before an outer snapshot-reading phase.

    The returned object is deliberately opaque.  A nested helper may validate
    its root/manifest/view identity and read the already-frozen snapshot
    without reopening the same 9-plus-implementation closure.  The outer
    owner MUST run its ordinary after-phase currency check; this scope is not
    a cache and never authorizes another transaction phase.
    """
    canonical_root = os.path.realpath(os.path.abspath(os.fspath(root)))
    errors = authorized_profile_view_errors(
        canonical_root, profile_manifest, authorized_view)
    if errors:
        return None, errors
    return _ProfileViewReadScope(
        root=canonical_root,
        profile_manifest=profile_manifest,
        authorized_view=authorized_view,
    ), []


def profile_view_read_scope_errors(
        scope, root, profile_manifest, authorized_view):
    """Reject a nested read not owned by this exact outer validation."""
    if not isinstance(scope, _ProfileViewReadScope):
        return ["Profile read scope was not opened by the currency owner"]
    canonical_root = os.path.realpath(os.path.abspath(os.fspath(root)))
    errors = []
    if scope.root != canonical_root:
        errors.append("Profile read scope belongs to another repository root")
    if scope.profile_manifest != profile_manifest:
        errors.append("Profile read scope selects another manifest")
    if scope.authorized_view is not authorized_view:
        errors.append("Profile read scope carries another authorized view")
    return errors


def profile_load_authorized_view_currency_errors(root, authorized_view):
    """Rebind a previously authorized Profile view without rerunning producer."""
    manifest = authorized_view.get("selected_profile_manifest") \
        if isinstance(authorized_view, dict) else None
    if not nonempty_string(manifest):
        return ["authorized Profile view has no selected manifest identity"]
    return authorized_profile_view_errors(root, manifest, authorized_view)
