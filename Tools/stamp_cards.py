#!/usr/bin/env python3
"""Stamp and verify the kernel-owned Runtime Card layer.

The canonical rule owner is kernel/00 Standards Control/03 Standards
Governance.  Cards live under kernel/Cards and are compiled from kernel source
files; they are never profile-selected and never canonical rule owners.

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
INDEX_NAME = "00 Card Index.md"


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
    resolved = (root / candidate).resolve()
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

    card_paths = sorted(path for path in cards_dir.rglob("*.md") if path.is_file())
    if not card_paths:
        print("stamp_cards: FAIL — Card directory contains zero Markdown files")
        return 1

    index_path = cards_dir / INDEX_NAME
    if not index_path.is_file():
        print("stamp_cards: FAIL — required Card Index is missing: %s" % INDEX_NAME)
        return 1

    records = []
    seen_ids = set()
    seen_read_sets = set()
    cards_real = cards_dir.resolve()
    kernel_real = (root / "kernel").resolve()

    for path in card_paths:
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            failures.append("%s must not be a symlink" % rel)
            continue
        text = path.read_text(encoding="utf-8")
        front = kblib.extract_frontmatter(text)
        if front is None:
            failures.append("%s has no fenced frontmatter" % rel)
            continue
        try:
            data = kblib.parse_yaml_subset(front)
        except kblib.YamlSubsetError as exc:
            failures.append("%s has invalid frontmatter: %s" % (rel, exc))
            continue

        expected_type = "card-index" if path == index_path else "runtime-card"
        if data.get("type") != expected_type:
            failures.append("%s must declare type: %s" % (rel, expected_type))

        card_id = str(data.get("card_id") or "")
        if not card_id:
            failures.append("%s is missing card_id" % rel)
        elif card_id in seen_ids:
            failures.append("duplicate card_id %s" % card_id)
        else:
            seen_ids.add(card_id)

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
            elif read_set in seen_read_sets:
                failures.append("more than one Runtime Card maps read_set %s" % read_set)
            else:
                seen_read_sets.add(read_set)

        records.append(
            {
                "path": path,
                "rel": rel,
                "text": text,
                "data": data,
                "type": expected_type,
                "card_id": card_id,
                "compiled_from": compiled_from,
                "source_paths": source_paths,
                "source_rels": source_rels,
                "source_hash": current_hash,
                "read_set": read_set,
            }
        )

    index_record = next((record for record in records if record["path"] == index_path), None)
    runtime_records = [record for record in records if record["type"] == "runtime-card"]
    if index_record is None:
        failures.append("Card Index could not be parsed")
    if not runtime_records:
        failures.append("Card layer contains zero runtime cards")

    if index_record is not None:
        registry = index_record["data"].get("card_registry")
        if not isinstance(registry, list) or not registry:
            failures.append("Card Index must declare a non-empty card_registry")
        else:
            registered = set()
            for entry in registry:
                if not isinstance(entry, dict):
                    failures.append("Card Index card_registry entries must be mappings")
                    continue
                triple = (
                    str(entry.get("card_id") or ""),
                    str(entry.get("path") or ""),
                    str(entry.get("read_set") or ""),
                )
                if not all(triple):
                    failures.append("Card Index has an incomplete card_registry entry")
                elif triple in registered:
                    failures.append("Card Index repeats registry entry %s" % (triple,))
                registered.add(triple)
            actual = {
                (record["card_id"], record["rel"], record["read_set"])
                for record in runtime_records
            }
            if registered != actual:
                missing = sorted(actual - registered)
                extra = sorted(registered - actual)
                failures.append(
                    "Card Index membership mismatch; missing=%s extra=%s" % (missing, extra)
                )

    expected_read_sets = {
        path.relative_to(root).as_posix()
        for path in (root / "kernel" / "Read Sets").glob("[0-9][0-9] * Read Set.md")
        if not path.name.startswith("00 ")
    }
    mapped_read_sets = {record["read_set"] for record in runtime_records if record["read_set"]}
    if expected_read_sets != mapped_read_sets:
        failures.append(
            "kernel Read Set coverage mismatch; missing=%s extra=%s"
            % (sorted(expected_read_sets - mapped_read_sets), sorted(mapped_read_sets - expected_read_sets))
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
        expected_hash = source_digest(record["source_paths"])
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
            "stamp_cards --check: %d card(s), %d stale"
            % (len(records), len(stale))
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
    print("stamp_cards: %d card(s), %d updated" % (len(records), changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
