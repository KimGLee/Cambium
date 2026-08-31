"""Direct Contract tests for the current Work Spec machine owners.

The shared Queue/Coverage binding shape belongs to ``work_spec_contract``.
The immutable document grammar and its repository binding belong to
``queue_runtime.work_spec``.  These tests exercise those owners directly;
they do not construct a Task, open a batch, or replay a close lifecycle.
"""

import ast
import copy
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import Tools.execution.planning.coverage_contract as coverage_contract  # noqa: E402
import Tools.execution.planning.queue_replan as queue_replan  # noqa: E402
import Tools.execution.planning.work_spec_contract as binding_contract  # noqa: E402
import Tools.execution.task_runtime.amendment_policy as amendment_policy  # noqa: E402
import Tools.execution.task_runtime.queue_runtime.work_spec as work_spec  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.platform.distribution.module_boundary_facts as module_boundary_facts  # noqa: E402


TEMPLATE = TOOLS / "schemas" / "batch_work_spec.template.yaml"
VALID_SHA = "sha256:" + "a" * 64


def valid_document():
    """Return the shipped template filled with current, non-sentinel values."""
    document = copy.deepcopy(kblib.load_yaml_file(TEMPLATE))
    document["batch_id"] = "B1"
    document["manifest"] = ["Topics/A.md", "Topics/B.md"]
    document["outcomes"][0]["required_result"] = \
        "Both manifest pages contain the requested current content."
    document["instructions"][0].update({
        "target_scope": ["Topics/A.md"],
        "required_transformation": "Update the first governed page.",
    })
    document["acceptance_conditions"][0].update({
        "target_scope": ["Topics/A.md", "Topics/B.md"],
        "observable_predicate": "Both pages expose the declared result.",
        "evidence_requirement": "Record the resulting page fingerprints.",
    })
    document["constraints"][0]["requirement"] = \
        "Preserve the declared manifest boundary."
    return document


