"""Derive the Tool-module facts the boundary guard and report both read.

The Tool engineering contract covers module identity, declared public surface,
and dependency direction. A guard and a report that measured the tree in two
different ways would create two machine owners, so both read this module and
neither parses Python a second time.

What is measured here is what the codebase actually does, not what a tidier
codebase would do.  The edge this module reports is `(consumer, module,
symbol)`, resolved by binding import names (including package submodules,
aliases and imports written inside a function body) and then walking
attribute access on those names.  Direct `from module import symbol` reads
remain direct symbol consumption rather than module bindings.

Two consumption forms stay deliberately outside: a subprocess invoking
another tool's command line consumes that tool's registered CLI surface,
owned by `cli-contract.yaml`; and registry-driven producer resolution such as
`queue_runtime.gate_registry.producer_module()` is a declared control
inversion, not a static edge. Both are exposed through
``EXCLUDED_CONSUMPTION_FORMS`` rather than silently omitted.
"""

import ast
import os

from Tools.platform.common import implementation_marker


TOOLS_DIRNAME = "Tools"
EXCLUDED_DIRS = frozenset(("tests", "__pycache__", "compiled", "schemas"))
EXCLUDED_CONSUMPTION_FORMS = (
    "subprocess-cli",
    "registry-driven-dynamic-import",
)

# This is Tool engineering implementation, not a test fixture. Tests consume
# it to verify the declared boundary; the report consumes the same facts to
# regenerate that declaration.


def shipped_modules(tools_root):
    """Return every shipped module path, relative to the Tools root.

    Membership is a rule over the tree rather than a list, because a list is
    exactly what a new file slips past.  Subpackages are walked so that code
    moved into one stays inside the contract.
    """
    found = []
    for base, dirnames, filenames in os.walk(tools_root):
        dirnames[:] = sorted(
            name for name in dirnames
            if name not in EXCLUDED_DIRS and not name.startswith("."))
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = os.path.relpath(os.path.join(base, filename), tools_root)
            found.append(path.replace(os.sep, "/"))
    return sorted(found)


def module_name(relative_path):
    """Map a Tools-relative path to the name importers actually write."""
    stem = relative_path[:-3] if relative_path.endswith(".py") else relative_path
    parts = [part for part in stem.split("/") if part]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _without_tools_prefix(name):
    """Return the repository-local identity for one imported module name."""
    if name == TOOLS_DIRNAME:
        return ""
    prefix = TOOLS_DIRNAME + "."
    return name[len(prefix):] if name.startswith(prefix) else name


def implementation_module(source_text):
    """Return the implementation named by a standard public wrapper."""
    qualified = implementation_marker.parse_implementation_module(
        ast.parse(source_text), required=False)
    return _without_tools_prefix(qualified) if qualified is not None else None


def _is_cli_tree(tree, qualified_implementation):
    """Whether one parsed top-level module declares a CLI adapter."""
    has_main = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
        node.name == "main"
        for node in tree.body
    )
    if not has_main:
        return False
    if qualified_implementation is not None:
        return True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(
            func, "id", "")
        if name == "ArgumentParser":
            return True
    return False


def is_cli_module(source_text):
    """Whether a top-level source is a repository CLI adapter.

    New adapters are deliberately thin and therefore do not build their own
    parser: their literal ``IMPLEMENTATION_MODULE`` assignment is the stable
    machine-readable edge to the implementation that does.  Direct parser
    ownership remains supported for older or isolated fixture commands.

    Callers that walk recursively must still apply the top-level-path rule.
    An implementation module can define ``main`` and an ``ArgumentParser``
    without becoming a second external interface.
    """
    tree = ast.parse(source_text)
    qualified = implementation_marker.parse_implementation_module(
        tree, required=False)
    return _is_cli_tree(tree, qualified)


def _from_module(node, current_package=""):
    """Resolve one ImportFrom owner to a repository-local dotted name."""
    if not node.level:
        return _without_tools_prefix(node.module or "")
    parts = current_package.split(".") if current_package else []
    ascend = node.level - 1
    if ascend > len(parts):
        return ""
    if ascend:
        parts = parts[:-ascend]
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(part for part in parts if part)


