"""Ownership tests for the Profile Structure Registry gate.

The closed representation is owned by the current machine contract in
``kblib``. Tests derive required field sets and role modes from that owner;
they do not maintain a second schema. The gate-specific filesystem resolver
gets one current Profile checkpoint and one public CLI transport.

Repository component membership, distribution-only paths, and the unrelated
``check_repository_structure`` observation have separate owner suites and are
deliberately outside this file.
"""

import copy
from pathlib import Path
import unittest

from Tools.platform.common import kblib
from Tools.tests.support.structure_registry_fixture import (
    StructureRegistryFixture,
    cases_layer,
    configured_registry,
    domain_unit,
    module_unit,
    not_applicable_registry,
    not_applicable_role,
    sources_layer,
    synthesis_layer,
)


def validation_details(document):
    return "\n".join(
        details for _check, _target, details
        in kblib.validate_structure_registry_shape(document))


def role_for_mode(mode):
    if mode == "embedded":
        return {"mode": mode, "path": "Domain/Entry.md", "heading": "Order"}
    if mode == "standalone":
        return {"mode": mode, "path": "Domain/Reference.md"}
    if mode == "derived":
        return {
            "mode": mode,
            "generator_capability": "fixture-projection-v1",
            "inputs_owner": "Domain/Input.md",
        }
    return {"mode": mode, "reason": "Fixture role is not applicable."}


def layer_for_role(role):
    layer = synthesis_layer()
    layer.update({
        "layer_id": "L-%s" % role.upper(),
        "role": role,
        "root": role.title(),
        "entry": {
            "path": "%s/Overview.md" % role.title(),
            "expected_type": "overview",
        },
    })
    bindings = {}
    for field in kblib.STRUCTURE_LAYER_BINDING_FIELDS[role]:
        if field == "index_mode":
            bindings[field] = "derived"
        elif field == "readiness_projection":
            bindings[field] = not_applicable_role()
        else:
            bindings[field] = "fixture-owner"
    layer["bindings"] = bindings
    return layer


