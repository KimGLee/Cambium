"""Minimal parsed Task Runtime objects for Runner unit tests.

These objects model the already-admitted output consumed by the Runner.  They
deliberately do not create a repository, load Profile or Kernel files, scan a
Receipt catalog, or execute any lifecycle producer.
"""

import copy


def parsed_runtime_state(**overrides):
    """Return one minimal, mutable admitted runtime snapshot.

    Callers may replace top-level fields through ``overrides`` and then adjust
    individual nested values for the decision branch under test.
    """
    result = {
        "root": "/fixture",
        "errors": [],
        "_writer_locks": [],
        "queue": {
            "task_id": "TASK-1",
            "upstream_revision_id": "a" * 40,
            "selected_profile_manifest": "profiles/example/profile.yaml",
            "queue_revision": "queue-revision-1",
            "state_revision": 1,
        },
        "_profile_authorized_view": {
            "selected_profile_manifest": "profiles/example/profile.yaml",
            "profile_snapshot_sha256": "sha256:" + "b" * 64,
        },
        "_active_standards_authorized_view": {
            "upstream_revision_id": "a" * 40,
        },
        "queue_sha256": "sha256:" + "1" * 64,
        "coverage_sha256": "sha256:" + "2" * 64,
        "progress_sha256": "sha256:" + "3" * 64,
        "progress": {
            "task_id": "TASK-1",
            "task_state": "active",
            "contract": {"completion_semantics": "build"},
        },
        "task_runtime": {
            "pending_guidance": [],
            "pending_amendments": [],
        },
        "items_by_id": {
            "B1": {
                "id": "B1",
                "state": "queued",
                "hold_state": "none",
                "order": 1,
            },
        },
        "ready": ["B1"],
        "remaining": 1,
        "applied_delta_receipts": [],
        "managed_deltas": [],
    }
    result.update(copy.deepcopy(overrides))
    return result
