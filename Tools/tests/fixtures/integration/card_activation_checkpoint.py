"""Minimal current-contract repository checkpoint for Card activation.

The checkpoint installs the current Profile owner inputs and evaluates one
minimal complete Profile through the real profile-load Gate. It then joins
that admitted view to a local R01 Card/Read Set pair and fixed Queue/Standards
inputs. It never replays adoption or Task lifecycle work.
"""

from pathlib import Path
import shutil

import Tools.execution.context_delivery.card_activation as card_activation
import Tools.platform.common.kblib as kblib
import Tools.platform.distribution.stamp_cards as stamp_cards
from Tools.execution.task_runtime.queue_runtime import profile_view
from Tools.tests.support.profile_contract_fixture import install_profile_package
from Tools.tests.support.profile_load_fixture import install_current_profile_load_inputs


REPOSITORY = Path(__file__).resolve().parents[4]
CONTRACT_FILES = (
    "Tools/schemas/card.schema.yaml",
    "Read Set/read-set.schema.yaml",
    "Card/card-budget.yaml",
)
CARD_PATH = "Card/R01 Fixture Card.md"
READ_SET_PATH = "Read Set/R01 Fixture Read Set.md"
PROFILE_PATH = "profiles/test/profile.toml"


def _write(root, relative, text):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha(label):
    return kblib.sha256_bytes(label.encode("utf-8"))


def install_checkpoint(root):
    """Return one Card checkpoint containing an actual admitted Profile view."""
    root = Path(root).resolve()
    install_current_profile_load_inputs(root)
    install_profile_package((root / PROFILE_PATH).parent, profile_id="test")
    for relative in CONTRACT_FILES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY / relative, target)

    source_path = "kernel/fixture.md"
    _write(root, source_path, "# Fixture source\n")
    read_set = {
        "type": "read-set",
        "schema_version": 1,
        "route_id": "R01",
        "activation_phase": card_activation.PHASE_BATCH_PREFLIGHT,
        "narrowable": False,
        "load_edges": [{
            "edge_id": "R01:start",
            "kind": "required",
            "phase_id": card_activation.PHASE_BATCH_PREFLIGHT,
            "trigger_id": "route-selected",
            "targets": [source_path],
            "read_sets": [],
        }],
    }
    _write(
        root,
        READ_SET_PATH,
        "---\n%s---\n# R01 Fixture Read Set\n\n"
        "## Purpose\n\nFixture load boundary.\n\n"
        "## Non-deterministic triggers\n\nNone.\n" %
        kblib.canonical_yaml(read_set),
    )

    body = (
        "# R01 Fixture Card\n\n"
        "## Purpose\n\nFixture action boundary.\n\n"
        "## Actions\n\n- Read the selected source.\n\n"
        "## Stop or escalate\n\n- Stop when the source is unavailable.\n\n"
        "## Read-back hook\n\nReturn to the paired Read Set.\n"
    )
    card = {
        "type": "card",
        "generation_mode": "curated",
        "route_id": "R01",
        "read_set_id": "R01",
        "read_set": READ_SET_PATH,
        "source_files": [READ_SET_PATH, source_path],
        "source_hash": "0" * 12,
        "reviewed_source_hash": "0" * 12,
        "reviewed_card_hash": "0" * 12,
    }
    provisional = "---\n%s---\n%s" % (kblib.canonical_yaml(card), body)
    source_hash = stamp_cards.source_digest(root, card["source_files"])
    card.update({
        "source_hash": source_hash,
        "reviewed_source_hash": source_hash,
        "reviewed_card_hash": stamp_cards.card_body_digest(provisional),
    })
    _write(root, CARD_PATH,
           "---\n%s---\n%s" % (kblib.canonical_yaml(card), body))
    admitted_profile, errors = profile_view.profile_load_authorized_view(root, PROFILE_PATH)
    if errors:
        raise AssertionError("Card checkpoint Profile failed admission: " + "; ".join(errors))
    progress = {
        "task_id": "TASK-1",
        "contract": {
            "upstream_revision_id": "current-upstream",
            "selected_profile_manifest": PROFILE_PATH,
            "selected_route_ids": ["R01"],
            "selected_card_paths": [CARD_PATH],
            "selected_profile_route_ids": [],
            "selected_read_sets": [READ_SET_PATH],
            "loaded_module_paths": [],
        },
    }
    item = {"id": "B1", "manifest": ["Topics/A.md"]}
    queue = {
        "task_id": "TASK-1",
        "upstream_revision_id": "current-upstream",
        "selected_profile_manifest": PROFILE_PATH,
        "queue_revision": 1,
        "state_revision": 1,
    }
    runtime = {
        "root": root,
        "queue": queue,
        "queue_sha256": _sha("queue"),
        "coverage_sha256": _sha("coverage"),
        "progress_sha256": kblib.sha256_bytes(
            kblib.canonical_yaml(progress)),
        "progress": progress,
        "items_by_id": {"B1": item},
        "_profile_authorized_view": admitted_profile,
        "_active_standards_authorized_view": {
            "active_standards_sha256": _sha("active-standards"),
        },
    }
    return progress, item, runtime
