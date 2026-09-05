"""Small current-contract fixtures for the upstream component boundary.

The synthetic snapshot deliberately derives the immutable component roots and
files from the production owner.  It is an input to the evaluator, not a
second manifest, and represents only the current contract.
"""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import subprocess
from unittest import mock

import Tools.platform.distribution.upstream_component_boundary as boundary
from Tools.governance.profile import profile_codec


SYNTHETIC_REVISION = "a" * 40
BOUNDARY_TEXT = """schema_version: 1
distribution_only:
  - path: Tools/tests/
    reason: "distribution tests do not ship to an adopter"
"""


def current_component_source():
    """Return one minimal snapshot shaped by the current production owner."""
    source = {
        root + "/owner.md": (root + " owner\n").encode("utf-8")
        for root in boundary.IMMUTABLE_DIRECTORY_ROOTS
    }
    source.update({
        boundary.DISTRIBUTION_BOUNDARY_PATH:
            BOUNDARY_TEXT.encode("utf-8"),
        "profiles/README.md": b"shared Profile guide\n",
        "Tools/tests/distribution_test.py": b"VALUE = 'distribution'\n",
    })
    return source


def write_component_tree(root, source=None, *, omit_distribution_only=True):
    """Materialize a tiny adopter tree without copying a repository."""
    source = current_component_source() if source is None else source
    root = Path(root)
    for relative, data in source.items():
        if omit_distribution_only and relative.startswith("Tools/tests/"):
            continue
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    selected = root / "profiles/adopter/profile.toml"
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_bytes(profile_codec.dumps_profile({
        "schema_version": 1, "profile_id": "adopter",
    }))


class SyntheticUpstreamSnapshot:
    """Patch only the Git snapshot reader; keep the real evaluator and FS."""

    def __init__(self, source=None):
        self.source = current_component_source() if source is None else source
        self.entries = tuple(sorted(
            (path, hashlib.sha1(path.encode("utf-8") + b"\0" + data).hexdigest())
            for path, data in self.source.items()
        ))
        self.blobs = {
            oid: self.source[path]
            for path, oid in self.entries
        }

    @contextmanager
    def installed(self):
        with mock.patch.object(
                boundary.upstream_identity, "resolve_revision",
                return_value=SYNTHETIC_REVISION), mock.patch.object(
                    boundary, "_tree_entries", return_value=self.entries), \
                mock.patch.object(
                    boundary, "_blob_bytes", return_value=self.blobs):
            yield

    def evaluate(self, adopter_root):
        with self.installed():
            return boundary.evaluate(
                adopter_root, adopter_root, SYNTHETIC_REVISION)


def build_real_git_pair(base):
    """Build the one small real-Git checkpoint used by the CLI integration."""
    base = Path(base)
    upstream = base / "upstream"
    adopter = base / "adopter"
    upstream.mkdir()
    adopter.mkdir()
    source = current_component_source()
    write_component_tree(upstream, source, omit_distribution_only=False)

    def git(*arguments):
        completed = subprocess.run(
            ["git", "-C", str(upstream), *arguments],
            text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stdout + completed.stderr)
        return completed.stdout.strip()

    git("init", "-q")
    git("config", "user.email", "tests@example.invalid")
    git("config", "user.name", "Cambium tests")
    git("add", ".")
    git("commit", "-q", "-m", "current component snapshot")
    revision = git("rev-parse", "HEAD")
    write_component_tree(adopter, source)
    return upstream, adopter, revision
