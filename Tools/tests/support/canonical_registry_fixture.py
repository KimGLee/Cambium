"""Install the Kernel machine registries needed by isolated Tool fixtures.

Scratch repositories execute copied production modules.  Those modules must
load the same Kernel-owned machine authorities as a real distribution; a
fixture-local fallback or a Python copy of their semantic values would hide a
broken distribution.  Keep the file membership in this one test-only
manifest, and let every isolated bundle install it through the helper below.

The contract-exception registry additionally validates that each declared
Markdown owner exists.  Those owner pages are therefore dependency closure,
not extra machine authorities, and are derived from the registry rather than
listed a second time.
"""

from pathlib import Path, PurePosixPath
import shutil
import sys

TESTS = Path(__file__).resolve().parents[1]
TOOLS = TESTS.parent
REPOSITORY = TOOLS.parent

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import Tools.platform.common.kblib as kblib  # noqa: E402


# The complete Kernel machine-authority bundle shipped by this distribution.
# A coverage test compares this manifest with the live Kernel tree so adding a
# registry cannot silently leave isolated Tool executions on a partial bundle.
KERNEL_MACHINE_REGISTRY_PATHS = (
    "kernel/K00 Standards Control/contract-exception-policy-base.yaml",
    "kernel/K00 Standards Control/control-registry.yaml",
    "kernel/K00 Standards Control/execution-defaults-base.yaml",
    "kernel/K00 Standards Control/profile-interface.yaml",
    "kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml",
    "kernel/K07 Sources and Accuracy/sources-role-base.yaml",
    "kernel/K08 Metadata and Status/applicability-base.yaml",
    "kernel/K08 Metadata and Status/metadata-authority-base.yaml",
    "kernel/K08 Metadata and Status/relationship-base.yaml",
    "kernel/K08 Metadata and Status/vocabulary-base.yaml",
    "kernel/K12 Quality Assurance/audit-dimension-base.yaml",
    "kernel/K12 Quality Assurance/audit-plan-contract.yaml",
    "kernel/K12 Quality Assurance/audit-receipt-contract.yaml",
    "kernel/K12 Quality Assurance/batch-close-closed-list.yaml",
    "kernel/K12 Quality Assurance/batch-review-obligation-registry.yaml",
    "kernel/K12 Quality Assurance/changed-scope-check-registry.yaml",
    "kernel/K12 Quality Assurance/deterministic-rendering-contract.yaml",
    "kernel/K12 Quality Assurance/rendering-verification-contract.yaml",
    "kernel/K12 Quality Assurance/substantive-review-contract.yaml",
    "kernel/K12 Quality Assurance/terminal-proof-contract.yaml",
    "kernel/K13 Task Runtime and Execution Control/runtime-state-model.json",
)

COMPONENT_MACHINE_REGISTRY_PATHS = (
    "Card/card-budget.yaml",
    "Read Set/read-set.schema.yaml",
)

TOOL_MACHINE_REGISTRY_PATHS = (
    "Tools/schemas/card.schema.yaml",
    "Tools/module-boundaries.yaml",
)

ISOLATED_TOOL_REGISTRY_PATHS = (
    KERNEL_MACHINE_REGISTRY_PATHS + COMPONENT_MACHINE_REGISTRY_PATHS +
    TOOL_MACHINE_REGISTRY_PATHS)

CONTRACT_EXCEPTION_REGISTRY_PATH = (
    "kernel/K00 Standards Control/contract-exception-policy-base.yaml")


def _copy_repository_file(root, relative):
    source = REPOSITORY / relative
    if not source.is_file():
        raise AssertionError(
            "canonical fixture source is absent: %s" % relative)
    target = Path(root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def contract_exception_owner_paths():
    """Derive the registry's required Markdown-owner dependency closure."""
    document = kblib.parse_yaml_subset(
        (REPOSITORY / CONTRACT_EXCEPTION_REGISTRY_PATH).read_text(
            encoding="utf-8"))
    owners = set()
    for family in document.get("families", ()):
        for policy in family.get("policies", ()):
            owner = policy.get("owner")
            if not isinstance(owner, str):
                raise AssertionError(
                    "contract-exception fixture owner must be a path")
            pure = PurePosixPath(owner)
            if (pure.is_absolute() or not pure.parts or
                    pure.parts[0] != "kernel" or
                    any(part in ("", ".", "..") for part in pure.parts) or
                    pure.suffix != ".md"):
                raise AssertionError(
                    "unsafe contract-exception fixture owner: %s" % owner)
            owners.add(owner)
    if not owners:
        raise AssertionError(
            "contract-exception fixture registry declares no owners")
    return tuple(sorted(owners))


def install_isolated_tool_registry_bundle(root):
    """Copy all registries needed by copied Tools and their owner closure."""
    installed = ISOLATED_TOOL_REGISTRY_PATHS + \
        contract_exception_owner_paths()
    for relative in installed:
        _copy_repository_file(root, relative)
    return installed


__all__ = [
    "COMPONENT_MACHINE_REGISTRY_PATHS",
    "CONTRACT_EXCEPTION_REGISTRY_PATH",
    "ISOLATED_TOOL_REGISTRY_PATHS",
    "KERNEL_MACHINE_REGISTRY_PATHS",
    "TOOL_MACHINE_REGISTRY_PATHS",
    "contract_exception_owner_paths",
    "install_isolated_tool_registry_bundle",
]
