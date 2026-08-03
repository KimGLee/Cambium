#!/usr/bin/env python3
"""Stamp and verify the kernel-owned Runtime Card layer.

The canonical rule owner is kernel/K00 Standards Control/03 Standards
Governance. Cards live under kernel/Cards and are compiled from kernel source
files; they are never profile-selected and never canonical rule owners. The
Read Set Index and Card Index share registry_id `kernel-runtime-routes`; their
route registries, the Read Set files, and the Runtime Cards must agree exactly
on the continuous route set R01-R10. A Read Set and its Card share route_id;
indexes have no route identity of their own.

Hash = the first 12 hexadecimal digits of SHA-256 over each source file's
bytes, concatenated in source_files order.

Usage:
  python3 Tools/stamp_cards.py <standards_root> [--cards-dir DIR]
      [--set-version VERSION] [--check]

Exit codes:
  0 = structurally complete and current
  1 = malformed or incomplete Card layer
  2 = structurally valid but stale hash/version in --check mode
"""

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib


DEFAULT_CARDS_DIR = "kernel/Cards"
DEFAULT_READ_SETS_DIR = "kernel/Read Sets"
CARD_INDEX_NAME = "Card Index.md"
READ_SET_INDEX_NAME = "Read Sets Index.md"
REGISTRY_ID = "kernel-runtime-routes"
ROUTE_ID_RE = re.compile(r"^R([0-9]{2})$")
EXPECTED_ROUTE_IDS = tuple("R%02d" % number for number in range(1, 11))


def replace_frontmatter_scalar(text, field, value):
    """Replace one existing top-level scalar without touching the body."""
    end = text.find("\n---", 4)
    if not text.startswith("---\n") or end < 0:
        raise ValueError("missing fenced frontmatter")
    front = text[:end]
    pattern = re.compile(r"(?m)^%s:\s*.*$" % re.escape(field))
    if not pattern.search(front):
        raise ValueError("missing frontmatter field %s" % field)
    front = pattern.sub("%s: %s" % (field, value), front, count=1)
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


def validate_unique_frontmatter_keys(front, rel, failures):
    """Reject duplicate top-level and route-registry-entry keys.

    The shared restricted YAML parser intentionally keeps its last value for a
    duplicate key. Identity-bearing Card metadata must instead fail closed, so
    this verifier checks the two mapping levels that own route identity.
    """
    prepared = []
    for lineno, raw in enumerate(front.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        prepared.append((indent, stripped, lineno))

    def mapping_key(content):
        match = re.match(r"^([^:\s][^:]*):(?:\s|$)", content)
        return match.group(1).strip() if match else ""

    top_level = set()
    registry_starts = []
    for index, (indent, content, lineno) in enumerate(prepared):
        if indent != 0 or content == "-" or content.startswith("- "):
            continue
        key = mapping_key(content)
        if not key:
            continue
        if key in top_level:
            failures.append(
                "%s repeats top-level frontmatter key %s (line %d)"
                % (rel, key, lineno)
            )
        else:
            top_level.add(key)
        if key == "route_registry":
            registry_starts.append(index)

    for start in registry_starts:
        base_indent = prepared[start][0]
        entry_number = 0
        entry_keys = None
        for indent, content, lineno in prepared[start + 1 :]:
            if indent <= base_indent:
                break
            if content == "-" or content.startswith("- "):
                entry_number += 1
                entry_keys = set()
                content = content[1:].strip()
            if entry_keys is None or not content:
                continue
            key = mapping_key(content)
            if not key:
                continue
            if key in entry_keys:
                failures.append(
                    "%s route_registry entry %d repeats key %s (line %d)"
                    % (rel, entry_number, key, lineno)
                )
            else:
                entry_keys.add(key)


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
    validate_unique_frontmatter_keys(front, rel, failures)
    return rel, text, data


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

    # ---- Read Set Index and on-disk Read Sets ----
    read_set_records = []
    read_set_index_record = None
    seen_read_set_routes = set()

    for path in read_set_paths:
        rel, text, data = parse_document(path, root, failures)
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
        read_set_records.append(
            {"path": path, "rel": rel, "data": data, "route_id": route_id}
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
                "%s routes must be continuous R01-R10; missing=%s extra=%s"
                % (
                    label,
                    sorted(expected_routes - route_ids),
                    sorted(route_ids - expected_routes),
                )
            )

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

    stale = []
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
        version_stale = bool(
            args.set_version and record["compiled_from"] != args.set_version
        )
        if args.check:
            if hash_stale or version_stale:
                stale.append(record["rel"])
                details = []
                if hash_stale:
                    details.append("hash %s -> %s" % (record["source_hash"], expected_hash))
                if version_stale:
                    details.append(
                        "compiled_from %s -> %s"
                        % (record["compiled_from"], args.set_version)
                    )
                print("  [CAND] %s: %s" % (record["rel"], "; ".join(details)))
            continue

        text = replace_frontmatter_scalar(record["text"], "source_hash", expected_hash)
        if args.set_version:
            text = replace_frontmatter_scalar(text, "compiled_from", args.set_version)
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

    changed = 0
    for path, rel, text, expected_hash in rendered:
        current = path.read_text(encoding="utf-8")
        if current == text:
            continue
        atomic_write(path, text)
        changed += 1
        print("  [STAMP] %s -> %s" % (rel, expected_hash))
    print(
        "stamp_cards: routes=%d read_sets=%d runtime_cards=%d indexes=2 "
        "stale=0 updated=%d"
        % (
            len(expected_routes),
            len(read_set_records),
            len(runtime_records),
            changed,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
