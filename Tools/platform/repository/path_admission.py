"""Transport-neutral admission of compiled path capabilities.

Callers supply the selected Tool contract and authorized invocation. This
module only binds its declared paths to retained filesystem objects; it owns
no governance, runtime selection, registry or RPC interpretation.
"""

import os
import stat
import contextlib
import json
import uuid
from dataclasses import dataclass

from Tools.platform.agent_interface.agent_interface_contract import PATH_EXTENSION_KEY
from Tools.platform.agent_interface import agent_interface_contract as interface


class PathAdmissionError(ValueError):
    def __init__(self, message, data=None):
        super().__init__(message)
        self.message = message
        self.data = data or {}


@dataclass(frozen=True)
class DelegationScope:
    """Validated parent authority and its local consumption sink, never wire input."""

    workspace_identity: tuple
    records: tuple
    acknowledge: object


def _delegated_inputs(rows, workspace_fd, parent_scope):
    if parent_scope is None:
        return {}
    if not isinstance(parent_scope, DelegationScope):
        raise PathAdmissionError("child requires a validated parent delegation scope")
    identity = os.fstat(workspace_fd)
    if ((identity.st_dev, identity.st_ino) != parent_scope.workspace_identity or
            not callable(parent_scope.acknowledge)):
        raise PathAdmissionError("child delegation differs from the parent workspace")
    delegated = {}
    for row in rows:
        for parent in parent_scope.records:
            exact = row["spelling"] == parent["spelling"]
            nested = (parent["kind"] == "directory" and
                      (parent["spelling"] == "." or
                       row["spelling"].startswith(parent["spelling"] + "/")))
            if not (exact or nested):
                continue
            if (parent["consumption"] != "transaction" and
                    parent["consumption"] != row["consumption"]):
                raise PathAdmissionError("child cannot widen inherited path mode")
            inherited_target, opened = retain_path(
                "delegated child", row["argument"], workspace_fd,
                parent["spelling"], parent, 0)
            try:
                expected = (parent["target_dev"], parent["target_ino"])
                if (inherited_target["target_dev"], inherited_target["target_ino"]) != expected:
                    raise PathAdmissionError("child path no longer names inherited effective target")
                if exact and (row["target_dev"], row["target_ino"]) != expected:
                    raise PathAdmissionError("child input differs from the retained parent object")
            finally:
                for fd in opened:
                    os.close(fd)
            # Independent write admissions cannot settle/advance their parent's
            # write scope through a read ACK. Current Runner outer inputs are
            # snapshots. Same-scope writer children retain their existing I/O
            # channel through kblib, including its after-image machinery.
            if row["consumption"] != "snapshot":
                raise PathAdmissionError(
                    "independent child cannot delegate a parent write scope; "
                    "use the admitted writer's same-scope I/O")
            if exact and parent["consumption"] == "snapshot":
                delegated.setdefault(row["capability_id"], []).append(parent)
            # A subtree read is not consumption of the full parent tree, and
            # a narrowed snapshot cannot complete a parent transaction scope.
    return delegated


