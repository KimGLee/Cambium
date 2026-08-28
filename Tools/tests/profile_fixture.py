"""Shared complete Profile package for runtime-control test repositories."""

from pathlib import Path
import json
import shutil
import sys


TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
REPOSITORY = TOOLS.parent
SYNTHETIC_PROFILE = TESTS / "fixtures" / "synthetic_profile"

for path in (str(TESTS), str(TOOLS)):
    if path not in sys.path:
        sys.path.insert(0, path)
import kblib  # noqa: E402
import metadata_execution_contract  # noqa: E402
import module_boundary_facts  # noqa: E402
import standards_state  # noqa: E402
import stamp_cards  # noqa: E402
from canonical_registry_fixture import (  # noqa: E402
    contract_exception_owner_paths,
    install_isolated_tool_registry_bundle,
)

RUNTIME_ROUTES = ["R%02d" % number for number in range(1, 14)]
RUNTIME_SELECTED_ROUTES = ("R01", "R03", "R07")
FIXTURE_UPSTREAM_REVISION = "0123456789abcdef0123456789abcdef01234567"


def _runtime_route_paths(route_id):
    names = {
        "R01": "Core Bootstrap",
        "R03": "Module Build",
        "R07": "Long-running Execution",
    }
    label = names.get(route_id, "Fixture")
    return (
        "Card/%s %s Card.md" % (route_id, label),
        "Read Set/%s %s Read Set.md" % (route_id, label),
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
    """Install minimal current Card and Read Set declarations in fixtures."""
    card_directory = root / "Card"
    read_directory = root / "Read Set"
    card_directory.mkdir(parents=True, exist_ok=True)
    read_directory.mkdir(parents=True, exist_ok=True)
    conditional = "kernel/K03 Fixture/01 Conditional Review.md"
    conditional_path = root / conditional
    conditional_path.parent.mkdir(parents=True, exist_ok=True)
    conditional_path.write_text(
        "# Conditional Review\n\nRead this source after the Card declares the "
        "fixture trigger.\n", encoding="utf-8")
    phase_by_route = {
        "R08": "task-completion",
        "R09": "governance",
        "R12": "batch-gate",
    }
    for route_id in RUNTIME_ROUTES:
        card_relative, read_relative = _runtime_route_paths(route_id)
        read_path = root / read_relative
        read_path.parent.mkdir(parents=True, exist_ok=True)
        edges = [{
            "edge_id": "%s:start" % route_id,
            "kind": "required",
            "phase_id": phase_by_route.get(
                route_id, "batch-preflight"),
            "trigger_id": "route-selected",
            "targets": [conditional],
            "read_sets": [],
        }]
        if route_id == "R03":
            edges.append({
                "edge_id": "R03:conditional",
                "kind": "read-back",
                "phase_id": "batch-running",
                "trigger_id": "R03:semantic-condition",
                "targets": [conditional],
                "read_sets": [],
            })
        declaration = {
            "type": "read-set",
            "schema_version": 1,
            "route_id": route_id,
            "activation_phase": phase_by_route.get(
                route_id, "batch-preflight"),
            "narrowable": route_id not in ("R01", "R08", "R09"),
            "load_edges": edges,
        }
        read_text = (
            "---\n%s---\n# %s Fixture Read Set\n\n## Purpose\n\n"
            "Bound the already selected fixture route.\n\n"
            "## Non-deterministic triggers\n\n"
            "The fixture conditional is declared by identity.\n" %
            (kblib.canonical_yaml(declaration), route_id))
        read_path.write_text(read_text, encoding="utf-8")
        source_hash = stamp_cards.source_digest(root, [read_relative])
        card = {
            "type": "card",
            "generation_mode": "curated",
            "route_id": route_id,
            "read_set_id": route_id,
            "read_set": read_relative,
            "source_files": [read_relative],
            "source_hash": source_hash,
            "reviewed_source_hash": source_hash,
            "reviewed_card_hash": "000000000000",
        }
        card_path = root / card_relative
        card_path.parent.mkdir(parents=True, exist_ok=True)
        card_path.write_text(
            "---\n%s---\n# %s Fixture Card\n\n"
            "## Purpose\n\nAct on an already selected fixture route.\n\n"
            "## Actions\n\n- Invoke the fixture capability.\n\n"
            "## Stop or escalate\n\n- Stop when fixture input is absent.\n\n"
            "## Read-back hook\n\nReturn to Read Set `%s`.\n" %
            (kblib.canonical_yaml(card), route_id, route_id),
            encoding="utf-8")
        card_text = card_path.read_text(encoding="utf-8")
        card_path.write_text(stamp_cards.replace_frontmatter_scalar(
            card_text, "reviewed_card_hash",
            stamp_cards.card_body_digest(card_text)), encoding="utf-8")

    (card_directory / "Card Index.md").write_text(
        "---\ntype: card-index\ngeneration_mode: generated\n"
        "source: fixture declarations\n---\n# Fixture Card Index\n",
        encoding="utf-8")
    (read_directory / "Read Sets Index.md").write_text(
        "---\ntype: route-index\ngeneration_mode: generated\n"
        "source: fixture declarations\n---\n# Fixture Read Set Index\n",
        encoding="utf-8")

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
    # Every selected runtime Read Set declares the same required fixture
    # target.  Freeze that resolved direct-target union into the Task Contract
    # just as the real task-plan/adoption writer does; leaving it empty makes
    # the shared fixture itself under-declare its canonical load closure.
    contract["loaded_module_paths"] = [conditional]
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
                             override_rows="",
                             standards_version=FIXTURE_UPSTREAM_REVISION):
    """Overlay a real Profile and the production dependencies it consumes.

    Runtime tests consume one shared R01-R13 activation declaration set so
    separate fixtures cannot claim the same route identity differently.
    """
    root = Path(root)
    # Copied production modules resolve their Kernel-owned registries against
    # this scratch root at import time. Install the complete canonical bundle
    # through one fixture owner rather than growing per-test path lists.
    install_isolated_tool_registry_bundle(root)
    # The contract-exception registry validates owner *existence*, while its
    # YAML remains the sole machine authority.  Exact copies of those prose
    # owners pull their full Wiki Link graph into this deliberately isolated
    # repository and make an unrelated link Gate fail on absent modules.
    # Replace only those explanatory pages with link-free fixture owners; do
    # not recreate any registry values in prose.
    for relative in contract_exception_owner_paths():
        owner = root / relative
        owner.write_text(
            "# Fixture Kernel Owner\n\n"
            "The canonical machine policy is installed from the Kernel "
            "registry.\n",
            encoding="utf-8",
        )
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

    (root / "Tools/schemas").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        TOOLS / "schemas/execution_defaults.template.yaml",
        root / "Tools/schemas/execution_defaults.template.yaml",
    )
    # A registered production consumer needs the verifier's whole shipped
    # dependency closure, not one copied entry-point file that crashes when
    # invoked in the adopting repository.  Derive that closure from the same
    # module-boundary owner used by distribution.
    module_boundary_facts.stage_shipped_modules(
        str(REPOSITORY), str(root), ["check_residual_content"])
    # ``profile-load`` and every metadata writer share one compiled authority
    # bundle.  Runtime fixtures install its canonical sources and after-image
    # together so tests exercise currentness rather than an implicit fallback
    # to the Cambium source checkout.
    (root / "Tools/compiled").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        TOOLS / "operation-capabilities.yaml",
        root / "Tools/operation-capabilities.yaml",
    )
    shutil.copy2(
        TOOLS / "runtime_paths.py",
        root / "Tools/runtime_paths.py",
    )
    shutil.copy2(
        TOOLS / "scan-capabilities.yaml",
        root / "Tools/scan-capabilities.yaml",
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
    # Bind the fixture projection to the exact implementation bytes copied
    # above. The source checkout may legitimately be testing an uncommitted
    # implementation revision while its committed projection still names HEAD.
    compiled = metadata_execution_contract.compile_metadata_execution_contract(
        str(root))
    kblib.atomic_write_text(
        root / metadata_execution_contract.DEFAULT_COMPILED_PATH,
        compiled.canonical_bytes.decode("utf-8"))
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
            "upstream_source_ref": "fixture://cambium",
            "upstream_revision_id": standards_version,
        }), encoding="utf-8")
    _install_runtime_activation_fixture(root)
    return profile
