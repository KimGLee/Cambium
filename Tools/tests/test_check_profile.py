"""Execution Default Overrides checks in check_profile.py.

Covers the closed item registry now carried by
`kernel/K00 Standards Control/execution-defaults-base.yaml` and the
`value_domain` validation attached to the same override-row path.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "Tools/check_profile.py"
EXECUTION_DEFAULTS = (
    REPOSITORY / "kernel/K00 Standards Control/execution-defaults-base.yaml"
)
PLACEHOLDER_DEFAULTS = (
    REPOSITORY / "Tools/schemas/execution_defaults.template.yaml"
)

MANIFEST_HEAD = (
    "# Profile\n\n"
    "## Profile Identity\n\n"
    "- `profile_id`: `sample`\n\n"
    "## Implemented Slots\n\n"
    "## Execution Default Overrides\n\n"
    "| Override item ID from the registry | Non-default profile value |\n"
    "|---|---|\n"
)


class ExecutionDefaultOverrideTests(unittest.TestCase):
    """Each case runs the real checker against a one-row override table."""

    def run_check(self, override_rows, execution_defaults=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_dir = root / "profiles/sample"
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.md").write_text(
                MANIFEST_HEAD + override_rows, encoding="utf-8")
            registry = EXECUTION_DEFAULTS
            if execution_defaults is not None:
                registry = root / "execution-defaults.yaml"
                registry.write_text(execution_defaults, encoding="utf-8")
            receipts = root / "receipts.jsonl"
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(profile_dir),
                 "--root", str(REPOSITORY),
                 "--defaults", str(PLACEHOLDER_DEFAULTS),
                 "--execution-defaults", str(registry),
                 "--receipts", str(receipts)],
                text=True, capture_output=True, check=False)
            written = []
            if receipts.exists():
                written = [json.loads(line) for line in
                           receipts.read_text(encoding="utf-8").splitlines()
                           if line.strip()]
            return completed, written

    def override_checks(self, receipts):
        return {r["check"] for r in receipts
                if r["result"] == "fail" and r["check"].startswith("override-")}

    # ---- the closed set now comes from the kernel registry ----

    def test_kernel_registry_supplies_the_closed_overridable_set(self):
        _, receipts = self.run_check("| `concurrency_cap` | `5` |\n")
        self.assertNotIn("override-item-unknown",
                         self.override_checks(receipts))

    def test_item_outside_the_kernel_registry_is_rejected(self):
        _, receipts = self.run_check("| `not_an_item` | `5` |\n")
        self.assertIn("override-item-unknown", self.override_checks(receipts))

    def test_constitutional_item_stays_rejected_after_the_move(self):
        _, receipts = self.run_check(
            "| `terminal_audit.round_cap` | `4` |\n")
        self.assertIn("override-constitutional-item",
                      self.override_checks(receipts))

    def test_missing_kernel_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_dir = Path(tmp) / "profiles/sample"
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.md").write_text(
                MANIFEST_HEAD, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(profile_dir),
                 "--root", str(REPOSITORY),
                 "--execution-defaults", str(Path(tmp) / "absent.yaml")],
                text=True, capture_output=True, check=False)
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("cannot read execution defaults", completed.stdout)

    # ---- value domain ----

    def test_positive_integer_domain_accepts_a_positive_integer(self):
        _, receipts = self.run_check("| `concurrency_cap` | `5` |\n")
        self.assertEqual(set(), self.override_checks(receipts))

    def test_positive_integer_domain_rejects_zero_negative_and_non_numeric(self):
        for value in ("0", "-1", "2.5", "many"):
            with self.subTest(value=value):
                _, receipts = self.run_check(
                    "| `concurrency_cap` | `%s` |\n" % value)
                self.assertIn("override-value-domain",
                              self.override_checks(receipts))

    def test_share_domain_accepts_bare_and_suffixed_percentages(self):
        for value in ("20", "20%", "0", "99.9%", "12.5%"):
            with self.subTest(value=value):
                _, receipts = self.run_check(
                    "| `priority_quota.P0` | `%s` |\n" % value)
                self.assertEqual(set(), self.override_checks(receipts))

    def test_share_domain_rejects_out_of_range_and_non_numeric(self):
        for value in ("120%", "-5", "a lot"):
            with self.subTest(value=value):
                _, receipts = self.run_check(
                    "| `priority_quota.P1` | `%s` |\n" % value)
                self.assertIn("override-value-domain",
                              self.override_checks(receipts))

    def test_a_share_of_the_whole_corpus_is_rejected_on_both_quota_items(self):
        """The named degenerate value: in 0..100, but it empties `P2`.

        Its owner keeps a remainder class outside the quota and demotes what
        exceeds the quota, so a share of the whole corpus states an empty
        class and leaves nothing able to exceed it.
        """
        for item in ("priority_quota.P0", "priority_quota.P1"):
            for value in ("100", "100%", "100.0"):
                with self.subTest(item=item, value=value):
                    _, receipts = self.run_check(
                        "| `%s` | `%s` |\n" % (item, value))
                    self.assertIn("override-value-domain",
                                  self.override_checks(receipts))

    def test_the_registry_names_a_domain_the_checker_implements(self):
        """Registry and checker are updated together, per the unknown path."""
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import check_profile
        import kblib
        registry = kblib.load_yaml_file(EXECUTION_DEFAULTS)
        named = {entry["item"]: entry.get("value_domain")
                 for entry in registry["overridable"]}
        self.assertEqual("percent-share-under-100", named["priority_quota.P0"])
        self.assertEqual("percent-share-under-100", named["priority_quota.P1"])
        for item, domain in named.items():
            if domain is not None:
                self.assertIn(domain, check_profile.VALUE_DOMAINS, item)

    def test_item_without_a_registered_domain_is_left_to_its_owner(self):
        _, receipts = self.run_check("| `batch_size.S` | `whatever` |\n")
        self.assertEqual(set(), self.override_checks(receipts))

    def test_unimplemented_domain_name_is_reported_not_ignored(self):
        registry = (
            "schema_version: 1\n"
            "overridable:\n"
            "  - item: \"concurrency_cap\"\n"
            "    owner: \"kernel/K13 Task Runtime and Execution Control/"
            "10 Batch Admission Transitions and Serial Integration.md\"\n"
            "    value_domain: \"prime-number\"\n"
            "constitutional: []\n"
        )
        _, receipts = self.run_check("| `concurrency_cap` | `5` |\n",
                                     execution_defaults=registry)
        self.assertIn("override-value-domain-unknown",
                      self.override_checks(receipts))

    def test_domain_failure_names_the_owner_module(self):
        _, receipts = self.run_check("| `priority_quota.P0` | `120%` |\n")
        details = [r["details"] for r in receipts
                   if r["check"] == "override-value-domain"]
        self.assertEqual(1, len(details), receipts)
        self.assertIn("07 Effort Tiering and Priority Quota.md", details[0])

    def test_empty_and_redundant_rows_keep_their_own_checks(self):
        _, receipts = self.run_check("| `concurrency_cap` |  |\n")
        self.assertIn("override-choice-empty", self.override_checks(receipts))
        _, receipts = self.run_check(
            "| `concurrency_cap` | `use-kernel-default` |\n")
        self.assertIn("override-redundant-default",
                      self.override_checks(receipts))


class ShippedRegistryTests(unittest.TestCase):
    """The two registries must stay split the way the licensing record says."""

    def test_placeholder_registry_no_longer_carries_the_rule_blocks(self):
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import kblib
        placeholders = kblib.load_yaml_file(PLACEHOLDER_DEFAULTS)
        self.assertNotIn("overridable", placeholders)
        self.assertNotIn("constitutional", placeholders)
        self.assertIn("reserved_profile_ids", placeholders)
        self.assertIn("unfilled_sentinel", placeholders)

    def test_kernel_registry_carries_both_closed_sets_with_owners(self):
        sys.path.insert(0, str(REPOSITORY / "Tools"))
        import kblib
        registry = kblib.load_yaml_file(EXECUTION_DEFAULTS)
        items = [entry["item"] for entry in registry["overridable"]]
        self.assertEqual([
            "concurrency_cap",
            "batch_size.S", "batch_size.M", "batch_size.L",
            "priority_quota.P0", "priority_quota.P1",
            "maintenance.unselected_rounds_before_log_only",
            "maintenance.incoming_retarget_divisor",
        ], items)
        self.assertEqual(
            ["substantive_review.round_cap", "terminal_audit.round_cap"],
            [entry["item"] for entry in registry["constitutional"]])
        for entry in registry["overridable"] + registry["constitutional"]:
            self.assertTrue(str(entry["owner"]).startswith("kernel/"), entry)
            self.assertTrue(
                (REPOSITORY / entry["owner"]).is_file(), entry["owner"])


if __name__ == "__main__":
    unittest.main()
