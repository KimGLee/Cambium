"""The Required Queue runtime, as modules instead of one file.

`check_queue.py` was seventeen thousand lines holding one runtime, one CLI and
one Gate producer, and the boundary contract in K00/18 could say nothing about
its inside: a module is the unit the contract speaks about, so a single module
is a single answer to every question the contract asks.  The runtime is split
here into named responsibilities with a declared direction between them; the
CLI entry and the Gate producer stay in `check_queue.py`, which also remains
the permanent façade every existing importer and test reads.

Two rules hold this together and both are machine-checked.  Intra-package
imports are absolute and name the defining submodule -- never `from . import`,
which the boundary collector cannot see, and never the package root, which
would point a submodule back at this file.  And every intra-package edge runs
strictly downward through the declared ranks, because `import_graph` collapses
a package to one node and cannot see a cycle that stays inside it.

This file re-exports the surface the façade needs and defines nothing.  A name
is exported here because something outside the package reads it, which is also
what makes the register able to say who offers what.
"""

import os
import sys

# Every submodule reads peer tools by their plain names, exactly as
# the rest of Tools/ does.  The package entry is the one place that
# can put the tools root on the path before any of them load.
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from queue_runtime.canon import (  # noqa: F401
    ACTIVE_STANDARDS_PATH,
    ACTIVE_STATES,
    ANY_PRODUCER_ERA_VERSION,
    APPLY_AMENDMENT_TOOL_VERSION,
    APPLY_DELTA_TOOL_VERSION,
    BATCH_CLOSE_TOOL,
    BATCH_CLOSE_TOOL_VERSION,
    BATCH_ID_RE,
    BATCH_REVIEW_GATE_ID,
    CONTRACT_AMENDMENT_TOOL_VERSION,
    CORPUS_PLAN_TOOL,
    CORPUS_PLAN_TOOL_VERSION,
    COVERAGE_PATH,
    EXECUTION_MODES,
    GATE_CHECK,
    HOLDS,
    LEGACY_PROPERTY_ADOPTION_OPERATION,
    MANUAL_ATTESTATION_TOOL,
    MANUAL_ATTESTATION_TOOL_VERSION,
    PROGRESS_PATH,
    QUEUE_PATH,
    REGISTER_AMENDMENT_TOOL,
    REGISTER_AMENDMENT_TOOL_VERSION,
    SEAL_TOOL,
    SHA256_RE,
    STANDARDS_ADOPTION_PLAN_PREFIX,
    STANDARDS_ADOPTION_TOOL,
    STANDARDS_ADOPTION_TOOL_VERSION,
    STATES,
    SUPPORTED_APPLY_AMENDMENT_TOOL_VERSIONS,
    SUPPORTED_CHECK_QUEUE_TOOL_VERSIONS,
    SUPPORTED_UPDATE_QUEUE_TOOL_VERSIONS,
    TASK_STATES,
    TERMINAL_PROOF_TOOL,
    TERMINAL_PROOF_TOOL_VERSION,
    TERMINAL_STATES,
    TOOL,
    TOOL_VERSION,
    UPDATE_QUEUE_TOOL_VERSION,
)
from queue_runtime.primitives import (  # noqa: F401
    _acyclic,
    _closed_mapping_errors,
    _explicit_string_list_errors,
    _identity,
    _nonempty_string,
    _timestamp_value,
    _valid_timestamp,
)
from queue_runtime.repofs import (  # noqa: F401
    _load_state,
    _normalized_repository_path,
    _path_error,
    _repository_evidence_file,
)
from queue_runtime.evidence_identity import (  # noqa: F401
    EVIDENCE_IDENTITY_USES,
    EVIDENCE_USE_ACTIVE_TRANSACTION,
    EVIDENCE_USE_COMPLETED_EVENT,
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    EVIDENCE_USE_TERMINAL_HISTORY,
    _current_property_receipt,
    evidence_identity_errors,
    property_receipt_utc_date,
)
