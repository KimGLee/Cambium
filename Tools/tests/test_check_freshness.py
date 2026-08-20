import contextlib
import json
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import check_freshness as checker


class FreshnessFutureBaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.page = self.root / "Topic.md"
        self.receipts = self.root / "freshness.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def write_page(self, *, name="Topic.md", last_verified=None,
                   last_reviewed=None, volatility="fast", extra_fields=()):
        page = self.root / name
        page.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "---",
            "type: concept",
            "priority: P0",
        ]
        if volatility is not None:
            fields.append("volatility: %s" % volatility)
        if last_verified is not None:
            fields.append("last_verified: %s" % last_verified)
        if last_reviewed is not None:
            fields.append("last_reviewed: %s" % last_reviewed)
        fields.extend(extra_fields)
        fields.extend(("---", "# Topic", ""))
        page.write_text("\n".join(fields), encoding="utf-8")
        return page

    def run_check(self, as_of="2026-08-14", *, scope=None,
                  extra_args=()):
        command = [
                sys.executable,
                str(TOOLS / "check_freshness.py"),
                str(self.root),
                "--as-of", as_of,
                "--receipts", str(self.receipts),
            ]
        if scope is not None:
            command.extend(("--scope", scope))
        command.extend(extra_args)
        return subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def receipt_rows(self):
        return [
            json.loads(line)
            for line in self.receipts.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def candidate_rows(self):
        return [
            row for row in self.receipt_rows()
            if row.get("check") == "freshness"
        ]

    def summary_row(self):
        rows = [
            row for row in self.receipt_rows()
            if row.get("check") == "freshness-check-summary"
        ]
        self.assertEqual(1, len(rows), rows)
        return rows[0]

    def assert_future_candidate(self, field):
        completed = self.run_check()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("future_baseline=1", completed.stdout)
        self.assertIn("fresh=0", completed.stdout)
        rows = self.candidate_rows()
        self.assertEqual(1, len(rows), rows)
        self.assertEqual("candidate", rows[0]["result"])
        self.assertEqual("future_baseline", rows[0]["candidate_kind"])
        self.assertIn("%s=2099-01-01" % field, rows[0]["details"])
        self.assertIn("as_of=2026-08-14", rows[0]["details"])
        self.assertEqual("2.0.0", rows[0]["tool_version"])
        summary = self.summary_row()
        self.assertEqual("candidate", summary["result"])
        self.assertTrue(summary["scan_complete"])
        self.assertEqual(1, summary["candidate_count"])
        self.assertEqual(rows[0]["scan_id"], summary["scan_id"])
        self.assertEqual([rows[0]["candidate_id"]],
                         summary["candidate_ids"])
        self.assertTrue(rows[0]["candidate_id"].startswith(
            "candidate-sha256:"))
        self.assertTrue(summary["candidate_set_sha256"].startswith(
            "sha256:"))
        self.assertEqual("sorted-candidate-records-v1",
                         summary["candidate_set_basis"])
        self.assertEqual([{
            "candidate_id": rows[0]["candidate_id"],
            "object_path": rows[0]["target"],
            "candidate_kind": rows[0]["candidate_kind"],
            "priority": "P0",
        }], summary["candidate_records"])
        candidate_commitment = {
            "schema_version": 1,
            "basis": "sorted-candidate-records-v1",
            "candidate_records": summary["candidate_records"],
        }
        expected_hash = "sha256:" + hashlib.sha256(json.dumps(
            candidate_commitment, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        self.assertEqual(expected_hash, summary["candidate_set_sha256"])
        self.assertTrue(summary["input_snapshot_sha256"].startswith(
            "sha256:"))
        self.assertIn("defaults_fingerprint", summary)
        self.assertEqual("none", summary["defaults_source_kind"])
        self.assertIsNone(summary["defaults_source"])
        self.assertEqual(".", summary["scope"])
        self.assertEqual([], summary["exclude_components"])
        self.assertEqual(1, summary["page_candidate_count"])
        self.assertEqual([], summary["scan_finding_codes"])

    def test_future_last_verified_is_a_candidate_not_freshness_evidence(self):
        self.write_page(last_verified="2099-01-01")
        self.assert_future_candidate("last_verified")

    def test_future_last_reviewed_fallback_is_a_candidate(self):
        self.write_page(last_reviewed="2099-01-01")
        self.assert_future_candidate("last_reviewed")

    def test_baseline_equal_to_as_of_remains_valid(self):
        self.write_page(last_verified="2026-08-14")
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("future_baseline=0", completed.stdout)
        self.assertIn("fresh=1", completed.stdout)
        rows = self.receipt_rows()
        self.assertEqual(1, len(rows), rows)
        self.assertEqual("pass", rows[0]["result"])
        self.assertEqual("freshness-check-summary", rows[0]["check"])
        self.assertTrue(rows[0]["scan_complete"])
        self.assertEqual(0, rows[0]["candidate_count"])

    def test_stable_page_does_not_hide_a_future_event_date(self):
        self.write_page(last_verified="2099-01-01", volatility="stable")
        self.assert_future_candidate("last_verified")

    def test_unselected_future_event_is_not_hidden_by_valid_selected_event(self):
        self.write_page(
            last_verified="2026-08-01", last_reviewed="2099-01-01")
        self.assert_future_candidate("last_reviewed")

    def test_invalid_verified_date_does_not_fall_back_to_reviewed_date(self):
        self.write_page(
            last_verified="not-a-date", last_reviewed="2026-08-01")
        completed = self.run_check()
        self.assertEqual(2, completed.returncode, completed.stdout)
        rows = self.candidate_rows()
        self.assertEqual(1, len(rows), rows)
        self.assertEqual("invalid_baseline", rows[0]["candidate_kind"])
        self.assertIn("invalid value cannot fall back", rows[0]["details"])
        self.assertEqual("candidate", self.summary_row()["result"])

    def test_mixed_future_without_volatility_and_fresh_page_cannot_pass(self):
        self.write_page(
            name="Future.md", last_verified="2099-01-01",
            volatility=None)
        self.write_page(
            name="Fresh.md", last_verified="2026-08-01",
            volatility="fast")
        completed = self.run_check()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("future_baseline=1", completed.stdout)
        self.assertIn("fresh=1", completed.stdout)
        rows = self.candidate_rows()
        self.assertEqual(["Future.md"], [row["target"] for row in rows])
        summary = self.summary_row()
        self.assertEqual("candidate", summary["result"])
        self.assertEqual(2, summary["discovered_count"])

    def test_mixed_unresolved_volatility_and_fresh_page_cannot_pass(self):
        self.write_page(
            name="Unresolved.md", last_verified="2026-08-01",
            volatility=None)
        self.write_page(
            name="Fresh.md", last_verified="2026-08-01",
            volatility="fast")
        completed = self.run_check()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("unresolved_volatility=1", completed.stdout)
        rows = self.candidate_rows()
        self.assertEqual("unresolved_volatility", rows[0]["candidate_kind"])
        self.assertEqual("candidate", self.summary_row()["result"])

    def test_mixed_unparseable_frontmatter_and_fresh_page_cannot_pass(self):
        (self.root / "Broken.md").write_text(
            "---\ntype: concept\ntype: duplicate\n---\n# Broken\n",
            encoding="utf-8")
        self.write_page(
            name="Fresh.md", last_verified="2026-08-01",
            volatility="fast")
        completed = self.run_check()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("unparseable_frontmatter=1", completed.stdout)
        rows = self.candidate_rows()
        self.assertEqual("unparseable_frontmatter", rows[0]["candidate_kind"])
        self.assertEqual("candidate", self.summary_row()["result"])

    def test_zero_file_scan_emits_typed_candidate_summary(self):
        completed = self.run_check()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("NOTHING CHECKED", completed.stdout)
        self.assertEqual([], self.candidate_rows())
        summary = self.summary_row()
        self.assertEqual("candidate", summary["result"])
        self.assertTrue(summary["scan_complete"])
        self.assertEqual(0, summary["discovered_count"])
        self.assertEqual(1, summary["candidate_count"])
        self.assertEqual(0, summary["page_candidate_count"])
        self.assertEqual(["nothing_checked"],
                         summary["scan_finding_codes"])
        self.assertEqual([], summary["candidate_ids"])
        self.assertEqual([], summary["candidate_records"])

    def test_non_utf8_page_is_an_unparseable_candidate_not_a_pass(self):
        (self.root / "InvalidUtf8.md").write_bytes(
            b"---\nvolatility: fast\n---\n# Invalid\n\xff\n")
        completed = self.run_check()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("unparseable_frontmatter=1", completed.stdout)
        rows = self.candidate_rows()
        self.assertEqual(1, len(rows), rows)
        self.assertEqual("unparseable_frontmatter",
                         rows[0]["candidate_kind"])
        self.assertEqual("candidate", self.summary_row()["result"])

    def test_stable_without_completed_event_is_pending_first_verification(self):
        self.write_page(volatility="stable")
        completed = self.run_check()
        self.assertEqual(2, completed.returncode, completed.stdout)
        row = self.candidate_rows()[0]
        self.assertEqual("pending_first_verification",
                         row["candidate_kind"])
        self.assertIsNone(row["review_by"])
        self.assertIn("no recurring review deadline", row["details"])
        self.assertIn("mtime is diagnostic only", row["details"])

    def test_canonical_directory_scope_is_preserved_in_summary(self):
        (self.root / "Docs").mkdir()
        self.write_page(
            name="Docs/Topic.md", last_verified="2026-08-01")
        completed = self.run_check(scope="Docs")
        self.assertEqual(0, completed.returncode, completed.stdout)
        summary = self.summary_row()
        self.assertEqual("Docs", summary["scope"])
        self.assertEqual("Docs", summary["target"])
        self.assertNotIn(str(self.root), json.dumps(summary, sort_keys=True))

    def test_explicit_dot_scope_is_the_canonical_root_alias(self):
        self.write_page(last_verified="2026-08-01")
        completed = self.run_check(scope=".")
        self.assertEqual(0, completed.returncode, completed.stdout)
        summary = self.summary_row()
        self.assertEqual(".", summary["scope"])
        self.assertEqual(".", summary["target"])
        self.assertNotIn(str(self.root), json.dumps(summary, sort_keys=True))

    def test_uppercase_markdown_suffix_preserves_cli_compatibility(self):
        self.write_page(
            name="Topic.MD", last_verified="2026-08-01")
        completed = self.run_check(scope="Topic.MD")
        self.assertEqual(0, completed.returncode, completed.stdout)
        summary = self.summary_row()
        self.assertEqual("Topic.MD", summary["scope"])
        self.assertEqual(1, summary["discovered_count"])

    def test_existing_probe_like_name_does_not_reserve_a_scope_path(self):
        (self.root / "Docs").mkdir()
        (self.root / "Docs" /
         ".__cambium_freshness_scope_probe_v1_0__").write_text(
             "legitimate repository content\n", encoding="utf-8")
        self.write_page(
            name="Docs/Topic.md", last_verified="2026-08-01")
        completed = self.run_check(scope="Docs")
        self.assertEqual(0, completed.returncode, completed.stdout)

    def test_scope_rejects_absolute_parent_and_noncanonical_spellings(self):
        (self.root / "Docs").mkdir()
        self.write_page(
            name="Docs/Topic.md", last_verified="2026-08-01")
        for scope in (str(self.root / "Docs"), "../Docs", "Docs/."):
            with self.subTest(scope=scope):
                if self.receipts.exists():
                    self.receipts.unlink()
                completed = self.run_check(scope=scope)
                self.assertEqual(1, completed.returncode, completed.stdout)
                self.assertIn("canonical page snapshot", completed.stdout)
                self.assertFalse(self.receipts.exists())

    def test_scope_rejects_symlink_components_final_symlink_and_hardlink(self):
        (self.root / "Docs").mkdir()
        page = self.write_page(
            name="Docs/Topic.md", last_verified="2026-08-01")
        (self.root / "AliasDir").symlink_to(self.root / "Docs",
                                             target_is_directory=True)
        (self.root / "Alias.md").symlink_to(page)
        os.link(page, self.root / "Hardlink.md")
        for scope in ("AliasDir", "Alias.md", "Hardlink.md"):
            with self.subTest(scope=scope):
                if self.receipts.exists():
                    self.receipts.unlink()
                completed = self.run_check(scope=scope)
                self.assertEqual(1, completed.returncode, completed.stdout)
                self.assertFalse(self.receipts.exists())

    def test_directory_scope_rejects_nested_visible_symlink_directory(self):
        (self.root / "Docs").mkdir()
        (self.root / "Elsewhere").mkdir()
        self.write_page(
            name="Docs/Topic.md", last_verified="2026-08-01")
        self.write_page(
            name="Elsewhere/Other.md", last_verified="2026-08-01")
        (self.root / "Docs" / "NestedAlias").symlink_to(
            self.root / "Elsewhere", target_is_directory=True)
        completed = self.run_check(scope="Docs")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("symlink directory", completed.stdout)
        self.assertFalse(self.receipts.exists())

    def test_currency_reports_new_symlink_directory_without_traceback(self):
        (self.root / "Docs").mkdir()
        (self.root / "Elsewhere").mkdir()
        self.write_page(
            name="Docs/Topic.md", last_verified="2026-08-01")
        scope, identity = checker._admit_scope(str(self.root), "Docs")
        _snapshots, records, _inputs = checker._capture_scope(
            str(self.root), scope, ())
        (self.root / "Docs" / "NestedAlias").symlink_to(
            self.root / "Elsewhere", target_is_directory=True)
        errors = checker._scope_currency_errors(
            str(self.root), scope, identity, records, ())
        self.assertTrue(any(
            "cannot enumerate final Markdown set" in error and
            "symlink directory" in error
            for error in errors), errors)

    def test_listing_propagates_walk_errors_instead_of_skipping_subtree(self):
        self.write_page(last_verified="2026-08-01")

        def failing_walk(_base, *, topdown, onerror, followlinks):
            self.assertTrue(topdown)
            self.assertFalse(followlinks)
            onerror(PermissionError("deterministic unreadable subtree"))
            if False:
                yield None

        with mock.patch.object(checker.os, "walk", side_effect=failing_walk):
            with self.assertRaisesRegex(
                    PermissionError, "deterministic unreadable subtree"):
                checker._listed_markdown_paths(str(self.root), ".")

    def _captured_scope(self, exclude_components=()):
        scope, identity = checker._admit_scope(str(self.root), None)
        _snapshots, records, inputs = checker._capture_scope(
            str(self.root), scope, tuple(exclude_components))
        return scope, identity, records, inputs

    def test_final_currency_detects_expected_set_and_exact_page_drift(self):
        page = self.write_page(last_verified="2026-08-01")

        scope, identity, records, _inputs = self._captured_scope()
        self.write_page(
            name="Added.md", last_verified="2026-08-01")
        self.assertTrue(checker._scope_currency_errors(
            str(self.root), scope, identity, records, ()))
        (self.root / "Added.md").unlink()

        scope, identity, records, _inputs = self._captured_scope()
        original = page.read_bytes()
        page.write_bytes(original + b"changed\n")
        self.assertTrue(checker._scope_currency_errors(
            str(self.root), scope, identity, records, ()))
        page.write_bytes(original)

        scope, identity, records, _inputs = self._captured_scope()
        replacement = self.root / "replacement.tmp"
        replacement.write_bytes(page.read_bytes())
        os.replace(replacement, page)
        self.assertTrue(checker._scope_currency_errors(
            str(self.root), scope, identity, records, ()))

        scope, identity, records, _inputs = self._captured_scope()
        before_mtime = records[0]["mtime_ns"]
        os.utime(page, ns=(before_mtime + 2_000_000_000,
                           before_mtime + 2_000_000_000))
        self.assertTrue(checker._scope_currency_errors(
            str(self.root), scope, identity, records, ()))

        scope, identity, records, _inputs = self._captured_scope()
        page.unlink()
        self.assertTrue(checker._scope_currency_errors(
            str(self.root), scope, identity, records, ()))

    def test_inactive_page_is_still_exactly_currency_bound(self):
        page = self.write_page(
            last_verified="2026-08-01",
            extra_fields=("lifecycle: retired",))
        scope, identity, records, _inputs = self._captured_scope()
        page.write_bytes(page.read_bytes() + b"changed\n")
        self.assertTrue(checker._scope_currency_errors(
            str(self.root), scope, identity, records, ()))

    def test_excluded_page_is_path_bound_without_content_hash_or_read(self):
        page = self.write_page(
            name="Excluded/Topic.md", last_verified="2026-08-01")
        page.chmod(0)
        try:
            _scope, _identity, records, inputs = self._captured_scope(
                ("Excluded",))
        finally:
            page.chmod(0o600)
        self.assertEqual(
            [{"path": "Excluded/Topic.md", "excluded": True}], records)
        self.assertEqual(records, inputs)

    def test_interleaved_change_blocks_receipt_publication(self):
        page = self.write_page(last_verified="2026-08-01")
        original_currency = checker._scope_currency_errors

        def mutate_then_validate(*args, **kwargs):
            page.write_bytes(page.read_bytes() + b"interleaved\n")
            return original_currency(*args, **kwargs)

        args = SimpleNamespace(
            vault_root=str(self.root),
            scope=None,
            as_of="2026-08-14",
            defaults=None,
            exclude=[],
            receipts=str(self.receipts),
            json=False,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(
                checker, "_scope_currency_errors",
                side_effect=mutate_then_validate), mock.patch.object(
                    checker.kblib, "write_receipts") as write_receipts:
            self.assertEqual(1, checker._run(args))
        write_receipts.assert_not_called()
        self.assertNotIn("Conclusion:", output.getvalue())

    def test_scope_identity_is_rechecked_after_second_set_enumeration(self):
        (self.root / "Docs").mkdir()
        page = self.write_page(
            name="Docs/Topic.md", last_verified="2026-08-01")
        page_bytes = page.read_bytes()
        scope, identity = checker._admit_scope(str(self.root), "Docs")
        _snapshots, records, _inputs = checker._capture_scope(
            str(self.root), scope, ())
        original_listing = checker._listed_markdown_paths
        calls = 0

        def replace_scope_after_second_listing(root, current_scope):
            nonlocal calls
            result = original_listing(root, current_scope)
            calls += 1
            if calls == 2:
                (self.root / "Docs").rename(self.root / "Docs-old")
                (self.root / "Docs").mkdir()
                (self.root / "Docs" / "Topic.md").write_bytes(page_bytes)
            return result

        with mock.patch.object(
                checker, "_listed_markdown_paths",
                side_effect=replace_scope_after_second_listing):
            errors = checker._scope_currency_errors(
                str(self.root), scope, identity, records, ())
        self.assertEqual(2, calls)
        self.assertTrue(any(
            "scope identity changed at final boundary" in error
            for error in errors), errors)

    def test_standalone_defaults_drift_blocks_receipt_publication(self):
        self.write_page(last_verified="2026-08-01")
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

        args = SimpleNamespace(
            vault_root=str(self.root),
            scope=None,
            as_of="2026-08-14",
            defaults=str(defaults),
            exclude=[],
            receipts=str(self.receipts),
            json=False,
        )
        with mock.patch.object(
                checker, "_stable_external_file_snapshot",
                side_effect=mutate_before_final_snapshot), mock.patch.object(
                    checker.kblib, "write_receipts") as write_receipts:
            self.assertEqual(1, checker._run(args))
        self.assertEqual(2, calls)
        write_receipts.assert_not_called()

    @unittest.skipUnless(hasattr(time, "tzset"), "requires POSIX tzset")
    def test_mtime_date_is_utc_and_independent_of_host_timezone(self):
        instant_ns = 1_788_739_200_000_000_000
        previous = os.environ.get("TZ")
        try:
            observed = []
            for timezone in ("UTC0", "PST8PDT", "JST-9"):
                os.environ["TZ"] = timezone
                time.tzset()
                observed.append(checker._utc_modified_on(instant_ns))
            self.assertEqual([observed[0]] * 3, observed)
        finally:
            if previous is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = previous
            time.tzset()

    def test_mtime_one_nanosecond_before_utc_midnight_stays_previous_day(self):
        midnight_ns = 1_786_665_600 * 1_000_000_000
        self.assertEqual(
            "2026-08-13",
            checker._utc_modified_on(midnight_ns - 1).isoformat())
        self.assertEqual(
            "2026-08-14",
            checker._utc_modified_on(midnight_ns).isoformat())


if __name__ == "__main__":
    unittest.main()
