"""`--json` must not change any tool's verdict.

The plan's layer boundary (v4 §1.5, check 2) states the one acceptance
condition for reshaping tool output: the same input must still produce
the same adjudication. The `--json` work satisfied it by argument --
"without --json nothing changes" -- and by the suite staying green,
which exercises the flagless path only. Neither shows that the *flagged*
path decides the same thing, and that is the half a caller actually uses.

This test compares the two paths directly. The verdict is the exit code:
K00/12 gives it a closed three-value meaning (0 passed, 1 failed or the
evidence is unreliable, 2 HOLD), and no consumer may map 2 onto either
of the others. If a flag ever shifts a tool between those, the contract
this whole interface line rests on is broken.

The tool set is derived from the compiled contract rather than listed
here, so a tool that gains `--json` later is covered without anyone
remembering to add it.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
PROJECTION = TOOLS / "compiled" / "mcp-tools.json"
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"

sys.path.insert(0, str(TOOLS / "tests"))
from profile_fixture import install_loadable_profile  # noqa: E402

# Root-shaped required parameters, and the flag each tool spells them
# with. A tool whose required set is not a subset of these needs inputs
# this fixture does not model, so it is out of scope here.
ROOT_PARAMS = {
    "root": None,                       # positional
    "vault_root": "--vault-root",
    "profile_dir": None,                # positional
}


def read_only_verifiers():
    """Tools that take only a root, accept `--json`, and write nothing."""
    tools = json.loads(PROJECTION.read_text(encoding="utf-8"))
    tools = tools.get("tools", tools)
    selected = []
    for tool in tools:
        schema = tool.get("inputSchema") or {}
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        if "json" not in properties or "apply" in properties:
            continue
        if not required or not required <= set(ROOT_PARAMS):
            continue
        selected.append((tool["name"], sorted(required)))
    return selected


class JsonFlagVerdictParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "repo"
        shutil.copytree(FIXTURE, cls.root)
        install_loadable_profile(cls.root)
        cls.verifiers = read_only_verifiers()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_tool(self, name, required, flagged):
        argv = [sys.executable, str(TOOLS / ("%s.py" % name))]
        for parameter in required:
            flag = ROOT_PARAMS[parameter]
            target = (str(self.root / "profiles" / "test-profile")
                      if parameter == "profile_dir" else str(self.root))
            argv.extend([flag, target] if flag else [target])
        if flagged:
            argv.append("--json")
        completed = subprocess.run(
            argv, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return completed.returncode

    def test_the_set_under_test_is_not_empty(self):
        # A contract change that dropped every match would make the
        # parity assertion below vacuously true.
        self.assertGreaterEqual(len(self.verifiers), 8)

    def test_the_flag_never_changes_the_verdict(self):
        for name, required in self.verifiers:
            with self.subTest(tool=name):
                bare = self.run_tool(name, required, flagged=False)
                flagged = self.run_tool(name, required, flagged=True)

                self.assertEqual(
                    bare, flagged,
                    "%s decided %d without --json and %d with it" %
                    (name, bare, flagged))

    def test_a_verdict_stays_inside_the_kernel_s_three_values(self):
        for name, required in self.verifiers:
            with self.subTest(tool=name):
                self.assertIn(self.run_tool(name, required, flagged=True),
                              (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