@contextlib.contextmanager
def invocation(tool, arguments, workspace_root, workspace_fd, environment,
               *, parent_scope=None):
    """Own the lifetime of one invocation's root, arguments, FDs and ACKs.

    The orchestrator supplies an already authorized Tool selection. No registry
    is loaded here, and a child invocation gets its own consumption channel.
    """
    rows, descriptors = admit_paths(tool, arguments, workspace_root, workspace_fd)
    scope = uuid.uuid4().hex
    for row in rows:
        row["capability_id"] = scope + ":" + row["capability_id"]
    try:
        delegated = _delegated_inputs(rows, workspace_fd, parent_scope)
    except BaseException:
        for fd in descriptors:
            os.close(fd)
        raise
    values = dict(arguments)
    values[tool["workspace_argument"]] = "."
    for name, prop in tool["schema"]["properties"].items():
        cap = prop.get(PATH_EXTENSION_KEY)
        if (name not in values and cap is not None and
                capability_is_active(cap, values) and prop.get("default") is not None):
            values[name] = prop["default"]
    ack_read, ack_write = os.pipe()
    env = dict(environment)
    identity = os.fstat(workspace_fd)
    env.update({
        interface.WORKSPACE_ENV: workspace_root,
        interface.WORKSPACE_FD_ENV: str(workspace_fd),
        interface.PATH_CAPABILITIES_ACK_ENV: str(ack_write),
        interface.PATH_CAPABILITIES_ENV: json.dumps({
            "schema_version": 1, "tool": tool["name"],
            "workspace_dev": identity.st_dev, "workspace_ino": identity.st_ino,
            "capabilities": rows,
        }),
    })
    binding = {"arguments": values, "rows": rows, "env": env,
               "pass_fds": tuple([workspace_fd, ack_write] + descriptors)}
    try:
        yield binding
    finally:
        os.close(ack_write)
        for descriptor in descriptors:
            os.close(descriptor)
        try:
            observed = b""
            while True:
                chunk = os.read(ack_read, 65536)
                if not chunk:
                    break
                observed += chunk
            binding["acknowledgement_error"] = None
            try:
                decoded = observed.decode("utf-8")
                acknowledged = set(decoded.splitlines())
                if decoded and not decoded.endswith("\n"):
                    binding["acknowledgement_error"] = "partial capability acknowledgement"
            except UnicodeError as exc:
                acknowledged = set()
                binding["acknowledgement_error"] = str(exc)
            required = {row["capability_id"] for row in rows}
            if not acknowledged.issubset(required):
                binding["acknowledgement_error"] = "foreign capability acknowledgement"
            binding["acknowledged"] = sorted(acknowledged & required)
            binding["missing"] = sorted(required - acknowledged)
            binding["delegated_consumptions"] = []
            if not binding["acknowledgement_error"]:
                try:
                    for child_id in binding["acknowledged"]:
                        for parent in delegated.get(child_id, ()):
                            parent_scope.acknowledge(parent)
                            binding["delegated_consumptions"].append(parent["capability_id"])
                except (OSError, ValueError) as exc:
                    binding["acknowledgement_error"] = "parent consumption settlement failed: %s" % exc
        finally:
            os.close(ack_read)


def _path_values(tool_name, argument, value):
    """Yield path strings from one scalar or list-valued path argument."""
    values = value if isinstance(value, list) else [value]
    for item in values:
        if not isinstance(item, str) or not item or item != item.strip() or \
                "\x00" in item:
            raise PathAdmissionError(
                "%s.%s must carry non-empty canonical path strings" %
                (tool_name, argument),
                {"tool": tool_name, "argument": argument})
        yield item


def _bound_path(workspace_root, spelling):
    candidate = spelling if os.path.isabs(spelling) else \
        os.path.join(workspace_root, spelling)
    return os.path.realpath(os.path.abspath(candidate))


def canonical_spelling(tool_name, argument, spelling):
    """Require one stable repository-relative spelling at the invocation boundary."""
    if os.path.isabs(spelling) or "\\" in spelling or \
            os.path.normpath(spelling).replace(os.sep, "/") != spelling or \
            spelling == ".." or spelling.startswith("../"):
        raise PathAdmissionError(
            "%s.%s must use a canonical repository-relative path" %
            (tool_name, argument),
            {"tool": tool_name, "argument": argument})
    return spelling


def capability_is_active(capability, arguments):
    """Evaluate one compiled, closed operation-mode predicate."""
    active_when_any = capability.get("active_when_any") or []
    inactive_when_any = capability.get("inactive_when_any") or []
    positive = (not active_when_any or
                any(arguments.get(name) is True
                    for name in active_when_any))
    excluded = any(arguments.get(name) is True
                   for name in inactive_when_any)
    return positive and not excluded


