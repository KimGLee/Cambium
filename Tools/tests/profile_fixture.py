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