def _known_import(name, known_full):
    """Whether ``name`` names or contains a shipped module."""
    if not name:
        return False
    return name in known_full or any(
        module.startswith(name + ".") or name.startswith(module + ".")
        for module in known_full)


def _import_bindings(tree, known, known_full=(), current_package=""):
    """Map each local name bound by an import to the shipped module it names.

    Aliases and function-body imports are both included: the lazy import that
    hid one dependency cycle in this tree was written inside a function, and a
    guard that only reads module-level statements would have called that tree
    acyclic.

    Only a name that is itself a module is bound here.  `from pkg import sub`
    binds a module, and attribute access on it is consumption of that module;
    `from mod import NAME` binds a value, and attribute access on a value is
    not consumption of anything its owner declared.  Recording the second as
    if it were the first puts `fullmatch` and `pattern` -- the methods of a
    compiled regex a consumer imported -- into the owner's declared public
    surface, and a surface that lists them has stopped answering who offers
    what.  The import itself is still recorded as consumption of `NAME`.
    """
    known_full = set(known_full) | set(known)
    bindings = {}

    class ModuleImportCollector(ast.NodeVisitor):
        """Collect imports executed in module scope, including control blocks.

        A flat ``ast.walk`` also collected lazy imports from every function.
        That made an import local to one function look available in sibling
        functions and at module scope. Function-local imports are resolved by
        ``_function_binding_facts`` instead; the module map must contain only
        names that Python actually binds in module scope.
        """

        def visit_FunctionDef(self, _node):
            return

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_Lambda = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Import(self, node):
            for alias in node.names:
                target = _without_tools_prefix(alias.name)
                if not _known_import(target, known_full):
                    continue
                if alias.asname:
                    bindings[alias.asname] = target
                    continue
                # Python binds the written root.  ``Tools`` is only the
                # repository package prefix, not a boundary node, so an empty
                # prefix lets attribute resolution continue at the Area.
                written_root = alias.name.split(".")[0]
                bindings[written_root] = "" if written_root == TOOLS_DIRNAME \
                    else target.split(".")[0]

        def visit_ImportFrom(self, node):
            owner = _from_module(node, current_package)
            for alias in node.names:
                submodule = "%s.%s" % (owner, alias.name) if owner \
                    else alias.name
                if submodule in known_full:
                    bindings[alias.asname or alias.name] = submodule

    ModuleImportCollector().visit(tree)
    return bindings


def _imported_modules(tree, known_full, current_package=""):
    """Every shipped module an import statement names, at full dotted name.

    `_import_bindings` answers "which module does this local name denote" so
    attribute reads can be assigned to the actual owner.  This function asks
    only which modules the import statement names, including full submodule
    identities used to order a package internally.
    """
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported = _without_tools_prefix(alias.name)
                if imported in known_full:
                    found.add(imported)
                    continue
                prefixes = [module for module in known_full
                            if imported.startswith(module + ".")]
                if prefixes:
                    found.add(max(prefixes, key=len))
        elif isinstance(node, ast.ImportFrom):
            owner = _from_module(node, current_package)
            for alias in node.names:
                submodule = "%s.%s" % (owner, alias.name) if owner \
                    else alias.name
                if submodule in known_full:
                    found.add(submodule)
                elif owner in known_full:
                    found.add(owner)
    return found


def source_imports(source_text, known_full, *, current_package="",
                   filename="<source>"):
    """Return complete shipped-module imports from one source string."""
    tree = ast.parse(source_text, filename=filename)
    return sorted(_imported_modules(
        tree, set(known_full), current_package=current_package))


def _attribute_chain(node):
    """Return ``name.attr...`` as parts, or None for a computed receiver."""
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return list(reversed(parts))


