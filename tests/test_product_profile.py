import unittest

from product_profile import (
    app_palette,
    infer_tool_slot_from_candidate_payload,
    infer_tool_slot_from_entry_payload,
    normalize_tool_slot,
    runtime_log_basename,
    runtime_product_name,
    tool_slot_hour,
    tool_slot_label,
)


class ProductProfileTests(unittest.TestCase):
    def test_runtime_names_are_single_product_names(self):
        self.assertEqual(runtime_product_name(), "AQUA EDGE AI")
        self.assertEqual(runtime_log_basename(), "aqua_edge_ai")

    def test_tool_slot_aliases_are_normalized_for_message_routing(self):
        self.assertEqual(normalize_tool_slot("モーニング"), "morning")
        self.assertEqual(normalize_tool_slot("daytime_consistent_earnings"), "daytime")
        self.assertEqual(normalize_tool_slot("attack"), "midnight")
        self.assertEqual(tool_slot_label("midnight_attack"), "ミッドナイト")
        self.assertEqual(tool_slot_hour("daytime"), 10)

    def test_candidate_payload_slot_can_be_inferred_from_requested_time(self):
        payload = {
            "message_type": "pre_race_candidates",
            "requested_at": "2026-03-15 08:00:00",
            "filters": {},
        }
        self.assertEqual(infer_tool_slot_from_candidate_payload(payload), "morning")

    def test_entry_payload_slot_can_be_inferred_from_strategy(self):
        payload = {
            "strategy_code": "daytime_consistent_earnings",
            "strategy_name": "日中収益主軸",
        }
        self.assertEqual(infer_tool_slot_from_entry_payload(payload), "daytime")

    def test_app_palette_exposes_aqua_accent(self):
        palette = app_palette()
        self.assertIn("accent", palette)
        self.assertEqual(palette["accent"][0], "#008BC7")


if __name__ == "__main__":
    unittest.main()

