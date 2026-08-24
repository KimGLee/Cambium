"""What contract shape did a receipt's own producer version promise.

Pure semver predicates, no state.  History is judged against the era that
wrote it rather than against today's constants -- a receipt written by a
producer that had not yet learned to bind a profile cannot be refused for
failing to bind one.  Each floor is named for the promise it introduced, so
the reason a record is exempt is legible at the call site.
"""

import re

from queue_runtime.canon import SHA256_RE
from queue_runtime.primitives import nonempty_string


# ``check_proof`` 1.16 first bound the authorized Profile snapshot and typed
# closure. Version 1.17 additionally binds the three root-owned profile-load
# inputs and the complete repository snapshot. Historical replay applies each
# producer era's promised shape only.
PROFILE_BOUND_TERMINAL_PROOF_MIN_VERSION = (1, 16, 0)
PROFILE_INPUT_BOUND_TERMINAL_PROOF_MIN_VERSION = (1, 17, 0)
REPOSITORY_BOUND_TERMINAL_PROOF_MIN_VERSION = (1, 17, 0)


STANDARDS_ADOPTION_PROFILE_CONTRACT_MIN_VERSION = (1, 3, 0)
# The 1.5 producer records where the adopted revision came from: the
# distribution has no version numbers by design, so upstream/downstream
# comparability is the adoption record's job, not a prose convention's.
STANDARDS_ADOPTION_UPSTREAM_MIN_VERSION = (1, 5, 0)
STANDARDS_ADOPTION_PROFILE_INPUT_MIN_VERSION = (1, 4, 0)
STANDARDS_ADOPTION_OWNER_PROJECTION_MIN_VERSION = (1, 6, 0)


def standards_adoption_profile_contract_required(producer_tool_version):
    """Return whether this producer era promised a durable typed contract.

    Only an exact semantic version below 1.3 selects the legacy contract.  An
    absent or malformed producer identity fails closed onto the current shape
    instead of becoming a way to erase the new binding.
    """
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(producer_tool_version),
    )
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= \
        STANDARDS_ADOPTION_PROFILE_CONTRACT_MIN_VERSION


def standards_adoption_profile_inputs_required(producer_tool_version):
    """Return whether this producer era promised root input binding.

    Only an exact semantic version below 1.4 selects the legacy contract. An
    absent or malformed producer identity fails closed onto the current shape.
    """
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(producer_tool_version),
    )
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= \
        STANDARDS_ADOPTION_PROFILE_INPUT_MIN_VERSION


def standards_adoption_upstream_required(producer_tool_version):
    """Return whether this producer era promised an upstream identity.

    Only an exact semantic version below 1.5 selects the legacy shape.  An
    absent or malformed producer identity fails closed onto the current
    shape.
    """
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(producer_tool_version),
    )
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= \
        STANDARDS_ADOPTION_UPSTREAM_MIN_VERSION


def standards_adoption_owner_projection_required(producer_tool_version):
    """Return whether this producer era stored projected boundary owners."""
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(producer_tool_version),
    )
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= \
        STANDARDS_ADOPTION_OWNER_PROJECTION_MIN_VERSION


def standards_adoption_state_file_required(producer_tool_version):
    """Return whether this era owns adopter identity in the state file."""
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(producer_tool_version),
    )
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= (1, 7, 0)


