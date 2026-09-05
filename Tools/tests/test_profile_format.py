"""Unit ownership of TOML encoding, distinct from governance acceptance.

No repository fixture, Profile adoption, external evaluator, or subprocess is
needed to prove lossless data encoding. CUE integration remains a contract
owner test, rather than being replayed for every codec edge case.
"""

from datetime import date
from types import MappingProxyType
import unittest

from Tools.governance.profile import profile_codec


class ProfileCodecTests(unittest.TestCase):
    def test_round_trip_preserves_typed_data_and_natural_language(self):
        data = {"schema_version": 1, "profile_id": "example", "slots": {
            "scope": {"text": "第一行\r\nsecond line\n", "values": [True, 3, 0.25],
                      "empty": [], "unanswered": {}}}}
        self.assertEqual(data, profile_codec.loads_profile(profile_codec.dumps_profile(data)))

    def test_mapping_order_does_not_change_generated_bytes(self):
        self.assertEqual(profile_codec.dumps_profile({"b": 2, "a": {"z": 1, "c": 3}}),
                         profile_codec.dumps_profile({"a": {"c": 3, "z": 1}, "b": 2}))

    def test_readonly_model_is_projected_without_mutating_it(self):
        value = MappingProxyType({"rows": (MappingProxyType({"id": "one"}),)})
        self.assertEqual({"rows": [{"id": "one"}]},
                         profile_codec.loads_profile(profile_codec.dumps_profile(value)))
        self.assertIsInstance(value["rows"], tuple)

    def test_codec_never_fills_absent_policy(self):
        self.assertEqual({"profile_id": "new"}, profile_codec.loads_profile(b'profile_id = "new"\n'))
        self.assertEqual({"registration": {"mode": "none"}},
                         profile_codec.loads_profile(b'[registration]\nmode = "none"\n'))

    def test_unrepresentable_values_are_rejected_instead_of_coerced(self):
        for value in (None, float("nan"), float("inf"), date(2026, 9, 5), object()):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(profile_codec.ProfileCodecError):
                    profile_codec.dumps_profile({"value": value})
        with self.assertRaises(profile_codec.ProfileCodecError):
            profile_codec.dumps_profile({"key": 1, 2: "not-a-string-key"})

    def test_malformed_input_and_duplicate_keys_fail(self):
        for value in (b"\xff", b"answer = ", b"answer=1\nanswer=2", b"answer=2026-09-05"):
            with self.subTest(source=value):
                with self.assertRaises(profile_codec.ProfileCodecError):
                    profile_codec.loads_profile(value)


if __name__ == "__main__":
    unittest.main()
