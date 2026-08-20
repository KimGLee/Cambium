"""Shared complete Profile package for runtime-control test repositories."""

from pathlib import Path
import shutil
import sys


TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
REPOSITORY = TOOLS.parent
SYNTHETIC_PROFILE = TESTS / "fixtures" / "synthetic_profile"

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import profile_contract  # noqa: E402  (path set above)
import kblib  # noqa: E402
import metadata_execution_contract  # noqa: E402

# Derived, never re-listed: `check_profile` refuses a repository whose
# interface slot list and this registry disagree, so deriving the synthetic
# interface from the registry keeps the fixture in step with the real one by
# construction instead of by whoever remembers to edit both.
PROFILE_INTERFACE = "# Profiles\n\n" + "".join(
    "## %s Slot\n\n" % name
    for name in profile_contract.PROFILE_FILE_SLOTS
)


def install_loadable_profile(root, profile_id="test-profile",
                             override_rows="", standards_version="3.0.0"):
    """Overlay a real 14-slot Profile and its root-owned dependencies."""
    root = Path(root)
    profile = root / "profiles" / profile_id
    shutil.copytree(SYNTHETIC_PROFILE, profile, dirs_exist_ok=True)
    for name in ("profile.md", "slots.md"):
        path = profile / name
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "test-profile", profile_id),
            encoding="utf-8",
        )
    if override_rows:
        manifest = profile / "profile.md"
        manifest.write_text(
            manifest.read_text(encoding="utf-8") + override_rows,
            encoding="utf-8",
        )

    (root / "profiles/README.md").write_text(
        PROFILE_INTERFACE, encoding="utf-8")
    (root / "Tools/schemas").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        TOOLS / "schemas/execution_defaults.template.yaml",
        root / "Tools/schemas/execution_defaults.template.yaml",
    )
    shutil.copy2(
        TOOLS / "check_residual_content.py",
        root / "Tools/check_residual_content.py",
    )
    # ``profile-load`` and every metadata writer share one compiled authority
    # bundle.  Runtime fixtures install its canonical sources and after-image
    # together so tests exercise currentness rather than an implicit fallback
    # to the Cambium source checkout.
    (root / "Tools/compiled").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        TOOLS / "operation-capabilities.yaml",
        root / "Tools/operation-capabilities.yaml",
    )
    capability_document = kblib.parse_yaml_subset(
        (TOOLS / "operation-capabilities.yaml").read_text(encoding="utf-8"))
    for relative in metadata_execution_contract.\
            capability_implementation_paths(capability_document):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY / relative, target)
    shutil.copy2(
        TOOLS / "compiled/metadata-execution-contract.json",
        root / "Tools/compiled/metadata-execution-contract.json",
    )
    metadata_authority = (
        root / "kernel/K08 Metadata and Status/metadata-authority-base.yaml")
    metadata_authority.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPOSITORY /
        "kernel/K08 Metadata and Status/metadata-authority-base.yaml",
        metadata_authority,
    )
    for relative in (
            profile_contract.KERNEL_APPLICABILITY_PATH,
            profile_contract.KERNEL_RELATIONSHIP_PATH):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY / relative, target)
    control_registry = (
        root / "kernel/K00 Standards Control/12 Control Registry.md")
    control_registry.parent.mkdir(parents=True, exist_ok=True)
    # Profile Gate compilation and Queue validation consume the two closed
    # registry tables, not K00/12's navigation prose.  Project only those
    # tables into the deliberately tiny fixture repository: copying the whole
    # module would add links to every kernel owner page and turn an interface
    # fixture into a partial, structurally broken kernel checkout.
    registry_source = (REPOSITORY /
        "kernel/K00 Standards Control/12 Control Registry.md").read_text(
            encoding="utf-8")
    wanted = {
        "Stable Gate ID Registry",
        "Standards Revalidation Capability Registry",
    }
    projected = ["# Fixture Control Registries", ""]
    active = None
    for line in registry_source.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip().strip("#").strip()
            active = heading if heading in wanted else None
            if active is not None:
                projected.extend(["## %s" % active, ""])
            continue
        if active is not None and line.lstrip().startswith("|"):
            projected.append(line)
        elif active is not None and projected[-1].startswith("|"):
            projected.append("")
            active = None
    control_registry.write_text("\n".join(projected).rstrip() + "\n",
                                encoding="utf-8")
    defaults = root / "kernel/K00 Standards Control/execution-defaults-base.yaml"
    defaults.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPOSITORY /
        "kernel/K00 Standards Control/execution-defaults-base.yaml",
        defaults,
    )
    active = root / "kernel/K00 Standards Control/03 Standards Governance.md"
    if not active.exists():
        active.write_text(
            "# Standards Governance\n\n## Standards Control\n\n"
            "| Field | Value |\n|---|---|\n"
            "| Standards version | `%s` |\n"
            "| Status | `approved` |\n"
            "| Effective date | `2026-08-01` |\n"
            "| Selected profile manifest | `profiles/%s/profile.md` |\n" %
            (standards_version, profile_id),
            encoding="utf-8")
    return profile
