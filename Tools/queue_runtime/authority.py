"""Does the transaction still hold the exact admission it froze.

An opaque authority context, its compare-and-swap against current bytes, and
its projection into writer-lock metadata.  The context is opaque on purpose:
a caller that could read it apart would be able to reconstruct a weaker
version of the same claim.
"""

import os

from queue_runtime.primitives import _nonempty_string
from queue_runtime.profile_view import (
    active_standards_view_currency_errors,
    profile_load_authorized_view_currency_errors,
)


def runtime_authority_context(result):
    """Freeze one successful runtime admission for a complete transaction.

    Ordinary writers call :func:`validate_runtime` once without injected
    views, then carry this opaque context through every proposed, locked, and
    post-write validation.  The Profile and K00/03 views are deliberately kept
    together: accepting a view from one admission and an active-Standards
    binding from another would recreate the split-revision window this API is
    intended to close.
    """
    if not isinstance(result, dict):
        raise TypeError("runtime validation result must be a mapping")
    if result.get("errors"):
        raise ValueError(
            "runtime authority context requires a successful validation")
    root = result.get("root")
    queue = result.get("queue")
    profile_view = result.get("_profile_authorized_view")
    active_view = result.get("_active_standards_authorized_view")
    if not _nonempty_string(root) or not isinstance(queue, dict):
        raise ValueError("runtime validation result has no canonical root or Queue")
    if not isinstance(profile_view, dict):
        raise ValueError("runtime validation result has no authorized Profile view")
    if not isinstance(active_view, dict):
        raise ValueError(
            "runtime validation result has no authorized active Standards view")
    expected_profile = queue.get("selected_profile_manifest")
    expected_standards = queue.get("standards_version")
    if (profile_view.get("selected_profile_manifest") != expected_profile or
            active_view.get("selected_profile_manifest") != expected_profile):
        raise ValueError(
            "runtime authority views do not select the validated Queue Profile")
    if active_view.get("standards_version") != expected_standards:
        raise ValueError(
            "runtime active Standards view does not select the validated "
            "Queue version")
    return {
        "root": os.path.realpath(os.path.abspath(root)),
        "profile_view": profile_view,
        "active_standards_view": active_view,
    }


def runtime_authority_validation_kwargs(context):
    """Return the indivisible view pair for a later runtime validation."""
    if not isinstance(context, dict):
        raise TypeError("runtime authority context must be a mapping")
    profile_view = context.get("profile_view")
    active_view = context.get("active_standards_view")
    if not isinstance(profile_view, dict) or not isinstance(active_view, dict):
        raise ValueError(
            "runtime authority context must contain both authorized views")
    return {
        "authorized_profile_view": profile_view,
        "authorized_active_standards_view": active_view,
    }


def runtime_authority_currency_errors(root, context):
    """Return CAS failures for every root authority bound by ``context``."""
    if not isinstance(context, dict):
        return ["runtime authority context must be a mapping"]
    canonical_root = os.path.realpath(os.path.abspath(os.fspath(root)))
    if context.get("root") != canonical_root:
        return ["runtime authority context belongs to a different repository root"]
    try:
        kwargs = runtime_authority_validation_kwargs(context)
    except (TypeError, ValueError) as exc:
        return [str(exc)]
    errors = []
    for detail in active_standards_view_currency_errors(
            canonical_root, kwargs["authorized_active_standards_view"]):
        errors.append("active Standards authority: %s" % detail)
    for detail in profile_load_authorized_view_currency_errors(
            canonical_root, kwargs["authorized_profile_view"]):
        errors.append("Profile-load authority: %s" % detail)
    return errors


def require_runtime_authority_current(root, context, phase):
    """Raise when a transaction no longer sees its admitted authority bytes."""
    errors = runtime_authority_currency_errors(root, context)
    if errors:
        raise ValueError("%s: %s" % (phase, "; ".join(errors)))


def runtime_authority_lock_fields(context):
    """Project one transaction authority binding into writer-lock metadata."""
    kwargs = runtime_authority_validation_kwargs(context)
    profile_view = kwargs["authorized_profile_view"]
    active_view = kwargs["authorized_active_standards_view"]
    return {
        "standards_version": active_view.get("standards_version"),
        "active_standards_sha256": active_view.get(
            "active_standards_sha256"),
        "selected_profile_manifest": profile_view.get(
            "selected_profile_manifest"),
        "profile_snapshot_sha256": profile_view.get(
            "profile_snapshot_sha256"),
        "profile_contract_fingerprint": profile_view.get(
            "profile_contract_fingerprint"),
        "profile_load_inputs_sha256": profile_view.get(
            "profile_load_inputs_sha256"),
    }
