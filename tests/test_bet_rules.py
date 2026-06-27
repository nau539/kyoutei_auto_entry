import unittest

from bet_rules import (
    apply_entry_rules,
    apply_raffine_distribution,
    apply_target_payout_distribution,
    sum_ticket_yen,
)


class BetRulesTests(unittest.TestCase):
    def test_apply_ratio_and_floor(self):
        tickets = [
            {"market": "単勝", "combo": "7", "bet_yen": 950},
            {"market": "馬連", "combo": "7-15", "bet_yen": 700},
        ]
        rows = apply_entry_rules(tickets, ratio_pct=50.0)
        self.assertEqual(rows[0]["bet_yen"], 400)
        self.assertEqual(rows[1]["bet_yen"], 300)

    def test_race_cap(self):
        tickets = [
            {"market": "単勝", "combo": "7", "bet_yen": 5000},
            {"market": "馬連", "combo": "7-15", "bet_yen": 1500},
            {"market": "ワイド", "combo": "7-15", "bet_yen": 3500},
        ]
        rows = apply_entry_rules(tickets, ratio_pct=100.0, race_cap_yen=3000)
        self.assertLessEqual(sum_ticket_yen(rows), 3000)
        self.assertGreater(len(rows), 0)

    def test_max_tickets(self):
        tickets = [
            {"market": "単勝", "combo": "7", "bet_yen": 5000},
            {"market": "馬連", "combo": "7-15", "bet_yen": 700},
            {"market": "馬連", "combo": "7-10", "bet_yen": 700},
        ]
        rows = apply_entry_rules(tickets, max_tickets=2)
        self.assertEqual(len(rows), 2)

    def test_preserve_odds_field(self):
        tickets = [
            {"market": "馬連", "combo": "7-15", "bet_yen": 900, "odds": 13.2},
        ]
        rows = apply_entry_rules(tickets, ratio_pct=100.0)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(float(rows[0]["odds"]), 13.2, places=2)

    def test_raffine_distribution_keeps_budget(self):
        tickets = [
            {"market": "単勝", "combo": "7", "bet_yen": 5000, "odds": 14.5},
            {"market": "ワイド", "combo": "7-13", "bet_yen": 1700, "odds": 177.8},
            {"market": "ワイド", "combo": "7-11", "bet_yen": 1700, "odds": 9.8},
        ]
        rows = apply_raffine_distribution(tickets, budget_yen=8400)
        self.assertEqual(sum_ticket_yen(rows), 8400)
        self.assertEqual(len(rows), 3)

    def test_target_payout_distribution_updates_each_ticket(self):
        tickets = [
            {"market": "単勝", "combo": "7", "bet_yen": 500, "odds": 5.0},
            {"market": "ワイド", "combo": "7-13", "bet_yen": 500, "odds": 20.0},
            {"market": "馬連", "combo": "7-11", "bet_yen": 500, "odds": 0},
        ]
        rows = apply_target_payout_distribution(tickets, target_payout_yen=10000)
        # 目標払戻を「超える」ように100円単位で繰り上げる。
        self.assertEqual(rows[0]["bet_yen"], 2100)
        self.assertEqual(rows[1]["bet_yen"], 600)
        # オッズ未設定・不正時は元金額を維持
        self.assertEqual(rows[2]["bet_yen"], 500)

    def test_target_payout_distribution_respects_minimum_unit(self):
        tickets = [
            {"market": "単勝", "combo": "1", "bet_yen": 300, "odds": 250.0},
        ]
        rows = apply_target_payout_distribution(tickets, target_payout_yen=10000)
        self.assertEqual(rows[0]["bet_yen"], 100)


if __name__ == "__main__":
    unittest.main()
