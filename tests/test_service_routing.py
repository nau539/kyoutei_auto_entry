import json
import queue
import time
import unittest
from datetime import datetime
from unittest import mock

import secrets_local
from config import AppSettings
from service import AutoEntryService, IpatEntryError


class ServiceRoutingTests(unittest.TestCase):
    class _DummyExecutor:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        def prepare_vote_menu(self):
            return {"ok": True}

    def setUp(self):
        self._orig = {
            "DISCORD_CENTRAL_CHANNEL_IDS": list(getattr(secrets_local, "DISCORD_CENTRAL_CHANNEL_IDS", [])),
            "DISCORD_LOCAL_CHANNEL_IDS": list(getattr(secrets_local, "DISCORD_LOCAL_CHANNEL_IDS", [])),
            "DISCORD_ALLOWED_CHANNEL_IDS": list(getattr(secrets_local, "DISCORD_ALLOWED_CHANNEL_IDS", [])),
            "DISCORD_ALLOWED_GUILD_IDS": list(getattr(secrets_local, "DISCORD_ALLOWED_GUILD_IDS", [])),
        }

    def tearDown(self):
        for key, value in self._orig.items():
            setattr(secrets_local, key, list(value))

    def _set_channels(self, central, local, legacy):
        secrets_local.DISCORD_CENTRAL_CHANNEL_IDS = list(central)
        secrets_local.DISCORD_LOCAL_CHANNEL_IDS = list(local)
        secrets_local.DISCORD_ALLOWED_CHANNEL_IDS = list(legacy)
        secrets_local.DISCORD_ALLOWED_GUILD_IDS = []

    def _sample_payload(self):
        return {
            "race": {
                "date": "20260410",
                "venue_name": "大村",
                "race_num": 1,
                "race_id": "20260410_大村_01R",
            },
            "tickets": [
                {"market": "2連複", "combo": "1-2", "bet_yen": 500, "odds": 4.2},
            ],
        }

    def test_routes_to_central_queue_by_channel_id(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = True
        logs = []
        svc = AutoEntryService(settings, logs.append)

        svc._on_discord_message(
            {
                "content": json.dumps(self._sample_payload(), ensure_ascii=False),
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_PAYLOAD)
        self.assertIn("payload", envelope)
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_LOCAL].get_nowait()

    def test_routes_to_local_queue_by_channel_id(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = True
        logs = []
        svc = AutoEntryService(settings, logs.append)

        svc._on_discord_message(
            {
                "content": json.dumps(self._sample_payload(), ensure_ascii=False),
                "channel_id": "200",
                "parent_channel_id": "",
            }
        )

        command, envelope = svc._queues[svc.TARGET_LOCAL].get_nowait()
        self.assertEqual(command, svc.CMD_PAYLOAD)
        self.assertIn("payload", envelope)
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_CENTRAL].get_nowait()

    def test_unmapped_channel_is_skipped_when_mapping_is_defined(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = True
        logs = []
        svc = AutoEntryService(settings, logs.append)

        svc._on_discord_message(
            {
                "content": json.dumps(self._sample_payload(), ensure_ascii=False),
                "channel_id": "999",
                "parent_channel_id": "",
            }
        )

        self.assertTrue(any("割り当てに存在しません" in line for line in logs))
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_CENTRAL].get_nowait()
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_LOCAL].get_nowait()

    def test_local_route_executes_when_selectors_are_configured(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = True
        settings.entry.enable_central = False
        settings.entry.enable_local = True
        settings.entry.confirm_each_race = False
        settings.entry.show_ticket_preview_window = False
        logs = []
        svc = AutoEntryService(settings, logs.append)

        svc._execute_payload(svc.TARGET_LOCAL, self._sample_payload())

        self.assertFalse(any("地方セレクタ未設定" in line for line in logs))
        self.assertTrue(any("DRY-RUN" in line for line in logs))

    def test_legacy_channel_setting_falls_back_to_central(self):
        self._set_channels(central=[], local=[], legacy=["300"])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        logs = []
        svc = AutoEntryService(settings, logs.append)

        svc._on_discord_message(
            {
                "content": json.dumps(self._sample_payload(), ensure_ascii=False),
                "channel_id": "300",
                "parent_channel_id": "",
            }
        )

        command, _envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_PAYLOAD)

    def test_pre_race_candidates_is_logged_but_not_enqueued(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = True
        logs = []
        svc = AutoEntryService(settings, logs.append)

        payload = {
            "message_type": "pre_race_candidates",
            "is_provisional": True,
            "advisory": "事前候補です。オッズ変動で見送りになる場合があります。",
            "provider": "kyoutei",
            "source": "discord_text",
            "date": "20260302",
            "odds_provider": "official",
            "candidates": [
                {
                    "date": "20260302",
                    "race_id": "大村_2R",
                    "venue_name": "大村",
                    "race_num": 2,
                    "race_key16": "2420260302030002",
                    "start_time": "2026-03-02 11:22:00",
                }
            ],
        }
        svc._on_discord_message(
            {
                "content": json.dumps(payload, ensure_ascii=False),
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        self.assertTrue(any("事前候補受信" in line for line in logs))
        self.assertTrue(any("候補注記:" in line for line in logs))
        self.assertTrue(any("候補: 大村 2R 2026-03-02 11:22:00" in line for line in logs))
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_CENTRAL].get_nowait()
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_LOCAL].get_nowait()

    def test_pre_race_candidates_zero_is_logged_as_no_candidates(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = True
        logs = []
        svc = AutoEntryService(settings, logs.append)

        payload = {
            "message_type": "pre_race_candidates",
            "is_provisional": True,
            "advisory": "事前候補です。オッズ変動で見送りになる場合があります。",
            "provider": "kyoutei",
            "source": "discord_text",
            "date": "20260315",
            "odds_provider": "official",
            "candidate_count": 0,
            "candidates": [],
        }
        svc._on_discord_message(
            {
                "content": json.dumps(payload, ensure_ascii=False),
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        self.assertTrue(any("事前候補受信" in line for line in logs))
        self.assertTrue(any("候補なし" in line for line in logs))
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_CENTRAL].get_nowait()
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_LOCAL].get_nowait()

    def test_pre_race_candidates_plain_text_is_logged_but_not_enqueued(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = True
        logs = []
        svc = AutoEntryService(settings, logs.append)

        text = (
            "[競艇候補] 20260410\n"
            "候補 1件 / 方式 ml2f\n"
            "学習 20210101 - 20251231\n"
            "08:32 大村 1R 2連複 1-2 conf=0.880"
        )
        svc._on_discord_message(
            {
                "content": text,
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        self.assertTrue(any("事前候補受信" in line for line in logs))
        self.assertTrue(any("候補: 大村 1R" in line for line in logs))
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_CENTRAL].get_nowait()

    def test_entry_plain_text_is_enqueued(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        logs = []
        svc = AutoEntryService(settings, logs.append)

        text = (
            "[競艇通知] 大村 1R\n"
            "締切 08:32 / オッズ更新 08:31\n"
            "方式 ml2f (学習 20210101 - 20251231)\n"
            "2連複 1-2 conf=0.880 odds=2.40\n"
            "投資 4,200円 / 想定払戻 10,080円"
        )
        svc._on_discord_message(
            {
                "content": text,
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_PAYLOAD)
        payload = envelope.get("payload") or {}
        self.assertEqual(payload.get("race", {}).get("venue_name"), "大村")
        self.assertEqual(payload.get("tickets", [])[0].get("bet_yen"), 4200)

    def test_entry_plain_text_sanrenpuku_is_enqueued(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        logs = []
        svc = AutoEntryService(settings, logs.append)

        text = (
            "[競艇通知] 大村 1R\n"
            "締切 08:32 / オッズ更新 08:31\n"
            "方式 ml2f (学習 20210101 - 20251231)\n"
            "三連複 3-1-2 conf=0.880 odds=12.40\n"
            "投資 500円 / 想定払戻 6,200円"
        )
        svc._on_discord_message(
            {
                "content": text,
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_PAYLOAD)
        payload = envelope.get("payload") or {}
        ticket = payload.get("tickets", [])[0]
        self.assertEqual(ticket.get("market"), "三連複")
        self.assertEqual(ticket.get("combo"), "3-1-2")
        self.assertEqual(ticket.get("bet_yen"), 500)

    def test_entry_plain_text_sanrenpuku_extra_metrics_is_enqueued_for_daytime_slot(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.plan_tier = "bronze"
        settings.entry.tool_slots = ["daytime"]
        logs = []
        svc = AutoEntryService(settings, logs.append)

        text = (
            "[競艇通知] 宮島 12R\n"
            "締切 16:46 / オッズ更新 16:45\n"
            "方式 stable3f (学習 20210101 - 20251231)\n"
            "3連複 1-3-4 conf=0.878 odds=3.30 ev=2.90\n"
            "投資 3,100円 / 想定払戻 10,230円\n"
            "上位確率 1=0.961 3=0.878 4=0.785 6=0.473"
        )
        svc._on_discord_message(
            {
                "content": text,
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_PAYLOAD)
        payload = envelope.get("payload") or {}
        self.assertEqual(payload.get("tool_slot"), "daytime")
        ticket = payload.get("tickets", [])[0]
        self.assertEqual(ticket.get("market"), "3連複")
        self.assertEqual(ticket.get("combo"), "1-3-4")
        self.assertEqual(ticket.get("bet_yen"), 3100)

    def test_keirin_pre_race_candidates_is_skipped_by_sport_filter(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        logs = []
        svc = AutoEntryService(settings, logs.append)

        payload = {
            "message_type": "pre_race_candidates",
            "provider": "ipat",
            "date": "20260410",
            "requested_at": "2026-04-10 10:00:00",
            "odds_provider": "shared_model",
            "tool_slot": "daytime",
            "candidate_count": 1,
            "candidates": [
                {
                    "date": "20260410",
                    "race_id": "防府_1R",
                    "venue_name": "防府",
                    "race_num": 1,
                    "race_key16": "6320260410010001",
                    "start_time": "2026-04-10 10:45:00",
                }
            ],
        }
        svc._on_discord_message(
            {
                "content": json.dumps(payload, ensure_ascii=False),
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        self.assertTrue(any("見送り: 競技不一致: keirin" in line for line in logs))
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_CENTRAL].get_nowait()

    def test_pre_race_candidates_morning_zero_keeps_central_browser_open_at_8(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dry_run = False
        logs = []
        svc = AutoEntryService(settings, logs.append)
        executor = self._DummyExecutor()
        svc._executors[svc.TARGET_CENTRAL] = executor

        payload = {
            "message_type": "pre_race_candidates",
            "provider": "ipat",
            "date": "20260315",
            "requested_at": "2026-03-15 08:01:30",
            "odds_provider": "official",
            "filters": {"exclude_midnight": True},
            "candidate_count": 0,
            "candidates": [],
        }

        svc._on_pre_race_candidates(svc.TARGET_CENTRAL, payload)

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_CANDIDATE_CONTROL)
        self.assertFalse(executor.closed)

        svc._handle_candidate_browser_control(
            svc.TARGET_CENTRAL,
            envelope["payload"],
            candidate_count=envelope["candidate_count"],
        )

        self.assertFalse(executor.closed)
        self.assertIs(svc._executors[svc.TARGET_CENTRAL], executor)
        self.assertTrue(svc._central_candidate_pause_active)
        self.assertEqual(svc._central_candidate_pause_date, "20260315")
        self.assertTrue(any("08時モーニング候補なしのためブラウザは保持し、自動起動のみ停止します" in line for line in logs))

    def test_pre_race_candidates_daytime_zero_keeps_central_browser_open_at_10(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dry_run = False
        logs = []
        svc = AutoEntryService(settings, logs.append)
        executor = self._DummyExecutor()
        svc._executors[svc.TARGET_CENTRAL] = executor

        payload = {
            "message_type": "pre_race_candidates",
            "provider": "ipat",
            "date": "20260315",
            "requested_at": "2026-03-15 10:00:05",
            "odds_provider": "official",
            "tool_slot": "daytime",
            "filters": {"exclude_midnight": True},
            "candidate_count": 0,
            "candidates": [],
        }

        svc._on_pre_race_candidates(svc.TARGET_CENTRAL, payload)

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_CANDIDATE_CONTROL)

        svc._handle_candidate_browser_control(
            svc.TARGET_CENTRAL,
            envelope["payload"],
            candidate_count=envelope["candidate_count"],
        )

        self.assertFalse(executor.closed)
        self.assertIs(svc._executors[svc.TARGET_CENTRAL], executor)
        self.assertTrue(svc._central_candidate_pause_active)
        self.assertEqual(svc._central_candidate_pause_date, "20260315")
        self.assertTrue(any("10時日中候補なしのためブラウザは保持し、自動起動のみ停止します" in line for line in logs))

    def test_pre_race_candidates_declared_zero_count_is_prioritized_over_candidate_rows(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dry_run = False
        logs = []
        svc = AutoEntryService(settings, logs.append)
        executor = self._DummyExecutor()
        svc._executors[svc.TARGET_CENTRAL] = executor

        payload = {
            "message_type": "pre_race_candidates",
            "provider": "ipat",
            "date": "20260315",
            "requested_at": "2026-03-15 10:00:05",
            "odds_provider": "official",
            "tool_slot": "daytime",
            "filters": {"exclude_midnight": True},
            "candidate_count": 0,
            "candidates": [
                {
                    "date": "20260315",
                    "venue_name": "戸田",
                    "race_num": 2,
                    "race_key16": "0220260315030002",
                    "start_time": "2026-03-15 13:05:00",
                }
            ],
        }

        svc._on_pre_race_candidates(svc.TARGET_CENTRAL, payload)

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_CANDIDATE_CONTROL)
        self.assertEqual(envelope["candidate_count"], 0)

        svc._handle_candidate_browser_control(
            svc.TARGET_CENTRAL,
            envelope["payload"],
            candidate_count=envelope["candidate_count"],
        )

        self.assertFalse(executor.closed)
        self.assertIs(svc._executors[svc.TARGET_CENTRAL], executor)
        self.assertTrue(svc._central_candidate_pause_active)
        self.assertEqual(svc._central_candidate_pause_date, "20260315")
        self.assertTrue(any("事前候補受信 [日中]: date=20260315 races=0 odds=official" in line for line in logs))
        self.assertTrue(any("候補なし" in line for line in logs))
        self.assertFalse(any("候補: 戸田 2R 2026-03-15 13:05:00" in line for line in logs))
        self.assertTrue(any("10時日中候補なしのためブラウザは保持し、自動起動のみ停止します" in line for line in logs))

    def test_pre_race_candidates_daytime_positive_restarts_central_browser_at_10(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dry_run = False
        logs = []
        svc = AutoEntryService(settings, logs.append)
        old_executor = self._DummyExecutor()
        svc._executors[svc.TARGET_CENTRAL] = old_executor
        svc._central_candidate_pause_active = True
        svc._central_candidate_pause_date = "20260315"
        svc._central_schedule_now = lambda: datetime(2026, 3, 15, 10, 0, 5)  # type: ignore[method-assign]

        new_executor = self._DummyExecutor()
        with mock.patch.object(svc, "_get_executor", return_value=new_executor):
            with mock.patch.object(new_executor, "prepare_vote_menu", return_value={"ok": True}):
                payload = {
                    "message_type": "pre_race_candidates",
                    "provider": "ipat",
                    "date": "20260315",
                    "requested_at": "2026-03-15 10:00:05",
                    "odds_provider": "official",
                    "filters": {"exclude_midnight": True},
                    "tool_slot": "daytime",
                    "candidate_count": 2,
                    "candidates": [
                        {
                            "date": "20260315",
                            "venue_name": "戸田",
                            "race_num": 2,
                            "race_key16": "0220260315030002",
                            "start_time": "2026-03-15 13:05:00",
                        }
                    ],
                }
                svc._on_pre_race_candidates(svc.TARGET_CENTRAL, payload)

                command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
                self.assertEqual(command, svc.CMD_CANDIDATE_CONTROL)

                svc._handle_candidate_browser_control(
                    svc.TARGET_CENTRAL,
                    envelope["payload"],
                    candidate_count=envelope["candidate_count"],
                )

        self.assertTrue(old_executor.closed)
        self.assertFalse(svc._central_candidate_pause_active)
        self.assertEqual(svc._central_candidate_pause_date, "20260315")
        self.assertTrue(any("10時日中候補ありのためブラウザを起動し直しました" in line for line in logs))

    def test_pre_race_candidates_daytime_positive_restarts_only_once_per_slot(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dry_run = False
        logs = []
        svc = AutoEntryService(settings, logs.append)
        old_executor = self._DummyExecutor()
        svc._executors[svc.TARGET_CENTRAL] = old_executor
        svc._central_candidate_pause_active = True
        svc._central_candidate_pause_date = "20260315"
        svc._central_schedule_now = lambda: datetime(2026, 3, 15, 10, 0, 5)  # type: ignore[method-assign]

        new_executor = self._DummyExecutor()
        prepare_calls = {"count": 0}

        def _prepare_vote_menu():
            prepare_calls["count"] += 1
            return {"ok": True}

        payload = {
            "message_type": "pre_race_candidates",
            "provider": "kyoutei",
            "source": "discord_text",
            "date": "20260315",
            "requested_at": "2026-03-15 10:00:05",
            "odds_provider": "official",
            "tool_slot": "daytime",
            "candidate_count": 2,
            "candidates": [
                {
                    "date": "20260315",
                    "venue_name": "戸田",
                    "race_num": 2,
                    "race_key16": "0220260315030002",
                    "start_time": "2026-03-15 13:05:00",
                }
            ],
        }

        with mock.patch.object(svc, "_get_executor", return_value=new_executor):
            with mock.patch.object(new_executor, "prepare_vote_menu", side_effect=_prepare_vote_menu):
                svc._handle_candidate_browser_control(svc.TARGET_CENTRAL, payload, candidate_count=2)
                svc._handle_candidate_browser_control(svc.TARGET_CENTRAL, payload, candidate_count=2)

        self.assertTrue(old_executor.closed)
        self.assertEqual(prepare_calls["count"], 1)
        self.assertEqual(sum("10時日中候補ありのためブラウザを起動し直しました" in line for line in logs), 1)

    def test_pre_race_candidates_midnight_positive_restarts_central_browser_at_18(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dry_run = False
        logs = []
        svc = AutoEntryService(settings, logs.append)
        old_executor = self._DummyExecutor()
        svc._executors[svc.TARGET_CENTRAL] = old_executor
        svc._central_candidate_pause_active = True
        svc._central_candidate_pause_date = "20260315"
        svc._central_schedule_now = lambda: datetime(2026, 3, 15, 18, 0, 5)  # type: ignore[method-assign]

        new_executor = self._DummyExecutor()
        with mock.patch.object(svc, "_get_executor", return_value=new_executor):
            with mock.patch.object(new_executor, "prepare_vote_menu", return_value={"ok": True}):
                payload = {
                    "message_type": "pre_race_candidates",
                    "provider": "ipat",
                    "date": "20260315",
                    "requested_at": "2026-03-15 18:00:05",
                    "odds_provider": "official",
                    "filters": {"midnight_only": True},
                    "candidate_count": 1,
                    "candidates": [
                        {
                            "date": "20260315",
                            "venue_name": "若松",
                            "race_num": 1,
                            "race_key16": "2020260313030001",
                            "start_time": "2026-03-15 20:40:00",
                        }
                    ],
                }
                svc._on_pre_race_candidates(svc.TARGET_CENTRAL, payload)

                command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
                self.assertEqual(command, svc.CMD_CANDIDATE_CONTROL)
                self.assertFalse(old_executor.closed)

                svc._handle_candidate_browser_control(
                    svc.TARGET_CENTRAL,
                    envelope["payload"],
                    candidate_count=envelope["candidate_count"],
                )

        self.assertTrue(old_executor.closed)
        self.assertFalse(svc._central_candidate_pause_active)
        self.assertEqual(svc._central_candidate_pause_date, "20260315")
        self.assertTrue(any("18時ミッドナイト候補ありのためブラウザを起動し直しました" in line for line in logs))

    def test_pre_race_candidates_midnight_restart_logs_failure_detail(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dry_run = False
        logs = []
        svc = AutoEntryService(settings, logs.append)
        old_executor = self._DummyExecutor()
        svc._executors[svc.TARGET_CENTRAL] = old_executor
        svc._central_candidate_pause_active = True
        svc._central_candidate_pause_date = "20260315"
        svc._central_schedule_now = lambda: datetime(2026, 3, 15, 18, 0, 5)  # type: ignore[method-assign]

        new_executor = self._DummyExecutor()
        with mock.patch.object(svc, "_get_executor", return_value=new_executor):
            with mock.patch.object(
                new_executor,
                "prepare_vote_menu",
                side_effect=IpatEntryError("競艇ログインフォームを検出できませんでした"),
            ):
                svc._restart_central_browser_by_candidates(date8="20260315", slot="midnight")

        self.assertTrue(old_executor.closed)
        self.assertTrue(any("18時ミッドナイト候補ありでブラウザ起動に失敗しました" in line for line in logs))
        self.assertTrue(any("候補連動詳細: 競艇ログインフォームを検出できませんでした" in line for line in logs))

    def test_entry_payload_is_accepted_even_when_dispatch_mode_differs(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dispatch_mode = "all_stable"
        logs = []
        svc = AutoEntryService(settings, logs.append)

        payload = self._sample_payload()
        payload["strategy_name"] = "全帯基準"
        payload["strategy_code"] = "all_base"
        svc._on_discord_message(
            {
                "content": json.dumps(payload, ensure_ascii=False),
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_PAYLOAD)
        self.assertEqual(envelope["payload"].get("strategy_code"), "all_base")
        self.assertFalse(any("受信戦略不一致" in line for line in logs))

    def test_entry_payload_is_accepted_when_dispatch_mode_matches(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dispatch_mode = "all_attack"
        logs = []
        svc = AutoEntryService(settings, logs.append)

        payload = self._sample_payload()
        payload["strategy_name"] = "全帯勝負"
        payload["strategy_code"] = "all_attack"
        svc._on_discord_message(
            {
                "content": json.dumps(payload, ensure_ascii=False),
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_PAYLOAD)
        self.assertEqual(envelope["payload"].get("strategy_code"), "all_attack")

    def test_entry_payload_is_accepted_even_when_legacy_all_setting_exists(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dispatch_mode = "all"
        logs = []
        svc = AutoEntryService(settings, logs.append)

        payload = self._sample_payload()
        payload["strategy_name"] = "全帯勝負"
        payload["strategy_code"] = "all_attack"
        svc._on_discord_message(
            {
                "content": json.dumps(payload, ensure_ascii=False),
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_PAYLOAD)
        self.assertEqual(envelope["payload"].get("strategy_code"), "all_attack")
        self.assertFalse(any("受信戦略不一致" in line for line in logs))

    def test_entry_payload_legacy_strategy_is_mapped_to_midnight_family(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.dispatch_mode = "midnight_attack"
        logs = []
        svc = AutoEntryService(settings, logs.append)

        payload = self._sample_payload()
        payload["strategy_name"] = "勝負"
        payload["strategy_code"] = "attack"
        svc._on_discord_message(
            {
                "content": json.dumps(payload, ensure_ascii=False),
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        command, envelope = svc._queues[svc.TARGET_CENTRAL].get_nowait()
        self.assertEqual(command, svc.CMD_PAYLOAD)
        self.assertEqual(envelope["payload"].get("strategy_code"), "midnight_attack")

    def test_entry_payload_is_skipped_when_selected_tool_slot_differs(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.plan_tier = "bronze"
        settings.entry.tool_slots = ["morning"]
        logs = []
        svc = AutoEntryService(settings, logs.append)

        payload = self._sample_payload()
        payload["strategy_name"] = "日中収益主軸"
        payload["strategy_code"] = "daytime_consistent_earnings"
        svc._on_discord_message(
            {
                "content": json.dumps(payload, ensure_ascii=False),
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        self.assertTrue(any("選択外ツール: 日中" in line for line in logs))
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_CENTRAL].get_nowait()

    def test_pre_race_candidates_is_skipped_when_selected_tool_slot_differs(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.plan_tier = "bronze"
        settings.entry.tool_slots = ["midnight"]
        logs = []
        svc = AutoEntryService(settings, logs.append)

        payload = {
            "message_type": "pre_race_candidates",
            "provider": "kyoutei",
            "source": "discord_text",
            "date": "20260315",
            "requested_at": "2026-03-15 08:00:00",
            "odds_provider": "official",
            "tool_slot": "morning",
            "candidate_count": 0,
            "candidates": [],
        }
        svc._on_discord_message(
            {
                "content": json.dumps(payload, ensure_ascii=False),
                "channel_id": "100",
                "parent_channel_id": "",
            }
        )

        self.assertTrue(any("選択外ツール: モーニング" in line for line in logs))
        with self.assertRaises(queue.Empty):
            svc._queues[svc.TARGET_CENTRAL].get_nowait()

    def test_replay_pre_race_candidates_from_history(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        logs = []
        svc = AutoEntryService(settings, logs.append)
        today = datetime.now().strftime("%Y%m%d")

        class _DummyDiscord:
            def fetch_recent_messages(self, _channel_id, *, limit=50, timeout_sec=10.0):
                del limit, timeout_sec
                return [
                    {
                        "id": "1",
                        "content": json.dumps(
                            {
                                "message_type": "pre_race_candidates",
                                "provider": "kyoutei",
                                "source": "discord_text",
                                "date": today,
                                "odds_provider": "official",
                                "candidates": [
                                    {
                                        "date": today,
                                        "race_id": "大村_2R",
                                        "venue_name": "大村",
                                        "race_num": 2,
                                        "race_key16": "2420260302030002",
                                        "start_time": "2026-03-02 11:22:00",
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                        "channel_id": "100",
                        "parent_channel_id": "",
                        "guild_id": "",
                    }
                ]

        svc._discord = _DummyDiscord()  # type: ignore[assignment]
        svc._replay_pre_race_candidates_from_history()

        self.assertTrue(any("事前候補受信" in line for line in logs))
        self.assertTrue(any("起動時候補再取得: payload=1件" in line for line in logs))

    def test_local_keepalive_refreshes_when_due(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.enable_local = True
        settings.local_ipat.submit_enabled = True
        logs = []
        svc = AutoEntryService(settings, logs.append)

        class _DummyExecutor:
            def __init__(self):
                self.calls = 0

            def refresh_local_info(self):
                self.calls += 1
                return {"ok": True, "status": "refreshed"}

        dummy = _DummyExecutor()
        svc._executors[svc.TARGET_LOCAL] = dummy
        svc._next_local_keepalive_monotonic = time.monotonic() - 1.0

        svc._maybe_keepalive_local()

        self.assertEqual(dummy.calls, 1)
        self.assertTrue(any("待機維持: 10分経過のため情報更新を実行しました" in line for line in logs))

    def test_central_keepalive_refreshes_when_due(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.enable_central = True
        logs = []
        svc = AutoEntryService(settings, logs.append)

        class _DummyExecutor:
            def __init__(self):
                self.calls = 0

            def refresh_central_info(self):
                self.calls += 1
                return {"ok": True, "status": "refreshed"}

        dummy = _DummyExecutor()
        svc._executors[svc.TARGET_CENTRAL] = dummy
        svc._next_central_keepalive_monotonic = time.monotonic() - 1.0

        svc._maybe_keepalive_central()

        self.assertEqual(dummy.calls, 1)
        self.assertTrue(any("待機維持: 10分経過のため中央投票サイトを更新しました" in line for line in logs))

    def test_local_keepalive_runs_even_when_submit_disabled(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.enable_local = True
        settings.local_ipat.submit_enabled = False
        logs = []
        svc = AutoEntryService(settings, logs.append)

        class _DummyExecutor:
            def __init__(self):
                self.calls = 0

            def refresh_local_info(self):
                self.calls += 1
                return {"ok": True, "status": "refreshed"}

        dummy = _DummyExecutor()
        svc._executors[svc.TARGET_LOCAL] = dummy
        svc._next_local_keepalive_monotonic = time.monotonic() - 1.0

        svc._maybe_keepalive_local()

        self.assertEqual(dummy.calls, 1)
        self.assertTrue(any("待機維持: 10分経過のため情報更新を実行しました" in line for line in logs))

    def test_central_schedule_starts_browser_in_active_window(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.enable_central = True
        settings.entry.central_schedule_enabled = True
        settings.entry.central_schedule_open_time = "10:00"
        settings.entry.central_schedule_close_time = "21:00"
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        logs = []
        svc = AutoEntryService(settings, logs.append)

        class _DummyExecutor:
            def __init__(self):
                self.prepare_calls = 0

            def prepare_vote_menu(self):
                self.prepare_calls += 1
                return {"ok": True, "status": "ready"}

        dummy = _DummyExecutor()

        def _fake_get_executor(_target):
            svc._executors[svc.TARGET_CENTRAL] = dummy
            return dummy

        svc._get_executor = _fake_get_executor  # type: ignore[method-assign]
        svc._central_schedule_now = lambda: datetime(2026, 3, 2, 10, 5, 0)  # type: ignore[method-assign]

        svc._maybe_schedule_central_session()

        self.assertEqual(dummy.prepare_calls, 1)
        self.assertTrue(any("待機スケジュール: 開始時刻帯のためブラウザを起動しました" in line for line in logs))

    def test_central_schedule_waits_until_startup_history_replay_finishes(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.enable_central = True
        settings.entry.central_schedule_enabled = True
        settings.entry.central_schedule_open_time = "10:00"
        settings.entry.central_schedule_close_time = "21:00"
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        logs = []
        svc = AutoEntryService(settings, logs.append)

        class _DummyExecutor:
            def __init__(self):
                self.prepare_calls = 0

            def prepare_vote_menu(self):
                self.prepare_calls += 1
                return {"ok": True, "status": "ready"}

        dummy = _DummyExecutor()

        def _fake_get_executor(_target):
            svc._executors[svc.TARGET_CENTRAL] = dummy
            return dummy

        svc._get_executor = _fake_get_executor  # type: ignore[method-assign]
        svc._startup_history_replay_active = True
        svc._central_schedule_now = lambda: datetime(2026, 3, 2, 10, 5, 0)  # type: ignore[method-assign]

        svc._maybe_schedule_central_session()

        self.assertEqual(dummy.prepare_calls, 0)
        self.assertFalse(any("待機スケジュール: 開始時刻帯のためブラウザを起動しました" in line for line in logs))

    def test_central_schedule_logs_failure_detail_on_prepare_error(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.enable_central = True
        settings.entry.central_schedule_enabled = True
        settings.entry.central_schedule_open_time = "10:00"
        settings.entry.central_schedule_close_time = "21:00"
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        logs = []
        svc = AutoEntryService(settings, logs.append)

        class _DummyExecutor:
            def prepare_vote_menu(self):
                raise IpatEntryError("競輪ログイン後の状態確認に失敗しました")

        dummy = _DummyExecutor()

        def _fake_get_executor(_target):
            svc._executors[svc.TARGET_CENTRAL] = dummy
            return dummy

        svc._get_executor = _fake_get_executor  # type: ignore[method-assign]
        svc._central_schedule_now = lambda: datetime(2026, 3, 2, 10, 5, 0)  # type: ignore[method-assign]

        svc._maybe_schedule_central_session()

        self.assertTrue(any("待機スケジュール: 自動起動に失敗しました" in line for line in logs))
        self.assertTrue(any("待機スケジュール詳細: 競輪ログイン後の状態確認に失敗しました" in line for line in logs))

    def test_central_schedule_stops_browser_outside_window(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.enable_central = True
        settings.entry.central_schedule_enabled = True
        settings.entry.central_schedule_open_time = "10:00"
        settings.entry.central_schedule_close_time = "21:00"
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        logs = []
        svc = AutoEntryService(settings, logs.append)

        class _DummyExecutor:
            def __init__(self):
                self.close_calls = 0

            def close(self):
                self.close_calls += 1

        dummy = _DummyExecutor()
        svc._executors[svc.TARGET_CENTRAL] = dummy
        svc._central_schedule_now = lambda: datetime(2026, 3, 2, 21, 5, 0)  # type: ignore[method-assign]

        svc._maybe_schedule_central_session()

        self.assertEqual(dummy.close_calls, 1)
        self.assertIsNone(svc._executors[svc.TARGET_CENTRAL])
        self.assertTrue(any("待機スケジュール: 起動時間外のためブラウザを停止しました" in line for line in logs))

    def test_central_prepare_is_skipped_outside_window_and_closes_browser(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.enable_central = True
        settings.entry.central_schedule_enabled = True
        settings.entry.central_schedule_open_time = "10:00"
        settings.entry.central_schedule_close_time = "21:00"
        settings.ipat.login_url = "https://ib.mbrace.or.jp/"
        logs = []
        svc = AutoEntryService(settings, logs.append)

        class _DummyExecutor:
            def __init__(self):
                self.close_calls = 0
                self.prepare_calls = 0

            def close(self):
                self.close_calls += 1

            def prepare_vote_menu(self):
                self.prepare_calls += 1
                return {"ok": True}

        dummy = _DummyExecutor()
        svc._executors[svc.TARGET_CENTRAL] = dummy
        svc._central_schedule_now = lambda: datetime(2026, 3, 2, 9, 59, 0)  # type: ignore[method-assign]

        svc._handle_prepare_ipat(svc.TARGET_CENTRAL)

        self.assertEqual(dummy.close_calls, 1)
        self.assertEqual(dummy.prepare_calls, 0)
        self.assertIsNone(svc._executors[svc.TARGET_CENTRAL])
        self.assertTrue(any("見送り: 起動時間外のため事前準備を実行しません" in line for line in logs))

    def test_central_payload_is_skipped_outside_window_without_browser_start(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.enable_central = True
        settings.entry.central_schedule_enabled = True
        settings.entry.central_schedule_open_time = "10:00"
        settings.entry.central_schedule_close_time = "21:00"
        settings.ipat.login_url = "https://ib.mbrace.or.jp/"
        logs = []
        svc = AutoEntryService(settings, logs.append)
        svc._central_schedule_now = lambda: datetime(2026, 3, 2, 21, 1, 0)  # type: ignore[method-assign]

        svc._execute_payload(svc.TARGET_CENTRAL, self._sample_payload())

        self.assertIsNone(svc._executors[svc.TARGET_CENTRAL])
        self.assertTrue(any("見送り: 起動時間外のためブラウザを起動しません" in line for line in logs))

    def test_local_keepalive_logs_debug_when_refresh_button_not_found(self):
        self._set_channels(central=["100"], local=["200"], legacy=[])
        settings = AppSettings()
        settings.entry.dry_run = False
        settings.entry.enable_local = True
        settings.local_ipat.submit_enabled = True
        logs = []
        svc = AutoEntryService(settings, logs.append)

        class _DummyExecutor:
            def refresh_local_info(self):
                return {
                    "ok": True,
                    "status": "ready_no_refresh_button",
                    "debug_before": {
                        "url": "https://www.spat4.jp/keiba/pc",
                        "popup_visible": True,
                        "mail_notice_visible": False,
                    },
                }

        svc._executors[svc.TARGET_LOCAL] = _DummyExecutor()
        svc._next_local_keepalive_monotonic = time.monotonic() - 1.0

        svc._maybe_keepalive_local()

        self.assertTrue(any("待機維持デバッグ: 情報更新ボタン未検出" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
