"""Minimal current Profile and path set for Structure Registry tests."""

import contextlib
import copy
import io
from pathlib import Path
import subprocess
import sys
import tempfile

from Tools.knowledge.structure import check_structure
from Tools.platform.common import kblib
from Tools.tests.support.profile_fixture import install_loadable_profile


REPOSITORY = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY / "Tools/check_structure.py"


def not_applicable_role(reason="Fixture role is not used."):
    return {"mode": "not-applicable", "reason": reason}


def domain_unit():
    return {
        "id": "U-DOMAIN",
        "kind": "domain",
        "parent": None,
        "root": "Domain",
        "entry": {
            "path": "Domain/Domain Overview.md",
            "expected_type": "overview",
        },
        "global_map_entry": None,
        "roles": {
            "sequence": {
                "mode": "embedded",
                "path": "Domain/Domain Overview.md",
                "heading": "Reading Order",
            },
            "coverage": {
                "mode": "derived",
                "generator_capability":
                    "structure-coverage-projection-v1",
                "inputs_owner": "Domain/Domain Overview.md",
                "path": "Domain/Domain Overview.md",
                "heading": "Coverage Reader View",
            },
            "quick_reference": not_applicable_role(),
            "expression": not_applicable_role(),
        },
    }


def module_unit():
    return {
        "id": "U-SUB",
        "kind": "module",
        "parent": "U-DOMAIN",
        "root": "Domain/Sub",
        "entry": {
            "path": "Domain/Sub/Sub Entry.md",
            "expected_type": "system-design",
        },
        "global_map_entry": None,
        "roles": {
            role: not_applicable_role() for role in kblib.STRUCTURE_UNIT_ROLES
        },
    }


def cases_layer():
    return {
        "layer_id": "L-CASES",
        "role": "cases",
        "root": "Cases",
        "entry": {
            "path": "Cases/Cases Overview.md",
            "expected_type": "overview",
        },
        "global_map_entry": None,
        "layout": "grouped",
        "taxonomy": {
            "axis": "evidence-form",
            "page_field": "case_class",
            "classes": [{
                "class": "reported-system",
                "directory": "Cases/Reported",
            }],
        },
        "coverage": not_applicable_role(),
        "bindings": {
            "evidence_binding_owner": "Domain/Domain Overview.md",
        },
    }


def synthesis_layer():
    return {
        "layer_id": "L-SYNTHESIS",
        "role": "synthesis",
        "root": "Synthesis",
        "entry": {
            "path": "Synthesis/Synthesis Overview.md",
            "expected_type": "overview",
        },
        "global_map_entry": None,
        "layout": "flat",
        "taxonomy": None,
        "coverage": not_applicable_role(),
        "bindings": {
            "question_identity_field": "claim_scope",
            "promotion_policy_ref": "Domain/Domain Overview.md",
        },
    }


def sources_layer():
    layer = synthesis_layer()
    layer.update({
        "layer_id": "L-SOURCES",
        "role": "sources",
        "root": "Sources",
        "entry": {
            "path": "Sources/Sources Overview.md",
            "expected_type": "overview",
        },
        "bindings": {
            "authority_taxonomy_ref": "Domain/Domain Overview.md",
            "intake_policy_ref": "Domain/Domain Overview.md",
            "freshness_policy_ref": "Domain/Domain Overview.md",
            "index_mode": "derived",
        },
    })
    return layer


def configured_registry(*, units=None, support_layers=None):
    return {
        "schema_version": 2,
        "applicability": {"state": "configured", "reason": None},
        "units": copy.deepcopy(
            units if units is not None else [domain_unit(), module_unit()]),
        "support_layers": copy.deepcopy(
            support_layers if support_layers is not None
            else [cases_layer(), synthesis_layer()]),
    }


def not_applicable_registry():
    return {
        "schema_version": 2,
        "applicability": {
            "state": "not-applicable",
            "reason": "Fixture corpus has no registered structure.",
        },
        "units": [],
        "support_layers": [],
    }


class StructureRegistryFixture:
    """One current Profile with a mutable, read-only validation surface."""

    PROFILE = "profiles/test-profile"
    REGISTRY = PROFILE + "/structure-registry.yaml"

    def __init__(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name).resolve() / "repository"
        self.profile = install_loadable_profile(self.root)
        manifest = self.profile / "profile.md"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "- `Profile Scope`: `slots.md`",
                "- `Profile Scope`: `scope.md`"),
            encoding="utf-8")
        (self.profile / "scope.md").write_text(
            "# Scope\n\n## Logical Architecture\n\n"
            "| Stable Layer ID | Repository-relative directories | "
            "Single layer responsibility |\n"
            "|---|---|---|\n"
            "| `L-DOMAIN` | `Domain` | Own the domain. |\n"
            "| `L-CASES` | `Cases` | Own cases. |\n"
            "| `L-SYNTHESIS` | `Synthesis` | Own synthesis. |\n",
            encoding="utf-8")
        self._write("Domain/Domain Overview.md", """---
type: overview
---
# Domain Overview

## Reading Order

Read in order.

## Coverage Reader View

The generated view belongs here.
""")
        self._write("Domain/Sub/Sub Entry.md", """---
type: system-design
---
# Sub Entry
""")
        self._write("Cases/Cases Overview.md", """---
type: overview
---
# Cases Overview
""")
        self._write("Cases/Reported/Case A.md", """---
type: case-study
case_class: reported-system
---
# Case A
""")
        self._write("Synthesis/Synthesis Overview.md", """---
type: overview
---
# Synthesis Overview
""")
        self._write("Synthesis/Question One.md", """---
type: research-synthesis
---
# Question One
""")
        self.set_registry(configured_registry())

    def cleanup(self):
        self._temporary.cleanup()

    def _write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def set_registry(self, document):
        self._write(self.REGISTRY, kblib.canonical_yaml(document))

    @contextlib.contextmanager
    def override(self, files):
        originals = {}
        for relative, content in files.items():
            path = self.root / relative
            originals[relative] = path.read_bytes() if path.is_file() else None
            if content is None:
                if path.exists():
                    path.unlink()
            elif isinstance(content, bytes):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            else:
                self._write(relative, content)
        try:
            yield
        finally:
            for relative, content in originals.items():
                path = self.root / relative
                if content is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)

    def run_in_process(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = check_structure.main([
                str(self.root), "--profile", self.PROFILE])
        return code, stdout.getvalue(), stderr.getvalue()

    def run_cli(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.root),
             "--profile", self.PROFILE],
            cwd=str(REPOSITORY), text=True, capture_output=True, check=False)


__all__ = [
    "StructureRegistryFixture", "cases_layer", "configured_registry",
    "domain_unit", "module_unit", "not_applicable_registry",
    "not_applicable_role", "sources_layer", "synthesis_layer",
]
