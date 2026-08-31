"""One pure interpretation of the public adapter implementation marker."""

import ast
import unittest

from Tools.platform.common import implementation_marker


class ImplementationMarkerTests(unittest.TestCase):

    def parse(self, source, *, required=False):
        return implementation_marker.parse_implementation_module(
            ast.parse(source), label="Tools/sample.py", required=required)

    def test_an_ordinary_module_may_have_no_marker(self):
        self.assertIsNone(self.parse("VALUE = 1\n"))
        with self.assertRaisesRegex(
                implementation_marker.ImplementationMarkerError,
                "exactly one IMPLEMENTATION_MODULE"):
            self.parse("VALUE = 1\n", required=True)

    def test_one_literal_qualified_tools_module_is_the_edge(self):
        self.assertEqual(
            "Tools.area.sample",
            self.parse(
                "IMPLEMENTATION_MODULE: str = 'Tools.area.sample'\n"),
        )

    def test_duplicate_marker_fails_in_optional_and_required_modes(self):
        sources = (
            "IMPLEMENTATION_MODULE = 'Tools.area.first'\n"
            "IMPLEMENTATION_MODULE = 'Tools.area.second'\n",
            "IMPLEMENTATION_MODULE = IMPLEMENTATION_MODULE = "
            "'Tools.area.sample'\n",
        )
        for source in sources:
            for required in (False, True):
                with self.subTest(
                        source=source, required=required), \
                        self.assertRaisesRegex(
                            implementation_marker.ImplementationMarkerError,
                            "exactly one IMPLEMENTATION_MODULE"):
                    self.parse(source, required=required)

    def test_nonliteral_marker_fails_in_optional_and_required_modes(self):
        sources = (
            "IMPLEMENTATION_MODULE = choose_owner()\n",
            "IMPLEMENTATION_MODULE += 'Tools.area.sample'\n",
            "IMPLEMENTATION_MODULE, other = 'Tools.area.sample'\n",
        )
        for source in sources:
            for required in (False, True):
                with self.subTest(
                        source=source, required=required), \
                        self.assertRaisesRegex(
                            implementation_marker.ImplementationMarkerError,
                            "must be one literal module name"):
                    self.parse(source, required=required)

    def test_invalid_module_name_fails_in_optional_and_required_modes(self):
        for module_name in (
                "area.sample", "Tools", "Tools.Area.sample",
                "Tools.area.sample-name", "Tools.area..sample"):
            for required in (False, True):
                with self.subTest(
                        module_name=module_name, required=required), \
                        self.assertRaisesRegex(
                            implementation_marker.ImplementationMarkerError,
                            "not a qualified Tools module"):
                    self.parse(
                        "IMPLEMENTATION_MODULE = %r\n" % module_name,
                        required=required)


if __name__ == "__main__":
    unittest.main()
