import os
import unittest
from unittest import mock

from product_profile import (
    build_trial_app_name,
    manual_review_enabled,
    plan_label,
    raw_plan_label,
    runtime_log_basename,
    runtime_product_name,
    update_tool_slot_selection,
)


class ProductProfileTests(unittest.TestCase):
    def test_raw_plan_label_is_not_overridden_by_fixed_plan_env(self):
        with mock.patch.dict(os.environ, {"KYOUTEI_AI_ZERO_FIXED_PLAN_TIER": "silver"}, clear=False):
            self.assertEqual(plan_label("gold"), "SILVER")
            self.assertEqual(raw_plan_label("gold"), "GOLD")

    def test_silver_slot_selection_can_return_from_midnight_pair(self):
        slots = ["morning", "daytime"]
        slots = update_tool_slot_selection(slots, "midnight", "silver")
        self.assertEqual(slots, ["morning", "daytime"])

        slots = update_tool_slot_selection(slots, "daytime", "silver")
        self.assertEqual(slots, ["morning"])

        slots = update_tool_slot_selection(slots, "midnight", "silver")
        self.assertEqual(slots, ["morning", "midnight"])

        slots = update_tool_slot_selection(slots, "morning", "silver")
        self.assertEqual(slots, ["midnight"])

        slots = update_tool_slot_selection(slots, "daytime", "silver")
        self.assertEqual(slots, ["midnight", "daytime"])

    def test_bronze_selection_replaces_existing_slot_when_switching(self):
        slots = ["morning"]
        slots = update_tool_slot_selection(slots, "daytime", "bronze")
        self.assertEqual(slots, ["daytime"])

        slots = update_tool_slot_selection(slots, "daytime", "bronze")
        self.assertEqual(slots, [])

    def test_classic_trial_runtime_names(self):
        with mock.patch.dict(os.environ, {"KYOUTEI_AI_ZERO_UI_VARIANT": "classic_trial"}, clear=False):
            self.assertEqual(runtime_product_name(), "kyoutei_auto_entry")
            self.assertEqual(runtime_log_basename(), "kyoutei_auto_entry_trial")
            self.assertEqual(build_trial_app_name(), "kyoutei_auto_entry_trial")

    def test_fixed_plan_enables_manual_review(self):
        with mock.patch.dict(os.environ, {"KYOUTEI_AI_ZERO_FIXED_PLAN_TIER": "silver"}, clear=False):
            self.assertTrue(manual_review_enabled())

    def test_classic_trial_disables_manual_review_even_with_fixed_plan(self):
        with mock.patch.dict(
            os.environ,
            {
                "KYOUTEI_AI_ZERO_FIXED_PLAN_TIER": "gold",
                "KYOUTEI_AI_ZERO_UI_VARIANT": "classic_trial",
            },
            clear=False,
        ):
            self.assertFalse(manual_review_enabled())

    def test_gold_selection_is_toggle_based_up_to_three(self):
        slots: list[str] = []
        slots = update_tool_slot_selection(slots, "morning", "gold")
        self.assertEqual(slots, ["morning"])

        slots = update_tool_slot_selection(slots, "daytime", "gold")
        self.assertEqual(slots, ["morning", "daytime"])

        slots = update_tool_slot_selection(slots, "morning", "gold")
        self.assertEqual(slots, ["daytime"])


if __name__ == "__main__":
    unittest.main()