def retain_path(tool_name, argument, workspace_fd, spelling,
                capability, value_index):
    """Retain the admitted target and parent objects for one typed path.

    Validation that closes a descriptor has only moved a pathname race.  This
    walk returns the exact descriptors a cooperating tool must consume: the
    existing target object for a snapshot, and the stable parent object for a
    create, append, replacement, or transaction.  The original spelling is
    retained only as display/lookup identity; it grants no filesystem reach.
    """
    if spelling == ".":
        components = []
    else:
        components = spelling.split("/")
    current_fd = os.dup(workspace_fd)
    retained = []
    try:
        if not components:
            target_fd = os.dup(current_fd)
            retained.append(target_fd)
            descriptor = os.fstat(target_fd)
            return ({
                "capability_id": "%s[%d]" % (argument, value_index),
                "argument": argument,
                "value_index": value_index,
                "spelling": spelling,
                "access": capability["access"],
                "consumption": capability["consumption"],
                "constraint": capability["constraint"],
                "exists": True,
                "kind": "directory",
                "target_fd": target_fd,
                "parent_fd": None,
                "basename": ".",
                "missing_components": [],
                "target_dev": descriptor.st_dev,
                "target_ino": descriptor.st_ino,
            }, retained)
        for index, component in enumerate(components):
            try:
                metadata = os.stat(
                    component, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                # A may-create path is anchored by the deepest existing
                # parent opened from the frozen workspace directory.
                parent_fd = os.dup(current_fd)
                retained.append(parent_fd)
                parent = os.fstat(parent_fd)
                return ({
                    "capability_id": "%s[%d]" % (argument, value_index),
                    "argument": argument,
                    "value_index": value_index,
                    "spelling": spelling,
                    "access": capability["access"],
                    "consumption": capability["consumption"],
                    "constraint": capability["constraint"],
                    "exists": False,
                    "kind": "missing",
                    "target_fd": None,
                    "parent_fd": parent_fd,
                    "basename": components[-1],
                    "missing_components": components[index:],
                    "target_dev": None,
                    "target_ino": None,
                    "parent_dev": parent.st_dev,
                    "parent_ino": parent.st_ino,
                }, retained)
            except OSError as exc:
                raise PathAdmissionError(
                    "%s.%s cannot be inspected safely: %s" %
                    (tool_name, argument, exc),
                    {"tool": tool_name, "argument": argument})
            if stat.S_ISLNK(metadata.st_mode):
                raise PathAdmissionError(
                    "%s.%s traverses a symlink, which is not a canonical "
                    "workspace artifact" % (tool_name, argument),
                    {"tool": tool_name, "argument": argument})
            if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
                raise PathAdmissionError(
                    "%s.%s names a multiply-linked file, so its repository "
                    "identity is ambiguous" % (tool_name, argument),
                    {"tool": tool_name, "argument": argument})
            if index == len(components) - 1:
                if stat.S_ISDIR(metadata.st_mode):
                    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                elif stat.S_ISREG(metadata.st_mode):
                    if capability["consumption"] == "append":
                        flags = os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW
                    else:
                        flags = os.O_RDONLY | os.O_NOFOLLOW
                else:
                    raise PathAdmissionError(
                        "%s.%s must name a regular file or directory" %
                        (tool_name, argument),
                        {"tool": tool_name, "argument": argument})
                if hasattr(os, "O_CLOEXEC"):
                    flags |= os.O_CLOEXEC
                try:
                    target_fd = os.open(
                        component, flags, dir_fd=current_fd)
                except OSError as exc:
                    raise PathAdmissionError(
                        "%s.%s changed while its target was being retained: "
                        "%s" % (tool_name, argument, exc),
                        {"tool": tool_name, "argument": argument})
                opened = os.fstat(target_fd)
                if ((metadata.st_dev, metadata.st_ino) !=
                        (opened.st_dev, opened.st_ino)):
                    os.close(target_fd)
                    raise PathAdmissionError(
                        "%s.%s changed while its target was being retained" %
                        (tool_name, argument),
                        {"tool": tool_name, "argument": argument})
                target_kind = ("directory" if stat.S_ISDIR(opened.st_mode)
                               else "file")
                parent_fd = os.dup(current_fd)
                retained.extend((target_fd, parent_fd))
                parent = os.fstat(parent_fd)
                return ({
                    "capability_id": "%s[%d]" % (argument, value_index),
                    "argument": argument,
                    "value_index": value_index,
                    "spelling": spelling,
                    "access": capability["access"],
                    "consumption": capability["consumption"],
                    "constraint": capability["constraint"],
                    "exists": True,
                    "kind": target_kind,
                    "target_fd": target_fd,
                    "parent_fd": parent_fd,
                    "basename": component,
                    "missing_components": [],
                    "target_dev": opened.st_dev,
                    "target_ino": opened.st_ino,
                    "parent_dev": parent.st_dev,
                    "parent_ino": parent.st_ino,
                }, retained)
            if not stat.S_ISDIR(metadata.st_mode):
                raise PathAdmissionError(
                    "%s.%s has a non-directory parent component" %
                    (tool_name, argument),
                    {"tool": tool_name, "argument": argument})
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            try:
                next_fd = os.open(component, flags, dir_fd=current_fd)
            except OSError as exc:
                raise PathAdmissionError(
                    "%s.%s changed while its path was being inspected: %s" %
                    (tool_name, argument, exc),
                    {"tool": tool_name, "argument": argument})
            os.close(current_fd)
            current_fd = next_fd
        raise PathAdmissionError(
            "%s.%s capability retention reached no terminal state" %
            (tool_name, argument),
            {"tool": tool_name, "argument": argument})
    except Exception:
        for descriptor in retained:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    finally:
        os.close(current_fd)


def admit_paths(tool, arguments, workspace_root,
                workspace_fd):
    """Validate and retain every effective typed path capability."""
    root_real = os.path.realpath(os.path.abspath(workspace_root))
    workspace_argument = tool["workspace_argument"]
    if workspace_argument not in arguments:
        raise PathAdmissionError(
            "%s requires %s so the operation is bound to this "
            "session's workspace" % (tool["name"], workspace_argument),
            {"tool": tool["name"], "required_workspace_argument":
             workspace_argument})
    workspace_values = list(_path_values(
        tool["name"], workspace_argument, arguments[workspace_argument]))
    if len(workspace_values) != 1 or \
            _bound_path(root_real, workspace_values[0]) != root_real:
        raise PathAdmissionError(
            "%s.%s must resolve exactly to the session workspace %s" %
            (tool["name"], workspace_argument, workspace_root),
            {"tool": tool["name"], "argument": workspace_argument,
             "workspace_root": workspace_root})

    properties = tool["schema"]["properties"]
    records = []
    descriptors = []
    semantic_slots = {}
    try:
        for argument, property_schema in properties.items():
            if argument == workspace_argument:
                continue
            capability = property_schema.get(PATH_EXTENSION_KEY)
            if capability is None:
                continue
            if not capability_is_active(capability, arguments):
                continue
            if argument in arguments:
                value = arguments[argument]
            elif "default" in property_schema and \
                    property_schema["default"] is not None:
                # An omitted option still has an effective path. Validate and
                # retain the compiled default before the child can use it.
                value = property_schema["default"]
            else:
                continue
            for value_index, spelling in enumerate(
                    _path_values(tool["name"], argument, value)):
                spelling = canonical_spelling(
                    tool["name"], argument, spelling)
                semantic_slot = (spelling, capability["consumption"])
                prior = semantic_slots.get(semantic_slot)
                if prior is not None and capability["consumption"] != "snapshot":
                    raise PathAdmissionError(
                        "%s.%s aliases active path capability %s at %s "
                        "with the same consumption mode" %
                        (tool["name"], argument, prior, spelling),
                        {"tool": tool["name"], "argument": argument,
                         "aliased_argument": prior, "path": spelling,
                         "consumption": capability["consumption"]})
                semantic_slots[semantic_slot] = argument
                constraint = capability["constraint"]
                registered = capability["value"]
                if constraint == "exact":
                    if spelling != registered:
                        raise PathAdmissionError(
                            "%s.%s must name exactly %s" %
                            (tool["name"], argument, registered),
                            {"tool": tool["name"], "argument": argument,
                             "expected": registered})
                elif constraint == "namespace":
                    in_namespace = spelling.startswith(registered + "/")
                    if not in_namespace:
                        raise PathAdmissionError(
                            "%s.%s must name an artifact under %s" %
                            (tool["name"], argument, registered),
                            {"tool": tool["name"], "argument": argument,
                             "namespace": registered})
                    suffixes = capability["suffixes"]
                    if suffixes and not any(
                            spelling.endswith(suffix) for suffix in suffixes):
                        raise PathAdmissionError(
                            "%s.%s must end in one of %s" %
                            (tool["name"], argument, ", ".join(suffixes)),
                            {"tool": tool["name"], "argument": argument,
                             "suffixes": suffixes})
                record, opened = retain_path(
                    tool["name"], argument, workspace_fd, spelling,
                    capability, value_index)
                records.append(record)
                descriptors.extend(opened)
    except Exception:
        for descriptor in descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    return records, descriptors
