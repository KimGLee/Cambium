"""Names this runtime may not disagree with anyone about.

Three kinds of fact live here and nothing else: this producer's own K00/12
identity, the canonical state-file paths and fingerprint grammars, and the
tool/version register of every peer producer whose receipts this runtime
reads back.  A constant is here because two modules would otherwise each
carry their own copy, and two copies of a version floor is how a receipt
comes to be judged against an era that never existed.

It imports nothing from the package by construction.  ``TOOL`` and
``TOOL_VERSION`` sit here rather than in the CLI entry for the same reason:
six modules read them, and reading them from ``check_queue`` would point
every one of those modules back at the façade.  The K00/12 authority for the
Gate rows is unaffected -- that is a registry fact, not an import.
"""

import re

import runtime_paths
from runtime_state_contract import (
    ACTIVE_STATES,
    EXECUTION_MODES,
    HOLDS,
    STATES,
    TASK_STATES,
    TERMINAL_STATES,
)


TOOL = "check_queue"
TOOL_VERSION = "1.25.0"
# 1.20.1 remains a producer-era identity for already-consumed maintenance
# gates. Current gate production and all live gate admission use 1.25.0;
# historical consumption replays the older receipt's own promised shape.
SUPPORTED_CHECK_QUEUE_TOOL_VERSIONS = frozenset((
    "1.20.1", "1.21.0", "1.22.0", "1.23.0", "1.24.0", "1.25.0",
))
# The `Check` cell K00/12 registers for every Gate this tool produces; each
# such Gate is distinguished by `Mode`, not by a second check name.
GATE_CHECK = "required_queue"
REGISTER_AMENDMENT_TOOL = "register_amendment"
REGISTER_AMENDMENT_TOOL_VERSION = "1.4.0"


APPLY_AMENDMENT_TOOL_VERSION = "1.4.0"
SUPPORTED_APPLY_AMENDMENT_TOOL_VERSIONS = frozenset((
    "1.1.0", "1.2.0", "1.3.0", "1.4.0",
))
COMPILE_QUEUE_TOOL_VERSION = "1.5.0"


QUEUE_PATH = runtime_paths.QUEUE_PATH
COVERAGE_PATH = runtime_paths.COVERAGE_PATH
PROGRESS_PATH = runtime_paths.PROGRESS_PATH
ACTIVE_STANDARDS_PATH = runtime_paths.ACTIVE_STANDARDS_PATH
WATERMARK_PATH = runtime_paths.WATERMARK_PATH


# Sentinel for require_receipt: accept any nonempty producer-era version
# on a sealed historical receipt (K12/10 producer-era identity).
ANY_PRODUCER_ERA_VERSION = object()

SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
BATCH_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


BATCH_CLOSE_TOOL = "check_batch_close"
BATCH_CLOSE_TOOL_VERSION = "1.12.0"
# Queue-transition *evidence protocol* emitted by
# ``kblib.make_queue_receipt``.  This is deliberately independent from
# ``Tools/update_queue.py``'s CLI/distribution TOOL_VERSION: changing the
# executable release does not reinterpret old transition evidence, while a
# receipt-shape change must advance this producer-era identity explicitly.
UPDATE_QUEUE_TOOL_VERSION = "1.5.0"
SUPPORTED_UPDATE_QUEUE_TOOL_VERSIONS = frozenset((
    "1.2.0", "1.3.0", "1.4.0", "1.5.0"))
APPLY_DELTA_TOOL_VERSION = "1.6.0"


CORPUS_PLAN_TOOL = "check_corpus_plan"
CORPUS_PLAN_TOOL_VERSION = "1.7.0"


MANUAL_ATTESTATION_TOOL = "manual-attestation"
MANUAL_ATTESTATION_TOOL_VERSION = "1.0.0"


BATCH_REVIEW_GATE_ID = "batch-review"


TERMINAL_PROOF_TOOL = "check_proof"
TERMINAL_PROOF_TOOL_VERSION = "1.17.0"


LEGACY_PROPERTY_ADOPTION_OPERATION = "legacy-property-adoption-v1"


# Producer eras whose close bundles externalize full candidate detail to a
# born-cold evidence file and keep only counts, the accepted-set fingerprint,
# and the policy-exception dispositions inline (K12/09 compact evidence).
# The sealing writer and the protocol versions whose cold archives this
# validator will vouch for.  Sealing is the one operation that removes bytes
# from a register, so an archive is exactly as trustworthy as the writer that
# produced it; a version whose protocol did not exclude concurrent appenders
# or bind its registers to a receipt cannot be certified after the fact.
SEAL_TOOL = "seal_receipts"


STANDARDS_ADOPTION_TOOL = "adopt_standards"
STANDARDS_ADOPTION_TOOL_VERSION = "1.9.0"


STANDARDS_ADOPTION_PLAN_PREFIX = runtime_paths.STANDARDS_ADOPTION_DELTA_ROOT


CONTRACT_AMENDMENT_TOOL_VERSION = "1.1.0"
