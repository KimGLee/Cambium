"""Ownership tests for the freshness scanner application boundary.

``freshness_engine`` owns date, volatility, and candidate classification.
Profile and vocabulary contracts own defaults, metadata contracts own page
frontmatter, receipt contracts own acceptance, and entrypoint tests own public
transport. This suite keeps only scanner-specific snapshot/currentness,
typed-result projection, and one minimal producer seam.
"""

import contextlib
import copy
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import Tools.knowledge.content.maintenance_candidates as maintenance_candidates
import Tools.knowledge.metadata.check_freshness as checker
import Tools.knowledge.metadata.freshness_engine as freshness_engine
import Tools.knowledge.metadata.freshness_receipt_contract as freshness_receipt_contract
import Tools.platform.common.kblib as kblib


AS_OF = datetime.date(2026, 8, 14)


def page_bytes(*, last_verified=None, volatility="fast", domain=None):
    fields = ["---", "type: concept", "priority: P0"]
    if domain is not None:
        fields.append("domain: %s" % domain)
    if volatility is not None:
        fields.append("volatility: %s" % volatility)
    if last_verified is not None:
        fields.append("last_verified: %s" % last_verified)
    fields.extend(("---", "# Topic", ""))
    return "\n".join(fields).encode("utf-8")


def receipt_pair():
    """Return one internally consistent candidate/summary contract pair."""
    future = freshness_engine.PageOutcome(
        path="B.md",
        kind=freshness_engine.FUTURE_BASELINE,
        priority="P0",
        reasons=(freshness_engine.FreshnessReason(
            code="future_completed_event_date",
            field="last_verified",
            date_value=datetime.date(2099, 1, 1),
        ),),
    )
    invalid = freshness_engine.PageOutcome(
        path="A.md",
        kind=freshness_engine.INVALID_BASELINE,
        priority="P1",
        reasons=(freshness_engine.FreshnessReason(
            code="invalid_completed_event_date",
            field="last_verified",
            raw_value="not-a-date",
        ),),
    )
    run = freshness_engine.FreshnessRun(
        as_of=AS_OF,
        outcomes=(future, invalid),
        candidates=(future, invalid),
    )
    bridge = checker._scan_bridge(
        run,
        scope=".",
        exclude_components=[],
        defaults_source_kind="none",
        defaults_source=None,
        defaults_fingerprint=checker._fingerprint({
            "schema_version": 1,
            "volatility_defaults": None,
        }),
        input_snapshot_sha256="sha256:" + "2" * 64,
    )
    candidate = kblib.make_receipt(
        checker.TOOL, checker.TOOL_VERSION,
        "freshness", future.path, "candidate", "fixture", 1,
        receipt_type_id=checker.RECEIPT_TYPE_ID,
    )
    checker._add_outcome_fields(candidate, future, AS_OF, bridge)
    summary = kblib.make_receipt(
        checker.TOOL, checker.TOOL_VERSION,
        "freshness-check-summary", ".", "candidate", "fixture", 2,
        receipt_type_id=checker.RECEIPT_TYPE_ID,
    )
    checker._add_summary_fields(summary, run, bridge)
    return run, bridge, candidate, summary


class FreshnessScannerAdapterUnitTests(unittest.TestCase):
    def test_filesystem_mtime_uses_integer_nanoseconds_at_utc_midnight(self):
        midnight_ns = 1_786_665_600 * 1_000_000_000
        self.assertEqual(
            datetime.date(2026, 8, 13),
            checker._utc_modified_on(midnight_ns - 1),
        )
        self.assertEqual(
            datetime.date(2026, 8, 14),
            checker._utc_modified_on(midnight_ns),
        )

    def test_standalone_defaults_adapter_accepts_only_flat_mappings(self):
        self.assertEqual(
            {"general": "slow"},
            checker._load_standalone_defaults(
                "unused.yaml", "general: slow\n"),
        )
        with self.assertRaisesRegex(ValueError, "must be a flat"):
            checker._load_standalone_defaults(
                "unused.yaml",
                "volatility_defaults:\n  general: slow\n",
            )


class FreshnessReceiptProjectionContractTests(unittest.TestCase):
    """Producer projection from already typed engine outcomes."""

    def test_typed_outcomes_bind_one_sorted_candidate_set_and_scan_identity(self):
        _run, bridge, candidate, summary = receipt_pair()

        self.assertEqual(
            ["A.md", "B.md"],
            [row["object_path"] for row in bridge["candidate_records"]],
        )
        expected_ids = sorted(
            maintenance_candidates.candidate_id_for_path(path)
            for path in ("A.md", "B.md")
        )
        self.assertEqual(expected_ids, bridge["candidate_ids"])
        commitment = {
            "schema_version": 1,
            "basis": "sorted-candidate-records-v1",
            "candidate_records": bridge["candidate_records"],
        }
        self.assertEqual(
            "sha256:" + hashlib.sha256(
                kblib.canonical_json_bytes(commitment)).hexdigest(),
            bridge["candidate_set_sha256"],
        )

        self.assertEqual(bridge["scan_id"], candidate["scan_id"])
        self.assertEqual(bridge["scan_id"], summary["scan_id"])
        self.assertEqual(bridge["candidate_ids"], summary["candidate_ids"])
        self.assertEqual(
            ["future_completed_event_date"], candidate["reason_codes"])
        # The producer projection is immediately accepted by the independent
        # typed payload contract; mutation coverage remains with that owner.
        self.assertEqual([], checker.current_receipt_errors(candidate))
        self.assertEqual([], checker.current_receipt_errors(summary))