def _literal_string_set(node):
    """Read one literal string collection from a shipped module AST."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and
            node.func.id in ("frozenset", "set", "tuple", "list") and
            len(node.args) == 1 and not node.keywords):
        node = node.args[0]
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return None
    values = []
    for child in node.elts:
        if not isinstance(child, ast.Constant) or not isinstance(
                child.value, str):
            return None
        values.append(child.value)
    return frozenset(values)


class WorkSpecSharedBindingOwnerTests(unittest.TestCase):
    def test_every_binding_consumer_uses_the_owner_object(self):
        fields = binding_contract.WORK_SPEC_BINDING_FIELDS
        self.assertIs(fields, amendment_policy.WORK_SPEC_FIELDS)
        self.assertIs(fields, queue_replan.WORK_SPEC_FIELDS)
        self.assertIs(fields, work_spec.WORK_SPEC_FIELDS)
        self.assertTrue(fields.issubset(
            coverage_contract.COVERAGE_BATCH_SPEC_FIELDS))

    def test_no_other_shipped_module_redeclares_the_binding_literal(self):
        fields = binding_contract.WORK_SPEC_BINDING_FIELDS
        duplicates = []
        for relative in module_boundary_facts.shipped_modules(str(TOOLS)):
            if relative == "execution/planning/work_spec_contract.py":
                continue
            path = TOOLS / relative
            tree = ast.parse(path.read_text(encoding="utf-8"),
                             filename=relative)
            for node in ast.walk(tree):
                value = node.value if isinstance(
                    node, (ast.Assign, ast.AnnAssign)) else None
                if _literal_string_set(value) == fields:
                    duplicates.append("%s:%d" % (relative, node.lineno))
        self.assertEqual([], duplicates,
                         "Work Spec binding fields must have one owner")


class WorkSpecDocumentContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.relative = ".cambium/work_specs/B1.yaml"

    def tearDown(self):
        self.temporary.cleanup()

    def errors(self, document=None, *, item=None, text=None):
        """Bind one document exactly as a current Queue consumer does."""
        path = self.root / self.relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            text = kblib.canonical_yaml(
                valid_document() if document is None else document)
        path.write_text(text, encoding="utf-8")
        queue_item = {
            "id": "B1",
            "manifest": ["Topics/A.md", "Topics/B.md"],
            "work_spec_path": self.relative,
            "work_spec_sha256": kblib.sha256_file(path),
        }
        queue_item.update(item or {})
        return work_spec.work_spec_errors(self.root, queue_item)

    def assert_contract_error(self, document, expected, *, item=None):
        errors = self.errors(document, item=item)
        self.assertTrue(any(expected in error for error in errors), errors)

    def test_template_is_the_exact_grammar_projection_and_fills_to_valid(self):
        template = kblib.load_yaml_file(TEMPLATE)
        self.assertEqual(work_spec.WORK_SPEC_TOP_LEVEL_FIELDS, set(template))
        groups = {
            "outcomes": work_spec.WORK_SPEC_OUTCOME_FIELDS,
            "instructions": work_spec.WORK_SPEC_INSTRUCTION_FIELDS,
            "acceptance_conditions": work_spec.WORK_SPEC_ACCEPTANCE_FIELDS,
            "constraints": work_spec.WORK_SPEC_CONSTRAINT_FIELDS,
        }
        for name, fields in groups.items():
            with self.subTest(group=name):
                self.assertEqual(fields, set(template[name][0]))
        self.assertEqual([], self.errors(valid_document()))

    def test_binding_pair_path_fingerprint_and_bytes_are_exact(self):
        self.assertEqual([], work_spec.work_spec_binding_errors(
            None, None, "batch"))
        self.assertEqual([], work_spec.work_spec_binding_errors(
            self.relative, VALID_SHA, "batch"))
        invalid = (
            (None, VALID_SHA, "both be null or both be non-null"),
            (self.relative, None, "both be null or both be non-null"),
            (" ", VALID_SHA, "non-empty string"),
            (".cambium/receipts/B1.yaml", VALID_SHA,
             "directly inside .cambium/work_specs/"),
            (".cambium/work_specs/nested/B1.yaml", VALID_SHA,
             "directly inside .cambium/work_specs/"),
            (".cambium/work_specs/B1.md", VALID_SHA,
             "directly inside .cambium/work_specs/"),
            (self.relative, "sha256:" + "A" * 64,
             "64 lowercase hex"),
        )
        for path, fingerprint, expected in invalid:
            with self.subTest(path=path, fingerprint=fingerprint):
                errors = work_spec.work_spec_binding_errors(
                    path, fingerprint, "batch")
                self.assertTrue(any(expected in error for error in errors),
                                errors)

        path = self.root / self.relative
        self.assertEqual([], self.errors())
        original_sha = kblib.sha256_file(path)
        path.write_text(path.read_text(encoding="utf-8") + "\n",
                        encoding="utf-8")
        item = {
            "id": "B1",
            "manifest": ["Topics/A.md", "Topics/B.md"],
            "work_spec_path": self.relative,
            "work_spec_sha256": original_sha,
        }
        errors = work_spec.work_spec_errors(self.root, item)
        self.assertTrue(any("Work Spec SHA mismatch" in error
                            for error in errors), errors)

        missing_item = dict(item)
        missing_item.update({
            "work_spec_path": ".cambium/work_specs/missing.yaml",
            "work_spec_sha256": VALID_SHA,
        })
        errors = work_spec.work_spec_errors(self.root, missing_item)
        self.assertTrue(any("unsafe or unreadable" in error
                            for error in errors), errors)

    def test_top_level_identity_manifest_and_closed_fields(self):
        cases = []
        missing = valid_document()
        missing.pop("constraints")
        cases.append((missing, {}, "misses field(s): constraints"))
        extra = valid_document()
        extra["state"] = "open"
        cases.append((extra, {}, "must not declare Queue-owned field"))
        wrong_schema = valid_document()
        wrong_schema["schema_version"] = True
        cases.append((wrong_schema, {}, "schema_version must be 1"))
        wrong_batch = valid_document()
        wrong_batch["batch_id"] = "B2"
        cases.append((wrong_batch, {}, "does not equal Queue id"))
        wrong_manifest = valid_document()
        wrong_manifest["manifest"].reverse()
        cases.append((wrong_manifest, {}, "membership and order"))
        for document, item, expected in cases:
            with self.subTest(expected=expected):
                self.assert_contract_error(document, expected, item=item)

        errors = self.errors(text="- not-a-mapping\n")
        self.assertTrue(any("top-level mapping" in error for error in errors),
                        errors)

    def test_each_record_collection_is_nonempty_and_closed(self):
        groups = {
            "outcomes": work_spec.WORK_SPEC_OUTCOME_FIELDS,
            "instructions": work_spec.WORK_SPEC_INSTRUCTION_FIELDS,
            "acceptance_conditions": work_spec.WORK_SPEC_ACCEPTANCE_FIELDS,
            "constraints": work_spec.WORK_SPEC_CONSTRAINT_FIELDS,
        }
        for name, fields in groups.items():
            with self.subTest(group=name, condition="empty"):
                document = valid_document()
                document[name] = []
                self.assert_contract_error(
                    document, "%s must be a non-empty list" % name)
            with self.subTest(group=name, condition="missing"):
                document = valid_document()
                document[name][0].pop(sorted(fields)[0])
                self.assert_contract_error(document, "misses field(s)")
            with self.subTest(group=name, condition="extra"):
                document = valid_document()
                document[name][0]["unexpected"] = True
                self.assert_contract_error(document, "unsupported field(s)")
            with self.subTest(group=name, condition="not-mapping"):
                document = valid_document()
                document[name][0] = "not-a-record"
                self.assert_contract_error(document, "must be a mapping")

    def test_record_ids_and_required_text_are_closed(self):
        id_fields = {
            "outcomes": "outcome_id",
            "instructions": "instruction_id",
            "acceptance_conditions": "condition_id",
            "constraints": "constraint_id",
        }
        for group, field in id_fields.items():
            with self.subTest(group=group, condition="invalid-id"):
                document = valid_document()
                document[group][0][field] = "not stable!"
                self.assert_contract_error(document, "must match")
            with self.subTest(group=group, condition="duplicate-id"):
                document = valid_document()
                document[group].append(copy.deepcopy(document[group][0]))
                if group == "instructions":
                    document[group][1]["order"] = 2
                self.assert_contract_error(document, "duplicate %s" % field)

        text_fields = (
            ("outcomes", "required_result"),
            ("instructions", "required_transformation"),
            ("acceptance_conditions", "observable_predicate"),
            ("acceptance_conditions", "evidence_requirement"),
            ("constraints", "requirement"),
        )
        for group, field in text_fields:
            with self.subTest(group=group, field=field):
                document = valid_document()
                document[group][0][field] = " "
                self.assert_contract_error(document, "non-empty string")

    def test_target_scope_and_instruction_dependency_graph_are_closed(self):
        scope_cases = (
            ([], "non-empty explicit string list"),
            (["Topics/A.md", "Topics/A.md"], "duplicate targets"),
            (["batch", "Topics/A.md"], "batch and paths cannot be mixed"),
            (["Topics/Unknown.md"], "outside the Queue manifest"),
        )
        for group in ("instructions", "acceptance_conditions", "constraints"):
            for scope, expected in scope_cases:
                with self.subTest(group=group, scope=scope):
                    document = valid_document()
                    document[group][0]["target_scope"] = scope
                    self.assert_contract_error(document, expected)

        document = valid_document()
        document["instructions"] = [
            {
                "instruction_id": "INS-001", "order": 1,
                "target_scope": ["Topics/A.md"],
                "required_transformation": "Make the first change.",
                "depends_on": [],
            },
            {
                "instruction_id": "INS-002", "order": 2,
                "target_scope": ["Topics/B.md"],
                "required_transformation": "Make the dependent change.",
                "depends_on": ["INS-001"],
            },
        ]
        self.assertEqual([], self.errors(document))

        graph_cases = []
        wrong_order = copy.deepcopy(document)
        wrong_order["instructions"][1]["order"] = 3
        graph_cases.append((wrong_order, "unique, contiguous"))
        bool_order = copy.deepcopy(document)
        bool_order["instructions"][0]["order"] = True
        graph_cases.append((bool_order, "order must be an integer"))
        duplicate_dependency = copy.deepcopy(document)
        duplicate_dependency["instructions"][1]["depends_on"] = [
            "INS-001", "INS-001"]
        graph_cases.append((duplicate_dependency, "must not contain duplicates"))
        unknown_dependency = copy.deepcopy(document)
        unknown_dependency["instructions"][1]["depends_on"] = ["INS-999"]
        graph_cases.append((unknown_dependency, "references unknown instruction"))
        forward_dependency = copy.deepcopy(document)
        forward_dependency["instructions"][0]["depends_on"] = ["INS-002"]
        graph_cases.append((forward_dependency, "only earlier instructions"))
        for malformed, expected in graph_cases:
            with self.subTest(expected=expected):
                self.assert_contract_error(malformed, expected)

    def test_template_sentinels_and_nested_queue_state_are_rejected(self):
        for sentinel in work_spec.WORK_SPEC_SENTINELS:
            with self.subTest(sentinel=sentinel):
                unfilled = valid_document()
                unfilled["constraints"][0]["requirement"] = sentinel
                self.assert_contract_error(
                    unfilled, "unfilled template sentinel")

        for field in sorted(work_spec.WORK_SPEC_QUEUE_OWNED_FIELDS):
            with self.subTest(queue_owned_field=field):
                document = valid_document()
                document[field] = "forbidden second owner"
                self.assert_contract_error(
                    document, "must not declare Queue-owned field")

        nested_state = valid_document()
        nested_state["outcomes"][0]["required_result"] = {
            "state": "open",
        }
        self.assert_contract_error(
            nested_state, "outcomes.0.required_result.state")

        valid = valid_document()
        errors = self.errors(valid)
        self.assertFalse(any("instructions.0.order" in error or
                             "instructions.0.depends_on" in error
                             for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
