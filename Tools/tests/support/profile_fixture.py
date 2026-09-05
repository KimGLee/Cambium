"""Shared complete Profile package for runtime-control test repositories."""

from pathlib import Path
import json
import shutil
import sys


TESTS = Path(__file__).resolve().parents[1]
TOOLS = TESTS.parent
REPOSITORY = TOOLS.parent

for path in (str(TESTS), str(TOOLS)):
    if path not in sys.path:
        sys.path.insert(0, path)
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.governance.profile.check_profile as check_profile  # noqa: E402
import Tools.platform.distribution.module_boundary_facts as module_boundary_facts  # noqa: E402
import Tools.governance.standards.adoption_lineage_contract as adoption_lineage_contract  # noqa: E402
import Tools.governance.standards.standards_state as standards_state  # noqa: E402
import Tools.platform.distribution.stamp_cards as stamp_cards  # noqa: E402
import Tools.execution.context_delivery.read_set_contract as read_set_contract  # noqa: E402
from Tools.tests.support.canonical_registry_fixture import (  # noqa: E402
    contract_exception_owner_paths,
)
from Tools.tests.support.initial_task_plan_fixture import (  # noqa: E402
    install_initial_task_plan_fixture,
)
from Tools.tests.support.profile_contract_fixture import (  # noqa: E402
    install_profile_package,
)
from Tools.tests.support.profile_load_fixture import (  # noqa: E402
    install_current_profile_load_inputs,
)

def _runtime_routes():
    """Derive the fixture route closed set from shipped Read Set owners."""
    routes = set()
    for path in sorted((REPOSITORY / "Read Set").glob("R*.md")):
        raw = kblib.extract_frontmatter(path.read_text(encoding="utf-8"))
        if raw is None:
            continue
        declaration = kblib.parse_yaml_subset(raw)
        if declaration.get("type") != "read-set":
            continue
        route_id = declaration.get("route_id")
        if not isinstance(route_id, str) or not route_id:
            raise AssertionError("Read Set fixture route identity is invalid: %s" % path)
        if route_id in routes:
            raise AssertionError("duplicate Read Set fixture route: %s" % route_id)
        routes.add(route_id)
    if not routes:
        raise AssertionError("shipped Read Sets declare no runtime routes")
    return tuple(sorted(routes))


RUNTIME_ROUTES = _runtime_routes()
RUNTIME_SELECTED_ROUTES = ("R01", "R03", "R07")
FIXTURE_UPSTREAM_REVISION = "0123456789abcdef0123456789abcdef01234567"
FIXTURE_ADOPTION_RECEIPT_ID = "audit-fixture-standards-adoption"