def _attribute_consumption(node, bindings, known_full):
    """Resolve an attribute read to its longest shipped module prefix."""
    parts = _attribute_chain(node)
    if not parts or parts[0] not in bindings:
        return None
    prefix = bindings[parts[0]]
    resolved = ([part for part in prefix.split(".") if part] + parts[1:])
    for end in range(len(resolved), 0, -1):
        target = ".".join(resolved[:end])
        if target not in known_full:
            continue
        if end == len(resolved):
            return None  # the expression denotes a module, not one symbol
        return target, resolved[end]
    return None


def _function_binding_facts(node, known_full, current_package):
    """Return local bindings that can shadow one module import.

    The static graph used to resolve every attribute against a flattened map
    of imports. A function argument named like an imported module therefore
    looked like a module read: ``profile_contract.root`` on a local contract
    object was reported as consumption of a nonexistent module-level
    ``root`` export. This scope summary keeps lazy function imports visible
    while stopping ordinary locals from widening another module's API.
    """
    local_names = set()
    import_bindings = {}
    global_names = set()
    nonlocal_names = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        arguments = node.args
        for argument in (
                list(arguments.posonlyargs) + list(arguments.args) +
                list(arguments.kwonlyargs)):
            local_names.add(argument.arg)
        if arguments.vararg is not None:
            local_names.add(arguments.vararg.arg)
        if arguments.kwarg is not None:
            local_names.add(arguments.kwarg.arg)

    class Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, child):
            if child is node:
                for statement in child.body:
                    self.visit(statement)
            else:
                local_names.add(child.name)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Lambda(self, child):
            if child is node:
                self.visit(child.body)

        def visit_ClassDef(self, child):
            local_names.add(child.name)

        def visit_Global(self, child):
            global_names.update(child.names)

        def visit_Nonlocal(self, child):
            nonlocal_names.update(child.names)

        def visit_Name(self, child):
            if isinstance(child.ctx, ast.Store):
                local_names.add(child.id)

        def visit_Import(self, child):
            for alias in child.names:
                local = alias.asname or alias.name.split(".")[0]
                local_names.add(local)
                target = _without_tools_prefix(alias.name)
                if _known_import(target, known_full):
                    import_bindings[local] = target if alias.asname else \
                        ("" if local == TOOLS_DIRNAME else target.split(".")[0])

        def visit_ImportFrom(self, child):
            owner = _from_module(child, current_package)
            for alias in child.names:
                local = alias.asname or alias.name
                local_names.add(local)
                submodule = "%s.%s" % (owner, alias.name) if owner \
                    else alias.name
                if submodule in known_full:
                    import_bindings[local] = submodule

    Collector().visit(node)
    local_names.difference_update(global_names)
    for name in global_names:
        import_bindings.pop(name, None)
    return {
        "locals": local_names,
        "imports": import_bindings,
        "globals": global_names,
        "nonlocals": nonlocal_names,
    }


