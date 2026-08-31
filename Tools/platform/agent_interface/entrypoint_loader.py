"""Resolve a stable public Tool entrypoint to its sole implementation owner.

Top-level ``Tools/<tool>.py`` files are invocation adapters.  Their literal
``IMPLEMENTATION_MODULE`` assignment is the machine-readable edge to the
module that owns executable behaviour.  This module parses that edge without
importing the adapter, so runtime consumers never need the adapter to
re-export business constants or functions.

The edge is deliberately stored only once: callers use this resolver instead
of maintaining private Tool-name maps.  Capability registries can additionally
constrain which public adapter is authorized, but they do not need a second
Python copy of the adapter-to-owner relationship.
"""

import argparse
import ast
import importlib
import importlib.util
import os
import re
import sys
from dataclasses import dataclass

from Tools.platform.common import implementation_marker
from Tools.platform.repository.repository import tools_source_root


IMPLEMENTATION_MARKER = implementation_marker.IMPLEMENTATION_MARKER
TOOL_NAME_RE = re.compile(r"[a-z][a-z0-9_]*\Z")


class EntrypointResolutionError(ValueError):
    """A public adapter has no unique, safe implementation owner."""


class _CapturedArgumentParser(Exception):
    """Carry a fully declared parser out of a Tool without executing it."""

    def __init__(self, parser):
        super().__init__("argument parser captured")
        self.parser = parser


@dataclass(frozen=True)
class EntrypointDescriptor:
    """Exact source closure for one public Tool adapter."""

    tool: str
    invocation_path: str
    invocation_source: str
    implementation_module: str
    implementation_path: str
    implementation_source: str


def describe_entrypoint(tool, tools_root=None, *, require_marker=True):
    """Return the public adapter and implementation source for ``tool``.

    ``require_marker=False`` exists only for isolated compiler fixtures whose
    CLI source is intentionally a single direct module.  Shipped public Tools
    always require the explicit edge.
    """
    if not isinstance(tool, str) or TOOL_NAME_RE.fullmatch(tool) is None:
        raise EntrypointResolutionError("invalid public Tool name %r" % tool)
    root = os.path.realpath(os.path.abspath(
        tools_root or tools_source_root(__file__)))
    invocation_relative = "Tools/%s.py" % tool
    invocation_path = os.path.join(root, tool + ".py")
    try:
        with open(invocation_path, "r", encoding="utf-8") as handle:
            invocation_source = handle.read()
    except (OSError, UnicodeError) as exc:
        raise EntrypointResolutionError(
            "cannot read %s: %s" % (invocation_relative, exc)) from exc

    try:
        implementation_module = \
            implementation_marker.parse_implementation_module_source(
                invocation_source, label=invocation_relative,
                required=require_marker)
    except implementation_marker.ImplementationMarkerError as exc:
        raise EntrypointResolutionError(str(exc)) from exc
    if implementation_module is None:
        implementation_module = tool
        implementation_relative = invocation_relative
        implementation_path = invocation_path
        implementation_source = invocation_source
    else:
        implementation_relative = implementation_module.replace(".", "/") \
            + ".py"
        implementation_path = os.path.realpath(os.path.join(
            os.path.dirname(root), *implementation_relative.split("/")))
        expected_prefix = root + os.sep
        if not implementation_path.startswith(expected_prefix):
            raise EntrypointResolutionError(
                "%s implementation escapes Tools" % invocation_relative)
        try:
            with open(implementation_path, "r", encoding="utf-8") as handle:
                implementation_source = handle.read()
        except (OSError, UnicodeError) as exc:
            raise EntrypointResolutionError(
                "cannot read %s: %s" %
                (implementation_relative, exc)) from exc

    return EntrypointDescriptor(
        tool=tool,
        invocation_path=invocation_relative,
        invocation_source=invocation_source,
        implementation_module=implementation_module,
        implementation_path=implementation_relative,
        implementation_source=implementation_source,
    )


def discover_entrypoints(tools_root=None):
    """Return every public CLI adapter and its unique implementation owner.

    A top-level module that declares ``main`` is part of the public command
    surface.  It therefore must carry the explicit implementation edge; a
    direct-parser fallback here would let a newly added hybrid command evade
    the same owner model as the rest of the interface.  Transport adapters
    such as ``mcp_server.py`` do not declare ``main`` and remain outside this
    CLI surface even when they carry their own implementation marker.
    """
    root = os.path.abspath(tools_root or tools_source_root(__file__))
    try:
        filenames = sorted(os.listdir(root))
    except OSError as exc:
        raise EntrypointResolutionError(
            "cannot list Tools directory %s: %s" % (root, exc)) from exc
    descriptors = []
    for filename in filenames:
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        path = os.path.join(root, filename)
        if not os.path.isfile(path):
            continue
        relative = "Tools/%s" % filename
        try:
            with open(path, "r", encoding="utf-8") as handle:
                source = handle.read()
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise EntrypointResolutionError(
                "cannot inspect %s: %s" % (relative, exc)) from exc
        if not any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
                node.name == "main" for node in tree.body):
            try:
                implementation_marker.parse_implementation_module(
                    tree, label=relative, required=False)
            except implementation_marker.ImplementationMarkerError as exc:
                raise EntrypointResolutionError(str(exc)) from exc
            continue
        descriptors.append(describe_entrypoint(
            filename[:-3], root, require_marker=True))
    if not descriptors:
        raise EntrypointResolutionError(
            "no public CLI adapter found under %s" % root)
    owners = {}
    for descriptor in descriptors:
        previous = owners.get(descriptor.implementation_path)
        if previous is not None:
            raise EntrypointResolutionError(
                "%s and %s name the same implementation owner %s" % (
                    previous, descriptor.tool,
                    descriptor.implementation_path))
        owners[descriptor.implementation_path] = descriptor.tool
    return descriptors


