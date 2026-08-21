"""Shared complete Profile package for runtime-control test repositories."""

from pathlib import Path
import json
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
import standards_state  # noqa: E402

# Derived, never re-listed: `check_profile` refuses a repository whose
# interface slot list and this registry disagree, so deriving the synthetic
# interface from the registry keeps the fixture in step with the real one by
# construction instead of by whoever remembers to edit both.
PROFILE_INTERFACE = "# Profiles\n\n" + "".join(
    "## %s Slot\n\n" % name
    for name in profile_contract.PROFILE_FILE_SLOTS
)


RUNTIME_ROUTES = ["R%02d" % number for number in range(1, 14)]
RUNTIME_SELECTED_ROUTES = ("R01", "R03", "R07")


def _runtime_route_paths(route_id):
    names = {
        "R01": "Core Bootstrap",
        "R03": "Module Build",
        "R07": "Long-running Execution",
    }
    label = names.get(route_id, "Fixture")
    return (
        "kernel/Cards/%s %s Card.md" % (route_id, label),
        "kernel/Read Sets/%s %s Read Set.md" % (route_id, label),
    )


def _runtime_index_text(document_type, card_index):
    rows = []
    for route_id in RUNTIME_ROUTES:
        card, read_set = _runtime_route_paths(route_id)
        rows.append("  - route_id: %s" % route_id)
        rows.append('    path: "%s"' % (card if card_index else read_set))
        if card_index:
            rows.append('    read_set: "%s"' % read_set)
    return (
        "---\ntype: %s\nregistry_id: kernel-runtime-routes\n"
        "route_registry:\n%s\n---\n# Fixture Runtime Route Index\n" %
        (document_type, "\n".join(rows))
    )


def _install_runtime_activation_fixture(root):
    """Install a small but exact Card-first boundary into runtime fixtures."""
    card_index = root / "kernel/Cards/Card Index.md"
    card_index.parent.mkdir(parents=True, exist_ok=True)
    card_index.write_text(
        _runtime_index_text("card-index", True), encoding="utf-8")
    read_index = root / "kernel/Read Sets/Read Sets Index.md"
    read_index.parent.mkdir(parents=True, exist_ok=True)
    read_index.write_text(
        _runtime_index_text("route-index", False), encoding="utf-8")
    conditional = "kernel/K03 Fixture/01 Conditional Review.md"
    conditional_path = root / conditional
    conditional_path.parent.mkdir(parents=True, exist_ok=True)
    conditional_path.write_text(
        "# Conditional Review\n\nRead this source after the Card declares the "
        "fixture trigger.\n", encoding="utf-8")
    for route_id in RUNTIME_SELECTED_ROUTES:
        card_relative, read_relative = _runtime_route_paths(route_id)
        read_path = root / read_relative
        read_path.parent.mkdir(parents=True, exist_ok=True)
        read_path.write_text(
            "---\ntype: read-set\nroute_id: %s\n---\n"
            "# %s Fixture Read Set\n\n## Purpose\n\n"
            "Bound the fixture route without transitive leaves.\n" %
            (route_id, route_id), encoding="utf-8")
        sources = [conditional] if route_id == "R03" else []
        card = {
            "type": "runtime-card",
            "route_id": route_id,
            "read_set": read_relative,
            "compiled_from": "3.0.0",
            "source_files": [read_relative],
            "readback_sources": sources,
            "readback_policy": "declared" if sources else "none",
            "source_hash": "0123456789ab",
            "compiled_source_hash": "0123456789ab",
        }
        card_path = root / card_relative
        card_path.parent.mkdir(parents=True, exist_ok=True)
        card_path.write_text(
            "---\n%s---\n# %s Fixture Card\n\n"
            "This compact Card is the exact activation payload.\n" %
            (kblib.canonical_yaml(card), route_id), encoding="utf-8")

    # The shared valid runtime predates Task Plan derivation.  Give only that
    # fixture the complete frozen envelope that a current task-plan writer
    # would have produced, and move its initial immutable anchor with it.
    progress_path = root / ".cambium/state/progress_ledger.yaml"
    receipt_path = root / ".cambium/receipts/task-transitions.jsonl"
    if not progress_path.exists() or not receipt_path.exists():
        return
    progress = kblib.load_yaml_file(progress_path)
    contract = progress.get("contract")
    if not isinstance(contract, dict) or contract.get("selected_route_ids"):
        return
    contract["selected_route_ids"] = list(RUNTIME_SELECTED_ROUTES)
    contract["selected_card_paths"] = sorted(
        _runtime_route_paths(route_id)[0]
        for route_id in RUNTIME_SELECTED_ROUTES)
    contract["selected_read_sets"] = sorted(
        _runtime_route_paths(route_id)[1]
        for route_id in RUNTIME_SELECTED_ROUTES)
    contract["loaded_module_paths"] = []
    progress_path.write_text(kblib.canonical_yaml(progress), encoding="utf-8")
    records = [json.loads(line) for line in receipt_path.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    for record in records:
        if record.get("receipt_id") == "audit-fixture-initial-queue":
            record["contract_sha256"] = kblib.sha256_bytes(
                kblib.canonical_yaml(contract))
            record["after_progress_sha256"] = kblib.sha256_file(progress_path)
    receipt_path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n"
                for record in records), encoding="utf-8")


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
    active = root / standards_state.STATE_PATH
    active.parent.mkdir(parents=True, exist_ok=True)
    if not active.exists():
        active.write_text(standards_state.canonical_text({
            "schema_version": 1,
            "state_revision": 1,
            "standards_version": standards_version,
            "status": "approved",
            "effective_date": "2026-08-01",
            "selected_profile_manifest":
                "profiles/%s/profile.md" % profile_id,
            "latest_adoption_receipt": "audit-fixture-standards-adoption",
            "upstream_source_ref": None,
            "upstream_revision_id": None,
        }), encoding="utf-8")
    _install_runtime_activation_fixture(root)
    return profile
