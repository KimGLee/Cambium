#!/usr/bin/env python3
"""Validate curated Cards and their top-level Read Set bindings.

Cards are reviewed action projections, not compiled rule artifacts.  This tool
checks their closed frontmatter shape, independent size budget, source
provenance, reviewed-source currentness, one-to-one Read Set binding, and the
two generated navigation indexes.  It does not judge semantic quality, parse
Markdown prose into loading obligations, validate Kernel leaf budgets, or own
route selection.

``source_hash`` observes the current bytes of ``source_files``.
``reviewed_source_hash`` records which exact source bytes the curator reviewed.
``reviewed_card_hash`` records the Card body that was reviewed against them.
Currentness proves only that those review inputs have not changed; it does not
prove that the summary is correct or that an Agent read or followed it.
"""

import hashlib
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_contract
import kblib
import read_set_contract
import standards_state


CARD_BUDGET_PATH = "Card/card-budget.yaml"
ACTIVE_STATE_PATH = standards_state.STATE_PATH
PROHIBITED_BODY_RE = re.compile(
    r"(?:python3\s+Tools/|`?Tools/[A-Za-z0-9_./-]+\.py|"
    r"compiled\s+(?:kernel\s+)?guidance)", re.IGNORECASE)


CardContractError = card_contract.CardContractError
load_card_schema = card_contract.load_schema


def _string_list(value, label, *, nonempty=False):
    if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value):
        raise CardContractError("%s must be an explicit string list" % label)
    if len(value) != len(set(value)):
        raise CardContractError("%s must not repeat values" % label)
    if nonempty and not value:
        raise CardContractError("%s must not be empty" % label)
    return list(value)


def _safe_relative(value, label, *, suffix=None):
    if not isinstance(value, str) or not value or value != value.strip():
        raise CardContractError("%s must be a non-empty canonical path" % label)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise CardContractError("%s must stay repository-relative" % label)
    if suffix is not None and not value.endswith(suffix):
        raise CardContractError("%s must end with %s" % (label, suffix))
    return value


def _frontmatter(text, label):
    raw = kblib.extract_frontmatter(text or "")
    if raw is None:
        raise CardContractError("%s has no YAML frontmatter" % label)
    try:
        value = kblib.parse_yaml_subset(raw)
    except (ValueError, kblib.YamlSubsetError) as exc:
        raise CardContractError("%s frontmatter is invalid: %s" % (label, exc))
    if not isinstance(value, dict):
        raise CardContractError("%s frontmatter must be a mapping" % label)
    return value


def _body(text):
    end = text.find("\n---", 4)
    if not text.startswith("---\n") or end < 0:
        raise CardContractError("Card has no fenced frontmatter")
    return text[end + 4:].lstrip("\n")


def _heading_sequence(text):
    result = []
    for _line_number, line in kblib.markdown_authority_lines(text):
        heading = kblib.markdown_atx_heading(line)
        if heading is not None and heading[0] == 2:
            result.append(heading[1])
    return tuple(result)


def _load_budget(root):
    try:
        path = kblib.repository_path(
            root, CARD_BUDGET_PATH, must_exist=True, reject_symlink=True)
        value = kblib.parse_yaml_subset(kblib.read_text(path))
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        raise CardContractError("%s is unsafe or invalid: %s" %
                                (CARD_BUDGET_PATH, exc))
    expected = {"schema_version", "max_body_bytes", "max_action_items"}
    if not isinstance(value, dict) or set(value) != expected:
        raise CardContractError("%s has an invalid closed shape" % CARD_BUDGET_PATH)
    if value.get("schema_version") != 1:
        raise CardContractError("unsupported Card budget schema_version")
    for field in ("max_body_bytes", "max_action_items"):
        number = value.get(field)
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise CardContractError("%s.%s must be a positive integer" %
                                    (CARD_BUDGET_PATH, field))
    return value


def source_digest(root, relative_paths):
    """Bind ordered source identities and bytes without boundary ambiguity."""
    digest = hashlib.sha256()
    for relative in relative_paths:
        try:
            path = kblib.repository_path(
                root, relative, must_exist=True, reject_symlink=True)
            identity = relative.encode("utf-8")
            payload = kblib.read_bytes(path)
            digest.update(("%d:" % len(identity)).encode("ascii"))
            digest.update(identity)
            digest.update(("%d:" % len(payload)).encode("ascii"))
            digest.update(payload)
        except (OSError, ValueError) as exc:
            raise CardContractError("source %s is unsafe or unreadable: %s" %
                                    (relative, exc))
    return digest.hexdigest()[:12]


