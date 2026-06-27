import unittest

from payload_parser import extract_payloads_from_text


class PayloadParserTests(unittest.TestCase):
    def test_extract_plain_json(self):
        text = '{"race":{"date":"20260210","venue_name":"東京","race_num":3},"tickets":[{"market":"単勝","combo":"7","bet_yen":500}]}'
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["race"]["venue_name"], "東京")

    def test_extract_fenced_json(self):
        text = "通知\n```json\n{\"race\":{\"date\":\"20260210\",\"venue_name\":\"京都\",\"race_num\":1},\"tickets\":[{\"market\":\"馬連\",\"combo\":\"7-15\",\"bet_yen\":700}]}\n```"
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tickets"][0]["combo"], "7-15")

    def test_ignore_invalid_payload(self):
        text = '{"race":{"date":"20260210","venue_name":"東京","race_num":3},"tickets":[{"market":"単勝","combo":"7","bet_yen":0}]}'
        rows = extract_payloads_from_text(text)
        self.assertEqual(rows, [])

    def test_extract_ticket_with_odds(self):
        text = (
            '{"race":{"date":"20260210","venue_name":"東京","race_num":3},'
            '"tickets":[{"market":"馬連","combo":"7-15","bet_yen":800,"odds":12.4}]}'
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(float(rows[0]["tickets"][0]["odds"]), 12.4, places=2)

    def test_extract_pre_race_candidates_payload(self):
        text = (
            '{"message_type":"pre_race_candidates","provider":"ipat","date":"20260302","is_provisional":true,'
            '"advisory":"事前候補です。オッズ変動により見送りあり","requested_at":"2026-03-02 08:00:00",'
            '"odds_provider":"official","candidates":['
            '{"date":"20260302","venue_name":"和歌山","race_num":2,"race_id":"和歌山_2R",'
            '"race_key16":"5520260302030002","start_time":"2026-03-02 11:22:00"}]}'
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message_type"], "pre_race_candidates")
        self.assertEqual(rows[0]["candidates"][0]["venue_name"], "和歌山")
        self.assertTrue(bool(rows[0]["is_provisional"]))
        self.assertIn("オッズ変動", str(rows[0]["advisory"]))
        self.assertEqual(rows[0]["tool_slot"], "morning")

    def test_extract_pre_race_candidates_payload_with_zero_candidates(self):
        text = (
            '{"message_type":"pre_race_candidates","provider":"ipat","date":"20260315","is_provisional":true,'
            '"advisory":"事前候補です。オッズ変動により見送りあり",'
            '"odds_provider":"official","candidate_count":0,"candidates":[]}'
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message_type"], "pre_race_candidates")
        self.assertEqual(rows[0]["candidate_count"], 0)
        self.assertEqual(rows[0]["candidates"], [])

    def test_extract_entry_payload_with_strategy(self):
        text = (
            '{"strategy_name":"ミッド基準","strategy_code":"midnight_base",'
            '"race":{"date":"20260210","venue_name":"東京","race_num":3},'
            '"tickets":[{"market":"馬連","combo":"7-15","bet_yen":800,"odds":12.4}]}'
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["strategy_name"], "ミッド基準")
        self.assertEqual(rows[0]["strategy_code"], "midnight_base")
        self.assertEqual(rows[0]["tool_slot"], "midnight")

    def test_extract_entry_payload_with_legacy_strategy_alias(self):
        text = (
            '{"strategy_name":"守り","strategy_code":"defense",'
            '"race":{"date":"20260210","venue_name":"東京","race_num":3},'
            '"tickets":[{"market":"馬連","combo":"7-15","bet_yen":800,"odds":12.4}]}'
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["strategy_code"], "midnight_stable")
        self.assertEqual(rows[0]["tool_slot"], "midnight")

    def test_extract_entry_payload_with_unknown_strategy_code(self):
        text = (
            '{"strategy_name":"モーニング収益主軸","strategy_code":"morning_consistent_earnings",'
            '"race":{"date":"20260210","venue_name":"東京","race_num":3},'
            '"tickets":[{"market":"馬連","combo":"7-15","bet_yen":800,"odds":12.4}]}'
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["strategy_code"], "morning_consistent_earnings")
        self.assertEqual(rows[0]["tool_slot"], "morning")

    def test_extract_kyoutei_candidate_text(self):
        text = (
            "[競艇候補] 20260410\n"
            "候補 1件 / 方式 ml2f\n"
            "学習 20210101 - 20251231\n"
            "08:32 大村 1R 2連複 1-2 conf=0.880"
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message_type"], "pre_race_candidates")
        self.assertEqual(rows[0]["date"], "20260410")
        self.assertEqual(rows[0]["candidate_count"], 1)
        self.assertEqual(rows[0]["tool_slot"], "morning")
        self.assertEqual(rows[0]["candidates"][0]["venue_name"], "大村")
        self.assertEqual(rows[0]["candidates"][0]["race_num"], 1)

    def test_extract_kyoutei_candidate_text_with_zero_candidates(self):
        text = (
            "[競艇候補] 20260410\n"
            "候補 0件 / 方式 ml2f\n"
            "学習 20210101 - 20251231\n"
            "候補なし"
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message_type"], "pre_race_candidates")
        self.assertEqual(rows[0]["candidate_count"], 0)
        self.assertEqual(rows[0]["candidates"], [])

    def test_extract_kyoutei_entry_text(self):
        text = (
            "[競艇通知] 大村 1R\n"
            "締切 08:32 / オッズ更新 08:31\n"
            "方式 ml2f (学習 20210101 - 20251231)\n"
            "2連複 1-2 conf=0.880 odds=2.40\n"
            "投資 4,200円 / 想定払戻 10,080円"
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message_type"], "entry_tickets")
        self.assertEqual(rows[0]["race"]["venue_name"], "大村")
        self.assertEqual(rows[0]["race"]["race_num"], 1)
        self.assertEqual(rows[0]["tickets"][0]["market"], "2連複")
        self.assertEqual(rows[0]["tickets"][0]["combo"], "1-2")
        self.assertEqual(rows[0]["tickets"][0]["bet_yen"], 4200)
        self.assertAlmostEqual(float(rows[0]["tickets"][0]["odds"]), 2.4, places=2)
        self.assertEqual(rows[0]["tool_slot"], "morning")

    def test_extract_kyoutei_entry_text_with_sanrenpuku(self):
        text = (
            "[競艇通知] 大村 1R\n"
            "締切 08:32 / オッズ更新 08:31\n"
            "方式 ml2f (学習 20210101 - 20251231)\n"
            "三連複 3-1-2 conf=0.880 odds=12.40\n"
            "投資 500円 / 想定払戻 6,200円"
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message_type"], "entry_tickets")
        self.assertEqual(rows[0]["race"]["venue_name"], "大村")
        self.assertEqual(rows[0]["tickets"][0]["market"], "三連複")
        self.assertEqual(rows[0]["tickets"][0]["combo"], "3-1-2")
        self.assertEqual(rows[0]["tickets"][0]["bet_yen"], 500)
        self.assertEqual(rows[0]["tool_slot"], "morning")

    def test_extract_kyoutei_entry_text_with_extra_metrics(self):
        text = (
            "[競艇通知] 宮島 12R\n"
            "締切 16:46 / オッズ更新 16:45\n"
            "方式 stable3f (学習 20210101 - 20251231)\n"
            "3連複 1-3-4 conf=0.878 odds=3.30 ev=2.90\n"
            "投資 3,100円 / 想定払戻 10,230円\n"
            "上位確率 1=0.961 3=0.878 4=0.785 6=0.473"
        )
        rows = extract_payloads_from_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message_type"], "entry_tickets")
        self.assertEqual(rows[0]["race"]["venue_name"], "宮島")
        self.assertEqual(rows[0]["race"]["race_num"], 12)
        self.assertEqual(rows[0]["race"]["start_time"], f'{rows[0]["race"]["date"][:4]}-{rows[0]["race"]["date"][4:6]}-{rows[0]["race"]["date"][6:8]} 16:46:00')
        self.assertEqual(rows[0]["strategy_name"], "stable3f (学習 20210101 - 20251231)")
        self.assertEqual(rows[0]["tool_slot"], "daytime")
        self.assertEqual(rows[0]["tickets"][0]["market"], "3連複")
        self.assertEqual(rows[0]["tickets"][0]["combo"], "1-3-4")
        self.assertEqual(rows[0]["tickets"][0]["bet_yen"], 3100)
        self.assertAlmostEqual(float(rows[0]["tickets"][0]["odds"]), 3.3, places=2)


if __name__ == "__main__":
    unittest.main()