def accounted_standards_versions(progress, queue=None):
    """Return the Standards versions this instance's own history accounts for.

    A receipt sealed into append-only history carries the producer identity of
    the Standards revision that emitted it.  K00/03 requires a producer's
    ``Tool version`` cell to move in the revision that changes its accept or
    reject set, so honouring that checklist retires the constant every past
    receipt was stamped with -- and no sanctioned transaction may rewrite a
    historical receipt to carry the new one.  Comparing a historical
    ``tool_version`` against today's constant therefore invalidates history for
    having been produced under an older Standards identity, which is precisely
    what K12/10 forbids.

    What is checkable without today's constants is internal consistency: the
    era a receipt claims must be an era this instance actually passed through.
    Each adoption record contributes both ends of the step it recorded, and the
    live Queue/contract identity covers the instance that has adopted nothing
    yet.  ``standards_version`` is the right field to carry this: it is already
    the field that demotes a receipt from current authorization the moment an
    adoption moves it, so it is also the field that states which Standards
    identity produced it.
    """
    versions = set()
    if isinstance(queue, dict) and nonempty_string(
            queue.get("standards_version")):
        versions.add(queue["standards_version"])
    if not isinstance(progress, dict):
        return versions
    contract = progress.get("contract")
    if isinstance(contract, dict) and nonempty_string(
            contract.get("standards_version")):
        versions.add(contract["standards_version"])
    records = progress.get("standards_adoptions")
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        for field in ("standards_version_before", "standards_version_after"):
            if nonempty_string(record.get(field)):
                versions.add(record[field])
    return versions


def producer_era_errors(receipt, receipt_id, label, accounted):
    """Return errors when a historical receipt claims an unaccounted era.

    This is what replaces a historical receipt's ``tool_version`` comparison
    against the current producer constant.  A receipt claiming a Standards
    version no adoption record and no live identity accounts for is one this
    instance never produced, so the replacement has teeth without freezing
    today's producer versions into the definition of valid history.  A
    current-action predicate keeps comparing the producer tuple exactly; see
    :func:`receipt_matches_gate_id`.

    A receipt that carries no ``standards_version`` claims no era, and absence
    is not an error here.  Demanding the field would repeat the very mistake
    this function removes: it would invalidate every receipt written before the
    identity fields existed, for a reason its producer could not have
    anticipated and no sanctioned transaction can repair.  Per ``kblib``, an
    omitted identity field already behaves as ``null`` against every consumer
    that compares it, so such a receipt is judged by its remaining bindings.
    """
    if not isinstance(receipt, dict):
        return []
    version = receipt.get("standards_version")
    if not nonempty_string(version) or version in accounted:
        return []
    return ["%s receipt %s claims standards_version=%r, which no Standards "
            "adoption record or live identity of this instance accounts for" %
            (label, receipt_id, version)]


def terminal_proof_profile_binding_errors(receipt, receipt_id):
    """Validate each current-use binding promised by its proof producer era.

    This is historical replay, not a new authorization decision.  It therefore
    checks only that a receipt retained the canonical fields its own producer
    promised: 1.16 introduced Profile snapshot/typed-contract bindings, and
    1.17 added the root-owned profile-load input and whole-repository snapshot
    bindings. It deliberately does not load today's selected Profile or
    reinterpret an already-consumed proof against changed bytes. The current
    completion transition performs those comparisons in :mod:`update_task`
    before history is sealed.
    """
    if not isinstance(receipt, dict):
        return []
    version = receipt.get("tool_version")
    match = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\."
                         r"(0|[1-9][0-9]*)", str(version))
    if match is None:
        return []
    version_tuple = tuple(int(part) for part in match.groups())
    if version_tuple < PROFILE_BOUND_TERMINAL_PROOF_MIN_VERSION:
        return []
    fields = [
        "profile_snapshot_sha256", "profile_contract_fingerprint",
    ]
    if version_tuple >= PROFILE_INPUT_BOUND_TERMINAL_PROOF_MIN_VERSION:
        fields.append("profile_load_inputs_sha256")
    if version_tuple >= REPOSITORY_BOUND_TERMINAL_PROOF_MIN_VERSION:
        fields.append("repository_snapshot_sha256")
    errors = []
    for field in fields:
        if not SHA256_RE.fullmatch(str(receipt.get(field))):
            errors.append(
                "complete Terminal Proof receipt %s lacks canonical %s "
                "required by check_proof %s" %
                (receipt_id, field, version)
            )
    return errors
