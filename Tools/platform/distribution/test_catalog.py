"""Generate the non-authoritative test ownership and execution catalog.

``Tools/test-ownership.yaml`` is the only reviewed source for test ownership,
level, lifecycle, and execution disposition.  This module joins that manifest
with facts observed directly from the test sources.  The generated Markdown
and JSON files are navigation and runner inputs; neither may be edited as a
second classification source.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import pathlib
import re
import sys
from collections import Counter

import Tools.platform.common.kblib as kblib


SCHEMA_VERSION = 1
CATALOG_SCHEMA_VERSION = 1
MANIFEST_PATH = "Tools/test-ownership.yaml"
MARKDOWN_OUTPUT = "Tools/TEST_CATALOG.md"
JSON_OUTPUT = "Tools/compiled/test-catalog.json"
TEST_DIRECTORY = "Tools/tests"
LEVELS = (
    "unit",
    "contract",
    "integration",
    "e2e",
    "slow",
    "historical-read-only",
)
LIFECYCLES = frozenset(("current", "historical-read-only"))
FAST_LEVELS = frozenset(("unit", "contract"))
PROCESS_CALLS = frozenset(
    (
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.run",
    )
)
TEMP_CALLS = frozenset(
    (
        "tempfile.NamedTemporaryFile",
        "tempfile.TemporaryDirectory",
        "tempfile.mkdtemp",
        "tempfile.mkstemp",
    )
)
COPY_CALLS = frozenset(("shutil.copy", "shutil.copy2", "shutil.copyfile"))
FULL_COPY_CALLS = frozenset(("shutil.copytree",))
EFFECT_KEYS = (
    "process_calls",
    "temp_resources",
    "file_copies",
    "full_repository_copies",
)
TEST_MODULE_RE = re.compile(r"^(?:Tools\.tests\.)?(test_[A-Za-z0-9_]+)(?:\.|$)")
_UNKNOWN = object()


class TestCatalogError(Exception):
    """The manifest or observed test sources violate the catalog contract."""


def _relative(path: pathlib.Path, root: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def _call_name(node: ast.Call) -> str:
    value = node.func
    parts = []
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def _effect_counts(node: ast.AST) -> dict[str, int]:
    calls = Counter(_call_name(item) for item in ast.walk(node) if isinstance(item, ast.Call))
    annotated = _annotated_effect_counts(node)
    return {
        "process_calls": sum(calls[name] for name in PROCESS_CALLS)
            + annotated["process_calls"],
        "temp_resources": sum(calls[name] for name in TEMP_CALLS)
            + annotated["temp_resources"],
        "file_copies": sum(calls[name] for name in COPY_CALLS)
            + annotated["file_copies"],
        "full_repository_copies": sum(calls[name] for name in FULL_COPY_CALLS)
            + annotated["full_repository_copies"],
    }


def _annotated_effect_counts(node: ast.AST) -> dict[str, int]:
    """Read source-adjacent effects hidden behind a production boundary.

    Most effects are observed directly from call sites.  A transport test can
    instead invoke a production function whose body starts the process; its
    test method then carries ``@catalog_effects(...)``.  The annotation is
    executable no-op metadata on the test itself, not a second ownership
    manifest, and this parser rejects any shape it cannot prove statically.
    """
    effects = Counter()
    for item in ast.walk(node):
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        declaration_count = 0
        for decorator in item.decorator_list:
            if not isinstance(decorator, ast.Call) or \
                    _call_name(decorator).rsplit(".", 1)[-1] != \
                    "catalog_effects":
                continue
            declaration_count += 1
            if declaration_count > 1:
                raise TestCatalogError(
                    "catalog_effects at line %d is declared more than once "
                    "for one function" % getattr(decorator, "lineno", 0))
            if decorator.args:
                raise TestCatalogError(
                    "catalog_effects at line %d accepts keyword counts only" %
                    getattr(decorator, "lineno", 0))
            seen = set()
            declared = Counter()
            for keyword in decorator.keywords:
                if keyword.arg not in EFFECT_KEYS or keyword.arg in seen:
                    raise TestCatalogError(
                        "catalog_effects at line %d has unsupported or "
                        "duplicate key %r" %
                        (getattr(decorator, "lineno", 0), keyword.arg))
                seen.add(keyword.arg)
                value = keyword.value.value if isinstance(
                    keyword.value, ast.Constant) else None
                if type(value) is not int or value < 0:
                    raise TestCatalogError(
                        "catalog_effects at line %d requires non-negative "
                        "integer counts" % getattr(decorator, "lineno", 0))
                declared[keyword.arg] = value
            if not seen or not any(declared.values()):
                raise TestCatalogError(
                    "catalog_effects at line %d must declare a positive "
                    "effect" % getattr(decorator, "lineno", 0))
            effects.update(declared)
    return {name: effects[name] for name in EFFECT_KEYS}


def _zero_effects() -> dict[str, int]:
    return {name: 0 for name in EFFECT_KEYS}


def _merge_effects(*effects: dict[str, int]) -> dict[str, int]:
    return {
        name: sum(int(effect.get(name, 0)) for effect in effects)
        for name in EFFECT_KEYS
    }


def _module_parts(path: str) -> tuple[str, ...]:
    pure = pathlib.PurePosixPath(path).with_suffix("")
    if pure.name == "__init__":
        return pure.parts[:-1]
    return pure.parts


def _import_from_module(path: str, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    source_parts = list(_module_parts(path))
    if pathlib.PurePosixPath(path).stem != "__init__":
        source_parts = source_parts[:-1]
    climb = node.level - 1
    if climb:
        source_parts = source_parts[:-climb]
    if node.module:
        source_parts.extend(node.module.split("."))
    return ".".join(source_parts)


def _condition_value(node: ast.AST, environment: dict) -> bool | None:
    if isinstance(node, ast.Constant):
        return bool(node.value)
    if isinstance(node, ast.Name) and node.id in environment:
        return bool(environment[node.id])
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in ("self", "cls")
        and node.attr in environment
    ):
        return bool(environment[node.attr])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        value = _condition_value(node.operand, environment)
        return None if value is None else not value
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left = _SourceCallIndex._literal_value(node.left, environment)
        right = _SourceCallIndex._literal_value(node.comparators[0], environment)
        left_known = (
            isinstance(node.left, ast.Constant)
            or isinstance(node.left, ast.Name) and node.left.id in environment
            or isinstance(node.left, ast.Attribute)
            and isinstance(node.left.value, ast.Name)
            and node.left.value.id in ("self", "cls")
            and node.left.attr in environment
        )
        right_node = node.comparators[0]
        right_known = (
            isinstance(right_node, ast.Constant)
            or isinstance(right_node, ast.Name) and right_node.id in environment
            or isinstance(right_node, ast.Attribute)
            and isinstance(right_node.value, ast.Name)
            and right_node.value.id in ("self", "cls")
            and right_node.attr in environment
        )
        if not left_known:
            return None
        if not right_known:
            return None
        operator = node.ops[0]
        if isinstance(operator, (ast.Is, ast.Eq)):
            return left == right
        if isinstance(operator, (ast.IsNot, ast.NotEq)):
            return left != right
        if isinstance(operator, (ast.In, ast.NotIn)):
            try:
                contained = left in right
            except TypeError:
                return None
            return not contained if isinstance(operator, ast.NotIn) else contained
    return None


def _static_value(node: ast.AST):
    """Return a safe import-time value used only for branch narrowing.

    Registry values frequently contain Paths or callables and therefore are
    not literal-evaluable, while membership in their string keys is still an
    exact source fact.  Retaining those keys lets the catalog distinguish a
    static checkpoint load from the dynamic scenario builder behind the same
    public fixture entrypoint.
    """

    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        pass
    if isinstance(node, ast.Dict):
        keys = []
        for key in node.keys:
            try:
                keys.append(ast.literal_eval(key))
            except (ValueError, TypeError):
                return _UNKNOWN
        return {key: None for key in keys}
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ("frozenset", "set", "tuple", "list")
        and len(node.args) == 1
        and not node.keywords
    ):
        try:
            values = ast.literal_eval(node.args[0])
        except (ValueError, TypeError):
            return _UNKNOWN
        constructor = {
            "frozenset": frozenset,
            "set": set,
            "tuple": tuple,
            "list": list,
        }[node.func.id]
        return constructor(values)
    return _UNKNOWN


def _definition_calls(
    node: ast.AST, environment: dict | None = None
) -> list[ast.Call]:
    """Return calls executed by one definition, excluding nested bodies."""

    found = []
    environment = environment or {}

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, item):  # noqa: N802 - ast visitor API
            found.append(item)
            self.generic_visit(item)

        def visit_FunctionDef(self, item):  # noqa: N802
            if item is node:
                for statement in item.body:
                    self.visit(statement)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, item):  # noqa: N802
            if item is node:
                for statement in item.body:
                    self.visit(statement)

        def visit_Lambda(self, item):  # noqa: N802
            return

        def visit_If(self, item):  # noqa: N802
            value = _condition_value(item.test, environment)
            if value is None:
                self.generic_visit(item)
                return
            for statement in item.body if value else item.orelse:
                self.visit(statement)

    Visitor().visit(node)
    return found


def _direct_effect_counts(
    node: ast.AST, environment: dict | None = None
) -> dict[str, int]:
    calls = Counter(
        _call_name(item) for item in _definition_calls(node, environment)
    )
    annotated = _annotated_effect_counts(node)
    return {
        "process_calls": sum(calls[name] for name in PROCESS_CALLS)
            + annotated["process_calls"],
        "temp_resources": sum(calls[name] for name in TEMP_CALLS)
            + annotated["temp_resources"],
        "file_copies": sum(calls[name] for name in COPY_CALLS)
            + annotated["file_copies"],
        "full_repository_copies": sum(calls[name] for name in FULL_COPY_CALLS)
            + annotated["full_repository_copies"],
    }


class _SourceCallIndex:
    """Resolve test-to-fixture calls without executing the test suite.

    The index intentionally follows only definitions in the test module and
    declared Python fixtures. Production calls are leaves: their behavior is
    tested elsewhere and must not be guessed here. This is sufficient to
    expose the expensive hidden prologues owned by test helpers and fixtures.
    """

    def __init__(self, root: pathlib.Path, source_paths: set[str]):
        self.root = root
        self.trees = {}
        self.sources = {}
        self.imports = {}
        self.module_import_paths = {}
        self.module_constants = {}
        self.definitions = {}
        self.classes = {}
        self.module_nodes = {}
        self.cached_fixture_entrypoints = set()
        self.e2e_builders = set()
        self.full_lifecycle_scenarios = {}
        self.scenario_builder_targets = {}
        self.scenario_parents = {}
        self._facts_cache = {}
        for relative_path in sorted(source_paths):
            path = root / relative_path
            if path.suffix != ".py" or not path.exists():
                continue
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative_path)
            self.trees[relative_path] = tree
            self.sources[relative_path] = source
        self.module_names = self._module_names()
        for path, tree in self.trees.items():
            self._index_source(path, tree)

    def _module_names(self) -> dict[str, str]:
        found = {}
        for path in self.trees:
            parts = _module_parts(path)
            dotted = ".".join(parts)
            found[dotted] = path
            if pathlib.PurePosixPath(path).stem != "__init__":
                found[pathlib.PurePosixPath(path).stem] = path
        return found

    @staticmethod
    def _key(path: str, symbol: str) -> str:
        return "%s:%s" % (path, symbol)

    def _index_source(self, path: str, tree: ast.Module) -> None:
        constants = {}
        empty_mapping_names = set()
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = _static_value(node.value)
            if value is _UNKNOWN:
                continue
            for name in _assigned_names(node):
                constants[name] = value
                if value == {}:
                    empty_mapping_names.add(name)
        self.module_constants[path] = constants

        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = self.module_names.get(alias.name)
                    if target:
                        aliases[alias.asname or alias.name.split(".")[0]] = (
                            target, None
                        )
            elif isinstance(node, ast.ImportFrom):
                target = self.module_names.get(
                    _import_from_module(path, node)
                )
                if not target:
                    continue
                for alias in node.names:
                    aliases[alias.asname or alias.name] = (target, alias.name)
        self.imports[path] = aliases
        top_level_imports = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [_import_from_module(path, node)]
            else:
                continue
            for name in names:
                target = self.module_names.get(name)
                if target and target != path:
                    top_level_imports.add(target)
        self.module_import_paths[path] = top_level_imports

        module_body = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.definitions[self._key(path, node.name)] = {
                    "path": path,
                    "symbol": node.name,
                    "class": None,
                    "node": node,
                }
            elif isinstance(node, ast.ClassDef):
                bases = []
                for base in node.bases:
                    resolved = self._resolve_reference(path, None, _expr_name(base))
                    bases.extend(resolved)
                methods = {}
                constants = {}
                for child in node.body:
                    if isinstance(child, (ast.Assign, ast.AnnAssign)):
                        try:
                            value = ast.literal_eval(child.value)
                        except (ValueError, TypeError):
                            value = None
                        for name in _assigned_names(child):
                            if isinstance(value, (str, int, float, bool, type(None))):
                                constants[name] = value
                        continue
                    if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    symbol = "%s.%s" % (node.name, child.name)
                    key = self._key(path, symbol)
                    self.definitions[key] = {
                        "path": path,
                        "symbol": symbol,
                        "class": node.name,
                        "node": child,
                    }
                    methods[child.name] = key
                self.classes[self._key(path, node.name)] = {
                    "path": path,
                    "name": node.name,
                    "bases": bases,
                    "methods": methods,
                    "constants": constants,
                }
            else:
                module_body.append(node)
        synthetic = ast.Module(body=module_body, type_ignores=[])
        module_key = self._key(path, "<module>")
        self.module_nodes[path] = module_key
        self.definitions[module_key] = {
            "path": path,
            "symbol": "<module>",
            "class": None,
            "node": synthetic,
        }

        # Cached fixture entrypoints are detected structurally. Their names
        # are not an interface contract: current E2E builders use private
        # entrypoints such as ``_template`` and ``_dynamic_template``. Both
        # guard a process-level mapping; Integration consumers instead load a
        # generated checkpoint through their dedicated static loader.
        for definition in tuple(self.definitions.values()):
            if definition["path"] != path or definition["class"] is not None:
                continue
            node = definition["node"]
            guarded_caches = {
                comparator.id
                for compare in ast.walk(node)
                if isinstance(compare, ast.Compare)
                and any(isinstance(operator, (ast.In, ast.NotIn))
                        for operator in compare.ops)
                for comparator in compare.comparators
                if isinstance(comparator, ast.Name)
                and comparator.id in empty_mapping_names
            }
            if guarded_caches:
                self.cached_fixture_entrypoints.add(
                    self._key(path, definition["symbol"])
                )

        # A scenario generator is the cached entrypoint that actually
        # dispatches a source-owned string->builder registry. Public checkpoint
        # loaders may call it only for uncached scenarios; branch narrowing in
        # ``facts`` keeps static checkpoint consumers from being mislabeled as
        # E2E walks.
        full, targets, parents, builder_names = self._scenario_contract(
            path, tree
        )
        if targets:
            for key in sorted(self.cached_fixture_entrypoints):
                definition = self.definitions.get(key)
                if not definition or definition["path"] != path:
                    continue
                referenced = {
                    item.id for item in ast.walk(definition["node"])
                    if isinstance(item, ast.Name)
                }
                if not referenced.intersection(builder_names):
                    continue
                self.e2e_builders.add(key)
                self.full_lifecycle_scenarios[key] = full
                self.scenario_builder_targets[key] = targets
                self.scenario_parents[key] = parents

    def _scenario_contract(
        self, path: str, tree: ast.Module
    ) -> tuple[
        set[str], dict[str, list[str]], dict[str, str | None], set[str]
    ]:
        """Derive scenarios that actually walk a complete batch lifecycle."""

        mapping_candidates = []
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            names = _assigned_names(node)
            value = node.value
            if not names or not isinstance(value, ast.Dict):
                continue
            rows = []
            for key, member in zip(value.keys, value.values):
                if not (isinstance(key, ast.Constant)
                        and isinstance(key.value, str)):
                    rows = []
                    break
                rows.append((key.value, member))
            if rows:
                mapping_candidates.append((set(names), rows))

        builder_names = set()
        builders = {}
        for names, rows in mapping_candidates:
            candidate = {scenario: _expr_name(member)
                         for scenario, member in rows}
            if candidate and all(
                    self._key(path, symbol) in self.definitions
                    for symbol in candidate.values()):
                builders = candidate
                builder_names = names
                break
        if not builders:
            return set(), {}, {}, set()

        parents = {scenario: None for scenario in builders}
        for _names, rows in mapping_candidates:
            candidate = {}
            for scenario, member in rows:
                if not isinstance(member, ast.Constant) or not (
                        member.value is None or isinstance(member.value, str)):
                    candidate = {}
                    break
                candidate[scenario] = member.value
            if candidate and set(builders).issubset(candidate):
                parents = {
                    scenario: candidate.get(scenario)
                    for scenario in builders
                }
                break
        direct_full = set()
        for scenario, builder in builders.items():
            definition = self.definitions.get(self._key(path, builder))
            if not definition:
                continue
            call_tails = {
                _call_name(call).rsplit(".", 1)[-1]
                for call in _definition_calls(definition["node"])
            }
            if "merge_and_close" in call_tails:
                direct_full.add(scenario)

        resolved = set(direct_full)
        # Descendants of a completed-lifecycle scenario also begin from that
        # completed state and therefore expose the same hidden prologue.
        changed = True
        while changed:
            changed = False
            for scenario, parent in parents.items():
                if parent in resolved and scenario not in resolved:
                    resolved.add(scenario)
                    changed = True
        targets = {}
        for scenario in builders:
            builder = builders.get(scenario)
            targets[scenario] = (
                [self._key(path, builder)] if builder else []
            )
        return resolved, targets, parents, builder_names

    def _resolve_reference(
        self, path: str, class_name: str | None, name: str
    ) -> list[str]:
        if not name:
            return []
        if name.startswith("self.") or name.startswith("cls."):
            if class_name:
                return self._class_method(
                    self._key(path, class_name), name.split(".", 1)[1]
                )
            return []
        if name.startswith("walker."):
            method = name.split(".", 1)[1]
            for candidate in (
                self._key(path, "_ScenarioWalker"),
                self._key(path, "ScenarioWalker"),
            ):
                resolved = self._class_method(candidate, method)
                if resolved:
                    return resolved
            return []
        if "." not in name:
            local = self._key(path, name)
            if local in self.definitions or local in self.classes:
                return [local]
            imported = self.imports.get(path, {}).get(name)
            if imported:
                target_path, symbol = imported
                return self._resolve_import_target(
                    target_path, symbol or "<module>"
                )
            return []
        head, tail = name.split(".", 1)
        imported = self.imports.get(path, {}).get(head)
        if imported and imported[1] is None:
            return self._resolve_import_target(imported[0], tail)
        return []

    def _resolve_import_target(
        self, path: str, symbol: str, seen=None
    ) -> list[str]:
        seen = set() if seen is None else seen
        identity = (path, symbol)
        if identity in seen:
            return []
        seen.add(identity)
        key = self._key(path, symbol)
        if key in self.definitions or key in self.classes:
            return [key]
        reexport = self.imports.get(path, {}).get(symbol)
        if reexport:
            target_path, target_symbol = reexport
            return self._resolve_import_target(
                target_path, target_symbol or "<module>", seen
            )
        return [key]

    def _class_method(self, class_key: str, method: str, seen=None) -> list[str]:
        seen = set() if seen is None else seen
        if class_key in seen:
            return []
        seen.add(class_key)
        row = self.classes.get(class_key)
        if not row:
            return []
        if method in row["methods"]:
            return [row["methods"][method]]
        found = []
        for base in row["bases"]:
            found.extend(self._class_method(base, method, seen))
        return found

    def _class_constants(self, class_key: str, seen=None) -> dict:
        seen = set() if seen is None else seen
        if class_key in seen:
            return {}
        seen.add(class_key)
        row = self.classes.get(class_key)
        if not row:
            return {}
        values = {}
        for base in row["bases"]:
            values.update(self._class_constants(base, seen))
        values.update(row["constants"])
        return values

    def class_roots(self, path: str, class_name: str, names) -> list[str]:
        roots = []
        for name in names:
            roots.extend(self._class_method(self._key(path, class_name), name))
        return roots

    @staticmethod
    def _literal_value(node: ast.AST, environment: dict) -> object:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return environment.get(node.id)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in ("self", "cls")
        ):
            return environment.get(node.attr)
        return None

    def _bound_arguments(
        self, target: str, call: ast.Call, environment: dict
    ) -> dict:
        definition = self.definitions.get(target)
        if not definition:
            return {}
        function_args = getattr(definition["node"], "args", None)
        if function_args is None:
            return {}
        arguments = list(function_args.args)
        names = [argument.arg for argument in arguments]
        if names and names[0] in ("self", "cls"):
            names = names[1:]
        bound = {}
        for name, value in zip(names, call.args):
            resolved = self._literal_value(value, environment)
            if resolved is not None:
                bound[name] = resolved
        for keyword in call.keywords:
            if keyword.arg in names:
                resolved = self._literal_value(keyword.value, environment)
                if resolved is not None:
                    bound[keyword.arg] = resolved
        return bound

    def _definition_targets(
        self, key: str, environment: dict
    ) -> list[tuple[str, dict]]:
        definition = self.definitions[key]
        found = []
        for call in _definition_calls(definition["node"], environment):
            targets = self._resolve_reference(
                definition["path"], definition["class"], _call_name(call)
            )
            for target in targets:
                # Scenario templates recurse through their parent registry.
                # The outer literal already determines whether the selected
                # scenario includes a full lifecycle; following the dynamic
                # local `parent` variable would turn every `base` request into
                # a false unknown/full result.
                if target == key and key in self.e2e_builders and environment:
                    continue
                found.append((
                    target, self._bound_arguments(target, call, environment)
                ))
        return found

    def _definition_environment(self, definition: dict, environment: dict) -> dict:
        """Join local/imported constants with call-bound arguments.

        Imported checkpoint registries remain owned by their fixture module;
        consuming modules merely use their keys to select the static or
        dynamic branch.  Reading that value here is source resolution, not a
        second manifest of scenarios.
        """

        path = definition["path"]
        active = dict(self.module_constants.get(path, {}))
        active["__name__"] = ".".join(_module_parts(path))
        for local_name, (target_path, symbol) in self.imports.get(
                path, {}).items():
            if symbol is None:
                continue
            target_values = self.module_constants.get(target_path, {})
            if symbol in target_values:
                active[local_name] = target_values[symbol]
        active.update(environment)
        return active

    def facts(
        self, roots: list[str], test_path: str, environment: dict | None = None
    ) -> dict:
        environment = dict(environment or {})
        cache_key = (
            test_path,
            tuple(sorted(set(roots))),
            tuple(sorted((key, repr(value)) for key, value in environment.items())),
        )
        if cache_key in self._facts_cache:
            return self._facts_cache[cache_key]
        visited = set()
        pending = [
            (root, environment, test_path, "recurring", None)
            for root in roots
        ]
        effects = Counter()
        first_use_effects = {}
        fixture_entrypoints = set()
        e2e_builders = set()
        builder_triggers = set()
        full_lifecycle = set()
        lifecycle_signals = set()
        while pending:
            key, environment, parent_path, frequency, build_identity = \
                pending.pop()
            visit_key = (
                key,
                tuple(sorted((name, repr(value))
                             for name, value in environment.items())),
                frequency,
                build_identity,
            )
            if visit_key in visited or key not in self.definitions:
                continue
            visited.add(visit_key)
            definition = self.definitions[key]
            active_environment = self._definition_environment(
                definition, environment)
            if (
                definition["path"] != test_path
                and parent_path == test_path
                and definition["symbol"] != "<module>"
            ):
                fixture_entrypoints.add(key)
            if key in self.cached_fixture_entrypoints:
                scenario = active_environment.get("name")
                own_build_identity = "%s[%s]" % (
                    key, scenario if scenario is not None else "dynamic"
                )
                if frequency == "recurring":
                    build_identity = own_build_identity
                    builder_triggers.add(build_identity)
                    if key in self.e2e_builders:
                        e2e_builders.add(key)
                        if scenario is None or scenario in \
                                self.full_lifecycle_scenarios.get(key, set()):
                            full_lifecycle.add(build_identity)
                    # A process cache makes the scenario construction a
                    # first-use cost. Re-enter the definition in that
                    # frequency instead of charging it to every method.
                    pending.append((
                        key, environment, parent_path, "first-use",
                        build_identity
                    ))
                    continue
                if (
                    frequency == "first-use"
                    and build_identity is not None
                    and scenario is not None
                    and not build_identity.endswith("[%s]" % scenario)
                ):
                    # A cached scenario may recursively request a cached
                    # parent. The parent has its own once-per-process cost,
                    # not another copy of the child's cost.
                    pending.append((
                        key, environment, parent_path, "first-use",
                        own_build_identity
                    ))
                    continue

            for call in _definition_calls(
                    definition["node"], active_environment):
                tail = _call_name(call).rsplit(".", 1)[-1]
                if tail not in ("merge_and_close", "task_transition"):
                    continue
                argument = (
                    self._literal_value(call.args[0], active_environment)
                    if call.args else None
                )
                lifecycle_signals.add(
                    "%s:%s" % (
                        tail,
                        argument if argument is not None else "dynamic",
                    )
                )

            if key in self.e2e_builders and frequency == "first-use":
                scenario = active_environment.get("name")
                if isinstance(scenario, str):
                    active_environment = dict(
                        active_environment,
                        parent=self.scenario_parents.get(key, {}).get(
                            scenario
                        ),
                    )
            direct_effects = _direct_effect_counts(
                definition["node"], active_environment
            )
            if frequency == "first-use":
                build_effects = first_use_effects.setdefault(
                    build_identity, Counter()
                )
                build_effects.update(direct_effects)
            else:
                effects.update(direct_effects)

            if key in self.e2e_builders and frequency == "first-use":
                e2e_builders.add(key)
                scenario = active_environment.get("name")
                if scenario is None or scenario in \
                        self.full_lifecycle_scenarios.get(key, set()):
                    full_lifecycle.add(build_identity)
                scenario_targets = self.scenario_builder_targets.get(key, {})
                if isinstance(scenario, str) and scenario in scenario_targets:
                    parent_scenario = self.scenario_parents.get(key, {}).get(
                        scenario
                    )
                    target_rows = self._definition_targets(
                        key, active_environment)
                    has_cached_peer = any(
                        target in self.cached_fixture_entrypoints
                        and target != key
                        for target, _bound in target_rows
                    )
                    if parent_scenario is not None and not has_cached_peer:
                        parent_identity = "%s[%s]" % (key, parent_scenario)
                        pending.append((
                            key, {"name": parent_scenario},
                            definition["path"], "first-use",
                            parent_identity,
                        ))
                    pending.extend(
                        (target, {}, definition["path"], "first-use",
                         build_identity)
                        for target in scenario_targets[scenario]
                    )
                else:
                    # A dynamic scenario cannot be narrowed statically. Keep
                    # conservative file facts rather than reporting a false
                    # cheap fixture.
                    first_use_effects[build_identity].update(
                        _effect_counts(self.trees[definition["path"]])
                    )
            pending.extend(
                (target, dict(environment, **bound), definition["path"], frequency,
                 build_identity)
                for target, bound in self._definition_targets(
                    key, active_environment)
            )
        result = {
            "effects": {name: effects[name] for name in EFFECT_KEYS},
            "first_use_builds": {
                identity: {name: values[name] for name in EFFECT_KEYS}
                for identity, values in sorted(first_use_effects.items())
            },
            "fixture_entrypoints": sorted(fixture_entrypoints),
            "e2e_builder_entrypoints": sorted(e2e_builders),
            "builder_triggers": sorted(builder_triggers),
            "full_lifecycle_entrypoints": sorted(full_lifecycle),
            "full_lifecycle": bool(full_lifecycle),
            "lifecycle_signals": sorted(lifecycle_signals),
        }
        self._facts_cache[cache_key] = result
        return result

    def case_facts(
        self, path: str, class_name: str | None, method_name: str
    ) -> dict:
        if class_name:
            class_environment = self._class_constants(
                self._key(path, class_name)
            )
            method = self._class_method(
                self._key(path, class_name), method_name
            )
            per_method_roots = self.class_roots(
                path, class_name, ("setUp", "tearDown")
            )
            per_class_roots = self.class_roots(
                path, class_name, ("setUpClass", "tearDownClass")
            )
        else:
            class_environment = {}
            method = [self._key(path, method_name)]
            per_method_roots = []
            per_class_roots = []
        per_process_roots = [self.module_nodes[path]]
        per_process_roots.extend(
            self._key(path, name)
            for name in ("setUpModule", "tearDownModule")
            if self._key(path, name) in self.definitions
        )
        # Import-time code of declared fixture modules executes once per test
        # process. Calls inside their definitions belong to other scopes.
        imported_paths = set()
        pending_imports = list(self.module_import_paths.get(path, ()))
        while pending_imports:
            target_path = pending_imports.pop()
            if target_path in imported_paths:
                continue
            imported_paths.add(target_path)
            pending_imports.extend(
                self.module_import_paths.get(target_path, ())
            )
        per_process_roots.extend(
            self.module_nodes[target_path]
            for target_path in sorted(imported_paths)
        )
        scopes = {
            "direct_method": self.facts(method, path, class_environment),
            "per_method": self.facts(
                per_method_roots, path, class_environment
            ),
            "per_class": self.facts(
                per_class_roots, path, class_environment
            ),
            "per_process": self.facts(per_process_roots, path),
        }
        first_use_builds = {}
        for scope in scopes.values():
            for identity, effects in scope["first_use_builds"].items():
                existing = first_use_builds.get(identity)
                if existing is None:
                    first_use_builds[identity] = effects
                else:
                    # The same scenario may be triggered from setUp and the
                    # method body; its cached build still runs once. Equal
                    # source closures are expected, and max remains
                    # conservative if static binding exposed different arms.
                    first_use_builds[identity] = {
                        name: max(existing[name], effects[name])
                        for name in EFFECT_KEYS
                    }
        triggered_once = _merge_effects(*first_use_builds.values()) \
            if first_use_builds else _zero_effects()
        recurring = _merge_effects(
            *(scope["effects"] for scope in scopes.values())
        )
        transitive = _merge_effects(
            recurring, triggered_once
        )
        fixture_entrypoints = sorted({
            entry
            for scope in scopes.values()
            for entry in scope["fixture_entrypoints"]
        })
        e2e_entrypoints = sorted({
            entry
            for scope in scopes.values()
            for entry in scope["e2e_builder_entrypoints"]
        })
        builder_triggers = sorted({
            entry
            for scope in scopes.values()
            for entry in scope["builder_triggers"]
        })
        full_lifecycle_entrypoints = sorted({
            entry
            for scope in scopes.values()
            for entry in scope["full_lifecycle_entrypoints"]
        })
        lifecycle_signals = sorted({
            entry
            for scope in scopes.values()
            for entry in scope["lifecycle_signals"]
        })
        closed_batches = {
            signal.split(":", 1)[1]
            for signal in lifecycle_signals
            if signal.startswith("merge_and_close:")
            and not signal.endswith(":dynamic")
        }
        if (
            len(closed_batches) >= 2
            and "task_transition:complete" in lifecycle_signals
        ):
            full_lifecycle_entrypoints.append(
                "source:two-batch-close+task-complete"
            )
        return {
            "scopes": scopes,
            "recurring_effects": recurring,
            "triggered_once_per_process": {
                "effects": triggered_once,
                "builds": dict(sorted(first_use_builds.items())),
            },
            "transitive_effects": transitive,
            "fixture_entrypoints": fixture_entrypoints,
            "e2e_builder_entrypoints": e2e_entrypoints,
            "builder_triggers": builder_triggers,
            "full_lifecycle_entrypoints": full_lifecycle_entrypoints,
            "full_lifecycle": bool(full_lifecycle_entrypoints),
            "lifecycle_signals": lifecycle_signals,
        }


def _expr_name(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _assigned_names(node: ast.AST) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name)]


def _cross_test_imports(tree: ast.AST, source: str) -> list[str]:
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [module]
            if module in ("", "Tools.tests"):
                names.extend(alias.name for alias in node.names)
        else:
            continue
        for name in names:
            match = TEST_MODULE_RE.match(name)
            if match:
                imports.add(match.group(1))
    # Dynamic imports remain imports even when hidden inside a test body.
    for match in re.finditer(
        r"(?:import_module|__import__)\s*\(\s*['\"](?:Tools\.tests\.)?"
        r"(test_[A-Za-z0-9_]+)",
        source,
    ):
        imports.add(match.group(1))
    return sorted(imports)


def _test_cases(tree: ast.Module, module_name: str) -> list[dict]:
    cases = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            cases.append(
                {
                    "selector": node.name,
                    "test_id": "%s.%s" % (module_name, node.name),
                    "effects": _effect_counts(node),
                    "_class_name": None,
                    "_method_name": node.name,
                }
            )
        if not isinstance(node, ast.ClassDef):
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_"):
                selector = "%s.%s" % (node.name, child.name)
                cases.append(
                    {
                        "selector": selector,
                        "test_id": "%s.%s" % (module_name, selector),
                        "effects": _effect_counts(child),
                        "_class_name": node.name,
                        "_method_name": child.name,
                    }
                )
    return sorted(cases, key=lambda row: row["test_id"])


def _read_manifest(root: pathlib.Path) -> dict:
    path = root / MANIFEST_PATH
    try:
        document = kblib.load_yaml_file(str(path))
    except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
        raise TestCatalogError("cannot read %s: %s" % (MANIFEST_PATH, exc)) from exc
    if document.get("schema_version") != SCHEMA_VERSION:
        raise TestCatalogError("%s schema_version must be %d" % (MANIFEST_PATH, SCHEMA_VERSION))
    return document


def _rows_by_path(rows, field: str) -> dict[str, dict]:
    if not isinstance(rows, list):
        raise TestCatalogError("%s must be a list" % field)
    found = {}
    for row in rows:
        path = row.get("path") if isinstance(row, dict) else None
        if not isinstance(path, str) or not path or path in found:
            raise TestCatalogError("%s has an invalid or duplicate path %r" % (field, path))
        found[path] = row
    return found


def _is_ephemeral_test_artifact(path: pathlib.Path) -> bool:
    """Return whether ``path`` is generated process/OS material, not a fixture.

    Git-managed worktrees already exclude these paths through the repository
    content boundary.  This source-kind guard preserves the same distinction
    for exported trees without ``.git`` and for fixture-bundle verification.
    It is intentionally narrow: an unknown ordinary file still enters fixture
    discovery and therefore fails closed until the ownership manifest names it.
    """

    return (
        path.name == ".DS_Store"
        or path.suffix == ".pyc"
        or "__pycache__" in path.parts
    )


def _discover_fixture_paths(
    root: pathlib.Path,
    *,
    bundle_roots: set[str] | None = None,
    bundle_manifests: set[str] | None = None,
) -> set[str]:
    tests = root / TEST_DIRECTORY
    bundle_roots = bundle_roots or set()
    bundle_manifests = bundle_manifests or set()
    repository_content = {
        relative
        for _absolute, relative in kblib.repository_content_files(root)
    }

    def covered(path: pathlib.Path) -> bool:
        relative = _relative(path, root)
        if relative in bundle_manifests:
            return True
        return any(
            relative == bundle or relative.startswith(bundle.rstrip("/") + "/")
            for bundle in bundle_roots
        )

    def discoverable(path: pathlib.Path) -> bool:
        return (
            _relative(path, root) in repository_content
            and not _is_ephemeral_test_artifact(path)
            and not covered(path)
        )

    paths = {
        _relative(path, root)
        for path in tests.glob("*.py")
        if not path.name.startswith("test_") and path.name != "__init__.py"
        and discoverable(path)
    }
    fixture_root = tests / "fixtures"
    if fixture_root.exists():
        paths.update(
            _relative(path, root)
            for path in fixture_root.rglob("*")
            if path.is_file() and discoverable(path)
        )
    support_root = tests / "support"
    if support_root.exists():
        paths.update(
            _relative(path, root)
            for path in support_root.rglob("*.py")
            if path.name != "__init__.py" and discoverable(path)
        )
    return paths


def _bundle_facts(root: pathlib.Path, row: dict, errors: list[str]) -> dict:
    relative = row["path"]
    bundle_root = root / relative
    manifest_relative = row.get("manifest")
    if bundle_root.is_symlink():
        errors.append("fixture bundle directory must not be a symlink: %s" % relative)
    if not bundle_root.is_dir():
        errors.append("fixture bundle directory does not exist: %s" % relative)
    if not isinstance(manifest_relative, str) or not manifest_relative:
        errors.append("fixture bundle %s has no manifest path" % relative)
        return {
            "path": relative,
            "manifest": manifest_relative,
            "files": 0,
            "bytes": 0,
            "tree_sha256": None,
            "generator": None,
        }
    manifest_path = root / manifest_relative
    if manifest_path.is_symlink():
        errors.append(
            "fixture bundle manifest must not be a symlink: %s"
            % manifest_relative
        )
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(
            "cannot read fixture bundle manifest %s: %s"
            % (manifest_relative, exc)
        )
        document = {}
    if document.get("schema_version") != 1:
        errors.append("fixture bundle %s manifest schema_version must be 1" % relative)
    generator = document.get("generator")
    owner_module = pathlib.PurePosixPath(row.get("owner", "")).with_suffix("")
    expected_prefix = ".".join(owner_module.parts) + "."
    if not isinstance(generator, str) or not generator.startswith(expected_prefix):
        errors.append(
            "fixture bundle %s generator is not owned by %s"
            % (relative, row.get("owner"))
        )
    declared = document.get("files")
    if not isinstance(declared, list):
        errors.append("fixture bundle %s manifest files must be a list" % relative)
        declared = []
    declared_by_path = {}
    for item in declared:
        path = item.get("path") if isinstance(item, dict) else None
        if not isinstance(path, str) or not path or path in declared_by_path:
            errors.append("fixture bundle %s has invalid file identity %r" % (relative, path))
            continue
        declared_by_path[path] = item
    declared_tree_sha256 = "sha256:" + hashlib.sha256(
        json.dumps(
            declared, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    if document.get("tree_sha256") != declared_tree_sha256:
        errors.append(
            "fixture bundle %s tree_sha256 differs from its file manifest"
            % relative
        )
    actual_paths = set()
    total_bytes = 0
    if bundle_root.is_dir():
        for path in sorted(bundle_root.rglob("*")):
            if path.is_symlink():
                errors.append(
                    "fixture bundle member must not be a symlink: %s/%s"
                    % (relative, path.relative_to(bundle_root).as_posix())
                )
                continue
            if not path.is_file() or _is_ephemeral_test_artifact(path):
                continue
            member = path.relative_to(bundle_root).as_posix()
            actual_paths.add(member)
            content = path.read_bytes()
            total_bytes += len(content)
            declared_row = declared_by_path.get(member)
            if declared_row is None:
                continue
            digest = "sha256:" + hashlib.sha256(content).hexdigest()
            if declared_row.get("size") != len(content) or declared_row.get("sha256") != digest:
                errors.append("fixture bundle member differs from manifest: %s/%s" % (relative, member))
    missing = sorted(set(declared_by_path) - actual_paths)
    extra = sorted(actual_paths - set(declared_by_path))
    if missing:
        errors.append("fixture bundle %s is missing members: %s" % (relative, ", ".join(missing)))
    if extra:
        errors.append("fixture bundle %s has unmanifested members: %s" % (relative, ", ".join(extra)))
    return {
        "path": relative,
        "manifest": manifest_relative,
        "files": len(actual_paths),
        "bytes": total_bytes,
        "tree_sha256": document.get("tree_sha256"),
        "generator": generator,
    }


def _python_fixture_modules(paths: set[str]) -> dict[str, str]:
    modules = {}
    for path in paths:
        pure = pathlib.PurePosixPath(path)
        if pure.suffix != ".py":
            continue
        if pure.stem != "__init__":
            modules[pure.stem] = path
        if pure.parts[:2] == ("Tools", "tests"):
            modules[".".join(_module_parts(path))] = path
    return modules


def _imported_fixtures(
    tree: ast.AST, fixture_modules: dict[str, str], source_path: str
) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [_import_from_module(source_path, node)]
        else:
            continue
        for name in names:
            if name in fixture_modules:
                found.add(fixture_modules[name])
    return found


def _fixture_import_symbols(
    tree: ast.AST, fixture_modules: dict[str, str], source_path: str
) -> dict[str, set[str] | None]:
    """Return the fixture symbols whose definitions a module consumes.

    Importing one constant executes the fixture module but does not execute
    every helper body in that module. Treating a constant import as though all
    fixture subprocess and copy helpers ran would incorrectly push pure
    contract tests out of the fast tier. A whole-module import remains
    conservative and consumes every definition.
    """
    found: dict[str, set[str] | None] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                path = fixture_modules.get(alias.name)
                if path:
                    found[path] = None
        elif isinstance(node, ast.ImportFrom):
            path = fixture_modules.get(
                _import_from_module(source_path, node)
            )
            if not path:
                continue
            if path in found and found[path] is None:
                continue
            symbols = found.setdefault(path, set())
            if symbols is not None:
                symbols.update(alias.name for alias in node.names)
    return found


def _fixture_definition_effects(tree: ast.Module) -> tuple[dict, dict[str, dict]]:
    zero = {
        "process_calls": 0,
        "temp_resources": 0,
        "file_copies": 0,
        "full_repository_copies": 0,
    }
    import_time = Counter()
    symbols = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols[node.name] = _effect_counts(node)
            continue
        import_time.update(_effect_counts(node))
        names = []
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        for name in names:
            symbols[name] = _effect_counts(node)
    return ({name: import_time[name] for name in zero}, symbols)


def _fixture_closure(direct: set[str], graph: dict[str, set[str]]) -> list[str]:
    resolved = set()
    pending = list(direct)
    while pending:
        path = pending.pop()
        if path in resolved:
            continue
        resolved.add(path)
        pending.extend(graph.get(path, ()))
    return sorted(resolved)


def _validate_owner(root: pathlib.Path, row: dict, path: str, errors: list[str]) -> None:
    owner = row.get("owner")
    if not isinstance(owner, str) or not owner:
        errors.append("%s has no owner path" % path)
        return
    if not (root / owner).exists():
        errors.append("%s owner does not exist: %s" % (path, owner))


def _validate_classification(
    root: pathlib.Path, classification: dict, subject: str, errors: list[str]
) -> None:
    lifecycle = classification.get("lifecycle")
    if lifecycle not in LIFECYCLES:
        errors.append("%s has unknown lifecycle %r" % (subject, lifecycle))
    disposition = classification.get("disposition")
    if disposition != "keep":
        errors.append(
            "%s has disposition %r; retired tests must be deleted" %
            (subject, disposition)
        )
    owner = classification.get("owner")
    if not isinstance(owner, str) or not owner:
        errors.append("%s has no machine or semantic owner path" % subject)
    elif not (root / owner).exists():
        errors.append("%s owner does not exist: %s" % (subject, owner))
    semantics = classification.get("semantics")
    if not isinstance(semantics, str) or not semantics.strip():
        errors.append("%s has no stable semantic classification" % subject)
    contract_symbol = classification.get("owner_contract_symbol")
    if not isinstance(contract_symbol, str) or not contract_symbol.strip():
        errors.append("%s has no owner contract symbol" % subject)
    primary_owner = classification.get("primary_owner_test")
    if not isinstance(primary_owner, str) or not primary_owner.strip():
        errors.append("%s has no primary owner test" % subject)
    if not isinstance(classification.get("consumer_only"), bool):
        errors.append("%s consumer_only must be boolean" % subject)
    duplicate_group = classification.get("duplicate_group")
    if duplicate_group is not None and (
        not isinstance(duplicate_group, str) or not duplicate_group.strip()
    ):
        errors.append("%s duplicate_group must be a non-empty string or null" % subject)


def _apply_overrides(case: dict, module: dict, errors: list[str]) -> dict:
    result = {
        "level": module["level"],
        "lifecycle": module.get("lifecycle", "current"),
        "disposition": module.get("disposition", "keep"),
        "owner": module["owner"],
        "semantics": module.get("semantics", pathlib.Path(module["path"]).stem),
        "parallel_safe": bool(module.get("parallel_safe", False)),
        "owner_contract_symbol": module.get(
            "owner_contract_symbol",
            module.get("semantics", pathlib.Path(module["path"]).stem),
        ),
        "primary_owner_test": module.get("primary_owner_test", "self"),
        "consumer_only": bool(module.get("consumer_only", False)),
        "duplicate_group": module.get("duplicate_group"),
    }
    matched = []
    for override in module.get("overrides", []):
        selector = override.get("selector") if isinstance(override, dict) else None
        if not isinstance(selector, str) or not selector:
            errors.append("%s has an invalid override selector" % module["path"])
            continue
        if fnmatch.fnmatchcase(case["selector"], selector):
            matched.append(selector)
            for field in (
                "level",
                "lifecycle",
                "disposition",
                "owner",
                "semantics",
                "parallel_safe",
                "owner_contract_symbol",
                "primary_owner_test",
                "consumer_only",
                "duplicate_group",
            ):
                if field in override:
                    result[field] = override[field]
            if (
                "owner_contract_symbol" not in override
                and "owner_contract_symbol" not in module
                and ("owner" in override or "semantics" in override)
            ):
                result["owner_contract_symbol"] = result["semantics"]
    if len(matched) > 1:
        errors.append(
            "%s %s matches multiple overrides: %s"
            % (module["path"], case["selector"], ", ".join(matched))
        )
    result["override"] = matched[0] if matched else None
    if result["primary_owner_test"] == "self":
        result["primary_owner_test"] = case["test_id"]
    return result


def build_catalog(root: pathlib.Path) -> tuple[dict, list[str]]:
    manifest = _read_manifest(root)
    level_policy = manifest.get("level_policy")
    if not isinstance(level_policy, dict) or set(level_policy) != set(LEVELS):
        raise TestCatalogError(
            "%s level_policy must define exactly: %s" %
            (MANIFEST_PATH, ", ".join(LEVELS))
        )
    for level in LEVELS:
        if not isinstance(level_policy[level], str) or not level_policy[level].strip():
            raise TestCatalogError(
                "%s level_policy.%s must be non-empty" % (MANIFEST_PATH, level)
            )
    baseline = manifest.get("baseline")
    if not isinstance(baseline, dict):
        raise TestCatalogError("%s must declare one baseline mapping" % MANIFEST_PATH)
    declared_tests = _rows_by_path(manifest.get("tests"), "tests")
    declared_fixtures = _rows_by_path(manifest.get("fixtures"), "fixtures")
    declared_bundles = _rows_by_path(
        manifest.get("fixture_bundles", []), "fixture_bundles"
    )
    bundle_manifests = set()
    for bundle_path, row in declared_bundles.items():
        if not bundle_path.startswith(TEST_DIRECTORY + "/fixtures/"):
            raise TestCatalogError(
                "fixture bundle must stay under %s/fixtures: %s"
                % (TEST_DIRECTORY, bundle_path)
            )
        overlapping = sorted(
            other for other in declared_bundles
            if other != bundle_path and (
                other.startswith(bundle_path.rstrip("/") + "/")
                or bundle_path.startswith(other.rstrip("/") + "/")
            )
        )
        if overlapping:
            raise TestCatalogError(
                "fixture bundle boundaries overlap: %s, %s"
                % (bundle_path, ", ".join(overlapping))
            )
        manifest_path = row.get("manifest")
        if isinstance(manifest_path, str) and manifest_path:
            if manifest_path in bundle_manifests:
                raise TestCatalogError(
                    "fixture_bundles repeat manifest %s" % manifest_path
                )
            bundle_manifests.add(manifest_path)
    discovered_tests = {
        _relative(path, root): path
        for path in sorted((root / TEST_DIRECTORY).glob("test_*.py"))
    }
    discovered_fixtures = _discover_fixture_paths(
        root,
        bundle_roots=set(declared_bundles),
        bundle_manifests=bundle_manifests,
    )
    fixture_modules = _python_fixture_modules(discovered_fixtures)
    call_index = _SourceCallIndex(
        root, set(discovered_tests) | set(discovered_fixtures)
    )
    errors = []
    missing = sorted(set(discovered_tests) - set(declared_tests))
    stale = sorted(set(declared_tests) - set(discovered_tests))
    if missing:
        errors.append("unclassified test modules: %s" % ", ".join(missing))
    if stale:
        errors.append("manifest references missing test modules: %s" % ", ".join(stale))
    missing_fixtures = sorted(discovered_fixtures - set(declared_fixtures))
    stale_fixtures = sorted(set(declared_fixtures) - discovered_fixtures)
    if missing_fixtures:
        errors.append("unclassified fixtures: %s" % ", ".join(missing_fixtures))
    if stale_fixtures:
        errors.append("manifest references missing fixtures: %s" % ", ".join(stale_fixtures))

    fixture_bundles = []
    for relative_path, row in sorted(declared_bundles.items()):
        _validate_owner(root, row, relative_path, errors)
        lifecycle = row.get("lifecycle", "current")
        if lifecycle not in LIFECYCLES:
            errors.append(
                "%s has unknown lifecycle %r" % (relative_path, lifecycle)
            )
        purpose = row.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            errors.append("%s has no stable fixture bundle purpose" % relative_path)
        facts = _bundle_facts(root, row, errors)
        facts.update({
            "owner": row.get("owner"),
            "purpose": purpose,
            "lifecycle": lifecycle,
        })
        fixture_bundles.append(facts)

    fixture_facts = {}
    fixture_import_effects = {}
    fixture_symbol_effects = {}
    fixture_graph = {}
    fixture_effect_totals = Counter()
    fixture_test_imports = []
    for relative_path in sorted(discovered_fixtures):
        path = root / relative_path
        if path.suffix != ".py":
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative_path)
        imported_tests = _cross_test_imports(tree, source)
        if imported_tests:
            fixture_test_imports.append({
                "path": relative_path,
                "imports": imported_tests,
            })
            errors.append(
                "%s imports test modules: %s; fixtures must own their "
                "builders instead of importing a test consumer"
                % (relative_path, ", ".join(imported_tests))
            )
        effects = _effect_counts(tree)
        import_effects, symbol_effects = _fixture_definition_effects(tree)
        fixture_effect_totals.update(effects)
        fixture_facts[relative_path] = effects
        fixture_import_effects[relative_path] = import_effects
        fixture_symbol_effects[relative_path] = symbol_effects
        fixture_graph[relative_path] = _imported_fixtures(
            tree, fixture_modules, relative_path
        )

    modules = []
    all_cases = []
    cross_imports = list(fixture_test_imports)
    effect_totals = Counter()
    for relative_path, source_path in sorted(discovered_tests.items()):
        row = declared_tests.get(relative_path)
        if row is None:
            continue
        _validate_owner(root, row, relative_path, errors)
        level = row.get("level")
        if level == "obsolete" or row.get("disposition") == "delete":
            errors.append("obsolete test must be deleted, not catalogued: %s" % relative_path)
            continue
        if level not in LEVELS:
            errors.append("%s has unknown level %r" % (relative_path, level))
            continue
        source = source_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=relative_path)
        except SyntaxError as exc:
            errors.append("cannot parse %s: %s" % (relative_path, exc))
            continue
        file_effects = _effect_counts(tree)
        effect_totals.update(file_effects)
        fixture_dependencies = _fixture_closure(
            _imported_fixtures(tree, fixture_modules, relative_path),
            fixture_graph,
        )
        fixture_effects = Counter()
        direct_imports = _fixture_import_symbols(
            tree, fixture_modules, relative_path
        )
        for fixture_path in fixture_dependencies:
            fixture_effects.update(fixture_import_effects.get(fixture_path, {}))
        for fixture_path, symbols in direct_imports.items():
            if symbols is None:
                fixture_effects.update(fixture_facts.get(fixture_path, {}))
                continue
            facts_by_symbol = fixture_symbol_effects.get(fixture_path, {})
            for symbol in symbols:
                fixture_effects.update(facts_by_symbol.get(symbol, {}))
        effective_effects = {
            name: file_effects[name] + fixture_effects[name]
            for name in file_effects
        }
        imports = _cross_test_imports(tree, source)
        if imports:
            cross_imports.append({"path": relative_path, "imports": imports})
            errors.append("%s imports test modules: %s" % (relative_path, ", ".join(imports)))
        cases = _test_cases(tree, source_path.stem)
        if not cases:
            errors.append("%s has no statically discoverable test cases" % relative_path)
        expanded = []
        used_overrides = set()
        for case in cases:
            classification = _apply_overrides(case, row, errors)
            if classification["level"] not in LEVELS:
                errors.append(
                    "%s %s has unknown level %r"
                    % (relative_path, case["selector"], classification["level"])
                )
                continue
            _validate_classification(
                root,
                classification,
                "%s %s" % (relative_path, case["selector"]),
                errors,
            )
            if classification["override"]:
                used_overrides.add(classification["override"])
            execution = call_index.case_facts(
                relative_path, case["_class_name"], case["_method_name"]
            )
            if classification["level"] in FAST_LEVELS and (
                execution["transitive_effects"]["process_calls"]
                or execution["transitive_effects"]["full_repository_copies"]
                or execution["e2e_builder_entrypoints"]
            ):
                errors.append(
                    "%s %s is %s but its method/class/process closure reaches "
                    "a process, full repository copy, or E2E builder"
                    % (relative_path, case["selector"], classification["level"])
                )
            if (execution["full_lifecycle"] and
                    classification["level"] != "e2e"):
                errors.append(
                    "%s %s reconstructs a complete lifecycle but is %s; "
                    "complete lifecycle execution belongs only to e2e"
                    % (relative_path, case["selector"],
                       classification["level"])
                )
            expanded_case = {
                key: value for key, value in case.items()
                if not key.startswith("_")
            }
            expanded_case.update(classification)
            expanded_case["path"] = relative_path
            expanded_case["execution"] = execution
            expanded.append(expanded_case)
            all_cases.append(expanded_case)
        declared_override_selectors = {
            override.get("selector")
            for override in row.get("overrides", [])
            if isinstance(override, dict)
        }
        unused = sorted(declared_override_selectors - used_overrides)
        if unused:
            errors.append("%s has unmatched overrides: %s" % (relative_path, ", ".join(unused)))
        scenario_first_use = {}
        for case in expanded:
            builds = case["execution"]["triggered_once_per_process"]["builds"]
            for identity, effects in builds.items():
                scenario_row = scenario_first_use.setdefault(identity, {
                    "effects": effects,
                    "triggered_by": [],
                    "full_lifecycle": False,
                })
                scenario_row["triggered_by"].append(case["test_id"])
                scenario_row["full_lifecycle"] = scenario_row[
                    "full_lifecycle"
                ] or (
                    identity in case["execution"]["full_lifecycle_entrypoints"]
                )
        modules.append(
            {
                "path": relative_path,
                "owner": row["owner"],
                "default_level": level,
                "lifecycle": row.get("lifecycle", "current"),
                "semantics": row.get("semantics", source_path.stem),
                "parallel_safe": bool(row.get("parallel_safe", False)),
                "effects": file_effects,
                "fixture_dependencies": fixture_dependencies,
                "effective_effects": effective_effects,
                "case_count": len(expanded),
                "override_count": len(used_overrides),
                "scenario_first_use_builds": {
                    identity: {
                        "effects": row["effects"],
                        "triggered_by": sorted(set(row["triggered_by"])),
                        "full_lifecycle": row["full_lifecycle"],
                    }
                    for identity, row in sorted(scenario_first_use.items())
                },
                "cases": expanded,
            }
        )

    fixtures = []
    fixture_consumers = {
        path: sorted(
            module["path"]
            for module in modules
            if path in module["fixture_dependencies"]
        )
        for path in discovered_fixtures
    }
    for relative_path in sorted(discovered_fixtures):
        row = declared_fixtures.get(relative_path)
        if row is None:
            continue
        _validate_owner(root, row, relative_path, errors)
        lifecycle = row.get("lifecycle", "current")
        if lifecycle not in LIFECYCLES:
            errors.append(
                "%s has unknown lifecycle %r" % (relative_path, lifecycle)
            )
        purpose = row.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            errors.append("%s has no stable fixture purpose" % relative_path)
        fixtures.append(
            {
                "path": relative_path,
                "owner": row["owner"],
                "purpose": purpose,
                "lifecycle": lifecycle,
                "effects": fixture_facts.get(
                    relative_path,
                    {
                        "process_calls": 0,
                        "temp_resources": 0,
                        "file_copies": 0,
                        "full_repository_copies": 0,
                    },
                ),
                "fixture_dependencies": sorted(fixture_graph.get(relative_path, ())),
                "consumers": fixture_consumers[relative_path],
                "consumer_detection": (
                    "python-import-closure"
                    if pathlib.PurePosixPath(relative_path).suffix == ".py"
                    else "not-traced-static-data"
                ),
            }
        )

    level_counts = Counter(case["level"] for case in all_cases)
    test_ids = {case["test_id"] for case in all_cases}
    duplicate_groups = Counter(
        case["duplicate_group"] for case in all_cases
        if case["duplicate_group"]
    )
    for case in all_cases:
        primary_owner = case["primary_owner_test"]
        if primary_owner not in test_ids:
            errors.append(
                "%s names missing primary owner test %s"
                % (case["test_id"], primary_owner)
            )
        if case["consumer_only"] and primary_owner == case["test_id"]:
            errors.append(
                "%s is consumer-only but owns its own tested semantics"
                % case["test_id"]
            )
        group = case["duplicate_group"]
        if group and duplicate_groups[group] < 2:
            errors.append(
                "%s names singleton duplicate group %s"
                % (case["test_id"], group)
            )
    parallel_safe_cases = sum(1 for case in all_cases if case["parallel_safe"])
    transitive_exposure = {
        "process_calls": sum(
            bool(case["execution"]["transitive_effects"]["process_calls"])
            for case in all_cases
        ),
        "temp_resources": sum(
            bool(case["execution"]["transitive_effects"]["temp_resources"])
            for case in all_cases
        ),
        "file_copies": sum(
            bool(case["execution"]["transitive_effects"]["file_copies"])
            for case in all_cases
        ),
        "full_repository_copies": sum(
            bool(case["execution"]["transitive_effects"]["full_repository_copies"])
            for case in all_cases
        ),
        "e2e_builder": sum(
            bool(case["execution"]["e2e_builder_entrypoints"])
            for case in all_cases
        ),
        "full_lifecycle": sum(
            bool(case["execution"]["full_lifecycle"])
            for case in all_cases
        ),
    }
    scenario_first_use_builds = sum(
        len(module["scenario_first_use_builds"]) for module in modules
    )
    catalog = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "generated_from": MANIFEST_PATH,
        "baseline": baseline,
        "level_policy": level_policy,
        "levels": list(LEVELS),
        "summary": {
            "test_modules": len(modules),
            "test_cases": len(all_cases),
            "fixtures": len(fixtures),
            "fixture_bundles": len(fixture_bundles),
            "levels": {level: level_counts[level] for level in LEVELS},
            "parallel_safe_cases": parallel_safe_cases,
            "source_effects": dict(sorted(effect_totals.items())),
            "fixture_source_effects": dict(sorted(fixture_effect_totals.items())),
            "method_transitive_exposure": transitive_exposure,
            "module_scenario_first_use_builds": scenario_first_use_builds,
            "cross_test_imports": len(cross_imports),
        },
        "modules": modules,
        "fixtures": fixtures,
        "fixture_bundles": fixture_bundles,
        "cross_test_imports": cross_imports,
    }
    return catalog, errors


def render_json(catalog: dict) -> str:
    return json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _effect_label(scope: dict) -> str:
    effects = scope["effects"]
    values = []
    for key, label in (
        ("process_calls", "proc"),
        ("temp_resources", "temp"),
        ("file_copies", "copy"),
        ("full_repository_copies", "full-copy"),
    ):
        if effects[key]:
            values.append("%s=%d" % (label, effects[key]))
    if scope["full_lifecycle"]:
        values.append("full-lifecycle")
    return ", ".join(values) if values else "—"


def render_markdown(catalog: dict) -> str:
    summary = catalog["summary"]
    lines = [
        "# Test Catalog",
        "",
        "This file is generated from `Tools/test-ownership.yaml` and static source facts. Run `python3 Tools/generate_test_catalog.py .` to regenerate it. Do not edit this projection by hand.",
        "",
        "## Summary",
        "",
        "| Test modules | Test cases | Fixtures | Fixture bundles | Parallel-safe cases | Test process calls | Fixture process calls | Test full copies | Fixture full copies | Cross-test imports |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        "| {test_modules} | {test_cases} | {fixtures} | {fixture_bundles} | {parallel_safe_cases} | {test_process} | {fixture_process} | {test_full} | {fixture_full} | {cross_test_imports} |".format(
            **summary,
            test_process=summary["source_effects"]["process_calls"],
            fixture_process=summary["fixture_source_effects"]["process_calls"],
            test_full=summary["source_effects"]["full_repository_copies"],
            fixture_full=summary["fixture_source_effects"]["full_repository_copies"],
        ),
        "",
        "### Method-level transitive exposure",
        "",
        "These counts identify test methods whose per-method, per-class, or per-process source closure reaches each effect. They are exposure counts, not runtime invocation totals.",
        "",
        "| Process | Temporary resource | File copy | Full repository copy | E2E builder | Full lifecycle |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
        "| {process_calls} | {temp_resources} | {file_copies} | {full_repository_copies} | {e2e_builder} | {full_lifecycle} |".format(
            **summary["method_transitive_exposure"]
        ),
        "",
        "## Before and current static baseline",
        "",
        "| Metric | Before closure | Current |",
        "| --- | ---: | ---: |",
        "| Test modules | {before_modules} | {test_modules} |".format(
            before_modules=catalog["baseline"]["test_modules"], **summary
        ),
        "| Test cases | {before_cases} | {test_cases} |".format(
            before_cases=catalog["baseline"]["test_cases"], **summary
        ),
        "| Process-launch call sites | {before_process} | {current_process} |".format(
            before_process=catalog["baseline"]["process_calls"],
            current_process=summary["source_effects"]["process_calls"]
            + summary["fixture_source_effects"]["process_calls"],
        ),
        "| Temporary-resource call sites | {before_temp} | {current_temp} |".format(
            before_temp=catalog["baseline"]["temp_resources"],
            current_temp=summary["source_effects"]["temp_resources"]
            + summary["fixture_source_effects"]["temp_resources"],
        ),
        "| Full repository copy call sites | {before_copy} | {current_copy} |".format(
            before_copy=catalog["baseline"]["full_repository_copies"],
            current_copy=summary["source_effects"]["full_repository_copies"]
            + summary["fixture_source_effects"]["full_repository_copies"],
        ),
        "| Cross-test import sites | {before_cross} | {current_cross} |".format(
            before_cross=catalog["baseline"]["cross_test_import_sites"],
            current_cross=summary["cross_test_imports"],
        ),
        "",
        "## Observed pre-closure runtime",
        "",
        "| Slice | Completed cases | Elapsed seconds | Status |",
        "| --- | ---: | ---: | --- |",
    ]
    for observation in catalog["baseline"].get("observed_runs", []):
        lines.append(
            "| {label} | {completed_cases} | {elapsed_seconds} | {status} |".format(
                **observation
            )
        )
    lines.extend([
        "",
        "## Execution levels",
        "",
        "| Level | Definition | Cases |",
        "| --- | --- | ---: |",
    ])
    for level in LEVELS:
        lines.append(
            "| `%s` | %s | %d |" %
            (level, catalog["level_policy"][level], summary["levels"][level])
        )
    lines.extend(
        [
            "",
            "## Test modules",
            "",
            "| Module | Owner | Default level | Parallel safe | Cases | Overrides | Process | Temp | Copies | Full copies |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for module in catalog["modules"]:
        effects = module["effects"]
        lines.append(
            "| `{path}` | `{owner}` | `{default_level}` | {parallel_safe} | {case_count} | {override_count} | {process_calls} | {temp_resources} | {file_copies} | {full_repository_copies} |".format(
                **module, **effects
            )
        )
    lines.extend([
        "",
        "## Cached scenario first-use builds",
        "",
        "Each row is charged once in that test module's child process. `Triggered by` is dependency exposure and does not multiply the build cost.",
        "",
        "| Module | Scenario build | Triggered by | Full lifecycle | Process | Temp | Copies | Full copies |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |",
    ])
    for module in catalog["modules"]:
        for identity, build in module["scenario_first_use_builds"].items():
            lines.append(
                "| `{module}` | `{identity}` | {trigger_count} | {full_lifecycle} | {process_calls} | {temp_resources} | {file_copies} | {full_repository_copies} |".format(
                    module=module["path"],
                    identity=identity,
                    trigger_count=len(build["triggered_by"]),
                    full_lifecycle=build["full_lifecycle"],
                    **build["effects"]
                )
            )
    override_cases = [
        case
        for module in catalog["modules"]
        for case in module["cases"]
        if case["override"]
    ]
    lines.extend(
        [
            "",
            "## Method overrides",
            "",
            "Only mixed test modules need method-level rows. All other cases inherit their module classification.",
            "",
            "| Test case | Owner | Level | Parallel safe | Stable semantics |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for case in override_cases:
        lines.append(
            "| `{test_id}` | `{owner}` | `{level}` | {parallel_safe} | {semantics} |".format(
                **case
            )
        )
    lines.extend(
        [
            "",
            "## Method ownership and execution facts",
            "",
            "Ownership fields come from `Tools/test-ownership.yaml`; fixture entrypoints and effects are derived from source call closures. Direct method work, per-method fixture work, per-class setup, and import-time process work remain separate. A cached scenario builder is shown as a trigger on every dependent method, while its walker cost appears under scenario first-use/process once per scenario rather than being multiplied by every method.",
            "",
            "| Test case | Contract symbol | Primary owner test | Level | Direct method | Per-method fixture | Per-class fixture | Import/process | Scenario first-use/process | Builder triggers | Fixture entrypoints | Consumer only | Duplicate group | Disposition |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for module in catalog["modules"]:
        for case in module["cases"]:
            execution = case["execution"]
            entrypoints = "<br>".join(
                "`%s`" % entry for entry in execution["fixture_entrypoints"]
            ) or "—"
            display = dict(case)
            display.update({
                "method": _effect_label(execution["scopes"]["direct_method"]),
                "per_method": _effect_label(
                    execution["scopes"]["per_method"]
                ),
                "class_scope": _effect_label(execution["scopes"]["per_class"]),
                "process": _effect_label(execution["scopes"]["per_process"]),
                "first_use": (
                    ", ".join(
                        "%s=%d" % (label, execution[
                            "triggered_once_per_process"]["effects"][key])
                        for key, label in (
                            ("process_calls", "proc"),
                            ("temp_resources", "temp"),
                            ("file_copies", "copy"),
                            ("full_repository_copies", "full-copy"),
                        )
                        if execution["triggered_once_per_process"][
                            "effects"][key]
                    ) or "—"
                ),
                "builder_triggers": "<br>".join(
                    "`%s`" % entry
                    for entry in execution["builder_triggers"]
                ) or "—",
                "entrypoints": entrypoints,
                "duplicate_group": (
                    "`%s`" % case["duplicate_group"]
                    if case["duplicate_group"] else "—"
                ),
            })
            lines.append(
                "| `{test_id}` | `{owner_contract_symbol}` | `{primary_owner_test}` | `{level}` | {method} | {per_method} | {class_scope} | {process} | {first_use} | {builder_triggers} | {entrypoints} | {consumer_only} | {duplicate_group} | `{disposition}` |".format(
                    **display
                )
            )
    lines.extend(
        [
            "",
            "## Fixtures",
            "",
            "Python fixture consumers are derived from the import closure. Static data fixtures show `—`: the catalog does not guess file consumption from path-shaped strings.",
            "",
            "| Fixture | Owner | Purpose | Consumers | Process | Temp | Copies | Full copies |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for fixture in catalog["fixtures"]:
        consumer_count = (
            str(len(fixture["consumers"]))
            if fixture["consumer_detection"] == "python-import-closure"
            else "—"
        )
        lines.append(
            "| `{path}` | `{owner}` | {purpose} | {consumer_count} | {process_calls} | {temp_resources} | {file_copies} | {full_repository_copies} |".format(
                **fixture,
                consumer_count=consumer_count,
                **fixture["effects"]
            )
        )
    lines.extend([
        "",
        "## Generated fixture bundles",
        "",
        "Bundle membership, sizes, and hashes come from the adjacent generated manifest; `Tools/test-ownership.yaml` classifies only the bundle boundary and owner.",
        "",
        "| Bundle | Manifest | Owner | Generator | Files | Bytes | Tree SHA-256 |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ])
    for bundle in catalog["fixture_bundles"]:
        lines.append(
            "| `{path}` | `{manifest}` | `{owner}` | `{generator}` | {files} | {bytes} | `{tree_sha256}` |".format(
                **bundle
            )
        )
    lines.append("")
    return "\n".join(lines)


def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _check_projection(path: pathlib.Path, expected: str, errors: list[str]) -> None:
    try:
        current = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append("cannot read generated projection %s: %s" % (path, exc))
        return
    if current != expected:
        errors.append("generated projection is stale: %s" % path)


def load_current_catalog(root: pathlib.Path) -> dict:
    """Return the compiled runner catalog only when both projections are current."""
    catalog, errors = build_catalog(root)
    markdown = render_markdown(catalog)
    json_text = render_json(catalog)
    _check_projection(root / MARKDOWN_OUTPUT, markdown, errors)
    _check_projection(root / JSON_OUTPUT, json_text, errors)
    if errors:
        raise TestCatalogError("; ".join(errors))
    # The byte comparison above makes this parsed projection equivalent to
    # the reviewed source plus observed facts, rather than a stale second
    # selection authority.
    try:
        return json.loads((root / JSON_OUTPUT).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TestCatalogError(
            "cannot load generated projection %s: %s" % (JSON_OUTPUT, exc)
        ) from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    try:
        catalog, errors = build_catalog(root)
    except TestCatalogError as exc:
        print("test catalog: FAIL: %s" % exc, file=sys.stderr)
        return 1
    markdown = render_markdown(catalog)
    json_text = render_json(catalog)
    if args.check:
        _check_projection(root / MARKDOWN_OUTPUT, markdown, errors)
        _check_projection(root / JSON_OUTPUT, json_text, errors)
    elif not errors:
        _write(root / MARKDOWN_OUTPUT, markdown)
        _write(root / JSON_OUTPUT, json_text)
    if errors:
        for error in errors:
            print("test catalog: FAIL: %s" % error, file=sys.stderr)
        return 1
    action = "checked" if args.check else "generated"
    print(
        "test catalog: %s %d modules, %d cases, %d fixtures, %d bundles"
        % (
            action,
            catalog["summary"]["test_modules"],
            catalog["summary"]["test_cases"],
            catalog["summary"]["fixtures"],
            catalog["summary"]["fixture_bundles"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
