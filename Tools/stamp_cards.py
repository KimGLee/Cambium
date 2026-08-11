#!/usr/bin/env python3
"""Stamp and verify the kernel-owned Runtime Card layer.

The canonical rule owner is kernel/K00 Standards Control/03 Standards
Governance. Cards live under kernel/Cards and are compiled from kernel source
files; they are never profile-selected and never canonical rule owners. The
Read Set Index and Card Index share registry_id `kernel-runtime-routes`; their
route registries, the Read Set files, and the Runtime Cards must agree exactly
on the continuous route set R01-R13. A Read Set and its Card share route_id;
indexes have no route identity of their own. Every Card's `compiled_from` must
equal the active `standards_version` recorded in K00/03; uniform but obsolete
version stamps are stale, not synchronized.

Hash = the first 12 hexadecimal digits of SHA-256 over each source file's
bytes, concatenated in source_files order.

A code span whose first token is `python3` is the copy-and-run command form an
agent types verbatim, so the Card and Read Set layer is also checked against
the tools' own declared interfaces: the named script must exist, and every
required positional and required option that script declares must be supplied.
Each tool's argument contract is read statically from its own source bytes; no
tool is imported or executed, and no argument list is duplicated here. Whether a
flag consumes the token after it comes from that declared contract -- a
`store_true` flag consumes nothing -- so a flag-before-positional spelling such
as `stamp_cards.py --check .` is read exactly as the tool would read it. A span
that only names a tool or a flag in prose is a reference, not a command, and is
not scanned.

Two further checks read their rule out of `Card And Read Set Skeleton` in
kernel/K00 Standards Control/14 Card And Read Set Skeleton and out of
kernel/K00 Standards Control/15 Read Set Loading Boundaries, which own them:
every Card and Read Set must carry the H2 sequence registered for it there, and
every kernel leaf module must be named by some Read Set loading boundary. Both
fail closed when that section is missing or unparseable, and no section name or
leaf path is restated here.

The same loading-boundary owner states that a Card compiles its route's
boundaries and owns none of them, so a route the Card names is one the paired
Read Set's boundaries name too. A route reachable only from the Card is
reported: the reader who follows the Card loads it and the reader who resolves
the Read Set does not, and a leaf named only through that route is reachable
for one of them. Only that direction is checked. A boundary the Card does not
repeat is the compression judgment its owner is entitled to make, and which
side of a reported disagreement moves is not decided here. Routes are read
from the artifacts on disk that carry a route identity, so no route path
spelling is restated here either.

A fourth check measures the size budget. kernel/K00 Standards Control/03
Standards Governance states the target and the soft cap and kernel/K00
Standards Control/16 Leaf Module Size Register carries the approved exceptions;
both numbers and every registered cap are read from those pages, never restated
here. A registered cap that is exceeded is an error, because its owner writes
that the registered cap must not be exceeded without a new governance change. A
page over the soft cap with no registered exception, and a registered measured
value that no longer matches the file, are candidates: the owner calls the 6KB
value a soft cap and asks for a re-measure, and neither sentence is a MUST. A
register row naming a leaf module in any width other than the two the register
defines -- 2 cells for an outside-the-cap declaration, 5 for an exception -- is
an error rather than a skipped row, because a dropped exception row would leave
its page measured against the soft cap alone.

Usage:
  python3 Tools/stamp_cards.py <standards_root> [--cards-dir DIR]
      [--set-version VERSION] [--check]

Exit codes:
  0 = structurally complete and current
  1 = malformed or incomplete Card layer
  2 = structurally valid but stale hash/version in --check mode
"""

import argparse
import ast
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import check_queue


