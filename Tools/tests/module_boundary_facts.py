"""Derive the module facts the boundary contract and its report both read.

`K00/18` states one rule set over three axes -- module identity, declared
public surface, and dependency direction -- and requires a machine guard.  A
guard and a report that each measured the tree their own way would drift into
two truths about the same bytes, so both read this module and neither parses
Python a second time.

What is measured here is what the codebase actually does, not what a tidier
codebase would do.  Every cross-module consumption in this distribution is
`import module` followed by attribute access -- `from x import y` appears
nowhere -- so an import-statement scan sees the dependency and none of the
symbols.  The edge this module reports is therefore `(consumer, module,
symbol)`, resolved by binding import names (including aliases and imports
written inside a function body) and then walking attribute access on those
names.

Two consumption forms stay deliberately outside: a subprocess invoking
another tool's command line consumes that tool's registered CLI surface,
owned by `cli-contract.yaml`; and the registry-driven producer resolution in
`check_queue.producer_module()` is a declared control inversion, not a static
edge.  Both are named in the contract rather than silently omitted.
"""

import ast
import os


TOOLS_DIRNAME = "Tools"
EXCLUDED_DIRS = frozenset(("tests", "__pycache__", "compiled", "schemas"))

# This module lives beside its only consumers, the distribution's own guard and
# report, because both are declared distribution-only.  Shipping it under
# `Tools/` would hand every adopter a module no adopter runtime consumes -- the
# exact shape the Distribution Boundary refuses -- and would also make the
# thing that decides what is shipped one of the things it decides about.


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


def _import_bindings(tree, known):
    """Map each local name bound by an import to the shipped module it names.

    Aliases and function-body imports are both included: the lazy import that
    hid one dependency cycle in this tree was written inside a function, and a
    guard that only reads module-level statements would have called that tree
    acyclic.
    """
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name.split(".")[0]
                if target in known:
                    bindings[alias.asname or target] = target
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            root = node.module.split(".")[0]
            if root in known:
                for alias in node.names:
                    # `from pkg import submodule` binds the submodule itself
                    # when the package ships one; otherwise it binds a symbol,
                    # which is already a direct consumption of that name.
                    bindings[alias.asname or alias.name] = root
    return bindings


def _imported_modules(tree, known_full):
    """Every shipped module an import statement names, at full dotted name.

    `_import_bindings` answers "which module does this local name come from"
    and deliberately keys by the first segment, because that is the unit the
    contract speaks about.  Inside a package that is not enough: every
    submodule would report an import of its own package and nothing else, and
    the direction between two submodules -- the only thing that can order a
    package internally -- would be unreadable.  This keeps the full name.
    """
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in known_full:
                    found.add(alias.name)
                elif alias.name.split(".")[0] in known_full:
                    found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            for alias in node.names:
                submodule = "%s.%s" % (node.module, alias.name)
                if submodule in known_full:
                    found.add(submodule)
                elif node.module in known_full:
                    found.add(node.module)
    return found


def module_facts(tools_root, relative_path, known, known_full=()):
    """Parse one module into the facts every consumer of this module reads.

    Consumption is cross-module consumption.  A module reading its own names
    is not consumption of anything, and for a package that has to mean the
    whole package: `import_graph`, the manifest and the exception register all
    key by the first name segment, so a submodule reading a sibling would
    otherwise be recorded as the package consuming itself -- hundreds of rows
    describing a boundary that does not exist, each demanding a judgment about
    a coupling nobody chose.  What holds a package together internally is the
    declared direction between its submodules, which `package_layers` reports
    and the guard checks separately.
    """
    path = os.path.join(tools_root, relative_path)
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source, filename=relative_path)
    name = module_name(relative_path)
    own = name.split(".")[0]

    bindings = _import_bindings(tree, known)
    edges = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        value = node.value
        if not isinstance(value, ast.Name):
            continue
        target = bindings.get(value.id)
        if target is None or target == own:
            continue
        edges.add((target, node.attr))
    # A `from module import symbol` is consumption of that symbol even though
    # no attribute node exists for it.
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        target = node.module.split(".")[0]
        if target not in known or target == own:
            continue
        for alias in node.names:
            edges.add((target, alias.name))

    defs, classes = [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

    return {
        "path": relative_path,
        "module": name,
        "lines": source.count("\n") + 1,
        "imports": sorted(set(bindings.values())),
        "imported_modules": sorted(_imported_modules(tree, known_full)),
        "consumes": sorted(edges),
        "top_level_defs": sorted(defs),
        "top_level_classes": sorted(classes),
    }


def collect(repo_root):
    """Parse the whole shipped tree once and index it by module name."""
    tools_root = os.path.join(repo_root, TOOLS_DIRNAME)
    paths = shipped_modules(tools_root)
    known = {module_name(path).split(".")[0] for path in paths}
    known_full = {module_name(path) for path in paths}
    facts = {}
    for path in paths:
        entry = module_facts(tools_root, path, known, known_full)
        facts[entry["module"]] = entry
    return facts


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
    """Adjacency over shipped modules, keyed by the first name segment."""
    graph = {}
    for name, entry in facts.items():
        root = name.split(".")[0]
        edges = graph.setdefault(root, set())
        for target in entry["imports"]:
            if target != root:
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
    """Return intra-package import edges, which the module graph hides.

    `import_graph` keys every module by its first name segment so that the
    contract can speak about modules rather than files.  That is right for
    the tree and wrong for a package: it collapses every submodule to one
    node, so a cycle entirely inside a package is invisible to the very rule
    that exists to forbid cycles.  This returns the edges at full name
    resolution so a caller can check the inside too.

    An edge to the package root is reported as such.  It is not noise: the
    root is the file that re-exports everything, so a submodule importing it
    is a submodule importing the whole package, and that is precisely the
    upward edge a layer rule has to refuse.
    """
    prefix = package + "."
    members = {name for name in facts
               if name == package or name.startswith(prefix)}
    edges = {}
    for name in sorted(members):
        targets = set()
        for imported in facts[name].get("imported_modules", ()):
            if imported in members and imported != name:
                targets.add(imported)
        edges[name] = sorted(targets)
    return edges
