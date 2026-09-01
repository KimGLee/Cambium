"""Shared current-contract Corpus Planning fixture."""

import atexit
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = Path(__file__).resolve().parents[1]
TOOLS = TESTS.parent
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"

import Tools.execution.planning.check_corpus_plan as check_corpus_plan
import Tools.platform.common.kblib as kblib
from Tools.tests.support.initial_task_plan_fixture import (
    install_initial_task_plan_fixture,
)
from Tools.tests.support.profile_fixture import (
    install_current_adoption_fixture,
    install_loadable_profile,
)
from Tools.tests.fixtures.contract.corpus_plan_objects import (
    CONFIGURED_SLOT,
    GAPS,
    GLOBAL_MAP,
    INACTIVE_SLOT,
    MANIFEST,
    MATRIX,
    ROLES,
    SCOPE,
)


_TEMPLATE_HOLDER = None
_TEMPLATE_ROOT = None


class CorpusPlanFixture(unittest.TestCase):
    """Validated current Corpus Planning checkpoint cloned per mutation.

    The expensive Profile/runtime construction is one Integration checkpoint
    producer for the class, not an implicit lifecycle replay in every test.
    Individual tests still receive private bytes because almost every case
    deliberately corrupts one contract input.
    """

    SCENARIO_GENERATION = "once-per-process"
    PER_METHOD_MATERIALIZATION = "private-copy"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        global _TEMPLATE_HOLDER, _TEMPLATE_ROOT
        if _TEMPLATE_ROOT is None:
            _TEMPLATE_HOLDER = tempfile.TemporaryDirectory()
            atexit.register(_TEMPLATE_HOLDER.cleanup)
            _TEMPLATE_ROOT = Path(_TEMPLATE_HOLDER.name) / "repo"
            cls._build_template(_TEMPLATE_ROOT)
        cls._template_root = _TEMPLATE_ROOT

    @staticmethod
    def _build_template(root):
        shutil.copytree(FIXTURE, root)
        profile = install_loadable_profile(root)
        manifest = profile / "profile.md"
        manifest.write_text(
            manifest.read_text(encoding="utf-8")
            .replace("- `Profile Scope`: `slots.md`",
                     "- `Profile Scope`: `scope-and-architecture.md`")
            .replace("- `Role Registry`: `slots.md`",
                     "- `Role Registry`: `roles.md`"),
            encoding="utf-8")
        (profile / "scope-and-architecture.md").write_text(
            SCOPE, encoding="utf-8")
        (profile / "roles.md").write_text(ROLES, encoding="utf-8")
        (profile / "corpus-planning.yaml").write_text(
            CONFIGURED_SLOT, encoding="utf-8")
        planning = root / "planning"
        planning.mkdir()
        (planning / "global-map.yaml").write_text(GLOBAL_MAP, encoding="utf-8")
        (planning / "capability-matrix.yaml").write_text(
            MATRIX, encoding="utf-8")
        (planning / "gap-register.yaml").write_text(GAPS, encoding="utf-8")
        # The Profile bytes above are the intended current semantics, not an
        # after-the-fact mutation of the synthetic Profile.  Rebuild the
        # current adoption and Task Plan bindings once in the checkpoint
        # producer so consumers never run against a stale Profile snapshot.
        install_current_adoption_fixture(root, profile, replace_current=True)
        install_initial_task_plan_fixture(root)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(self._template_root, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def profile(self):
        return self.root / "profiles/test-profile"

    @property
    def slot(self):
        return self.profile / "corpus-planning.yaml"

    @property
    def scope(self):
        return self.profile / "scope-and-architecture.md"

    @property
    def global_map(self):
        return self.root / "planning/global-map.yaml"

    @property
    def matrix(self):
        return self.root / "planning/capability-matrix.yaml"

    @property
    def gaps(self):
        return self.root / "planning/gap-register.yaml"

    def validate(self, profile=None):
        return check_corpus_plan.validate_corpus_plan(
            self.root, profile=profile)

    def assert_error(self, result, fragment):
        messages = [error["details"] for error in result["errors"]]
        self.assertTrue(any(fragment in message for message in messages),
                        messages)

    def replace(self, path, old, new):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def load_yaml(self, path):
        return kblib.load_yaml_file(path)

    def write_yaml(self, path, value):
        path.write_text(kblib.canonical_yaml(value), encoding="utf-8")

    def refresh_profile_authority(self):
        """Confirm changed Profile bytes and rebind the current Task Plan.

        Only tests whose subject is a new, valid Profile choice call this.
        Negative mutation tests intentionally leave the prior authority in
        place and prove the current runtime refuses the unconfirmed bytes.
        """
        install_current_adoption_fixture(
            self.root, self.profile, replace_current=True)
        install_initial_task_plan_fixture(self.root)

    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "check_corpus_plan.py"),
             str(self.root), *args],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )


__all__ = [
    "CONFIGURED_SLOT", "CorpusPlanFixture", "GAPS", "GLOBAL_MAP",
    "INACTIVE_SLOT", "MANIFEST", "MATRIX", "ROLES", "SCOPE",
]