class FreshnessReceiptAcceptanceContractTests(unittest.TestCase):
    def test_payload_closure_rejects_drift_from_typed_scan(self):
        _run, _bridge, candidate, summary = receipt_pair()
        invalidated_current_format = copy.deepcopy(candidate)
        invalidated_current_format["invalidated_by"] = (
            "audit-check_freshness-successor")
        self.assertEqual(
            [],
            freshness_receipt_contract.current_receipt_errors(
                invalidated_current_format),
        )

        mutations = (
            (candidate, "candidate-extra-field",
             lambda value: value.update({"unexpected_scan_state": "accepted"})),
            (candidate, "candidate-kind-binding",
             lambda value: value.update({
                 "candidate_kind": freshness_engine.OVERDUE,
             })),
            (summary, "candidate-set-fingerprint",
             lambda value: value.update({
                 "candidate_set_sha256": "sha256:" + "0" * 64,
             })),
            (summary, "classification-closure",
             lambda value: value["classification_counts"].update({
                 freshness_engine.FRESH: 1,
             })),
            (summary, "profile-binding-all-or-none",
             lambda value: value.update({
                 "profile_snapshot_sha256": "sha256:" + "3" * 64,
             })),
        )
        for original, label, mutate in mutations:
            with self.subTest(label=label):
                changed = copy.deepcopy(original)
                mutate(changed)
                self.assertTrue(
                    freshness_receipt_contract.current_receipt_errors(changed))


class FreshnessRepositoryCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.receipts = self.root / "freshness.jsonl"

    def write_page(self, name="Topic.md", **kwargs):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(page_bytes(**kwargs))
        return path

    def args(self, *, scope=None, defaults=None, exclude=()):
        return SimpleNamespace(
            vault_root=str(self.root),
            scope=scope,
            as_of=AS_OF.isoformat(),
            defaults=None if defaults is None else str(defaults),
            exclude=list(exclude),
            receipts=str(self.receipts),
            json=False,
        )

    def rows(self):
        if not self.receipts.exists():
            return []
        return [
            json.loads(line)
            for line in self.receipts.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def captured_scope(self, scope=None, exclude=()):
        admitted, identity = checker._admit_scope(str(self.root), scope)
        _snapshots, records, inputs = checker._capture_scope(
            str(self.root), admitted, tuple(exclude))
        return admitted, identity, records, inputs


class FreshnessScannerIntegrationTests(FreshnessRepositoryCase):
    def test_current_page_snapshot_produces_candidate_and_summary_receipts(self):
        self.write_page(last_verified="2099-01-01")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = checker._run(self.args())

        self.assertEqual(2, code, output.getvalue())
        candidate, summary = self.rows()
        self.assertEqual(
            ["freshness", "freshness-check-summary"],
            [candidate["check"], summary["check"]],
        )
        self.assertEqual(candidate["scan_id"], summary["scan_id"])
        self.assertEqual([candidate["candidate_id"]],
                         summary["candidate_ids"])
        self.assertEqual([], checker.current_receipt_errors(candidate))
        self.assertEqual([], checker.current_receipt_errors(summary))


class FreshnessScannerSlowTests(FreshnessRepositoryCase):
    def test_scope_snapshot_admission_and_listing_fail_closed(self):
        docs = self.root / "Docs"
        elsewhere = self.root / "Elsewhere"
        docs.mkdir()
        elsewhere.mkdir()
        page = self.write_page(
            "Docs/Topic.MD", last_verified=AS_OF.isoformat())
        excluded = self.write_page(
            "Docs/Excluded/Private.md", last_verified=AS_OF.isoformat())
        excluded.chmod(0)
        try:
            scope, _identity, records, inputs = self.captured_scope(
                "Docs", ("Excluded",))
        finally:
            excluded.chmod(0o600)
        self.assertEqual("Docs", scope)
        self.assertEqual(
            {"path": "Docs/Excluded/Private.md", "excluded": True},
            records[0],
        )
        self.assertEqual(records[0], inputs[0])
        self.assertIn("content_sha256", records[1])

        (self.root / "AliasDir").symlink_to(docs, target_is_directory=True)
        (self.root / "Alias.md").symlink_to(page)
        os.link(page, self.root / "Hardlink.md")
        for requested in (
                str(docs), "../Docs", "Docs/.",
                "AliasDir", "Alias.md", "Hardlink.md"):
            with self.subTest(scope=requested):
                with self.assertRaises((OSError, ValueError)):
                    checker._admit_scope(str(self.root), requested)

        nested_alias = docs / "NestedAlias"
        nested_alias.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink directory"):
            checker._listed_markdown_paths(str(self.root), "Docs")
        nested_alias.unlink()

        def failing_walk(_base, *, topdown, onerror, followlinks):
            self.assertTrue(topdown)
            self.assertFalse(followlinks)
            onerror(PermissionError("unreadable subtree"))
            if False:
                yield None

        with mock.patch.object(checker.os, "walk", side_effect=failing_walk):
            with self.assertRaisesRegex(PermissionError, "unreadable subtree"):
                checker._listed_markdown_paths(str(self.root), "Docs")

    def test_currentness_detects_set_bytes_identity_mtime_and_scope_drift(self):
        page = self.write_page(last_verified=AS_OF.isoformat())

        scope, identity, records, _inputs = self.captured_scope()
        added = self.write_page("Added.md", last_verified=AS_OF.isoformat())
        self.assertTrue(checker._scope_currency_errors(
            str(self.root), scope, identity, records, ()))
        added.unlink()

        scope, identity, records, _inputs = self.captured_scope()
        original = page.read_bytes()
        page.write_bytes(original + b"changed\n")
        self.assertTrue(checker._scope_currency_errors(
            str(self.root), scope, identity, records, ()))
        page.write_bytes(original)

        scope, identity, records, _inputs = self.captured_scope()
        replacement = self.root / "replacement.tmp"
        replacement.write_bytes(page.read_bytes())
        os.replace(replacement, page)
        self.assertTrue(checker._scope_currency_errors(
            str(self.root), scope, identity, records, ()))

        scope, identity, records, _inputs = self.captured_scope()
        mtime = records[0]["mtime_ns"] + 2_000_000_000
        os.utime(page, ns=(mtime, mtime))
        self.assertTrue(checker._scope_currency_errors(
            str(self.root), scope, identity, records, ()))

        docs = self.root / "Docs"
        docs.mkdir()
        scoped_page = self.write_page(
            "Docs/Topic.md", last_verified=AS_OF.isoformat())
        scoped_bytes = scoped_page.read_bytes()
        scope, identity, records, _inputs = self.captured_scope("Docs")
        original_listing = checker._listed_markdown_paths
        calls = 0

        def replace_scope_after_second_listing(root, current_scope):
            nonlocal calls
            result = original_listing(root, current_scope)
            calls += 1
            if calls == 2:
                docs.rename(self.root / "Docs-old")
                docs.mkdir()
                (docs / "Topic.md").write_bytes(scoped_bytes)
            return result

        with mock.patch.object(
                checker, "_listed_markdown_paths",
                side_effect=replace_scope_after_second_listing):
            errors = checker._scope_currency_errors(
                str(self.root), scope, identity, records, ())
        self.assertEqual(2, calls)
        self.assertTrue(any(
            "scope identity changed at final boundary" in error
            for error in errors
        ), errors)

    def test_interleaved_page_or_defaults_drift_blocks_receipt_publication(self):
        page = self.write_page(last_verified=AS_OF.isoformat())
        original_bytes = page.read_bytes()
        original_currency = checker._scope_currency_errors

        def mutate_then_validate(*args, **kwargs):
            page.write_bytes(page.read_bytes() + b"interleaved\n")
            return original_currency(*args, **kwargs)

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(
                checker, "_scope_currency_errors",
                side_effect=mutate_then_validate), mock.patch.object(
                checker.kblib, "write_receipts") as writer:
            self.assertEqual(1, checker._run(self.args()))
        writer.assert_not_called()
        self.assertNotIn("Conclusion:", output.getvalue())

        page.write_bytes(page_bytes(
            last_verified=AS_OF.isoformat(),
            volatility=None,
            domain="systems",
        ))
        defaults = self.root / "defaults.yaml"
        defaults.write_text("systems: fast\n", encoding="utf-8")
        original_snapshot = checker._stable_external_file_snapshot
        calls = 0

        def mutate_before_final_snapshot(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                defaults.write_text("systems: slow\n", encoding="utf-8")
            return original_snapshot(path)

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(
                checker, "_stable_external_file_snapshot",
                side_effect=mutate_before_final_snapshot), mock.patch.object(
                checker.kblib, "write_receipts") as writer:
            self.assertEqual(1, checker._run(self.args(defaults=defaults)))
        self.assertEqual(2, calls)
        writer.assert_not_called()
        self.assertIn("standalone --defaults changed", output.getvalue())
        self.assertNotEqual(original_bytes, page.read_bytes())


if __name__ == "__main__":
    unittest.main()