def card_body_digest(text):
    """Return the stable identity of the curated Card projection body."""
    return hashlib.sha256(_body(text).encode("utf-8")).hexdigest()[:12]


def replace_frontmatter_scalar(text, field, value):
    """Replace one existing top-level scalar while preserving all other bytes."""
    end = text.find("\n---", 4)
    if not text.startswith("---\n") or end < 0:
        raise CardContractError("missing fenced frontmatter")
    front = text[:end]
    pattern = re.compile(r"(?m)^%s:\s*.*$" % re.escape(field))
    if not pattern.search(front):
        raise CardContractError("missing frontmatter field %s" % field)
    scalar = str(value)
    if "\n" in scalar or "\r" in scalar or "'" in scalar:
        raise CardContractError("frontmatter scalar %s is not safely quotable" % field)
    front = pattern.sub("%s: '%s'" % (field, scalar), front, count=1)
    return front + text[end:]


def discover_cards(root, cards_dir=None):
    """Return route -> validated Card record, excluding the generated Index."""
    root = Path(root).resolve()
    schema = load_card_schema(root)
    canonical_directory = schema["directory"]
    cards_dir = canonical_directory if cards_dir is None else cards_dir
    if cards_dir != canonical_directory:
        raise CardContractError(
            "Card directory must be exactly %s" % canonical_directory)
    directory = root / canonical_directory
    if not directory.is_dir() or directory.is_symlink():
        raise CardContractError("canonical Card directory is missing or unsafe")
    budget = _load_budget(root)
    read_set_schema = read_set_contract.load_schema(root)
    read_sets = read_set_contract.discover(root, schema=read_set_schema)
    records = {}
    for path in sorted(directory.glob("*.md")):
        if path.name == schema["index_name"]:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            text = kblib.read_text(path)
        except (OSError, UnicodeError) as exc:
            raise CardContractError("%s is unreadable: %s" % (relative, exc))
        data = _frontmatter(text, relative)
        card_fields = set(schema["document_fields"])
        if set(data) != card_fields:
            raise CardContractError(
                "%s fields differ from the curated Card shape; missing=%s extra=%s"
                % (relative, sorted(card_fields - set(data)),
                   sorted(set(data) - card_fields)))
        if (data.get("type") != schema["document_type"] or
                data.get("generation_mode") != schema["generation_mode"]):
            raise CardContractError("%s must be a curated Card" % relative)
        route_id = data.get("route_id")
        if (not isinstance(route_id, str) or
                not schema["route_id_re"].fullmatch(route_id)):
            raise CardContractError("%s has invalid route_id %r" %
                                    (relative, route_id))
        if route_id not in read_sets:
            raise CardContractError("%s route_id %r has no Read Set declaration" %
                                    (relative, route_id))
        if route_id in records:
            raise CardContractError("more than one Card declares %s" % route_id)
        if not path.name.startswith(route_id + " "):
            raise CardContractError("%s filename must start with %s" %
                                    (relative, route_id))
        if data.get("read_set_id") != route_id:
            raise CardContractError("%s read_set_id must equal route_id" % relative)
        expected_read_set = read_sets[route_id]["path"]
        if data.get("read_set") != expected_read_set:
            raise CardContractError("%s must bind %s" % (relative, expected_read_set))
        version = data.get("standards_version")
        if not isinstance(version, str) or not version:
            raise CardContractError("%s standards_version is missing" % relative)
        sources = _string_list(data.get("source_files"),
                               "%s source_files" % relative, nonempty=True)
        for source in sources:
            _safe_relative(source, "%s source" % relative)
        if expected_read_set not in sources:
            raise CardContractError("%s source_files must include its Read Set" % relative)
        observed = data.get("source_hash")
        reviewed = data.get("reviewed_source_hash")
        reviewed_card = data.get("reviewed_card_hash")
        hash_re = schema["hash_re"]
        if not isinstance(observed, str) or not hash_re.fullmatch(observed):
            raise CardContractError("%s source_hash must be 12 lowercase hex" % relative)
        if not isinstance(reviewed, str) or not hash_re.fullmatch(reviewed):
            raise CardContractError(
                "%s reviewed_source_hash must be 12 lowercase hex" % relative)
        if not isinstance(reviewed_card, str) or not hash_re.fullmatch(
                reviewed_card):
            raise CardContractError(
                "%s reviewed_card_hash must be 12 lowercase hex" % relative)
        body = _body(text)
        body_hash = card_body_digest(text)
        body_bytes = len(body.encode("utf-8"))
        action_items = sum(1 for line in body.splitlines()
                           if line.startswith("- "))
        if body_bytes > budget["max_body_bytes"]:
            raise CardContractError("%s body has %d bytes; budget is %d" %
                                    (relative, body_bytes,
                                     budget["max_body_bytes"]))
        if action_items > budget["max_action_items"]:
            raise CardContractError("%s has %d action items; budget is %d" %
                                    (relative, action_items,
                                     budget["max_action_items"]))
        if list(_heading_sequence(text)) != schema["body_sections"]:
            raise CardContractError("%s sections must be exactly %s" %
                                    (relative, schema["body_sections"]))
        match = PROHIBITED_BODY_RE.search(body)
        if match:
            raise CardContractError("%s contains implementation/compiled prose: %s" %
                                    (relative, match.group(0)))
        records[route_id] = {
            "route_id": route_id,
            "path": relative,
            "text": text,
            "data": data,
            "source_files": sources,
            "source_hash": observed,
            "reviewed_source_hash": reviewed,
            "reviewed_card_hash": reviewed_card,
            "body_hash": body_hash,
            "standards_version": version,
            "read_set": expected_read_set,
            "body_bytes": body_bytes,
            "action_items": action_items,
        }
    if not records:
        raise CardContractError("canonical Card directory has no Cards")
    if set(records) != set(read_sets):
        raise CardContractError(
            "Card/Read Set route mismatch; cards_only=%s read_sets_only=%s" %
            (sorted(set(records) - set(read_sets)),
             sorted(set(read_sets) - set(records))))
    return records, read_sets


