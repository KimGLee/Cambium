"""Owned tests for the current Receipt reference graph.

Receipt body schemas, producers, sealing, runtime transitions, and Terminal
Proof have separate owners. This module verifies only the graph's reference
extraction, materialization policy, closure, and the current/history authority
split at the catalog connection.
"""

import unittest

from Tools.execution.evidence import receipt_reference_contract as graph
from Tools.execution.task_runtime.queue_runtime.receipts import (
    CurrentReceiptCatalog,
    HistoricalReceiptCatalog,
    adoption_filtered_catalog,
    current_receipt_catalog,
    historical_receipt_catalog,
)


def _record_for_spec(spec, receipt_id="R"):
    """Build one minimal record that materializes exactly ``spec.path``."""
    record = {}
    current = record
    for index, token in enumerate(spec.path):
        if token.endswith("[]"):
            field, shape = token[:-2], "list"
        elif token.endswith("{}"):
            field, shape = token[:-2], "mapping"
        else:
            field, shape = token, "scalar"
        last = index == len(spec.path) - 1
        value = receipt_id if last else {}
        if shape == "list":
            current[field] = [value]
            if not last:
                current = current[field][0]
        elif shape == "mapping":
            current[field] = {"fixture": value}
            if not last:
                current = current[field]["fixture"]
        else:
            current[field] = value
            if not last:
                current = current[field]
    return record


class ReceiptReferenceRegistryContractTests(unittest.TestCase):
    def test_registry_is_a_closed_partition_with_one_named_edge(self):
        specs = graph.RECEIPT_REFERENCE_SPECS
        edge_ids = [spec.edge_id for spec in specs]
        source_kinds = {spec.source_kind for spec in specs}

        self.assertEqual(len(edge_ids), len(set(edge_ids)))
        self.assertTrue(specs)
        for source_kind in source_kinds:
            with self.subTest(source_kind=source_kind):
                expected = tuple(
                    spec for spec in specs
                    if spec.source_kind == source_kind)
                self.assertEqual(expected, graph.reference_specs(source_kind))
        for spec in specs:
            with self.subTest(edge_id=spec.edge_id):
                self.assertIs(spec, graph.reference_spec(spec.edge_id))
                self.assertTrue(spec.path)
                self.assertIn(spec.cardinality, {
                    graph.CARDINALITY_ONE,
                    graph.CARDINALITY_OPTIONAL,
                    graph.CARDINALITY_MANY,
                })
                self.assertIn(
                    spec.materialization, graph.MATERIALIZATION_ORDER)
                if spec.materialization == \
                        graph.MATERIALIZATION_COLD_PROJECTION:
                    self.assertTrue(spec.projection_fields)

        with self.assertRaises(graph.UnknownReceiptSource):
            graph.reference_specs("unknown-source")
        with self.assertRaises(graph.UnknownReceiptSource):
            graph.reference_spec("unknown.edge")

    def test_cold_projection_is_the_stable_union_of_graph_consumers(self):
        expected = list(graph.BASE_COLD_PROJECTION_FIELDS)
        for spec in graph.RECEIPT_REFERENCE_SPECS:
            for field in spec.projection_fields:
                if field not in expected:
                    expected.append(field)

        self.assertEqual(
            tuple(expected), graph.RECEIPT_COLD_PROJECTION_FIELDS)
        self.assertEqual(tuple(expected), graph.cold_projection_fields())


class ReceiptReferenceExtractionContractTests(unittest.TestCase):
    def test_every_declared_edge_extracts_and_filters_from_its_policy(self):
        materializations = tuple(graph.MATERIALIZATION_ORDER)
        for index, spec in enumerate(graph.RECEIPT_REFERENCE_SPECS):
            receipt_id = "R%03d" % index
            record = _record_for_spec(spec, receipt_id)
            with self.subTest(edge_id=spec.edge_id):
                references = tuple(graph.iter_receipt_references(
                    record, spec.source_kind, recursive=False))
                self.assertEqual(1, len(references))
                reference = references[0]
                self.assertEqual(receipt_id, reference.receipt_id)
                self.assertIs(spec, reference.spec)
                self.assertEqual(spec.path, reference.source_path)
                self.assertEqual(
                    {receipt_id},
                    graph.edge_reference_ids(
                        record, spec.source_kind, spec.edge_id,
                        recursive=False))

                for minimum in materializations:
                    expected = ({receipt_id}
                                if graph.MATERIALIZATION_ORDER[
                                    spec.materialization] >=
                                graph.MATERIALIZATION_ORDER[minimum]
                                else set())
                    self.assertEqual(
                        expected,
                        graph.reference_ids(
                            record, spec.source_kind, recursive=False,
                            minimum_materialization=minimum))
                self.assertEqual(
                    {receipt_id},
                    graph.reference_ids(
                        record, spec.source_kind, recursive=False,
                        keep_hot=spec.keep_hot))
                self.assertEqual(
                    set(),
                    graph.reference_ids(
                        record, spec.source_kind, recursive=False,
                        keep_hot=not spec.keep_hot))
                if spec.closure is not None:
                    self.assertEqual(
                        {receipt_id},
                        graph.reference_ids(
                            record, spec.source_kind, recursive=False,
                            closure=spec.closure))
                    self.assertEqual(
                        set(),
                        graph.reference_ids(
                            record, spec.source_kind, recursive=False,
                            closure="different-closure"))

    def test_reference_shapes_and_source_identity_fail_closed(self):
        cases = (
            ({"transition_receipts": "R"}, graph.SOURCE_ITEM),
            ({"closed_list_evidence": ["R"]}, graph.SOURCE_CLOSE),
            ({"close_gate_receipt": ["R"]}, graph.SOURCE_ITEM),
            ("not-a-record", graph.SOURCE_ITEM),
        )
        for record, source_kind in cases:
            with self.subTest(record=record, source_kind=source_kind):
                with self.assertRaises(graph.ReferenceShapeError):
                    tuple(graph.iter_receipt_references(
                        record, source_kind, recursive=False))

        with self.assertRaises(graph.UnknownReceiptSource):
            graph.edge_reference_ids(
                {"transition_receipts": ["R"]},
                graph.SOURCE_ITEM,
                "queue-transition.evidence",
                recursive=False)

    def test_child_sources_join_the_parent_without_a_second_field_list(self):
        record = {
            "transition_receipts": ["direct-transition"],
            "invalidation_history": [{
                "transition_receipt": "invalidated-transition",
                "delta_gate_receipts": ["invalidated-gate"],
            }],
        }

        direct = graph.reference_ids(
            record, graph.SOURCE_ITEM, recursive=False)
        recursive = graph.reference_ids(
            record, graph.SOURCE_ITEM, recursive=True)

        self.assertEqual({"direct-transition"}, direct)
        self.assertEqual({
            "direct-transition", "invalidated-transition",
            "invalidated-gate",
        }, recursive)