def install_current_adoption_fixture(root, profile, *, replace_current=False):
    """Materialize the evidence chain named by the synthetic current state.

    Runtime fixtures previously created only the state-side pointer.  That
    made the fixture assert an adoption had happened while omitting K00/03's
    canonical history.  Derive the Profile fingerprints from the real
    profile-load producer and use the production lineage contract's producer
    identities, so the fixture cannot silently invent a second receipt identity.
    """
    state_path = root / standards_state.STATE_PATH
    state = kblib.load_yaml_file(state_path)
    adoption_receipt_id = state.get("latest_adoption_receipt")
    if not isinstance(adoption_receipt_id, str) or not adoption_receipt_id:
        return
    receipt_path = root / adoption_lineage_contract.ADOPTION_RECEIPT_PATH
    existing = []
    if receipt_path.exists():
        existing = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
    current = next((record for record in existing
                    if isinstance(record, dict) and
                    record.get("receipt_id") == adoption_receipt_id), None)
    if current is not None and not replace_current:
        return
    if current is not None:
        linked_gate = current.get("profile_load_receipt_id")
        existing = [
            record for record in existing
            if record.get("receipt_id") not in {
                adoption_receipt_id, linked_gate,
            }
        ]

    evaluation = check_profile.evaluate_profile_load(
        str(profile), root=str(root),
        receipt_identity={
            "selected_profile_manifest":
                state["selected_profile_manifest"],
        },
    )
    if not evaluation.authorized:
        raise AssertionError(
            "shared runtime fixture Profile is not loadable: %s" %
            evaluation.output)
    gate = dict(evaluation.summary_receipt)
    adoption = kblib.make_receipt(
        adoption_lineage_contract.PROFILE_ADOPTION_TOOL,
        adoption_lineage_contract.PROFILE_ADOPTION_TOOL_VERSION,
        "profile_adoption", "fixture-profile-adoption", "pass",
        "fixture current Standards/Profile adoption", 1,
        receipt_type_id=(
            adoption_lineage_contract.PROFILE_ADOPTION_RECEIPT_TYPE_ID
        ),
        identity={
            "selected_profile_manifest":
                state["selected_profile_manifest"],
        },
    )
    adoption["receipt_id"] = adoption_receipt_id
    adoption.update({
        "upstream_revision_id_after": state["upstream_revision_id"],
        "selected_profile_manifest_after":
            state["selected_profile_manifest"],
        "standards_effective_date_after": state["effective_date"],
        "standards_state_sha256_after": kblib.sha256_file(state_path),
        "upstream_source_ref": state["upstream_source_ref"],
        "profile_snapshot_sha256_after":
            evaluation.profile_snapshot_sha256,
        "profile_contract_fingerprint_after":
            evaluation.profile_contract_fingerprint,
        "profile_load_inputs_sha256_after":
            evaluation.profile_load_inputs_sha256,
        "profile_load_gate_id":
            adoption_lineage_contract.PROFILE_LOAD_GATE_ID,
        "profile_load_receipt_id": gate["receipt_id"],
    })
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) +
                "\n" for record in existing + [gate, adoption]),
        encoding="utf-8",
    )


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
    read_set_schema_version = read_set_contract.load_schema(
        root)["schema_version"]
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
            "schema_version": read_set_schema_version,
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
        _runtime_index_text("card-index", True), encoding="utf-8")
    (read_directory / "Read Sets Index.md").write_text(
        _runtime_index_text("route-index", False), encoding="utf-8")

    # The shared seed predates Task Plan derivation. Give it the complete
    # frozen envelope that the current fixture writer will publish below.
    # The seed deliberately carries no Receipt: a current typed Receipt is
    # created only after the Profile and its Task Plan are both available.
    progress_path = root / ".cambium/state/progress_ledger.yaml"
    if not progress_path.exists():
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


def install_loadable_profile(root, profile_id="test-profile",
                             upstream_revision_id=FIXTURE_UPSTREAM_REVISION,
                             before_adoption=None):
    """Install a typed Profile for tests that own an actual runtime lifecycle.

    Local contract/adapter tests use install_profile_package instead. Only
    this runtime fixture creates the declared current adoption evidence and
    completes a pre-existing task checkpoint.
    """
    root = Path(root)
    install_current_profile_load_inputs(root)
    # Keep prose-only explanatory owners link-free in the isolated runtime
    # corpus; their machine policy remains the current copied Kernel source.
    for relative in contract_exception_owner_paths():
        owner = root / relative
        owner.write_text(
            "# Fixture Kernel Owner\n\n"
            "The canonical machine policy is installed from the Kernel "
            "registry.\n", encoding="utf-8")
    profile = root / "profiles" / profile_id
    install_profile_package(profile, profile_id)
    (root / "Tools/schemas").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        TOOLS / "schemas/execution_defaults.template.yaml",
        root / "Tools/schemas/execution_defaults.template.yaml")
    module_boundary_facts.stage_shipped_modules(
        str(REPOSITORY), str(root), ["check_residual_content"])
    active = root / standards_state.STATE_PATH
    active.parent.mkdir(parents=True, exist_ok=True)
    if not active.exists():
        active.write_text(standards_state.canonical_text({
            "schema_version": standards_state.SCHEMA_VERSION,
            "state_revision": 1,
            "upstream_revision_id": upstream_revision_id,
            "status": "approved",
            "effective_date": "2026-08-01",
            "selected_profile_manifest":
                "profiles/%s/profile.toml" % profile_id,
            "latest_adoption_receipt": FIXTURE_ADOPTION_RECEIPT_ID,
            "upstream_source_ref": "fixture://cambium",
        }), encoding="utf-8")
    _install_runtime_activation_fixture(root)
    if before_adoption is not None:
        before_adoption(root, profile)
    install_current_adoption_fixture(root, profile)
    progress_path = root / ".cambium/state/progress_ledger.yaml"
    if progress_path.is_file():
        progress = kblib.load_yaml_file(progress_path)
        if not isinstance(progress.get("initial_task_plan_receipt"), str):
            install_initial_task_plan_fixture(root)
    return profile