class StructureRegistryShapeContractTests(unittest.TestCase):
    """Contract: all closed sets come from the sole machine owner."""

    def assert_invalid(self, document, expected):
        details = validation_details(document)
        self.assertTrue(details, "mutation unexpectedly remained valid")
        self.assertIn(expected, details)

    def test_required_and_forbidden_fields_follow_machine_closed_sets(self):
        valid = configured_registry()
        self.assertEqual(validation_details(valid), "")
        self.assertEqual(validation_details(not_applicable_registry()), "")

        for field in sorted(kblib.STRUCTURE_REGISTRY_TOP_FIELDS):
            with self.subTest(mapping="registry", field=field):
                changed = copy.deepcopy(valid)
                changed.pop(field)
                self.assert_invalid(changed, field)

        for field in sorted(kblib.STRUCTURE_UNIT_FIELDS):
            with self.subTest(mapping="unit", field=field):
                changed = copy.deepcopy(valid)
                changed["units"][0].pop(field)
                self.assert_invalid(changed, field)

        for field in sorted(kblib.STRUCTURE_ENTRY_FIELDS):
            with self.subTest(mapping="entry", field=field):
                changed = copy.deepcopy(valid)
                changed["units"][0]["entry"].pop(field)
                self.assert_invalid(changed, field)

        for role in kblib.STRUCTURE_UNIT_ROLES:
            with self.subTest(mapping="roles", field=role):
                changed = copy.deepcopy(valid)
                changed["units"][0]["roles"].pop(role)
                self.assert_invalid(changed, role)

        for mode, (required, _optional) in \
                kblib.STRUCTURE_ROLE_MODE_FIELDS.items():
            base_role = role_for_mode(mode)
            changed = configured_registry(units=[domain_unit()],
                                          support_layers=[])
            changed["units"][0]["roles"]["sequence"] = base_role
            self.assertEqual(validation_details(changed), "")
            for field in sorted(required):
                with self.subTest(mapping="role", mode=mode, field=field):
                    missing = copy.deepcopy(changed)
                    missing["units"][0]["roles"]["sequence"].pop(field)
                    self.assertTrue(validation_details(missing))

        for field in sorted(kblib.STRUCTURE_LAYER_FIELDS):
            with self.subTest(mapping="support-layer", field=field):
                changed = configured_registry(
                    units=[domain_unit()], support_layers=[cases_layer()])
                changed["support_layers"][0].pop(field)
                self.assert_invalid(changed, field)

        taxonomy = configured_registry(
            units=[domain_unit()], support_layers=[cases_layer()])
        for field in sorted(kblib.STRUCTURE_TAXONOMY_FIELDS):
            with self.subTest(mapping="taxonomy", field=field):
                changed = copy.deepcopy(taxonomy)
                changed["support_layers"][0]["taxonomy"].pop(field)
                self.assert_invalid(changed, field)
        for field in sorted(kblib.STRUCTURE_TAXONOMY_CLASS_FIELDS):
            with self.subTest(mapping="taxonomy-class", field=field):
                changed = copy.deepcopy(taxonomy)
                changed["support_layers"][0]["taxonomy"]["classes"][0].pop(
                    field)
                self.assert_invalid(changed, field)

        for role in kblib.STRUCTURE_LAYER_ROLES:
            layer = layer_for_role(role)
            document = configured_registry(
                units=[domain_unit()], support_layers=[layer])
            self.assertEqual(validation_details(document), "")
            for field in sorted(kblib.STRUCTURE_LAYER_BINDING_FIELDS[role]):
                with self.subTest(mapping="bindings", role=role, field=field):
                    changed = copy.deepcopy(document)
                    changed["support_layers"][0]["bindings"].pop(field)
                    self.assert_invalid(changed, field)

        for mapping in ("registry", "unit", "role", "support-layer"):
            with self.subTest(forbidden=mapping):
                changed = copy.deepcopy(valid)
                if mapping == "registry":
                    target = changed
                elif mapping == "unit":
                    target = changed["units"][0]
                elif mapping == "role":
                    target = changed["units"][0]["roles"]["sequence"]
                else:
                    target = changed["support_layers"][0]
                target["fixture_unknown_field"] = True
                self.assert_invalid(changed, "fixture_unknown_field")

        configured_empty = configured_registry(units=[], support_layers=[])
        self.assert_invalid(configured_empty, "requires at least one unit")

    def test_identity_graph_and_stable_references_fail_closed(self):
        duplicate = configured_registry(
            units=[domain_unit(), domain_unit()], support_layers=[])
        unknown_parent = configured_registry(
            units=[domain_unit(), module_unit()], support_layers=[])
        unknown_parent["units"][1]["parent"] = "U-GHOST"
        first = module_unit()
        second = module_unit()
        first.update({"id": "U-FIRST", "parent": "U-SECOND"})
        second.update({"id": "U-SECOND", "parent": "U-FIRST"})
        cycle = configured_registry(
            units=[first, second], support_layers=[])
        capability_path = configured_registry(
            units=[domain_unit()], support_layers=[])
        capability_path["units"][0]["roles"]["coverage"][
            "generator_capability"] = "Tools/render_projection.py"
        runtime_path = configured_registry(
            units=[domain_unit()], support_layers=[])
        runtime_path["units"][0]["roles"]["coverage"][
            "inputs_owner"] = ".cambium/state/coverage_ledger.yaml"
        index_mode = configured_registry(
            units=[domain_unit()], support_layers=[sources_layer()])
        index_mode["support_layers"][0]["bindings"]["index_mode"] = "manual"

        for name, document, expected in (
                ("duplicate", duplicate, "duplicate unit id"),
                ("unknown-parent", unknown_parent,
                 "not a registered unit id"),
                ("cycle", cycle, "cycle"),
                ("capability-path", capability_path,
                 "stable Tool capability ID"),
                ("runtime-path", runtime_path, "stable object ID"),
                ("manual-index", index_mode, "must be derived or none")):
            with self.subTest(case=name):
                self.assert_invalid(document, expected)

        reference_document = configured_registry(
            units=[domain_unit()], support_layers=[])
        capability_id = reference_document["units"][0]["roles"][
            "coverage"]["generator_capability"]
        capabilities = {
            capability_id: {
                "kind": "projection",
                "input_owners": [],
            },
        }
        self.assertEqual(
            kblib.validate_structure_registry_references(
                reference_document, capabilities),
            [])
        unknown_capability = kblib.validate_structure_registry_references(
            reference_document, {})
        self.assertIn("is not registered", unknown_capability[0][2])

        runtime_owner = copy.deepcopy(reference_document)
        runtime_owner["units"][0]["roles"]["coverage"][
            "inputs_owner"] = "coverage-ledger"
        capabilities[capability_id]["input_owners"] = ["coverage-ledger"]
        self.assertEqual(
            kblib.validate_structure_registry_references(
                runtime_owner, capabilities),
            [])
        runtime_owner["units"][0]["roles"]["coverage"][
            "inputs_owner"] = "unknown-runtime-ledger"
        details = kblib.validate_structure_registry_references(
            runtime_owner, capabilities)
        self.assertIn("not a registered stable object ID", details[0][2])

        expression = layer_for_role("expression")
        expression["coverage"] = role_for_mode("derived")
        expression["bindings"]["readiness_projection"] = {
            "mode": "derived",
            "generator_capability": capability_id,
            "inputs_owner": "coverage-ledger",
        }
        records = list(kblib.structure_derived_role_records(
            configured_registry(
                units=[domain_unit()], support_layers=[expression]
            )
        ))
        identities = {
            (record["object_id"], record["role_name"])
            for record in records
        }
        self.assertIn(("U-DOMAIN", "coverage"), identities)
        self.assertIn(("L-EXPRESSION", "coverage"), identities)
        self.assertIn(
            ("L-EXPRESSION", "readiness_projection"), identities
        )


