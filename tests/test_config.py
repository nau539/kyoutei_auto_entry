import tempfile
import unittest
from pathlib import Path

from config import AppSettings, ensure_selectors_file, load_selectors, load_settings, save_settings


class ConfigTests(unittest.TestCase):
    def test_default_operation_flags(self):
        settings = AppSettings()
        self.assertTrue(settings.ipat.headless)
        self.assertTrue(settings.ipat.submit_enabled)
        self.assertEqual(settings.ipat.timeout_sec, 2)
        self.assertEqual(settings.ipat.browser_channel, "")
        self.assertEqual(settings.local_ipat.login_url, "https://www.spat4.jp/keiba/pc")
        self.assertEqual(settings.local_ipat.member_number, "")
        self.assertEqual(settings.local_ipat.member_id, "")
        self.assertEqual(settings.local_ipat.pin, "")
        self.assertEqual(settings.local_ipat.browser_channel, "")
        self.assertFalse(settings.entry.confirm_each_race)
        self.assertFalse(settings.entry.show_ticket_preview_window)
        self.assertTrue(settings.entry.enable_central)
        self.assertFalse(settings.entry.enable_local)
        self.assertTrue(settings.entry.central_schedule_enabled)
        self.assertEqual(settings.entry.central_schedule_open_time, "10:00")
        self.assertEqual(settings.entry.central_schedule_close_time, "21:00")
        self.assertEqual(settings.entry.dispatch_mode, "midnight_base")
        self.assertEqual(settings.entry.fixed_ticket_yen, 100)
        self.assertEqual(settings.entry.raffine_budget_yen, 10000)
        self.assertEqual(settings.entry.entry_abort_total_yen, 10000)
        self.assertEqual(settings.entry.entry_abort_mode, "yen")
        self.assertEqual(settings.entry.entry_abort_ratio_pct, 100.0)
        self.assertEqual(settings.entry.target_payout_mode, "yen")
        self.assertEqual(settings.entry.target_payout_ratio_pct, 1000.0)
        self.assertEqual(settings.entry.target_payout_yen, 10000)
        self.assertEqual(settings.entry.allocation_mode, "target_payout")
        self.assertEqual(settings.theme_mode, "system")

    def test_ipat_timeout_is_clamped_to_short_range(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text('{"ipat":{"timeout_sec":30}}', encoding="utf-8")
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.ipat.timeout_sec, 2)

            cfg_path.write_text('{"ipat":{"timeout_sec":0}}', encoding="utf-8")
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.ipat.timeout_sec, 1)

    def test_auth_settings_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            settings = AppSettings()
            settings.auth.user_id = "demo_user"
            settings.auth.auto_login = True
            save_settings(settings, cfg_path)

            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.auth.user_id, "demo_user")
            self.assertTrue(loaded.auth.auto_login)

    def test_auth_settings_default_for_legacy_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text('{"ipat": {}, "entry": {}}', encoding="utf-8")

            loaded = load_settings(cfg_path)
            self.assertTrue(loaded.ipat.headless)
            self.assertTrue(loaded.ipat.submit_enabled)
            self.assertEqual(loaded.local_ipat.login_url, "https://www.spat4.jp/keiba/pc")
            self.assertFalse(loaded.entry.confirm_each_race)
            self.assertFalse(loaded.entry.show_ticket_preview_window)
            self.assertTrue(loaded.entry.enable_central)
            self.assertFalse(loaded.entry.enable_local)
            self.assertTrue(loaded.entry.central_schedule_enabled)
            self.assertEqual(loaded.entry.central_schedule_open_time, "10:00")
            self.assertEqual(loaded.entry.central_schedule_close_time, "21:00")
            self.assertEqual(loaded.entry.dispatch_mode, "midnight_base")
            self.assertEqual(loaded.entry.fixed_ticket_yen, 100)
            self.assertEqual(loaded.entry.raffine_budget_yen, 10000)
            self.assertEqual(loaded.entry.entry_abort_total_yen, 10000)
            self.assertEqual(loaded.entry.entry_abort_mode, "yen")
            self.assertEqual(loaded.entry.entry_abort_ratio_pct, 100.0)
            self.assertEqual(loaded.entry.target_payout_mode, "yen")
            self.assertEqual(loaded.entry.target_payout_ratio_pct, 1000.0)
            self.assertEqual(loaded.entry.target_payout_yen, 10000)
            self.assertEqual(loaded.entry.allocation_mode, "target_payout")
            self.assertEqual(loaded.auth.user_id, "")
            self.assertTrue(loaded.auth.auto_login)
            self.assertEqual(loaded.theme_mode, "system")

    def test_local_ipat_legacy_fields_are_migrated(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text(
                '{"local_ipat":{"login_id":"1122334455","inet_id":"ABCD1234","password":"9999"}}',
                encoding="utf-8",
            )
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.local_ipat.member_number, "1122334455")
            self.assertEqual(loaded.local_ipat.member_id, "ABCD1234")
            self.assertEqual(loaded.local_ipat.pin, "9999")
            self.assertEqual(loaded.local_ipat.browser_channel, "")

    def test_browser_channel_aliases_are_normalized_without_forcing_chrome_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text(
                '{"ipat":{"browser_channel":"edge"},"local_ipat":{"browser_channel":"chromium"}}',
                encoding="utf-8",
            )
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.ipat.browser_channel, "msedge")
            self.assertEqual(loaded.local_ipat.browser_channel, "")

    def test_theme_mode_coercion(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text('{"theme_mode":"dark"}', encoding="utf-8")
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.theme_mode, "dark")

            cfg_path.write_text('{"theme_mode":"invalid"}', encoding="utf-8")
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.theme_mode, "system")

    def test_hidden_operation_flags_are_forced_to_compact_defaults(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text(
                (
                    '{"ipat":{"headless":false,"submit_enabled":false},'
                    '"entry":{"dry_run":true,"confirm_each_race":true,'
                    '"show_ticket_preview_window":true,"allocation_mode":"target_payout",'
                    '"entry_abort_mode":"percent","race_cap_yen":500,'
                    '"ticket_cap_yen":300,"max_tickets":2,'
                    '"central_schedule_enabled":false,'
                    '"central_schedule_open_time":"10:00","central_schedule_close_time":"21:00"}}'
                ),
                encoding="utf-8",
            )
            loaded = load_settings(cfg_path)
            self.assertFalse(loaded.ipat.headless)
            self.assertTrue(loaded.ipat.submit_enabled)
            self.assertFalse(loaded.entry.dry_run)
            self.assertFalse(loaded.entry.confirm_each_race)
            self.assertFalse(loaded.entry.show_ticket_preview_window)
            self.assertEqual(loaded.entry.allocation_mode, "target_payout")
            self.assertEqual(loaded.entry.entry_abort_mode, "yen")
            self.assertEqual(loaded.entry.race_cap_yen, 0)
            self.assertEqual(loaded.entry.ticket_cap_yen, 0)
            self.assertEqual(loaded.entry.max_tickets, 0)
            self.assertTrue(loaded.entry.central_schedule_enabled)
            self.assertEqual(loaded.entry.central_schedule_open_time, "10:00")
            self.assertEqual(loaded.entry.central_schedule_close_time, "21:00")

    def test_hidden_target_payout_ratio_mode_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text('{"entry":{"target_payout_mode":"percent","target_payout_ratio_pct":250}}', encoding="utf-8")
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.entry.target_payout_mode, "yen")
            self.assertEqual(loaded.entry.target_payout_ratio_pct, 250.0)

    def test_entry_legacy_ratio_mode_is_migrated_to_target_payout(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text('{"entry":{"allocation_mode":"ratio","ratio_pct":250}}', encoding="utf-8")
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.entry.allocation_mode, "target_payout")
            self.assertEqual(loaded.entry.fixed_ticket_yen, 250)

    def test_entry_schedule_time_is_normalized(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text(
                '{"entry":{"central_schedule_open_time":"8:00","central_schedule_close_time":"99:99"}}',
                encoding="utf-8",
            )
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.entry.central_schedule_open_time, "10:00")
            self.assertEqual(loaded.entry.central_schedule_close_time, "21:00")

    def test_hidden_dispatch_mode_is_forced_to_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text('{"entry":{"dispatch_mode":"守り"}}', encoding="utf-8")
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.entry.dispatch_mode, "midnight_base")

    def test_hidden_dispatch_mode_ignores_legacy_all_value(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text('{"entry":{"dispatch_mode":"all"}}', encoding="utf-8")
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.entry.dispatch_mode, "midnight_base")

    def test_hidden_dispatch_mode_ignores_all_day_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "kyoutei_auto_entry_config.json"
            cfg_path.write_text('{"entry":{"dispatch_mode":"all_stable"}}', encoding="utf-8")
            loaded = load_settings(cfg_path)
            self.assertEqual(loaded.entry.dispatch_mode, "midnight_base")

    def test_selectors_are_internal_only(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            selector_path = Path(tmp_dir) / "ipat_selectors.json"
            selector_path.write_text('{"login_id_input":"input#override"}', encoding="utf-8")
            selectors = load_selectors(selector_path)
            self.assertEqual(selectors.get("login_id_input"), "input[name='i']")
            local_selectors = load_selectors(selector_path, target="local")
            self.assertTrue(bool(local_selectors.get("__configured__", False)))
            self.assertEqual(str((local_selectors.get("market_value_map") or {}).get("馬連", "")), "5")
            self.assertIn("情報更新", str(local_selectors.get("local_refresh_button", "")))

            missing_path = Path(tmp_dir) / "missing_selectors.json"
            resolved = ensure_selectors_file(missing_path)
            self.assertEqual(resolved, missing_path)
            self.assertFalse(missing_path.exists())


if __name__ == "__main__":
    unittest.main()