def _display_name(path, suffix):
    name = Path(path).name
    name = re.sub(r"^R[0-9]{2} ", "", name)
    if name.endswith(suffix):
        name = name[:-len(suffix)]
    return name


def render_card_index(cards, read_sets):
    lines = [
        "---",
        "type: card-index",
        "generation_mode: generated",
        "source: Card/card.schema.yaml, Card frontmatter, and Read Set declarations",
        "---",
        "# Card Index",
        "",
        "This is a generated navigation view. It does not select a route, define a load",
        "boundary, or authorize activation. Route selection remains with its canonical",
        "owner; each Card and Read Set frontmatter supplies the machine identity below.",
        "",
        "| Route ID | Card | Read Set |",
        "|---|---|---|",
    ]
    for route_id in sorted(cards):
        card = cards[route_id]["path"][:-3]
        read_set = read_sets[route_id]["path"][:-3]
        card_name = _display_name(cards[route_id]["path"], " Card.md")
        lines.append(
            "| `%s` | [[%s\\|%s]] | [[%s\\|Read Set]] |" %
            (route_id, card, card_name, read_set))
    return "\n".join(lines) + "\n"


def render_read_set_index(read_sets):
    lines = [
        "---",
        "type: route-index",
        "generation_mode: generated",
        "source: Read Set declarations",
        "---",
        "# Read Set Index",
        "",
        "This is a generated navigation view. It is not a route registry and is never",
        "an input to route selection, load resolution, activation, or proof. The",
        "frontmatter of each linked Read Set is the sole machine loading declaration.",
        "",
        "| Route ID | Read Set |",
        "|---|---|",
    ]
    for route_id in sorted(read_sets):
        path = read_sets[route_id]["path"][:-3]
        name = _display_name(read_sets[route_id]["path"], " Read Set.md")
        lines.append("| `%s` | [[%s\\|%s]] |" % (route_id, path, name))
    return "\n".join(lines) + "\n"


def _active_version(root, set_version=None):
    state_path = Path(root).resolve() / ACTIVE_STATE_PATH
    if not state_path.exists():
        return set_version or "{{ standards_version }}"
    state, _view, errors = standards_state.snapshot(root)
    if errors or state is None:
        raise CardContractError("active Standards state is invalid: %s" %
                                "; ".join(errors))
    return str(state["standards_version"]).strip()


def _write_changes(changes):
    originals = []
    try:
        for path, text in changes:
            originals.append((path, kblib.read_text(path) if path.exists() else None))
            kblib.atomic_write_text(path, text)
    except (OSError, ValueError):
        for path, original in reversed(originals):
            if original is not None:
                kblib.atomic_write_text(path, original)
        raise


