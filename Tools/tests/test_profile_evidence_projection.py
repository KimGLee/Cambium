"""Single-owner checks for the durable Profile-load evidence projection."""

import ast
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import Tools.governance.profile.profile_contract as profile_contract  # noqa: E402


def _literal_string_collection(node):
    items = node.keys if isinstance(node, ast.Dict) else getattr(
        node, "elts", None)
    if items is None or not all(
            isinstance(item, ast.Constant) and isinstance(item.value, str)
            for item in items):
        return None
    return frozenset(item.value for item in items)


class ProfileLoadEvidenceProjectionTests(unittest.TestCase):
    def test_owner_exports_the_exact_fingerprint_subset(self):
        self.assertEqual(
            (
                "selected_profile_manifest",
                "profile_snapshot_sha256",
                "profile_contract_fingerprint",
                "profile_load_inputs_sha256",
            ),
            profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS,
        )
        self.assertEqual(
            profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS[1:],
            profile_contract.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS,
        )

    def test_consumers_do_not_redeclare_the_owner_collections(self):
        owner = Path(profile_contract.__file__).resolve()
        protected = {
            frozenset(profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS),
            frozenset(
                profile_contract.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS),
        }
        duplicates = []
        for path in sorted(TOOLS.rglob("*.py")):
            relative = path.relative_to(TOOLS)
            if "tests" in relative.parts or path.resolve() == owner:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                literal = _literal_string_collection(node)
                if literal in protected:
                    duplicates.append(
                        "%s:%d" % (relative.as_posix(), node.lineno))
        self.assertEqual([], duplicates)


if __name__ == "__main__":
    unittest.main()
