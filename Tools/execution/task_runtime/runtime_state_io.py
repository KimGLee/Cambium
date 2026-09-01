"""Shared mechanical I/O for Cambium's three canonical runtime ledgers.

This module owns only path resolution, byte loading, restricted-YAML parsing,
and comparison with an already-declared before image.  Transaction policy and
the caller-specific refusal type remain with each writer.
"""

import Tools.platform.common.kblib as kblib
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract


def state_paths(root):
    """Resolve the three existing canonical state files inside ``root``."""
    return {
        "coverage": kblib.managed_repository_path(
            root, queue_runtime.COVERAGE_PATH, runtime_paths.STATE_ROOT,
            suffixes=(".yaml",), must_exist=True),
        "queue": kblib.managed_repository_path(
            root, queue_runtime.QUEUE_PATH, runtime_paths.STATE_ROOT,
            suffixes=(".yaml",), must_exist=True),
        "progress": kblib.managed_repository_path(
            root, queue_runtime.PROGRESS_PATH, runtime_paths.STATE_ROOT,
            suffixes=(".yaml",), must_exist=True),
    }


def read_state(paths):
    """Read exact bytes and parse the corresponding restricted-YAML values."""
    raw = {}
    documents = {}
    for name, path in paths.items():
        with open(path, "rb") as handle:
            raw[name] = handle.read()
        documents[name] = kblib.parse_yaml_subset(raw[name].decode("utf-8"))
    return raw, documents


def before_image_mismatch(plan, raw):
    """Return the first canonical-state CAS mismatch, or ``None``."""
    for name in runtime_state_contract.RUNTIME_LEDGER_IDS:
        expected = plan["before"]["%s_sha256" % name]
        actual = kblib.sha256_bytes(raw[name])
        if expected != actual:
            return (
                "%s is %s but the plan was prepared against %s; the runtime "
                "moved after this plan was confirmed, so re-prepare it rather "
                "than merging" % (name, actual, expected)
            )
    return None
