"""Unique current-contract fixture producer for Profile-load consumers."""

from pathlib import Path
import shutil

import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.governance.profile.check_profile as check_profile
import Tools.platform.common.kblib as kblib
from Tools.tests.support.canonical_registry_fixture import (
    KERNEL_MACHINE_REGISTRY_PATHS,
    install_isolated_tool_registry_bundle,
)


REPOSITORY = Path(__file__).resolve().parents[3]
ADDITIONAL_PROFILE_LOAD_INPUTS = (
    "Tools/schemas/residual_scan_config.template.yaml",
    "Tools/knowledge/content/check_residual_content.py",
)


def profile_load_input_paths():
    """Derive the direct root-input closure from the production owners."""
    capabilities = kblib.parse_yaml_subset(
        (REPOSITORY / check_profile.DEFAULT_OPERATION_CAPABILITIES).read_text(
            encoding="utf-8"))
    implementations = metadata_execution_contract.\
        capability_implementation_paths(capabilities)
    return tuple(sorted(set(
        check_profile.CANONICAL_PROFILE_LOAD_INPUTS
        + tuple(implementations)
        + ADDITIONAL_PROFILE_LOAD_INPUTS
    )))


def install_current_profile_load_inputs(root):
    """Install sources, then compile their one current machine projection."""
    root = Path(root)
    install_isolated_tool_registry_bundle(root)
    for relative in profile_load_input_paths():
        if (relative in KERNEL_MACHINE_REGISTRY_PATHS or
                relative == metadata_execution_contract.DEFAULT_COMPILED_PATH):
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY / relative, target)

    compiled = metadata_execution_contract.compile_metadata_execution_contract(
        root)
    target = root / metadata_execution_contract.DEFAULT_COMPILED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    kblib.atomic_write_text(
        target, compiled.canonical_bytes.decode("utf-8"))
    return compiled


__all__ = [
    "install_current_profile_load_inputs",
]
