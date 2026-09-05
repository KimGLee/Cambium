"""Unique current-contract fixture producer for Profile-load consumers."""

from pathlib import Path

import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.governance.profile.check_profile as check_profile
import Tools.platform.common.kblib as kblib
from Tools.tests.support.canonical_registry_fixture import (
    install_isolated_tool_registry_bundle,
)


REPOSITORY = Path(__file__).resolve().parents[3]
ADDITIONAL_PROFILE_LOAD_INPUTS = (
    "Tools/schemas/residual_scan_config.template.yaml",
)


def profile_load_input_paths():
    """Derive the direct root-input closure from the production owners."""
    snapshots, _fingerprint = check_profile.canonical_profile_load_inputs(
        REPOSITORY)
    return tuple(sorted(set(
        tuple(snapshots)
        + ADDITIONAL_PROFILE_LOAD_INPUTS
    )))


def install_current_profile_load_inputs(root):
    """Install one frozen owner closure and compile its current projection.

    Fixture source membership comes from the production evaluator, including
    CUE source/projection owners and the Tool encoding. Copy the frozen bytes
    rather than deriving membership and reopening a possibly changed source.
    """
    root = Path(root)
    snapshots, _fingerprint = check_profile.canonical_profile_load_inputs(
        REPOSITORY, additional_paths=ADDITIONAL_PROFILE_LOAD_INPUTS)
    install_isolated_tool_registry_bundle(root)
    for relative, snapshot in snapshots.items():
        if relative == metadata_execution_contract.DEFAULT_COMPILED_PATH:
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(snapshot.data)

    return refresh_profile_load_projection(root)


def refresh_profile_load_projection(root):
    """Compile fixture-local owner edits without overwriting those edits."""
    root = Path(root)

    compiled = metadata_execution_contract.compile_metadata_execution_contract(
        root)
    target = root / metadata_execution_contract.DEFAULT_COMPILED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    kblib.atomic_write_text(
        target, compiled.canonical_bytes.decode("utf-8"))
    return compiled


__all__ = [
    "install_current_profile_load_inputs",
    "profile_load_input_paths",
    "refresh_profile_load_projection",
]
