"""Minimal current-template checkpoint for scaffold_profile tests."""

import contextlib
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import Tools.governance.profile.scaffold_profile as scaffold_profile


REPOSITORY = Path(__file__).resolve().parents[3]
TEMPLATE = REPOSITORY / "profiles/_template"
MANIFEST = REPOSITORY / "profiles/template-files.yaml"
SCRIPT = REPOSITORY / "Tools/scaffold_profile.py"


class ScaffoldProfileFixture:
    """One private repository containing only the current scaffold inputs."""

    def __init__(self, owner, profile_id="candidate"):
        self.temporary = tempfile.TemporaryDirectory()
        owner.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "repo"
        self.template = self.root / "profiles/_template"
        self.template.mkdir(parents=True)
        target_manifest = self.root / "profiles/template-files.yaml"
        shutil.copy2(MANIFEST, target_manifest)
        for source in sorted(TEMPLATE.rglob("*")):
            relative = source.relative_to(TEMPLATE)
            target = self.template / relative
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        self.profile_id = profile_id
        self.destination = self.root / "profiles" / profile_id
        self.outside_marker = self.root / "outside-scaffold.marker"
        self.outside_marker.write_text("unchanged\n", encoding="utf-8")

    @staticmethod
    def tree_state(root):
        state = {}
        for path in sorted(Path(root).rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                state[relative] = "symlink:%s" % path.readlink()
            elif path.is_dir():
                state[relative] = "dir"
            else:
                state[relative] = hashlib.sha256(
                    path.read_bytes()).hexdigest()
        return state

    def run(self, *extra, profile_id=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = scaffold_profile.main([
                str(self.root),
                "--profile-id=%s" % (profile_id or self.profile_id),
                *extra,
            ])
        return code, output.getvalue()

    def run_cli(self, *extra):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(self.root),
             "--profile-id", self.profile_id, *extra],
            text=True, capture_output=True, check=False)

    def candidate_files(self):
        return sorted(
            path.relative_to(self.destination).as_posix()
            for path in self.destination.rglob("*") if path.is_file())

    def staging_paths(self):
        return sorted(
            path for path in (self.root / "profiles").iterdir()
            if path.name.startswith(".scaffold-"))


__all__ = ["ScaffoldProfileFixture"]