def main(argv=None):
    parser = kblib.ArgumentParser(description="Validate curated Cambium Cards")
    parser.add_argument("root", help="repository root")
    parser.add_argument(
        "--cards-dir", default=None,
        help="Card directory relative to <root> (default: schema path_prefix)")
    parser.add_argument(
        "--set-version", help="set every Card standards_version value")
    parser.add_argument(
        "--acknowledge-curated-review", dest="acknowledge_review",
        action="store_true",
        help="after human review, bind the current sources and Card bodies")
    parser.add_argument("--check", action="store_true",
                        help="verify only; never write")
    args = parser.parse_args(argv)
    if args.check and args.acknowledge_review:
        print("stamp_cards: FAIL — --check and review acknowledgement are mutually exclusive")
        return 1
    root = Path(args.root).resolve()
    if not root.is_dir():
        print("stamp_cards: FAIL — repository root does not exist: %s" % root)
        return 1
    try:
        active_version = _active_version(root, args.set_version)
        if args.check and args.set_version and args.set_version != active_version:
            print("stamp_cards: FAIL — --check cannot judge candidate version %s while active version is %s" %
                  (args.set_version, active_version))
            return 1
        cards, read_sets = discover_cards(root, args.cards_dir)
    except (CardContractError,
            read_set_contract.ReadSetContractError) as exc:
        print("stamp_cards: FAIL — %s" % exc)
        return 1

    stale = []
    rendered = []
    for route_id in sorted(cards):
        record = cards[route_id]
        try:
            expected_hash = source_digest(root, record["source_files"])
        except CardContractError as exc:
            print("stamp_cards: FAIL — %s" % exc)
            return 1
        reasons = []
        if record["source_hash"] != expected_hash:
            reasons.append("source_hash %s -> %s" %
                           (record["source_hash"], expected_hash))
        if record["reviewed_source_hash"] != expected_hash:
            reasons.append("reviewed_source_hash %s -> %s" %
                           (record["reviewed_source_hash"], expected_hash))
        if record["reviewed_card_hash"] != record["body_hash"]:
            reasons.append("reviewed_card_hash %s -> %s" %
                           (record["reviewed_card_hash"],
                            record["body_hash"]))
        if record["standards_version"] != active_version:
            reasons.append("standards_version %s -> %s" %
                           (record["standards_version"], active_version))
        if args.check:
            if reasons:
                stale.append(record["path"])
                print("  [CAND] %s: %s" % (record["path"], "; ".join(reasons)))
            continue
        text = replace_frontmatter_scalar(
            record["text"], "source_hash", expected_hash)
        if args.acknowledge_review:
            text = replace_frontmatter_scalar(
                text, "reviewed_source_hash", expected_hash)
            text = replace_frontmatter_scalar(
                text, "reviewed_card_hash", record["body_hash"])
        if args.set_version:
            text = replace_frontmatter_scalar(
                text, "standards_version", args.set_version)
        if ((record["reviewed_source_hash"] != expected_hash or
             record["reviewed_card_hash"] != record["body_hash"]) and
                not args.acknowledge_review):
            stale.append(record["path"])
        rendered.append((root / record["path"], text))

    card_index = render_card_index(cards, read_sets)
    read_index = render_read_set_index(read_sets)
    try:
        card_schema = load_card_schema(root)
        read_set_schema = read_set_contract.load_schema(root)
    except (CardContractError,
            read_set_contract.ReadSetContractError) as exc:
        print("stamp_cards: FAIL — %s" % exc)
        return 1
    index_pairs = (
        (root / card_schema["index_path"], card_index),
        (root / read_set_schema["index_path"], read_index),
    )
    for path, expected in index_pairs:
        try:
            current = kblib.read_text(path)
        except (OSError, UnicodeError) as exc:
            print("stamp_cards: FAIL — generated index %s is unreadable: %s" %
                  (path.relative_to(root), exc))
            return 1
        if current != expected:
            if args.check:
                stale.append(path.relative_to(root).as_posix())
                print("  [CAND] %s: generated navigation is stale" %
                      path.relative_to(root))
            else:
                rendered.append((path, expected))

    if args.check:
        print("stamp_cards --check: read_sets=%d curated_cards=%d indexes=2 stale=%d" %
              (len(read_sets), len(cards), len(stale)))
        return 2 if stale else 0

    changes = []
    for path, text in rendered:
        try:
            current = kblib.read_text(path)
        except (OSError, UnicodeError) as exc:
            print("stamp_cards: FAIL — %s is unreadable: %s" %
                  (path.relative_to(root), exc))
            return 1
        if current != text:
            changes.append((path, text))
    try:
        _write_changes(changes)
    except (OSError, ValueError) as exc:
        print("stamp_cards: FAIL — write transaction aborted: %s" % exc)
        return 1
    print("stamp_cards: read_sets=%d curated_cards=%d indexes=2 review_stale=%d updated=%d" %
          (len(read_sets), len(cards), len(stale), len(changes)))
    return 2 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
