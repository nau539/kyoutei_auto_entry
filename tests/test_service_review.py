import unittest
from datetime import datetime
from pathlib import Path

from config import AppSettings
from ipat_playwright import IpatEntryError
from service import AutoEntryService


class ServiceReviewTests(unittest.TestCase):
    def _sample_payload(self):
        return {
            "race": {
                "date": "20260212",
                "venue_name": "東京",
                "race_num": 2,
                "race_id": "東京_2R",
            },
            "tickets": [
                {"market": "単勝", "combo": "7", "bet_yen": 5000, "odds": 14.5},
                {"market": "馬連", "combo": "7-11", "bet_yen": 700, "odds": 29.6},
            ],
        }

    def test_review_mutation_is_reflected_in_dry_run_result(self):
        settings = AppSettings()
        settings.entry.dry_run = True
        settings.entry.confirm_each_race = True
        settings.entry.show_ticket_preview_window = False

        logs = []

        def review_func(payload, tickets, total_yen, require_confirm, show_window):
            del payload, total_yen, require_confirm, show_window
            tickets[:] = [{"market": "単勝", "combo": "7", "bet_yen": 1200, "odds": 14.5}]
            return True

        svc = AutoEntryService(settings, logs.append, review_func=review_func)
        svc._write_runtime_file = lambda payload, tickets, result, target: Path("runtime_logs/dummy.json")  # type: ignore[method-assign]
        svc._execute_payload(svc.TARGET_CENTRAL, self._sample_payload())

        self.assertTrue(any("DRY-RUN" in line and "1点 1,200円" in line for line in logs))

    def test_review_empty_result_skips_execution(self):
        settings = AppSettings()
        settings.entry.dry_run = True
        settings.entry.confirm_each_race = True
        settings.entry.show_ticket_preview_window = False

        logs = []

        def review_func(payload, tickets, total_yen, require_confirm, show_window):
            del payload, total_yen, require_confirm, show_window
            tickets.clear()
            return True

        svc = AutoEntryService(settings, logs.append, review_func=review_func)
        svc._write_runtime_file = lambda payload, tickets, result, target: Path("runtime_logs/dummy.json")  # type: ignore[method-assign]
        svc._execute_payload(svc.TARGET_CENTRAL, self._sample_payload())

        self.assertTrue(any("レビュー後チケットなし" in line for line in logs))

    def test_prepare_tickets_ignores_discord_amounts(self):
        settings = AppSettings()
        settings.entry.fixed_ticket_yen = 300
        settings.entry.min_ticket_yen = 100
        settings.entry.allocation_mode = "flat"

        svc = AutoEntryService(settings, lambda _line: None)
        rows = svc._prepare_tickets(self._sample_payload())

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["bet_yen"], 300)
        self.assertEqual(rows[1]["bet_yen"], 300)

    def test_prepare_tickets_uses_kyoutei_discord_text_amounts(self):
        settings = AppSettings()
        settings.entry.min_ticket_yen = 100
        settings.entry.allocation_mode = "target_payout"
        settings.entry.target_payout_yen = 20000

        payload = self._sample_payload()
        payload.update({
            "message_type": "entry_tickets",
            "provider": "kyoutei",
            "source": "discord_text",
        })
        payload["tickets"] = [
            {"market": "3連複", "combo": "1-3-4", "bet_yen": 1200, "odds": 5.0},
        ]

        svc = AutoEntryService(settings, lambda _line: None)
        rows = svc._prepare_tickets(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["market"], "3連複")
        self.assertEqual(rows[0]["combo"], "1-3-4")
        self.assertEqual(rows[0]["bet_yen"], 1200)

    def test_prepare_tickets_raffine_uses_configured_budget(self):
        settings = AppSettings()
        settings.entry.fixed_ticket_yen = 100
        settings.entry.raffine_budget_yen = 1000
        settings.entry.min_ticket_yen = 100
        settings.entry.allocation_mode = "raffine"

        svc = AutoEntryService(settings, lambda _line: None)
        rows = svc._prepare_tickets(self._sample_payload())

        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(int(r.get("bet_yen", 0) or 0) for r in rows), 1000)

    def test_prepare_tickets_target_payout_ratio_mode_uses_percentage_base(self):
        settings = AppSettings()
        settings.entry.fixed_ticket_yen = 300
        settings.entry.min_ticket_yen = 100
        settings.entry.allocation_mode = "target_payout"
        settings.entry.target_payout_mode = "ratio"
        settings.entry.target_payout_ratio_pct = 1000.0

        svc = AutoEntryService(settings, lambda _line: None)
        rows = svc._prepare_tickets(self._sample_payload())

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["bet_yen"], 500)
        self.assertEqual(rows[1]["bet_yen"], 300)

    def test_post_entry_text_includes_expected_payout(self):
        settings = AppSettings()
        svc = AutoEntryService(settings, lambda _line: None)
        tickets = [
            {"market": "単勝", "combo": "7", "bet_yen": 1200, "odds": 14.5},
            {"market": "馬連", "combo": "7-11", "bet_yen": 300},
        ]
        text = svc._build_post_entry_text("20260214_東京_02R", tickets, 1500, "submitted")
        self.assertIn("単勝 7 14.5 1,200円 想定払い戻し:17,400円", text)
        self.assertIn("馬連 7-11 - 300円 想定払い戻し:-", text)

    def test_preview_text_includes_expected_payout(self):
        settings = AppSettings()
        svc = AutoEntryService(settings, lambda _line: None)
        tickets = [
            {"market": "単勝", "combo": "7", "bet_yen": 1200, "odds": 14.5},
            {"market": "馬連", "combo": "7-11", "bet_yen": 300},
        ]
        text = svc._build_preview_text({}, tickets, 1500, "20260214_東京_02R")
        self.assertIn("単勝 7 1,200円 想定払い戻し:17,400円", text)
        self.assertIn("馬連 7-11 300円 想定払い戻し:-", text)

    def test_execute_payload_skips_when_total_reaches_abort_threshold(self):
        settings = AppSettings()
        settings.entry.dry_run = True
        settings.entry.confirm_each_race = False
        settings.entry.show_ticket_preview_window = False
        settings.entry.fixed_ticket_yen = 600
        settings.entry.entry_abort_total_yen = 1000
        settings.entry.allocation_mode = "flat"
        logs = []

        svc = AutoEntryService(settings, logs.append)
        svc._execute_payload(svc.TARGET_CENTRAL, self._sample_payload())

        self.assertTrue(any("エントリー中止金額1,000円以上" in line for line in logs))
        self.assertFalse(any("DRY-RUN" in line for line in logs))

    def test_execute_payload_skips_when_abort_threshold_is_ratio_of_target_payout(self):
        settings = AppSettings()
        settings.entry.dry_run = True
        settings.entry.confirm_each_race = False
        settings.entry.show_ticket_preview_window = False
        settings.entry.fixed_ticket_yen = 600
        settings.entry.entry_abort_mode = "ratio"
        settings.entry.entry_abort_ratio_pct = 50.0
        settings.entry.target_payout_mode = "yen"
        settings.entry.target_payout_yen = 2000
        settings.entry.allocation_mode = "flat"
        logs = []

        svc = AutoEntryService(settings, logs.append)
        svc._execute_payload(svc.TARGET_CENTRAL, self._sample_payload())

        self.assertTrue(any("エントリー中止金額1,000円以上" in line for line in logs))
        self.assertFalse(any("DRY-RUN" in line for line in logs))

    def test_execute_payload_does_not_skip_when_abort_ratio_is_zero(self):
        settings = AppSettings()
        settings.entry.dry_run = True
        settings.entry.confirm_each_race = False
        settings.entry.show_ticket_preview_window = False
        settings.entry.fixed_ticket_yen = 600
        settings.entry.entry_abort_mode = "ratio"
        settings.entry.entry_abort_ratio_pct = 0.0
        settings.entry.target_payout_mode = "yen"
        settings.entry.target_payout_yen = 2000
        logs = []

        svc = AutoEntryService(settings, logs.append)
        svc._write_runtime_file = lambda payload, tickets, result, target: Path("runtime_logs/dummy.json")  # type: ignore[method-assign]
        svc._execute_payload(svc.TARGET_CENTRAL, self._sample_payload())

        self.assertFalse(any("エントリー中止金額" in line for line in logs))
        self.assertTrue(any("DRY-RUN" in line for line in logs))

    def test_execute_payload_skips_after_review_when_total_reaches_abort_threshold(self):
        settings = AppSettings()
        settings.entry.dry_run = True
        settings.entry.confirm_each_race = True
        settings.entry.show_ticket_preview_window = False
        settings.entry.entry_abort_total_yen = 1000
        settings.entry.allocation_mode = "flat"
        logs = []

        def review_func(payload, tickets, total_yen, require_confirm, show_window):
            del payload, total_yen, require_confirm, show_window
            tickets[:] = [
                {"market": "単勝", "combo": "7", "bet_yen": 1200, "odds": 14.5},
                {"market": "馬連", "combo": "7-11", "bet_yen": 200, "odds": 29.6},
            ]
            return True

        svc = AutoEntryService(settings, logs.append, review_func=review_func)
        svc._execute_payload(svc.TARGET_CENTRAL, self._sample_payload())

        self.assertTrue(any("レビュー後の合計金額1,400円" in line for line in logs))
        self.assertFalse(any("DRY-RUN" in line for line in logs))

    def test_execute_payload_skips_by_abort_threshold_in_target_payout_mode(self):
        settings = AppSettings()
        settings.entry.dry_run = True
        settings.entry.confirm_each_race = False
        settings.entry.show_ticket_preview_window = False
        settings.entry.fixed_ticket_yen = 600
        settings.entry.entry_abort_total_yen = 1000
        settings.entry.allocation_mode = "target_payout"
        logs = []

        svc = AutoEntryService(settings, logs.append)
        svc._write_runtime_file = lambda payload, tickets, result, target: Path("runtime_logs/dummy.json")  # type: ignore[method-assign]
        svc._execute_payload(svc.TARGET_CENTRAL, self._sample_payload())

        self.assertTrue(any("エントリー中止金額1,000円以上" in line for line in logs))
        self.assertFalse(any("DRY-RUN" in line for line in logs))

    def test_execute_payload_skips_by_abort_threshold_ratio_in_target_payout_mode(self):
        settings = AppSettings()
        settings.entry.dry_run = True
        settings.entry.confirm_each_race = False
        settings.entry.show_ticket_preview_window = False
        settings.entry.fixed_ticket_yen = 600
        settings.entry.entry_abort_mode = "ratio"
        settings.entry.entry_abort_ratio_pct = 10.0
        settings.entry.target_payout_mode = "yen"
        settings.entry.target_payout_yen = 1000
        settings.entry.allocation_mode = "target_payout"
        logs = []

        svc = AutoEntryService(settings, logs.append)
        svc._write_runtime_file = lambda payload, tickets, result, target: Path("runtime_logs/dummy.json")  # type: ignore[method-assign]
        svc._execute_payload(svc.TARGET_CENTRAL, self._sample_payload())

        self.assertTrue(any("エントリー中止金額100円以上" in line for line in logs))
        self.assertFalse(any("DRY-RUN" in line for line in logs))

    def test_discord_error_log_does_not_expose_raw_detail(self):
        settings = AppSettings()
        logs = []
        svc = AutoEntryService(settings, logs.append)

        svc._on_discord_error("Shard ID None WebSocket closed with 1006")

        self.assertTrue(any("連携エラー: 接続エラーが発生しました。自動再接続を待機します" in line for line in logs))
        self.assertFalse(any("WebSocket" in line for line in logs))

    def test_reconnect_failure_log_does_not_expose_raw_detail(self):
        settings = AppSettings()
        logs = []
        svc = AutoEntryService(settings, logs.append)
        svc._last_discord_start_monotonic = 0.0

        def _raise_start_error():
            raise RuntimeError("discord handshake timeout")

        svc._start_discord_gateway = _raise_start_error  # type: ignore[method-assign]
        svc._ensure_discord_alive()

        self.assertTrue(any("連携再接続失敗: しばらく待って再試行します" in line for line in logs))
        self.assertFalse(any("handshake timeout" in line for line in logs))

    def test_on_discord_status_logs_raw_and_drop_debug(self):
        settings = AppSettings()
        logs = []
        svc = AutoEntryService(settings, logs.append)

        svc._on_discord_status("raw_message: channel=111 guild=222 content_len=123")
        svc._on_discord_status("drop(channel_filter): channel=111 parent=- guild=222 webhook=-")

        self.assertTrue(any("連携デバッグ: raw_message:" in line for line in logs))
        self.assertTrue(any("連携デバッグ: drop(channel_filter)" in line for line in logs))

    def test_on_discord_message_logs_payload_zero_debug(self):
        settings = AppSettings()
        logs = []
        svc = AutoEntryService(settings, logs.append)

        svc._on_discord_message(
            {
                "content": "これはJSONではありません",
                "channel_id": "111",
                "parent_channel_id": "",
            }
        )

        self.assertTrue(any("受信デバッグ: payload抽出0件" in line for line in logs))

    def test_execute_payload_logs_entry_error_detail(self):
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.confirm_each_race = False
        settings.entry.show_ticket_preview_window = False
        logs = []
        svc = AutoEntryService(settings, logs.append)
        svc._central_schedule_now = lambda: datetime(2026, 2, 12, 10, 5, 0)  # type: ignore[method-assign]

        class _DummyExecutor:
            def execute(self, _payload, _tickets):
                raise IpatEntryError("地方式別を選択できませんでした (debug: runtime_logs/debug/20260218_103000)")

        svc._get_executor = lambda _target: _DummyExecutor()  # type: ignore[method-assign]
        svc._execute_payload(svc.TARGET_CENTRAL, self._sample_payload())

        self.assertTrue(any("発注失敗: 20260212_東京_02R 入力処理でエラーが発生しました" in line for line in logs))
        self.assertTrue(any("発注失敗詳細:" in line and "debug:" in line for line in logs))

if __name__ == "__main__":
    unittest.main()