class StructureRegistryFilesystemIntegrationTests(unittest.TestCase):
    """Integration: one current Profile exercises the gate's path resolver."""

    def assert_run(self, fixture, expected_code, *needles):
        code, stdout, stderr = fixture.run_in_process()
        self.assertEqual(code, expected_code, stdout + stderr)
        for needle in needles:
            self.assertIn(needle, stdout)

    def test_current_registry_cli_and_resolution_failures_share_one_checkpoint(self):
        fixture = StructureRegistryFixture()
        self.addCleanup(fixture.cleanup)
        base = configured_registry()

        completed = fixture.run_cli()
        self.assertEqual(
            completed.returncode, 0,
            completed.stdout + completed.stderr)
        self.assertIn("units=2 modules=1 support_layers=2", completed.stdout)

        with fixture.override({
                fixture.REGISTRY:
                    kblib.canonical_yaml(not_applicable_registry())}):
            self.assert_run(fixture, 0, "state=not-applicable")

        heading = copy.deepcopy(base)
        heading["units"][0]["roles"]["sequence"]["heading"] = \
            "Missing Order"
        with fixture.override({
                fixture.REGISTRY: kblib.canonical_yaml(heading)}):
            self.assert_run(fixture, 1, "'Missing Order' not found")

        entry_type = copy.deepcopy(base)
        entry_type["units"][0]["entry"]["expected_type"] = "roadmap"
        with fixture.override({
                fixture.REGISTRY: kblib.canonical_yaml(entry_type)}):
            self.assert_run(fixture, 1, "expected 'roadmap'")

        scope = copy.deepcopy(base)
        scope["units"][0].update({
            "root": "Elsewhere",
            "entry": {
                "path": "Elsewhere/Overview.md",
                "expected_type": "overview",
            },
        })
        with fixture.override({
                fixture.REGISTRY: kblib.canonical_yaml(scope),
                "Elsewhere/Overview.md": "---\ntype: overview\n---\n# Elsewhere\n",
        }):
            self.assert_run(fixture, 1, "registered layer directories")

        parent = copy.deepcopy(base)
        parent["units"][1].update({
            "root": "Cases/Stray",
            "entry": {
                "path": "Cases/Stray/Entry.md",
                "expected_type": "system-design",
            },
        })
        with fixture.override({
                fixture.REGISTRY: kblib.canonical_yaml(parent),
                "Cases/Stray/Entry.md":
                    "---\ntype: system-design\n---\n# Stray\n",
        }):
            self.assert_run(fixture, 1, "strictly inside its parent's root")

        with fixture.override({
                "Cases/Reported/Case A.md":
                    "---\ntype: case-study\n"
                    "case_class: controlled-study\n---\n# Case A\n",
                "Cases/Unfiled Case.md":
                    "---\ntype: case-study\n"
                    "case_class: reported-system\n---\n# Unfiled\n",
                "Synthesis/Group/Question Two.md":
                    "---\ntype: research-synthesis\n---\n# Question Two\n",
        }):
            self.assert_run(
                fixture, 1,
                "the declared class and the path must agree",
                "neither the canonical entry nor inside",
                "sits in a subdirectory")

        global_map = copy.deepcopy(base)
        global_map["units"][0]["global_map_entry"] = "E-GHOST"
        coverage = (
            "schema_version: 1\n"
            "pages:\n"
            "  - path: \"Domain/Domain Overview.md\"\n"
            "    structural_unit: U-GHOST\n")
        with fixture.override({
                fixture.REGISTRY: kblib.canonical_yaml(global_map),
                ".cambium/state/coverage_ledger.yaml": coverage,
        }):
            self.assert_run(
                fixture, 1,
                "Corpus Planning is not configured",
                "not a registered unit or support layer id")


if __name__ == "__main__":
    unittest.main()
