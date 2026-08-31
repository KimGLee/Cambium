"""Current Profile linker fixture derived from machine-owned sources."""

from pathlib import Path
import shutil
import tempfile

import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.governance.profile.profile_contract as profile_contract
import Tools.platform.common.kblib as kblib
from Tools.tests.support.canonical_registry_fixture import (
    install_isolated_tool_registry_bundle,
)


REPOSITORY = Path(__file__).resolve().parents[3]
SYNTHETIC_PROFILE = REPOSITORY / "Tools/tests/fixtures/synthetic_profile"


class CurrentProfileContractFixture:
    """Isolate one current Profile without adoption or runtime lifecycle."""

    def __init__(self, owner):
        self.temporary = tempfile.TemporaryDirectory()
        owner.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "repo"
        self.root.mkdir()
        install_isolated_tool_registry_bundle(self.root)
        self.profile = self.root / "profiles/test-profile"
        for source in sorted(SYNTHETIC_PROFILE.rglob("*")):
            relative = source.relative_to(SYNTHETIC_PROFILE)
            target = self.profile / relative
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        for relative in (
                profile_contract.SCAN_CAPABILITY_PATH,
                "Tools/knowledge/content/check_residual_content.py"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPOSITORY / relative, target)
        self.manifest = self.profile / "profile.md"
        self.slots = self.profile / "slots.md"
        self.vocabulary = self.profile / "vocabulary-extensions.yaml"
        self.metadata = self.profile / "metadata-contract.yaml"
        self.scan_config = self.profile / "scan-configs/residual-scan.yaml"
        self.operation_capabilities = (
            self.root / "Tools/operation-capabilities.yaml")

    def load(self, sentinel="TODO(profile)"):
        return profile_contract.load_profile_contract(
            self.root, self.manifest, sentinel=sentinel)

    def checks(self, contract=None):
        contract = contract or self.load()
        return {diagnostic.check for diagnostic in contract.diagnostics}

    def install_profile_load_inputs(self):
        """Install the current checker's canonical input closure.

        The fixture compiles the metadata projection from the exact copied
        authority and implementation bytes.  It never borrows a possibly
        stale generated artifact from the source checkout.
        """
        for relative in (
                "Tools/schemas/execution_defaults.template.yaml",
                "Tools/operation-capabilities.yaml",
                "Tools/execution/task_runtime/runtime_paths.py"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPOSITORY / relative, target)
        capabilities = kblib.load_yaml_file(
            REPOSITORY / "Tools/operation-capabilities.yaml")
        for relative in metadata_execution_contract.\
                capability_implementation_paths(capabilities):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPOSITORY / relative, target)
        compiled = metadata_execution_contract.\
            compile_metadata_execution_contract(self.root)
        target = self.root / metadata_execution_contract.\
            DEFAULT_COMPILED_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        kblib.atomic_write_text(
            target, compiled.canonical_bytes.decode("utf-8"))
        return compiled

    @staticmethod
    def replace(path, old, new):
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise AssertionError("fixture anchor is absent: %r" % old)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def enable_gate_contract(self, *, field_id="expression_status",
                             values=("pending", "ready"),
                             role="Expression Status Axis"):
        role_line = "    role: %s\n" % role if role is not None else ""
        self.vocabulary.write_text(
            "schema_version: 1\n"
            "frontmatter_extensions:\n"
            "  fields: []\n"
            "fields:\n"
            "  %s:\n%s"
            "    values:\n%s"
            "volatility_defaults:\n"
            "  general: slow\n" % (
                field_id, role_line,
                "".join("      - %s\n" % value for value in values)),
            encoding="utf-8")
        self.metadata.write_text(
            "schema_version: 1\n"
            "applicability:\n"
            "  state: configured\n"
            "applicability_differences: []\n"
            "extension_fields:\n"
            "  - field: %s\n"
            "    mode: optional\n"
            "    shape: nonempty-string\n"
            "    owner: profiles/test-profile/slots.md\n"
            "relationship_extensions: []\n"
            "section_roles: []\n" % field_id,
            encoding="utf-8")
        self.slots.write_text(
            self.slots.read_text(encoding="utf-8") +
            "\n## Process Roles\n\n"
            "| Kernel role | Bound actor or system ID/name |\n"
            "|---|---|\n"
            "| `proposer` | Agent |\n"
            "| `gatekeeper` | Maintainer |\n"
            "| `executor` | Agent |\n"
            "| `stopper` | Maintainer |\n\n"
            "## Knowledge Host\n\n"
            "| Kernel role | Binding |\n"
            "|---|---|\n"
            "| `knowledge-host` | Markdown tree |\n"
            "| `knowledge-host UI` | Headless |\n\n"
            "## Extension Roles\n\n"
            "- Registration: None\n\n"
            "| Role ID | Bound actor or system ID/name | Responsibility |\n"
            "|---|---|---|\n",
            encoding="utf-8")
        custom_tool = self.root / "Tools/custom_profile_capability.py"
        custom_tool.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        self.operation_capabilities.write_text(
            "schema_version: 3\n"
            "capabilities:\n" + "".join(
                "  - capability_id: %s\n"
                "    kind: %s\n"
                "    capability_version: 1.0.0\n"
                "    implementation_owner: Tools/custom_profile_capability.py\n"
                "    writers: []\n"
                "    checkers: []\n"
                "    consumers: []\n"
                "    operations:%s\n" % (capability_id, kind, operations)
                for capability_id, kind, operations in (
                    ("project-page-state-v2", "writer",
                     "\n      - operation: "
                     "profile-extension-enum-owner-projection-v1"),
                    ("typed-metadata-transition-v1", "consumer",
                     "\n      - operation: typed-field-metadata-transition"),
                    ("manual-attestation-v1", "producer", " []"),
                    ("registered-scan-v1", "producer", " []"),
                    ("manual-gate-attestation-v1", "receipt-schema", " []"),
                    ("deterministic-gate-result-v1", "receipt-schema", " []"),
                )),
            encoding="utf-8")

    def gate_row(self, *, gate_id="P:test-profile:expression-ready",
                 owner="profiles/test-profile/slots.md#Synthetic Predicate",
                 transition="expression-ready", role="stopper",
                 applicability="Expression is ready.",
                 field="expression_status", completions="ready",
                 judgment="test-profile-foundation-depth",
                 producer_kind="manual-attestation",
                 producer_capability="manual-attestation-v1",
                 receipt_schema="manual-gate-attestation-v1",
                 consumer_capability="typed-metadata-transition-v1"):
        return (
            "| `%s` | `%s` | `%s` | `%s` | %s | `%s` | `%s` | `%s` | "
            "`%s` | `%s` | `%s` | `%s` |\n" % (
                gate_id, owner, transition, role, applicability, field,
                completions, judgment, producer_kind, producer_capability,
                receipt_schema, consumer_capability))

    def configure_gate(self, **overrides):
        text = self.slots.read_text(encoding="utf-8")
        start = text.index("## Extension Gates")
        end = text.index("\n## ", start + 4)
        section = text[start:end]
        section = section.replace(
            "- Registration: None", "- Registration: Configured", 1)
        separator = "|" + "---|" * len(
            profile_contract.EXTENSION_GATE_HEADER) + "\n"
        section = section.replace(
            separator, separator + self.gate_row(**overrides), 1)
        self.slots.write_text(
            text[:start] + section + text[end:], encoding="utf-8")

    def configure_extension_dimensions(self, rows):
        """Replace the synthetic Profile's typed extension-dimension rows."""
        text = self.slots.read_text(encoding="utf-8")
        start = text.index("## Extension Dimensions")
        end = text.index("\n## ", start + 4)
        section = text[start:end]
        registration = "Configured" if rows else "None"
        section = section.replace(
            "- Registration: None", "- Registration: %s" % registration, 1)
        section = section.replace(
            "- Registration: Configured",
            "- Registration: %s" % registration, 1)
        separator = "|---|---|---|"
        boundary = section.index(separator) + len(separator)
        body = "".join(
            "\n| `%s` | `%s` | %s |" % row for row in rows)
        section = section[:boundary] + body + "\n"
        self.slots.write_text(
            text[:start] + section + text[end:], encoding="utf-8")


__all__ = ["CurrentProfileContractFixture"]