def _scoped_attribute_consumption(
        node, bindings, known_full, parents, scope_cache, current_package):
    """Resolve one attribute against the nearest actual module binding."""
    parts = _attribute_chain(node)
    if not parts:
        return None
    root = parts[0]
    child = node
    ancestor = parents.get(node)
    scopes = []
    while ancestor is not None:
        if isinstance(ancestor, (
                ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            # Function arguments, annotations, defaults, decorators and return
            # annotations execute in the enclosing scope. Only the function
            # or lambda body sees its local bindings. ``child`` is the direct
            # descendant on the path from the attribute to this scope.
            in_body = child is ancestor.body if isinstance(
                ancestor, ast.Lambda) else child in ancestor.body
            if in_body:
                scopes.append(ancestor)
        child = ancestor
        ancestor = parents.get(ancestor)
    for scope in scopes:
        facts = scope_cache.get(scope)
        if facts is None:
            facts = _function_binding_facts(
                scope, known_full, current_package)
            scope_cache[scope] = facts
        if root in facts["globals"]:
            break
        target = facts["imports"].get(root)
        if target is not None:
            return _attribute_consumption(node, {root: target}, known_full)
        if root in facts["locals"] and root not in facts["nonlocals"]:
            return None
    return _attribute_consumption(node, bindings, known_full)


def module_facts(tools_root, relative_path, known, known_full=()):
    """Parse one module into the facts every consumer of this module reads.

    Consumption is cross-module consumption.  A module reading its own names
    is not consumption of anything; a sibling module is a different owner and
    remains visible.  Collapsing siblings to their first path segment hid both
    ownership and cycles after the Area/Domain migration.
    """
    path = os.path.join(tools_root, relative_path)
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source, filename=relative_path)
    name = module_name(relative_path)
    known_full = set(known_full) | set(known)
    is_package = relative_path.replace("\\", "/").endswith("/__init__.py")
    current_package = name if is_package else name.rpartition(".")[0]

    bindings = _import_bindings(
        tree, known, known_full, current_package=current_package)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    scope_cache = {}
    edges = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        edge = _scoped_attribute_consumption(
            node, bindings, known_full, parents, scope_cache,
            current_package)
        if edge is not None and edge[0] != name:
            edges.add(edge)
    # A `from module import symbol` is consumption of that symbol even though
    # no attribute node exists for it.  Attribute it to the module that
    # actually defines the symbol, not to the root of its dotted name: a
    # package whose submodules were credited to the root produced one entry
    # carrying every name and thirty entries offering nothing, which describes
    # no boundary anyone could read.
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        owner = _from_module(node, current_package)
        target = owner if owner in known_full else None
        if target is None:
            continue
        if target == name:
            continue
        for alias in node.names:
            submodule = "%s.%s" % (owner, alias.name) if owner else alias.name
            if submodule in known_full:
                continue  # importing a submodule is a dependency, not a read
            edges.add((target, alias.name))

    defs, classes = [], []
    top_level_symbols = set()
    source_public_exports = None
    source_public_export_errors = []
    source_public_export_assignments = 0

    def add_target_names(target):
        if isinstance(target, ast.Name):
            top_level_symbols.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                add_target_names(element)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.append(node.name)
            top_level_symbols.add(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
            top_level_symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                add_target_names(target)
            if any(isinstance(target, ast.Name) and target.id == "__all__"
                   for target in node.targets):
                source_public_export_assignments += 1
                if source_public_export_assignments > 1:
                    source_public_export_errors.append(
                        "module assigns __all__ more than once")
                try:
                    exported = ast.literal_eval(node.value)
                except (TypeError, ValueError):
                    exported = None
                if not isinstance(exported, (list, tuple)) or any(
                        not isinstance(value, str) or not value
                        for value in exported or ()):
                    source_public_export_errors.append(
                        "__all__ must be a literal list or tuple of names")
                elif len(exported) != len(set(exported)):
                    source_public_export_errors.append(
                        "__all__ repeats a public name")
                else:
                    source_public_exports = tuple(exported)
        elif isinstance(node, ast.AnnAssign):
            add_target_names(node.target)
            if isinstance(node.target, ast.Name) and \
                    node.target.id == "__all__":
                source_public_export_assignments += 1
                if source_public_export_assignments > 1:
                    source_public_export_errors.append(
                        "module assigns __all__ more than once")
                try:
                    exported = ast.literal_eval(node.value)
                except (TypeError, ValueError):
                    exported = None
                if not isinstance(exported, (list, tuple)) or any(
                        not isinstance(value, str) or not value
                        for value in exported or ()):
                    source_public_export_errors.append(
                        "__all__ must be a literal list or tuple of names")
                elif len(exported) != len(set(exported)):
                    source_public_export_errors.append(
                        "__all__ repeats a public name")
                else:
                    source_public_exports = tuple(exported)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top_level_symbols.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    top_level_symbols.add(alias.asname or alias.name)

    imported_modules = _imported_modules(
        tree, known_full, current_package=current_package)
    qualified_implementation = \
        implementation_marker.parse_implementation_module(
            tree, label=relative_path, required=False)
    top_level = "/" not in relative_path.replace("\\", "/")
    wrapper_implementation = (
        _without_tools_prefix(qualified_implementation)
        if top_level and qualified_implementation is not None else None)
    if wrapper_implementation in known_full and wrapper_implementation != name:
        imported_modules.add(wrapper_implementation)

    return {
        "path": relative_path,
        "module": name,
        "lines": source.count("\n") + 1,
        # Dependency and consumption are different questions and were sharing
        # one answer.  `bindings` maps a local name to the module it came from,
        # which is what attribute access must be resolved against -- but it
        # only holds names that are themselves modules, so `from mod import
        # VALUE` left no trace and the dependency became invisible to the very
        # rule that forbids a cycle.  Dependency now derives from every import
        # statement; consumption still derives from bindings.
        "imports": sorted(imported_modules),
        "imported_modules": sorted(imported_modules),
        "consumes": sorted(edges),
        "top_level_defs": sorted(defs),
        "top_level_classes": sorted(classes),
        "top_level_symbols": sorted(top_level_symbols),
        "source_public_exports": (
            list(source_public_exports)
            if source_public_exports is not None else None),
        "source_public_export_errors": sorted(
            set(source_public_export_errors)),
        "cli_entrypoint": (
            top_level and _is_cli_tree(tree, qualified_implementation)),
        "implementation_module": wrapper_implementation,
    }


def collect(repo_root):
    """Parse the whole shipped tree once and index it by module name."""
    tools_root = os.path.join(repo_root, TOOLS_DIRNAME)
    paths = shipped_modules(tools_root)
    known_full = {module_name(path) for path in paths}
    known = set(known_full)
    facts = {}
    for path in paths:
        entry = module_facts(tools_root, path, known, known_full)
        facts[entry["module"]] = entry
    return facts


def cli_modules(facts):
    """Return sorted modules whose source declares a CLI entry point."""
    return sorted(
        name for name, row in facts.items() if row.get("cli_entrypoint"))


def consumption_pairs(facts):
    """Return every (consumer, module, symbol) edge, sorted."""
    pairs = []
    for consumer, entry in facts.items():
        for target, symbol in entry["consumes"]:
            pairs.append((consumer, target, symbol))
    return sorted(pairs)


def private_pairs(facts):
    """Cross-module consumption of a name the owner marked internal."""
    return [row for row in consumption_pairs(facts)
            if row[2].startswith("_")]


def import_graph(facts):
    """Adjacency over complete shipped module identities.

    The leading import package ``Tools`` is syntax, not an architecture node;
    facts remove it at parse time.  Every remaining Area/Domain/package segment
    stays in the identity so two modules inside one Area cannot collapse into a
    self-edge and disappear from cycle detection.
    """
    graph = {name: set() for name in facts}
    for name, entry in facts.items():
        edges = graph[name]
        for target in entry["imports"]:
            if target in facts and target != name:
                edges.add(target)
    return {name: sorted(targets) for name, targets in graph.items()}


def strongly_connected(graph):
    """Return every cycle-bearing component, largest first (Tarjan).

    Reported rather than merely detected: a contract that says "no cycles"
    owes its reader the actual set when it refuses.
    """
    index = {}
    low = {}
    stack = []
    on_stack = set()
    counter = [0]
    components = []

    def visit(node):
        # Iterative: this tree is small, but a recursive Tarjan would tie the
        # guard's reliability to the interpreter's stack depth.
        work = [(node, iter(graph.get(node, ())))]
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on_stack.add(node)
        while work:
            current, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter[0]
                    counter[0] += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(graph.get(child, ()))))
                    advanced = True
                    break
                if child in on_stack:
                    low[current] = min(low[current], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[current])
            if low[current] == index[current]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == current:
                        break
                if len(component) > 1:
                    components.append(sorted(component))

    for node in sorted(graph):
        if node not in index:
            visit(node)
    return sorted(components, key=lambda members: (-len(members), members))