class ReceiptReferenceClosureContractTests(unittest.TestCase):
    @staticmethod
    def source_kind(body):
        return (graph.SOURCE_WRITER_OPERATION
                if body.get("record_kind") == "writer-operation"
                else None)

    def test_body_required_closure_is_complete_or_fails_closed(self):
        root = {"receipt_id": "A"}
        records = {
            "A": {
                "record_kind": "writer-operation",
                "commit_receipt_id": "B",
            },
            "B": {"record_kind": "leaf"},
        }
        self.assertEqual(
            {"A", "B"},
            graph.walk_receipt_closure(
                root, graph.SOURCE_WRITER_OPERATION, records.get,
                graph.WRITER_TRANSACTION_CLOSURE, self.source_kind))

        with self.assertRaises(graph.UnresolvedBodyReference):
            graph.walk_receipt_closure(
                root, graph.SOURCE_WRITER_OPERATION, {}.get,
                graph.WRITER_TRANSACTION_CLOSURE, self.source_kind)

        cyclic = {
            "A": {
                "record_kind": "writer-operation",
                "commit_receipt_id": "B",
            },
            "B": {
                "record_kind": "writer-operation",
                "abort_receipt_id": "A",
            },
        }
        with self.assertRaises(graph.ReferenceCycleError):
            graph.walk_receipt_closure(
                root, graph.SOURCE_WRITER_OPERATION, cyclic.get,
                graph.WRITER_TRANSACTION_CLOSURE, self.source_kind)


class CurrentReceiptAuthorityHistoryTests(unittest.TestCase):
    """Minimal current/history catalog connection; no runtime replay."""

    def test_history_is_preserved_but_cannot_fall_back_into_current_authority(self):
        history = HistoricalReceiptCatalog({
            "hot-current": (
                ".cambium/receipts/current.jsonl",
                {"receipt_id": "hot-current", "result": "pass"}),
            "hot-invalidated": (
                ".cambium/receipts/current.jsonl",
                {"receipt_id": "hot-invalidated", "result": "pass"}),
        })
        projection = {
            field: None for field in graph.IDENTITY_PROJECTION_FIELDS
        }
        projection.update({
            "receipt_id": "cold-current",
            "result": "pass",
            "invalidated_by": None,
        })
        invalidated_projection = dict(
            projection, receipt_id="cold-invalidated")
        history.cold = {
            "cold-current": projection,
            "cold-invalidated": invalidated_projection,
        }

        current = adoption_filtered_catalog(
            history, {"hot-invalidated", "cold-invalidated"})

        self.assertIsInstance(current, CurrentReceiptCatalog)
        self.assertEqual({"hot-current"}, set(current))
        self.assertEqual({"cold-current"}, set(current.cold))
        self.assertEqual(
            {"hot-current", "hot-invalidated"}, set(history))
        self.assertEqual(
            {"cold-current", "cold-invalidated"}, set(history.cold))

        runtime = {
            "receipt_catalog": history,
            "current_receipt_catalog": current,
        }
        self.assertIs(current, current_receipt_catalog(runtime))
        self.assertIs(history, historical_receipt_catalog(runtime))
        no_current_view = current_receipt_catalog({
            "receipt_catalog": history,
        })
        self.assertIsInstance(no_current_view, CurrentReceiptCatalog)
        self.assertEqual({}, no_current_view)
        self.assertEqual({}, no_current_view.cold)

        hot = current.resolve_reference(
            "hot-current", "queue-item.confirmation")
        cold = current.resolve_reference(
            "cold-current", "queue-item.confirmation")
        current.cold["body-required-only"] = dict(
            projection, receipt_id="body-required-only")
        unavailable_body = current.resolve_reference(
            "body-required-only", "queue-item.transition")
        self.assertEqual("hot-body", hot.origin)
        self.assertEqual("cold-projection", cold.origin)
        self.assertIsNone(unavailable_body)


if __name__ == "__main__":
    unittest.main()