def load_tool_implementation(tool, tools_root=None):
    """Import and return the unique implementation module for ``tool``."""
    descriptor = describe_entrypoint(tool, tools_root, require_marker=True)
    return importlib.import_module(descriptor.implementation_module)


def entrypoint_for_implementation_path(implementation_path, tools_root=None):
    """Resolve one implementation owner back to its sole public adapter.

    ``IMPLEMENTATION_MODULE`` remains the only stored edge. This reverse view
    is computed from those bytes so scan registries and capability contracts
    can name the internal owner without also copying the public invocation
    path. A direct top-level Tool without a marker is accepted as a single-file
    interface, chiefly for isolated fixtures and adopter extensions.
    """
    if not isinstance(implementation_path, str) or \
            not implementation_path.startswith("Tools/") or \
            not implementation_path.endswith(".py") or \
            any(part in ("", ".", "..")
                for part in implementation_path.split("/")):
        raise EntrypointResolutionError(
            "invalid implementation path %r" % implementation_path)
    root = os.path.realpath(os.path.abspath(
        tools_root or tools_source_root(__file__)))
    matches = []
    for filename in sorted(os.listdir(root)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        tool = filename[:-3]
        descriptor = describe_entrypoint(tool, root, require_marker=False)
        if descriptor.implementation_path == implementation_path:
            matches.append(descriptor)
    if len(matches) != 1:
        raise EntrypointResolutionError(
            "%s must resolve to exactly one public adapter; found %d" %
            (implementation_path, len(matches)))
    return matches[0]


def _load_parser_from_path(module_name, path):
    """Import one implementation owner for ``capture_argument_parser``."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise EntrypointResolutionError(
            "%s has no import specification" % module_name)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            # Import-time exit is still allowed to leave a declared main().
            pass
        except Exception as exc:  # noqa: BLE001 - fail closed with context
            raise EntrypointResolutionError(
                "%s import failed: %s: %s" %
                (module_name, type(exc).__name__, exc)) from exc
        entry = getattr(module, "main", None)
        if entry is None:
            raise EntrypointResolutionError(
                "%s has no main()" % module_name)
        try:
            entry()
        except _CapturedArgumentParser as captured:
            return captured.parser
        except SystemExit as exc:
            raise EntrypointResolutionError(
                "%s exited before declaring a parser: %s" %
                (module_name, exc)) from exc
        raise EntrypointResolutionError(
            "%s main() returned before parsing arguments" % module_name)
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous


def capture_argument_parser(tool, tools_root=None, *, require_marker=True):
    """Return the parser declared by a public Tool without running its work.

    The invocation adapter remains the public interface while its unique
    implementation owns the parser.  Capturing the parser from that real edge
    lets runtime capability checks and generated interface projections share
    one source-derived mechanism instead of maintaining option whitelists.
    """
    # Preserve the caller's absolute spelling when loading the owner. Some
    # CLIs derive repository-relative defaults from ``__file__``; resolving a
    # platform symlink here while the compiler root retains it would turn the
    # same in-repository default into an apparent external path. Descriptor
    # validation separately resolves and bounds the implementation owner.
    root = os.path.abspath(tools_root or tools_source_root(__file__))
    descriptor = describe_entrypoint(
        tool, root, require_marker=require_marker)
    invocation_path = os.path.join(root, tool + ".py")
    implementation_path = os.path.join(
        os.path.dirname(root), *descriptor.implementation_path.split("/"))
    original_parse_args = argparse.ArgumentParser.parse_args
    original_dont_write = sys.dont_write_bytecode
    original_argv = list(sys.argv)
    repository_root = os.path.dirname(root)
    added_repository_root = repository_root not in sys.path

    def _capture(parser, _args=None, _namespace=None):
        raise _CapturedArgumentParser(parser)

    argparse.ArgumentParser.parse_args = _capture
    sys.dont_write_bytecode = True
    sys.argv = [os.path.basename(invocation_path)]
    if added_repository_root:
        sys.path.insert(0, repository_root)
    try:
        return _load_parser_from_path(
            descriptor.implementation_module, implementation_path)
    finally:
        if added_repository_root:
            try:
                sys.path.remove(repository_root)
            except ValueError:
                pass
        argparse.ArgumentParser.parse_args = original_parse_args
        sys.dont_write_bytecode = original_dont_write
        sys.argv = original_argv


__all__ = [
    'EntrypointResolutionError',
    'describe_entrypoint',
    'discover_entrypoints',
    'capture_argument_parser',
    'entrypoint_for_implementation_path',
    'load_tool_implementation',
]