def def_span_sha256(repo_root, module, symbol):
    """Hash the source span of one definition, for exception content binding.

    An excepted private symbol carries no compatibility promise, so the ledger
    binds what it excepted: if the definition is rewritten the entry stops
    matching and the exception must be re-argued rather than silently
    inherited.  Returns None when the symbol is not a module-level definition
    -- a constant's value is bound by the manifest review, not by a span.
    """
    import hashlib

    facts_path = None
    tools_root = os.path.join(repo_root, TOOLS_DIRNAME)
    for path in shipped_modules(tools_root):
        if module_name(path) == module:
            facts_path = os.path.join(tools_root, path)
            break
    if facts_path is None:
        return None
    with open(facts_path, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    tree = ast.parse("\n".join(lines), filename=module)
    for node in tree.body:
        name = getattr(node, "name", None)
        if name != symbol:
            continue
        start = node.lineno - 1
        end = getattr(node, "end_lineno", node.lineno)
        span = "\n".join(lines[start:end])
        return "sha256:" + hashlib.sha256(span.encode("utf-8")).hexdigest()

    # A façade re-exports a name it does not define.  Following the
    # re-export keeps the binding attached to the definition rather than to
    # the spelling a consumer happens to use: without this, moving a
    # definition into a package silently turns every exception over it into
    # an unbound entry, and the only advertised remedy would strip the
    # bindings for good.
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if (alias.asname or alias.name) != symbol:
                    continue
                target = node.module
                if node.level:
                    package = module.rsplit(".", 1)[0] if "." in module else ""
                    target = "%s.%s" % (package, node.module) if package \
                        else node.module
                return def_span_sha256(repo_root, target, alias.name)
    return None


def import_closure(repo_root, roots):
    """Return every shipped module reachable from ``roots`` by import.

    Tests that stage a partial Tools tree used to name their dependencies by
    hand, which made every new module a latent break in an unrelated test: the
    list said what the tree needed on the day it was written, and nothing
    re-derived it afterwards.  Extracting one capability into a new module is
    a normal act, and it should not require finding every hand-copied
    inventory that happened to reach the old home.

    The closure is over static imports, matching what the guard reads, so a
    module the copier misses is the same module the guard would have named.
    """
    facts = collect(repo_root)
    seen = set()
    pending = [name for name in roots]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        # A package name reached by import stands for every module beneath it:
        # staging only `pkg/__init__.py` produces a tree that imports cleanly
        # and then fails at the first real call.
        beneath = sorted(other for other in facts
                         if other == name or other.startswith(name + "."))
        if not beneath:
            continue
        seen.add(name)
        for member in beneath:
            seen.add(member)
            pending.extend(facts[member]["imports"])
    return sorted(seen)


def stage_shipped_modules(repo_root, destination, roots):
    """Copy ``roots`` and their import closure into ``destination``/Tools.

    The staged layout mirrors the real one rather than flattening it, because
    a staged tree exists to be run against, and the modules resolve each other
    by the same relative paths there as here.

    Returns the module names copied, so a caller can assert over them.
    """
    import shutil

    tools_root = os.path.join(repo_root, TOOLS_DIRNAME)
    staged_root = os.path.join(destination, TOOLS_DIRNAME)
    names = import_closure(repo_root, roots)
    by_module = {module_name(path): path
                 for path in shipped_modules(tools_root)}
    for name in names:
        relative = by_module.get(name)
        if relative is None:
            continue
        target = os.path.join(staged_root, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(tools_root, relative), target)
    return names


def package_layers(facts, package):
    """Return the induced subgraph for one package.

    ``import_graph`` now retains complete identities and already detects these
    cycles.  This projection remains for reports that want a package-scoped
    view; it is not a second dependency detector or a separately maintained
    rank boundary.

    An edge to the package root is reported as such.  It is not noise: the
    root is the file that re-exports everything, so a submodule importing it
    is a submodule importing the whole package, and that is precisely the
    upward edge a layer rule has to refuse.
    """
    prefix = package + "."
    members = {name for name in facts
               if name == package or name.startswith(prefix)}
    graph = import_graph(facts)
    edges = {}
    for name in sorted(members):
        edges[name] = sorted(target for target in graph.get(name, ())
                             if target in members)
    return edges
