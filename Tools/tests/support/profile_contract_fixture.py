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


def _h2_sections(text):
    """Return raw H2 sections by title for fixture projection only."""
    lines = text.splitlines(keepends=True)
    starts = []
    for index, line in enumerate(lines):
        heading = kblib.markdown_atx_heading(line.rstrip("\r\n"))
        if heading is not None and heading[0] == 2:
            starts.append((index, heading[1]))
    sections = {}
    for position, (start, title) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) \
            else len(lines)
        sections[title] = "".join(lines[start:end])
    return sections


def materialize_current_profile_forms(profile, source_slots=None):
    """Project compact fixture answers into the canonical Profile forms."""
    profile = Path(profile)
    source_slots = Path(source_slots or profile / "slots.md")
    source_sections = _h2_sections(source_slots.read_text(encoding="utf-8"))
    interface = profile_contract.load_profile_interface(REPOSITORY)
    _manifest_form, forms = profile_contract.profile_interface_forms(interface)
    for form in forms.values():
        if not form.path.endswith(".md"):
            continue
        template = REPOSITORY / "profiles/_template" / form.path
        text = template.read_text(encoding="utf-8").replace(
            "TODO(profile)", "fixture-value")
        template_sections = _h2_sections(text)
        for title, replacement in source_sections.items():
            current = template_sections.get(title)
            if current is not None:
                text = text.replace(current, replacement, 1)
        target = profile / form.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


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
                kblib.STRUCTURE_REGISTRY_CONTRACT_PATH,
                kblib.METADATA_PROFILE_CONTRACT_PATH,
                profile_contract.vocabulary_contract.
                VOCABULARY_EXTENSIONS_CONTRACT_PATH,
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
        self._materialize_form_files()

    def load(self, sentinel="TODO(profile)"):
        self._materialize_form_files()
        return profile_contract.load_profile_contract(
            self.root, self.manifest, sentinel=sentinel)

    def _materialize_form_files(self):
        """Project the composite unit-test source into current slot forms.

        ``slots.md`` remains a compact authoring helper for tests that mutate
        one typed table.  It is not a bound Profile slot.  Each load projects
        those mutated sections into the canonical per-slot form, so the test
        fixture exercises current production structure without making every
        test rebuild fourteen files by hand.
        """
        materialize_current_profile_forms(self.profile, self.slots)

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

    def expression_artifact_row(
            self, *, artifact_id="test-expression-guide",
            artifact_type="cheat-sheet", label="Expression Guide",
            entry_point="Expression/Guide.md",
            dependency_map="Expression/Overview.md", binding_fields="None",
            revalidation="Revalidate when a bound canonical owner changes.",
            contract_reference=(
                "profiles/test-profile/slots.md#Synthetic Predicate"),
            readiness="None"):
        return (
            "| `%s` | `%s` | %s | `%s` | `%s` | `%s` | %s | `%s` | `%s` |\n"
            % (artifact_id, artifact_type, label, entry_point,
               dependency_map, binding_fields, revalidation,
               contract_reference, readiness))

    def configure_expression_artifacts(self, rows):
        """Replace the fixture's typed Registered Artifacts rows."""
        text = self.slots.read_text(encoding="utf-8")
        start = text.index("## Registered Artifacts")
        end = text.index("\n## ", start + 4)
        section = text[start:end]
        registration = "Configured" if rows else "None"
        section = section.replace(
            "- Registration: None", "- Registration: %s" % registration, 1)
        section = section.replace(
            "- Registration: Configured",
            "- Registration: %s" % registration, 1)
        separator = "|" + "---|" * len(
            profile_contract.REGISTERED_ARTIFACT_HEADER) + "\n"
        section = section.replace(separator, separator + "".join(rows), 1)
        self.slots.write_text(
            text[:start] + section + text[end:], encoding="utf-8")


__all__ = [
    "CurrentProfileContractFixture",
    "materialize_current_profile_forms",
]