DEFAULT_CARDS_DIR = "kernel/Cards"
DEFAULT_READ_SETS_DIR = "kernel/Read Sets"
CARD_INDEX_NAME = "Card Index.md"
READ_SET_INDEX_NAME = "Read Sets Index.md"
REGISTRY_ID = "kernel-runtime-routes"
ROUTE_ID_RE = re.compile(r"^R([0-9]{2})$")
EXPECTED_ROUTE_IDS = tuple("R%02d" % number for number in range(1, 14))
ACTIVE_STATE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
COMMAND_PREFIX = "python3"
SKELETON_OWNER_PATH = (
    "kernel/K00 Standards Control/14 Card And Read Set Skeleton.md"
)
SKELETON_SECTION = "Card And Read Set Skeleton"
COVERAGE_OWNER_PATH = (
    "kernel/K00 Standards Control/15 Read Set Loading Boundaries.md"
)
SKELETON_KEY_RE = re.compile(r"(?:(R[0-9]{2}) (Card|Read Set))|(?:(Card|Read Set) default)")
KERNEL_LEAF_RE = re.compile(r"K[0-9]{2} [^/]+/[0-9]{2} .+\.md")
# The loading-boundary parser lives in kblib because two tools apply the same
# K00/15 rule to the same bytes: this one asks which kernel leaves no boundary
# names, and check_queue asks which boundary-named modules an adoption plan's
# declared load set omits.  These names stay bound to it so neither tool
# carries a second spelling of what a boundary is.
NON_BOUNDARY_SECTIONS = kblib.READ_SET_NON_BOUNDARY_SECTIONS
WIKI_LINK_RE = kblib.WIKI_LINK_RE
SIZE_BUDGET_OWNER_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
SIZE_BUDGET_SECTION = "Leaf Module Size Budget"
SIZE_REGISTER_OWNER_PATH = (
    "kernel/K00 Standards Control/16 Leaf Module Size Register.md"
)
SIZE_REGISTER_SECTION = "Leaf Module Size Register"
SIZE_BUDGET_RE = re.compile(
    r"target\s*[≤<]=?\s*([0-9]+(?:\.[0-9]+)?)\s*KB.*?soft cap\s*"
    r"([0-9]+(?:\.[0-9]+)?)\s*KB",
    re.IGNORECASE,
)
KB_UNIT_RE = re.compile(r"KB means ([0-9]+) bytes", re.IGNORECASE)
MEASURED_RE = re.compile(r"^([0-9]+)\s*bytes$", re.IGNORECASE)
CAP_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*KB$", re.IGNORECASE)
ACTIVE_COUNT_RE = re.compile(r"^([0-9]+) active\b")
ESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def replace_frontmatter_scalar(text, field, value):
    """Replace one existing top-level scalar without touching the body."""
    end = text.find("\n---", 4)
    if not text.startswith("---\n") or end < 0:
        raise ValueError("missing fenced frontmatter")
    front = text[:end]
    pattern = re.compile(r"(?m)^%s:\s*.*$" % re.escape(field))
    if not pattern.search(front):
        raise ValueError("missing frontmatter field %s" % field)
    scalar = str(value)
    if "\n" in scalar or "\r" in scalar:
        raise ValueError("frontmatter scalar %s must stay on one line" % field)
    if "'" not in scalar:
        rendered_value = "'%s'" % scalar
    elif '"' not in scalar:
        rendered_value = '"%s"' % scalar
    else:
        raise ValueError(
            "frontmatter scalar %s contains both quote styles and cannot be "
            "represented by the restricted YAML subset" % field
        )
    front = pattern.sub(
        lambda _match: "%s: %s" % (field, rendered_value), front, count=1
    )
    return front + text[end:]


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(prefix=".stamp_cards-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def as_repo_path(root, value, label, failures):
    raw = str(value)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        failures.append("%s must be a repository-relative path: %s" % (label, raw))
        return None
    try:
        root = Path(root).resolve()
        resolved = (root / candidate).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        failures.append("%s cannot be resolved: %s (%s)" % (label, raw, exc))
        return None
    try:
        resolved.relative_to(root)
    except ValueError:
        failures.append("%s escapes the repository root: %s" % (label, raw))
        return None
    return resolved


def read_owner_text(root, rel, label, failures):
    """Read one kernel rule owner, failing closed when it cannot be read."""
    path = as_repo_path(root, rel, label, failures)
    if path is None or not path.is_file():
        failures.append("%s is missing: %s" % (label, rel))
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        failures.append("%s is unreadable: %s (%s)" % (label, rel, exc))
        return None


def source_digest(paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def markdown_paths(directory):
    """Return Markdown files and links, case-insensitively, for fail-closed scans."""
    return sorted(
        path
        for path in directory.rglob("*")
        if path.suffix.lower() == ".md" and (path.is_file() or path.is_symlink())
    )


def parse_document(path, root, failures):
    """Return (root-relative path, text, frontmatter mapping), or mapping=None."""
    rel = path.relative_to(root).as_posix()
    if path.is_symlink():
        failures.append("%s must not be a symlink" % rel)
        return rel, None, None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        failures.append("%s is not readable UTF-8: %s" % (rel, exc))
        return rel, None, None
    front = kblib.extract_frontmatter(text)
    if front is None:
        failures.append("%s has no fenced frontmatter" % rel)
        return rel, text, None
    try:
        data = kblib.parse_yaml_subset(front)
    except kblib.YamlSubsetError as exc:
        failures.append("%s has invalid frontmatter: %s" % (rel, exc))
        return rel, text, None
    if not isinstance(data, dict):
        failures.append("%s frontmatter must be a mapping" % rel)
        return rel, text, None
    return rel, text, data


# argparse actions that store a constant and therefore never read the token
# after the flag. Every other action reads at least one value.
VALUELESS_ACTIONS = frozenset((
    "store_true", "store_false", "store_const", "count", "help", "version",
))


def tool_argument_contract(source_text):
    """Read one tool's argparse contract from its own source bytes.

    Returns (required positional dests, required option flags, option flag ->
    whether it reads a value). The third element is what a command span needs
    in order to tell an option's value from a positional: `--json` declared
    `action='store_true'` reads nothing, so the token after it is a positional,
    while `--plan <plan>` consumes one. Guessing from the shape of the next
    token instead reports a legitimate `stamp_cards.py --check .` as missing
    its `root`.

    The scan is a static AST walk: no tool code is imported or executed, so the
    same bytes always yield the same contract. Only `add_argument` calls are
    read; the tool remains the sole owner of its own interface. Every option
    string of a call carries the same answer, so a short alias resolves like its
    long form.
    """
    tree = ast.parse(source_text)
    positionals = []
    required_options = []
    option_reads_value = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "add_argument":
            continue
        names = [
            arg.value for arg in node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        ]
        if not names:
            continue
        keywords = {
            keyword.arg: keyword.value for keyword in node.keywords
            if keyword.arg
        }
        if not names[0].startswith("-"):
            if "default" not in keywords and "nargs" not in keywords:
                positionals.append(names[0])
            continue
        action = keywords.get("action")
        nargs = keywords.get("nargs")
        reads_value = True
        if isinstance(action, ast.Constant) and action.value in VALUELESS_ACTIONS:
            reads_value = False
        elif isinstance(nargs, ast.Constant) and nargs.value == 0:
            reads_value = False
        for name in names:
            if name.startswith("-"):
                option_reads_value[name] = reads_value
        required = keywords.get("required")
        if isinstance(required, ast.Constant) and required.value is True:
            required_options.append(names[0])
    return positionals, required_options, option_reads_value


def command_span_failures(rel, text, root, tool_contracts):
    """Report Card/Read Set command spans that their own tool would reject.

    A code span whose first token is `python3` is the copy-and-run form an
    agent types verbatim, so it must name an existing tool and supply every
    argument that tool declares as required. A span that only names a tool or
    a flag in prose is a reference, not a command, and is not scanned.
    """
    failures = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in CODE_SPAN_RE.finditer(line):
            tokens = match.group(1).split()
            if len(tokens) < 2 or tokens[0] != COMMAND_PREFIX:
                continue
            script = tokens[1]
            location = "%s:%d" % (rel, number)
            tool_path = as_repo_path(root, script, "%s command" % location, failures)
            if tool_path is None:
                continue
            if not tool_path.is_file():
                failures.append(
                    "%s runs a tool that does not exist: %s" % (location, script)
                )
                continue
            if script not in tool_contracts:
                try:
                    source_text = tool_path.read_text(encoding="utf-8")
                    tool_contracts[script] = tool_argument_contract(source_text)
                except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
                    failures.append(
                        "%s names a tool whose argument contract is unreadable: "
                        "%s (%s)" % (location, script, exc)
                    )
                    tool_contracts[script] = None
            contract = tool_contracts[script]
            if contract is None:
                continue
            positionals, required_options, option_reads_value = contract
            arguments = tokens[2:]
            supplied_options = {
                argument.split("=", 1)[0] for argument in arguments
                if argument.startswith("-")
            }
            supplied_positionals = [
                argument for argument in arguments if not argument.startswith("-")
            ]
            # An option that reads a value consumes the token after it, which
            # would otherwise be counted as a positional. Whether it reads one
            # is taken from the tool's own argparse declaration, never from the
            # shape of the following token: a `store_true` flag reads nothing,
            # so the token after it is a positional the command did supply.
            consumed = 0
            for index, argument in enumerate(arguments[:-1]):
                if not argument.startswith("-") or "=" in argument:
                    continue
                # An option this tool does not declare has no contract to read.
                # Whether the span may name it at all is a separate question;
                # for counting positionals, fall back to the token shape rather
                # than asserting either answer.
                reads_value = option_reads_value.get(argument, True)
                following = arguments[index + 1]
                if reads_value and not following.startswith("-"):
                    consumed += 1
            filled = max(0, len(supplied_positionals) - consumed)
            missing_positionals = positionals[filled:]
            missing_options = [
                flag for flag in required_options if flag not in supplied_options
            ]
            if missing_positionals or missing_options:
                failures.append(
                    "%s command is missing required argument(s) of %s: %s"
                    % (
                        location,
                        script,
                        ", ".join(sorted(missing_positionals) + sorted(missing_options)),
                    )
                )
    return failures


def heading_sequence(text):
    """Return one document's ordered H2 names."""
    return tuple(
        line[3:].strip() for line in text.splitlines() if line.startswith("## ")
    )


def parse_skeleton_contract(text):
    """Read the registered Card and Read Set section skeletons from their owner.

    The owner section carries one registry table whose first cell is a single
    code span naming the artifact (`Card default`, `Read Set default`, or
    `Rxx Card` / `Rxx Read Set`) and whose second cell lists that artifact's H2
    sequence as ordered code spans. The sequences live in the kernel leaf; this
    function only reads them, so no section name is restated in tool code.
    """
    contract = {}
    errors = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == SKELETON_SECTION
            continue
        if not inside or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        keys = CODE_SPAN_RE.findall(cells[0])
        if len(keys) != 1 or not SKELETON_KEY_RE.fullmatch(keys[0]):
            continue
        key = keys[0]
        route_id = key.split(" ", 1)[0]
        if ROUTE_ID_RE.fullmatch(route_id) and route_id not in EXPECTED_ROUTE_IDS:
            errors.append(
                "%s registers a section skeleton for %s, which is outside the "
                "closed route set" % (SKELETON_OWNER_PATH, route_id)
            )
            continue
        sequence = tuple(CODE_SPAN_RE.findall(cells[1]))
        if not sequence:
            errors.append(
                "%s registers %s with an empty section sequence"
                % (SKELETON_OWNER_PATH, key)
            )
            continue
        if key in contract:
            errors.append("%s registers %s more than once" % (SKELETON_OWNER_PATH, key))
            continue
        contract[key] = sequence
    for required in ("Card default", "Read Set default"):
        if required not in contract:
            errors.append(
                "%s does not register the `%s` section skeleton"
                % (SKELETON_OWNER_PATH, required)
            )
    return contract, errors


def skeleton_failure(kind, route_id, rel, text, contract):
    """Compare one artifact's H2 sequence with the skeleton registered for it."""
    if not contract:
        return None
    key = "%s %s" % (route_id, kind) if route_id else ""
    expected = contract.get(key) or contract.get("%s default" % kind)
    if expected is None:
        return None
    actual = heading_sequence(text)
    if actual == expected:
        return None
    return (
        "%s does not follow the %s skeleton registered in %s; expected %s, found %s"
        % (
            rel,
            key if key in contract else "%s default" % kind,
            SKELETON_OWNER_PATH,
            list(expected),
            list(actual),
        )
    )


def leaf_coverage_failures(root, read_set_records):
    """Report kernel leaf modules that no Read Set loading boundary names.

    A leaf no boundary names cannot be reached by any routed task. Which
    sections are boundaries and what a boundary names are resolved by
    `kblib.read_set_boundary_targets`, the single parser this rule has.
    """
    root = Path(root).resolve()
    kernel_dir = (root / "kernel").resolve()
    if not kernel_dir.is_dir():
        return ["kernel directory is missing; leaf coverage cannot be resolved"]
    named = set()
    for record in read_set_records:
        named.update(
            kblib.read_set_boundary_targets(record.get("text") or ""))
    failures = []
    for path in markdown_paths(kernel_dir):
        family_rel = path.relative_to(kernel_dir).as_posix()
        if not KERNEL_LEAF_RE.fullmatch(family_rel):
            continue
        rel = path.relative_to(root).as_posix()
        if rel not in named:
            failures.append(
                "%s is named by no Read Set loading boundary; every kernel leaf "
                "module enters one, per %s" % (rel, COVERAGE_OWNER_PATH)
            )
    return failures


def named_routes(text, artifact_routes, sections=None):
    """Return the route IDs one document's Wiki Links name.

    A route is named by linking an artifact that carries a route identity, so
    the mapping comes from the artifacts actually on disk rather than from a
    path spelling restated here; the two indexes carry no route identity and
    therefore name no route. `sections` restricts the scan to the H2 sections
    it contains, and scanning the whole document when it is None.
    """
    found = set()
    section = ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if sections is not None and section not in sections:
            continue
        for inner in WIKI_LINK_RE.findall(line):
            target, _heading = kblib.parse_wiki_link(inner)
            route_id = artifact_routes.get(target + ".md", "")
            if route_id:
                found.add(route_id)
    return found


def card_route_load_failures(read_set_records, runtime_records):
    """Report routes a Card names that its own Read Set's boundaries do not.

    A Card compiles the loading boundaries of its route and owns none of them,
    so a route the Card tells its reader to load is one the paired Read Set
    already names. A route reachable only from the Card is a load instruction
    with no boundary behind it: the reader who follows the Card loads it and
    the reader who resolves the Read Set does not.

    `Purpose` and `Related` are excluded on the Read Set side for the same
    reason they are excluded from leaf coverage, and no Card section is
    excluded, because the Card's own applicability section is where it states
    what loads with the route. Only the Card-adds-a-route direction is
    reported: a boundary the Card does not repeat is a compression judgment
    its owner makes, while a Card-only route is a disagreement about what the
    task read. Which side moves is not decided here.
    """
    artifact_routes = {}
    for record in list(read_set_records) + list(runtime_records):
        if record.get("route_id"):
            artifact_routes[record["rel"]] = record["route_id"]
    boundaries = {}
    for record in read_set_records:
        route_id = record.get("route_id")
        if not route_id:
            continue
        text = record.get("text") or ""
        sections = set(heading_sequence(text)) - set(NON_BOUNDARY_SECTIONS)
        boundaries[route_id] = named_routes(text, artifact_routes, sections)
    failures = []
    for record in runtime_records:
        route_id = record.get("route_id")
        if not route_id or route_id not in boundaries:
            continue
        named = named_routes(record.get("text") or "", artifact_routes)
        for missing in sorted(named - boundaries[route_id] - {route_id}):
            failures.append(
                "%s tells its reader to load %s, which no loading boundary of "
                "%s names; a Card compiles its route's boundaries and owns "
                "none of them, per %s"
                % (record["rel"], missing, record["read_set"] or route_id,
                   COVERAGE_OWNER_PATH)
            )
    return failures


def table_cells(line):
    """Split one Markdown table row, honouring the escaped Wiki-alias pipe."""
    return [cell.strip() for cell in ESCAPED_PIPE_RE.split(line.strip().strip("|"))]


def registered_target(cell):
    """Return the repository path a register cell's Wiki Link names, or ''."""
    match = WIKI_LINK_RE.search(cell)
    if match is None:
        return ""
    target, _heading = kblib.parse_wiki_link(match.group(1))
    return target + ".md" if target else ""


def parse_size_budget(text):
    """Read the leaf module target, soft cap, and KB unit from their owner.

    The three numbers live in the owner's budget section. They are read, never
    restated here, so a governance change to the budget takes effect without a
    tool change and a budget this function cannot read fails closed.
    """
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == SIZE_BUDGET_SECTION
            continue
        if not inside:
            continue
        budget = SIZE_BUDGET_RE.search(line)
        unit = KB_UNIT_RE.search(line)
        if budget is None or unit is None:
            continue
        factor = int(unit.group(1))
        target = int(float(budget.group(1)) * factor)
        soft_cap = int(float(budget.group(2)) * factor)
        if factor <= 0 or target <= 0 or soft_cap < target:
            return None, [
                "%s states an unusable leaf module budget: target %d, soft cap "
                "%d, KB %d" % (SIZE_BUDGET_OWNER_PATH, target, soft_cap, factor)
            ]
        return (target, soft_cap, factor), []
    return None, [
        "%s does not state a leaf module target, soft cap, and KB unit in `%s`"
        % (SIZE_BUDGET_OWNER_PATH, SIZE_BUDGET_SECTION)
    ]


def parse_size_register(text, factor):
    """Read the registered size exceptions and the outside-the-cap list.

    Both live in one section of the register page. A five-column row whose
    first cell links a page is an exception carrying that page's measured value
    and growth cap; a two-column row whose first cell links a page declares it
    outside the cap; the row stating `N active` declares how many exceptions the
    register believes it holds.

    Cell count is the whole discriminator, so a row whose first cell links a
    page and whose width is neither 2 nor 5 is an error, never a skip: the two
    dispositions are exclusive and a page carrying neither would otherwise be
    measured against the soft cap only, turning a "MUST NOT be exceeded" growth
    cap into a candidate. A malformed row cannot be read as an outside-the-cap
    declaration either, because that disposition is a claim the register makes,
    not the residue of a truncated exception row.
    """
    entries = {}
    outside = {}
    declared = None
    errors = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == SIZE_REGISTER_SECTION
            continue
        if not inside or not line.startswith("|"):
            continue
        cells = table_cells(line)
        rel = registered_target(cells[0]) if cells else ""
        if not rel:
            count = ACTIVE_COUNT_RE.search(cells[1]) if len(cells) > 1 else None
            if count is not None:
                declared = int(count.group(1))
            continue
        if len(cells) == 2:
            if rel in outside:
                errors.append(
                    "%s declares %s outside the cap more than once"
                    % (SIZE_REGISTER_OWNER_PATH, rel)
                )
            outside[rel] = cells[1]
            continue
        if len(cells) != 5:
            errors.append(
                "%s registers %s in a row of %d cell(s); a register row naming "
                "a leaf module is either a 2-cell outside-the-cap declaration "
                "or a 5-cell exception (object, measured, necessity, growth "
                "cap, follow-up)"
                % (SIZE_REGISTER_OWNER_PATH, rel, len(cells))
            )
            continue
        measured = MEASURED_RE.match(cells[1])
        cap = CAP_RE.match(cells[3])
        if measured is None or cap is None:
            errors.append(
                "%s registers %s without a readable measured value and growth "
                "cap" % (SIZE_REGISTER_OWNER_PATH, rel)
            )
            continue
        if rel in entries:
            errors.append(
                "%s registers %s more than once" % (SIZE_REGISTER_OWNER_PATH, rel)
            )
            continue
        entries[rel] = {
            "measured": int(measured.group(1)),
            "cap": int(float(cap.group(1)) * factor),
        }
    return entries, outside, declared, errors


def size_budget_findings(root, budget, entries, outside, declared):
    """Measure every kernel leaf module against the budget and the register.

    Returns (errors, candidates). Exceeding a registered growth cap is an
    error: its owner writes that the registered cap MUST NOT be exceeded
    without a new governance change. Standing over the soft cap with no
    declared disposition, and a registered measured value that no longer
    matches the file, are candidates: the owner calls 6KB a soft cap and asks
    for a re-measure, and neither sentence is a MUST.
    """
    _target, soft_cap, _factor = budget
    root = Path(root).resolve()
    kernel_dir = (root / "kernel").resolve()
    if not kernel_dir.is_dir():
        return ["kernel directory is missing; leaf sizes cannot be measured"], []
    errors = []
    candidates = []
    seen = set()
    for path in markdown_paths(kernel_dir):
        family_rel = path.relative_to(kernel_dir).as_posix()
        if not KERNEL_LEAF_RE.fullmatch(family_rel):
            continue
        rel = path.relative_to(root).as_posix()
        seen.add(rel)
        try:
            size = path.stat().st_size
        except OSError as exc:
            errors.append("%s cannot be measured: %s" % (rel, exc))
            continue
        entry = entries.get(rel)
        if rel in outside:
            if entry is not None:
                errors.append(
                    "%s both registers %s as an exception and declares it "
                    "outside the cap; the two dispositions are exclusive, per %s"
                    % (SIZE_REGISTER_OWNER_PATH, rel, SIZE_BUDGET_OWNER_PATH)
                )
            continue
        if entry is None:
            if size > soft_cap:
                candidates.append(
                    "%s is %d bytes, over the %d-byte soft cap, and %s neither "
                    "registers an exception for it nor declares it outside the "
                    "cap" % (rel, size, soft_cap, SIZE_REGISTER_OWNER_PATH)
                )
            continue
        if size > entry["cap"]:
            errors.append(
                "%s is %d bytes, over the %d-byte growth cap registered for it "
                "in %s; that cap MUST NOT be exceeded without a new governance "
                "change, per %s"
                % (
                    rel,
                    size,
                    entry["cap"],
                    SIZE_REGISTER_OWNER_PATH,
                    SIZE_BUDGET_OWNER_PATH,
                )
            )
        if size != entry["measured"]:
            candidates.append(
                "%s measures %d bytes; %s still registers %d and asks for a "
                "re-measure"
                % (rel, size, SIZE_REGISTER_OWNER_PATH, entry["measured"])
            )
    for rel in sorted(set(entries) | set(outside)):
        if rel not in seen:
            errors.append(
                "%s registers %s, which is not a kernel leaf module in this "
                "repository" % (SIZE_REGISTER_OWNER_PATH, rel)
            )
    if declared is None:
        errors.append(
            "%s does not state how many leaf module exceptions are active"
            % SIZE_REGISTER_OWNER_PATH
        )
    elif declared != len(entries):
        candidates.append(
            "%s states %d active leaf module exception(s) and carries %d"
            % (SIZE_REGISTER_OWNER_PATH, declared, len(entries))
        )
    return errors, candidates


def route_id_of(value, label, failures):
    """Validate and return one Rxx route identity, or an empty string."""
    route_id = str(value or "")
    if not route_id:
        failures.append("%s is missing route_id" % label)
        return ""
    if not ROUTE_ID_RE.fullmatch(route_id):
        failures.append("%s has invalid route_id %r (expected Rxx)" % (label, route_id))
        return ""
    return route_id


def main():
    ap = argparse.ArgumentParser(description="Stamp kernel Runtime Cards")
    ap.add_argument("root", help="repository root")
    ap.add_argument(
        "--cards-dir",
        default=DEFAULT_CARDS_DIR,
        help="Card directory relative to <root> (default: kernel/Cards)",
    )
    ap.add_argument(
        "--set-version",
        help="also set every card's compiled_from value",
    )
    ap.add_argument("--check", action="store_true", help="verify only; never write")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print("stamp_cards: FAIL — repository root does not exist: %s" % root)
        return 1

    failures = []
    tool_contracts = {}
    active_path = as_repo_path(
        root, ACTIVE_STATE_PATH, "active Standards state", failures
    )
    active_version = ""
    if active_path is not None:
        if not active_path.is_file():
            failures.append(
                "active Standards state is not a regular file: %s"
                % ACTIVE_STATE_PATH
            )
        else:
            try:
                active_text = active_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                failures.append("active Standards state is unreadable: %s" % exc)
            else:
                active_state, state_errors = kblib.active_standards_state(
                    active_text
                )
                failures.extend(
                    "%s: %s" % (ACTIVE_STATE_PATH, error)
                    for error in state_errors
                )
                active_version = str(
                    active_state.get("standards_version") or ""
                ).strip()
                if not active_version:
                    failures.append(
                        "%s has no usable Standards version"
                        % ACTIVE_STATE_PATH
                    )
    if args.set_version and active_version and args.set_version != active_version:
        failures.append(
            "--set-version %r does not equal active standards_version %r in %s"
            % (args.set_version, active_version, ACTIVE_STATE_PATH)
        )
    if failures:
        for failure in failures:
            print("  [FAIL] %s" % failure)
        print("stamp_cards: FAIL — %d active-state error(s)" % len(failures))
        return 1

    cards_arg = Path(args.cards_dir)
    if cards_arg.is_absolute() or ".." in cards_arg.parts:
        print("stamp_cards: FAIL — --cards-dir must stay inside the repository")
        return 1
    cards_dir = (root / cards_arg).resolve()
    try:
        cards_dir.relative_to(root)
    except ValueError:
        print("stamp_cards: FAIL — Card directory escapes the repository root")
        return 1
    if not cards_dir.is_dir():
        print("stamp_cards: FAIL — required Card directory is missing: %s" % args.cards_dir)
        return 1

    read_sets_dir = (root / DEFAULT_READ_SETS_DIR).resolve()
    try:
        read_sets_dir.relative_to(root)
    except ValueError:
        print("stamp_cards: FAIL — Read Set directory escapes the repository root")
        return 1
    if not read_sets_dir.is_dir():
        print(
            "stamp_cards: FAIL — required Read Set directory is missing: %s"
            % DEFAULT_READ_SETS_DIR
        )
        return 1

    try:
        card_paths = markdown_paths(cards_dir)
        read_set_paths = markdown_paths(read_sets_dir)
    except (OSError, RuntimeError) as exc:
        print("stamp_cards: FAIL — route directories cannot be scanned: %s" % exc)
        return 1

    if not card_paths:
        print("stamp_cards: FAIL — Card directory contains zero Markdown files")
        return 1

    if not read_set_paths:
        print("stamp_cards: FAIL — Read Set directory contains zero Markdown files")
        return 1

    card_index_path = cards_dir / CARD_INDEX_NAME
    if not card_index_path.is_file():
        print(
            "stamp_cards: FAIL — required Card Index is missing: %s"
            % CARD_INDEX_NAME
        )
        return 1

    read_set_index_path = read_sets_dir / READ_SET_INDEX_NAME
    if not read_set_index_path.is_file():
        print(
            "stamp_cards: FAIL — required Read Set Index is missing: %s"
            % READ_SET_INDEX_NAME
        )
        return 1

    # ---- Registered section skeletons, read from their kernel owner ----
    skeleton_contract = {}
    skeleton_path = as_repo_path(
        root, SKELETON_OWNER_PATH, "section skeleton owner", failures
    )
    if skeleton_path is None or not skeleton_path.is_file():
        failures.append(
            "section skeleton owner is missing: %s" % SKELETON_OWNER_PATH
        )
    else:
        try:
            skeleton_text = skeleton_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            failures.append(
                "section skeleton owner is unreadable: %s (%s)"
                % (SKELETON_OWNER_PATH, exc)
            )
        else:
            skeleton_contract, skeleton_errors = parse_skeleton_contract(
                skeleton_text
            )
            failures.extend(skeleton_errors)

    # ---- Read Set Index and on-disk Read Sets ----
    read_set_records = []
    read_set_index_record = None
    seen_read_set_routes = set()

    for path in read_set_paths:
        rel, text, data = parse_document(path, root, failures)
        if text is not None:
            failures.extend(
                command_span_failures(rel, text, root, tool_contracts)
            )
        if data is None:
            continue

        is_index = path == read_set_index_path
        expected_type = "route-index" if is_index else "read-set"
        if data.get("type") != expected_type:
            failures.append("%s must declare type: %s" % (rel, expected_type))
        for legacy_key in ("card_id", "card_registry"):
            if legacy_key in data:
                failures.append(
                    "%s carries legacy %s; route_id/route_registry are the only route identities"
                    % (rel, legacy_key)
                )

        if is_index:
            if "route_id" in data:
                failures.append("%s must not declare route_id; an index is not a route" % rel)
            if data.get("registry_id") != REGISTRY_ID:
                failures.append(
                    "%s must declare registry_id: %s" % (rel, REGISTRY_ID)
                )
            read_set_index_record = {
                "path": path,
                "rel": rel,
                "text": text,
                "data": data,
            }
            continue

        route_id = route_id_of(data.get("route_id"), rel, failures)
        if route_id:
            if route_id in seen_read_set_routes:
                failures.append("more than one Read Set declares route_id %s" % route_id)
            else:
                seen_read_set_routes.add(route_id)
            if not path.name.startswith(route_id + " "):
                failures.append(
                    "%s filename must start with its route_id %s" % (rel, route_id)
                )
        skeleton_error = skeleton_failure(
            "Read Set", route_id, rel, text, skeleton_contract
        )
        if skeleton_error:
            failures.append(skeleton_error)
        read_set_records.append(
            {
                "path": path,
                "rel": rel,
                "text": text,
                "data": data,
                "route_id": route_id,
            }
        )

    if read_set_index_record is None:
        failures.append("Read Set Index could not be parsed")
        read_registry = []
    else:
        read_registry = read_set_index_record["data"].get("route_registry")
        if not isinstance(read_registry, list) or not read_registry:
            failures.append("Read Set Index must declare a non-empty route_registry")
            read_registry = []

    read_registry_pairs = set()
    read_registry_routes = set()
    read_registry_paths = set()
    read_sets_real = read_sets_dir.resolve()
    for entry in read_registry:
        if not isinstance(entry, dict):
            failures.append("Read Set Index route_registry entries must be mappings")
            continue
        for legacy_key in ("card_id", "card_registry"):
            if legacy_key in entry:
                failures.append(
                    "Read Set Index route_registry entries must not carry legacy %s"
                    % legacy_key
                )
        route_id = route_id_of(entry.get("route_id"), "Read Set Index entry", failures)
        read_set_rel = str(entry.get("path") or "")
        if not read_set_rel:
            failures.append("Read Set Index has an incomplete route_registry entry")
            continue
        if route_id in read_registry_routes:
            failures.append("Read Set Index repeats route_id %s" % route_id)
        if read_set_rel in read_registry_paths:
            failures.append("Read Set Index repeats path %s" % read_set_rel)
        if route_id:
            read_registry_routes.add(route_id)
            read_registry_pairs.add((route_id, read_set_rel))
        read_registry_paths.add(read_set_rel)

        read_set_path = as_repo_path(
            root, read_set_rel, "Read Set Index path", failures
        )
        if read_set_path is not None:
            try:
                read_set_path.relative_to(read_sets_real)
            except ValueError:
                failures.append(
                    "Read Set Index path must be under kernel/Read Sets: %s"
                    % read_set_rel
                )

    actual_read_pairs = {
        (record["route_id"], record["rel"])
        for record in read_set_records
        if record["route_id"]
    }
    if read_registry_pairs != actual_read_pairs:
        failures.append(
            "Read Set Index/disk mismatch; missing=%s extra=%s"
            % (
                sorted(actual_read_pairs - read_registry_pairs),
                sorted(read_registry_pairs - actual_read_pairs),
            )
        )

    records = []
    seen_card_routes = set()
    seen_card_read_sets = set()
    cards_real = cards_dir.resolve()
    kernel_real = (root / "kernel").resolve()

    for path in card_paths:
        rel, text, data = parse_document(path, root, failures)
        if text is not None:
            failures.extend(
                command_span_failures(rel, text, root, tool_contracts)
            )
        if data is None:
            continue

        is_index = path == card_index_path
        expected_type = "card-index" if is_index else "runtime-card"
        if data.get("type") != expected_type:
            failures.append("%s must declare type: %s" % (rel, expected_type))

        for legacy_key in ("card_id", "card_registry"):
            if legacy_key in data:
                failures.append(
                    "%s carries legacy %s; route_id/route_registry are the only route identities"
                    % (rel, legacy_key)
                )
        if is_index:
            if "route_id" in data:
                failures.append("%s must not declare route_id; an index is not a route" % rel)
            if data.get("registry_id") != REGISTRY_ID:
                failures.append(
                    "%s must declare registry_id: %s" % (rel, REGISTRY_ID)
                )
            route_id = ""
        else:
            route_id = route_id_of(data.get("route_id"), rel, failures)
            if route_id:
                if route_id in seen_card_routes:
                    failures.append("more than one Runtime Card declares route_id %s" % route_id)
                else:
                    seen_card_routes.add(route_id)
                if not path.name.startswith(route_id + " "):
                    failures.append(
                        "%s filename must start with its route_id %s" % (rel, route_id)
                    )
            skeleton_error = skeleton_failure(
                "Card", route_id, rel, text, skeleton_contract
            )
            if skeleton_error:
                failures.append(skeleton_error)

        compiled_from = str(data.get("compiled_from") or "")
        if not compiled_from:
            failures.append("%s is missing compiled_from" % rel)

        current_hash = str(data.get("source_hash") or "")
        if not current_hash:
            failures.append("%s is missing source_hash" % rel)

        source_values = data.get("source_files")
        if not isinstance(source_values, list) or not source_values:
            failures.append("%s must declare a non-empty source_files list" % rel)
            source_values = []

        source_rels = []
        source_paths = []
        for value in source_values:
            source_rel = str(value)
            if source_rel in source_rels:
                failures.append("%s repeats source file %s" % (rel, source_rel))
                continue
            source_rels.append(source_rel)
            source = as_repo_path(root, source_rel, "%s source_files" % rel, failures)
            if source is None:
                continue
            if not source.is_file():
                failures.append("%s source is not a regular file: %s" % (rel, source_rel))
                continue
            try:
                source.relative_to(kernel_real)
            except ValueError:
                failures.append("%s source must be under kernel/: %s" % (rel, source_rel))
                continue
            try:
                source.relative_to(cards_real)
                failures.append("%s cannot use another compiled Card as a source: %s" % (rel, source_rel))
                continue
            except ValueError:
                pass
            source_paths.append(source)

        read_set = str(data.get("read_set") or "")
        if expected_type == "runtime-card":
            if not read_set:
                failures.append("%s is missing read_set" % rel)
            elif read_set not in source_rels:
                failures.append("%s source_files must include its read_set %s" % (rel, read_set))
            elif read_set in seen_card_read_sets:
                failures.append("more than one Runtime Card maps read_set %s" % read_set)
            else:
                seen_card_read_sets.add(read_set)

        records.append(
            {
                "path": path,
                "rel": rel,
                "text": text,
                "data": data,
                "type": expected_type,
                "route_id": route_id,
                "compiled_from": compiled_from,
                "source_paths": source_paths,
                "source_rels": source_rels,
                "source_hash": current_hash,
                "read_set": read_set,
            }
        )

    index_record = next(
        (record for record in records if record["path"] == card_index_path), None
    )
    runtime_records = [record for record in records if record["type"] == "runtime-card"]
    if index_record is None:
        failures.append("Card Index could not be parsed")
    if not runtime_records:
        failures.append("Card layer contains zero runtime cards")

    registered = set()
    registered_routes = set()
    registered_paths = set()
    registered_read_sets = set()
    if index_record is not None:
        registry = index_record["data"].get("route_registry")
        if not isinstance(registry, list) or not registry:
            failures.append("Card Index must declare a non-empty route_registry")
        else:
            for entry in registry:
                if not isinstance(entry, dict):
                    failures.append("Card Index route_registry entries must be mappings")
                    continue
                for legacy_key in ("card_id", "card_registry"):
                    if legacy_key in entry:
                        failures.append(
                            "Card Index route_registry entries must not carry legacy %s"
                            % legacy_key
                        )
                route_id = route_id_of(
                    entry.get("route_id"), "Card Index entry", failures
                )
                triple = (
                    route_id,
                    str(entry.get("path") or ""),
                    str(entry.get("read_set") or ""),
                )
                if not all(triple):
                    failures.append("Card Index has an incomplete route_registry entry")
                    continue
                if route_id in registered_routes:
                    failures.append("Card Index repeats route_id %s" % route_id)
                if triple[1] in registered_paths:
                    failures.append("Card Index repeats path %s" % triple[1])
                if triple[2] in registered_read_sets:
                    failures.append("Card Index repeats read_set %s" % triple[2])
                registered_routes.add(route_id)
                registered_paths.add(triple[1])
                registered_read_sets.add(triple[2])
                registered.add(triple)
            actual = {
                (record["route_id"], record["rel"], record["read_set"])
                for record in runtime_records
                if record["route_id"]
            }
            if registered != actual:
                missing = sorted(actual - registered)
                extra = sorted(registered - actual)
                failures.append(
                    "Card Index membership mismatch; missing=%s extra=%s" % (missing, extra)
                )

    expected_routes = set(EXPECTED_ROUTE_IDS)
    route_sets = {
        "Read Set Index": read_registry_routes,
        "Read Set files": {
            record["route_id"] for record in read_set_records if record["route_id"]
        },
        "Card Index": (
            registered_routes if index_record is not None and isinstance(
                index_record["data"].get("route_registry"), list
            ) else set()
        ),
        "Runtime Card files": {
            record["route_id"] for record in runtime_records if record["route_id"]
        },
    }
    for label, route_ids in route_sets.items():
        if route_ids != expected_routes:
            failures.append(
                "%s routes must be continuous R01-R13; missing=%s extra=%s"
                % (
                    label,
                    sorted(expected_routes - route_ids),
                    sorted(route_ids - expected_routes),
                )
            )

    failures.extend(leaf_coverage_failures(root, read_set_records))
    failures.extend(card_route_load_failures(read_set_records, runtime_records))

    # ---- Leaf module size budget, read from its owner and its register ----
    budget_candidates = []
    budget_text = read_owner_text(
        root, SIZE_BUDGET_OWNER_PATH, "leaf module size budget owner", failures
    )
    register_text = read_owner_text(
        root, SIZE_REGISTER_OWNER_PATH, "leaf module size register", failures
    )
    if budget_text is not None and register_text is not None:
        budget, budget_errors = parse_size_budget(budget_text)
        failures.extend(budget_errors)
        if budget is not None:
            entries, outside, declared, register_errors = parse_size_register(
                register_text, budget[2]
            )
            failures.extend(register_errors)
            size_errors, budget_candidates = size_budget_findings(
                root, budget, entries, outside, declared
            )
            failures.extend(size_errors)

    # ---- Stable Gate ID Registry against the producers it names ----
    # The registry rows are kernel text; the Tool/Tool-version/Check/Gate ID
    # they select is a constant in an installed producer.  Nothing on the
    # runtime path notices the two drifting apart: `check_queue` consumes the
    # registry only at a Standards revalidation boundary and at
    # `open -> merge-ready`, so a bumped TOOL_VERSION shows up as a receipt
    # that "does not match registered Gate ID" after the batch is already
    # built.  This run is the input K00/12 itself names for
    # `runtime-card-synchronization`, and Governance close -- when a producer
    # version or a registry row changes -- is exactly when the two sides move.
    # The check reports that the two disagree; which side to change is the
    # governance decision, not this tool's.
    _registry, registry_errors = check_queue.standards_gate_registry(root)
    failures.extend(registry_errors)

    canonical_read_sets = dict(read_registry_pairs)
    for record in runtime_records:
        route_id = record["route_id"]
        if route_id and canonical_read_sets.get(route_id) != record["read_set"]:
            failures.append(
                "%s route %s must bind Read Set %s, not %s"
                % (
                    record["rel"],
                    route_id,
                    canonical_read_sets.get(route_id, "<unregistered>"),
                    record["read_set"] or "<missing>",
                )
            )

    versions = {record["compiled_from"] for record in records if record["compiled_from"]}
    if len(versions) > 1:
        failures.append("compiled_from is not uniform across the Card layer: %s" % sorted(versions))

    if failures:
        for failure in failures:
            print("  [FAIL] %s" % failure)
        print("stamp_cards: FAIL — %d structural error(s)" % len(failures))
        return 1

    version_mismatches = [
        record["rel"] for record in records
        if record["compiled_from"] != active_version
    ]
    if version_mismatches and not args.check and not args.set_version:
        print(
            "stamp_cards: FAIL — %d Card version stamp(s) do not equal the "
            "active standards_version %r" %
            (len(version_mismatches), active_version)
        )
        print(
            "  Re-run with --set-version %s to synchronize compiled_from."
            % active_version
        )
        return 1

    stale = list(budget_candidates)
    for candidate in budget_candidates:
        print("  [CAND] %s" % candidate)

    rendered = []
    for record in records:
        try:
            expected_hash = source_digest(record["source_paths"])
        except OSError as exc:
            print(
                "stamp_cards: FAIL — source changed or became unreadable while hashing %s: %s"
                % (record["rel"], exc)
            )
            return 1
        hash_stale = record["source_hash"] != expected_hash
        version_stale = record["compiled_from"] != active_version
        if args.check:
            if hash_stale or version_stale:
                stale.append(record["rel"])
                details = []
                if hash_stale:
                    details.append("hash %s -> %s" % (record["source_hash"], expected_hash))
                if version_stale:
                    details.append(
                        "compiled_from %s -> %s"
                        % (record["compiled_from"], active_version)
                    )
                print("  [CAND] %s: %s" % (record["rel"], "; ".join(details)))
            continue

        try:
            text = replace_frontmatter_scalar(
                record["text"], "source_hash", expected_hash
            )
            if args.set_version:
                text = replace_frontmatter_scalar(
                    text, "compiled_from", args.set_version
                )
            parsed_front = kblib.parse_yaml_subset(
                kblib.extract_frontmatter(text) or ""
            )
        except (ValueError, kblib.YamlSubsetError) as exc:
            print(
                "stamp_cards: FAIL — rendered frontmatter is invalid for %s: %s"
                % (record["rel"], exc)
            )
            return 1
        if (parsed_front.get("source_hash") != expected_hash or
                parsed_front.get("compiled_from") != active_version):
            print(
                "stamp_cards: FAIL — rendered frontmatter does not round-trip "
                "for %s (source_hash=%r compiled_from=%r)" %
                (record["rel"], parsed_front.get("source_hash"),
                 parsed_front.get("compiled_from"))
            )
            return 1
        rendered.append((record["path"], record["rel"], text, expected_hash))

    if args.check:
        print(
            "stamp_cards --check: routes=%d read_sets=%d runtime_cards=%d "
            "indexes=2 stale=%d"
            % (
                len(expected_routes),
                len(read_set_records),
                len(runtime_records),
                len(stale),
            )
        )
        return 2 if stale else 0

    changes = []
    for path, rel, text, expected_hash in rendered:
        current = path.read_text(encoding="utf-8")
        if current == text:
            continue
        changes.append((path, rel, text, expected_hash, current))

    written = []
    try:
        for path, rel, text, expected_hash, original in changes:
            atomic_write(path, text)
            written.append((path, rel, original))
    except (OSError, ValueError) as exc:
        rollback_errors = []
        for path, rel, original in reversed(written):
            try:
                atomic_write(path, original)
            except (OSError, ValueError) as rollback_exc:
                rollback_errors.append("%s: %s" % (rel, rollback_exc))
        print("stamp_cards: FAIL — write transaction aborted: %s" % exc)
        if rollback_errors:
            print("  [FAIL] rollback was incomplete: %s" %
                  "; ".join(rollback_errors))
        else:
            print("  No Card changes remain; earlier writes were rolled back.")
        return 1

    for _path, rel, _text, expected_hash, _original in changes:
        print("  [STAMP] %s -> %s" % (rel, expected_hash))
    print(
        "stamp_cards: routes=%d read_sets=%d runtime_cards=%d indexes=2 "
        "stale=0 updated=%d"
        % (
            len(expected_routes),
            len(read_set_records),
            len(runtime_records),
            len(changes),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
