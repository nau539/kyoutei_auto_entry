import unittest

from product_profile import (
    app_palette,
    clamp_enabled_bet_types,
    default_enabled_bet_types,
    edition_auth_module,
    edition_profile,
    edition_requires_auth,
    infer_tool_slot_from_candidate_payload,
    infer_tool_slot_from_entry_payload,
    max_bet_types,
    normalize_bet_type,
    normalize_tool_slot,
    runtime_log_basename,
    runtime_product_name,
    tool_slot_hour,
    tool_slot_label,
)


class ProductProfileTests(unittest.TestCase):
    def test_default_edition_is_gold_branded_aqua_product(self):
        # 既定(未指定/未凍結)は GOLD エディション。製品ラインは AQUA EDGE AI。
        self.assertEqual(runtime_product_name(), "AQUA EDGE AI GOLD")
        self.assertEqual(runtime_log_basename(), "aqua_edge_ai_gold")

    def test_edition_caps_and_auth(self):
        self.assertEqual(max_bet_types("GOLD"), 3)
        self.assertEqual(max_bet_types("SILVER"), 2)
        self.assertEqual(max_bet_types("BRONZE"), 1)
        self.assertEqual(max_bet_types("DEMO"), 3)
        # 全エディションが認証する。クリアイズム様向けは auth_clear、それ以外は auth_master。
        self.assertTrue(edition_requires_auth("GOLD"))
        self.assertTrue(edition_requires_auth("DEMO"))
        self.assertEqual(edition_auth_module("GOLD", "clearism"), "auth_clear")
        self.assertEqual(edition_auth_module("SILVER", "clearism"), "auth_clear")
        self.assertEqual(edition_auth_module("BRONZE", "clearism"), "auth_clear")
        self.assertEqual(edition_auth_module("BRONZE", "aqua"), "auth_master")
        self.assertEqual(edition_auth_module("DEMO"), "auth_master")
        self.assertEqual(edition_profile("DEMO")["exe_basename"], "KYOUTEI")
        self.assertEqual(edition_profile("GOLD")["exe_basename"], "AQUA EDGE AI_GOLD")

    def test_bet_type_selection_is_clamped_to_edition_cap(self):
        self.assertEqual(normalize_bet_type("２連複"), "2連複")
        self.assertEqual(normalize_bet_type("三連単"), "3連単")
        self.assertEqual(normalize_bet_type("馬連"), "")
        # BRONZE は最大1種。選択順を優先して切り詰める。
        self.assertEqual(clamp_enabled_bet_types(["3連単", "3連複", "2連複"], "BRONZE"), ["3連単"])
        self.assertEqual(clamp_enabled_bet_types(["3連複", "2連複", "3連単"], "SILVER"), ["3連複", "2連複"])
        self.assertEqual(default_enabled_bet_types("GOLD"), ["3連複", "2連複", "3連単"])
        self.assertEqual(default_enabled_bet_types("BRONZE"), ["3連複"])

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
