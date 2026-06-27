from __future__ import annotations

import math
from typing import Any, Dict, List


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_odds(value: Any) -> float:
    odds = _safe_float(value, -1.0)
    return float(odds) if odds > 0 else -1.0


def floor_100(value: float) -> int:
    n = int(value // 100.0) * 100
    return max(0, int(n))


def round_100(value: float) -> int:
    if value <= 0:
        return 0
    n = int(round(float(value) / 100.0)) * 100
    return max(0, int(n))


def sum_ticket_yen(tickets: List[Dict[str, Any]]) -> int:
    return int(sum(max(0, _safe_int(t.get("bet_yen"), 0)) for t in tickets or []))


def apply_raffine_distribution(
    tickets: List[Dict[str, Any]],
    budget_yen: int = 0,
) -> List[Dict[str, Any]]:
    rows = [dict(t) for t in tickets or []]
    if not rows:
        return []

    base_budget = int(sum_ticket_yen(rows))
    budget = int(budget_yen) if int(budget_yen) > 0 else int(base_budget)
    if budget <= 0:
        return rows

    valid_indexes = [idx for idx, row in enumerate(rows) if _safe_odds(row.get("odds")) > 0]
    if not valid_indexes:
        return rows

    fixed_budget = int(sum(_safe_int(rows[idx].get("bet_yen"), 0) for idx in range(len(rows)) if idx not in valid_indexes))
    target_budget = max(0, int(budget - fixed_budget))
    if target_budget <= 0:
        return rows

    odds_map = {idx: _safe_odds(rows[idx].get("odds")) for idx in valid_indexes}
    inv_sum = sum(1.0 / max(1e-9, odds_map[idx]) for idx in valid_indexes)
    if inv_sum <= 0:
        return rows

    target_return = float(target_budget) / inv_sum
    bets: Dict[int, int] = {idx: 0 for idx in valid_indexes}
    for idx in valid_indexes:
        raw = target_return / max(1e-9, odds_map[idx])
        bets[idx] = floor_100(raw)

    remain = int(budget - fixed_budget - sum(bets.values()))
    while remain >= 100:
        pick = min(valid_indexes, key=lambda i: float(odds_map[i]) * float(bets[i]))
        bets[pick] += 100
        remain -= 100

    for idx in valid_indexes:
        rows[idx]["bet_yen"] = int(max(0, bets.get(idx, 0)))
    return rows


def apply_target_payout_distribution(
    tickets: List[Dict[str, Any]],
    target_payout_yen: int = 10000,
    min_ticket_yen: int = 100,
) -> List[Dict[str, Any]]:
    rows = [dict(t) for t in tickets or []]
    if not rows:
        return []

    target = max(0, _safe_int(target_payout_yen, 10000))
    if target <= 0:
        return rows
    min_ticket = max(100, _safe_int(min_ticket_yen, 100))

    for idx, row in enumerate(rows):
        odds = _safe_odds(row.get("odds"))
        if odds <= 0:
            continue
        raw = float(target) / max(1e-9, odds)
        bet = int(math.ceil(raw / 100.0)) * 100
        # 目標払戻を「必ず超える」条件に合わせる（同額は不可）。
        while float(odds) * float(bet) <= float(target):
            bet += 100
        if bet < min_ticket:
            bet = min_ticket
        rows[idx]["bet_yen"] = int(bet)
    return rows


def scale_to_budget(tickets: List[Dict[str, Any]], budget_yen: int) -> List[Dict[str, Any]]:
    if budget_yen <= 0:
        return [dict(t) for t in tickets]
    rows = [dict(t) for t in tickets]
    total = sum_ticket_yen(rows)
    if total <= budget_yen:
        return rows

    factor = float(budget_yen) / float(total) if total > 0 else 0.0
    scaled: List[Dict[str, Any]] = []
    for row in rows:
        orig = max(0, _safe_int(row.get("bet_yen"), 0))
        val = floor_100(float(orig) * factor)
        if val <= 0:
            continue
        out = dict(row)
        out["bet_yen"] = int(val)
        out["_orig"] = int(orig)
        scaled.append(out)

    if not scaled:
        return []

    remain = floor_100(float(budget_yen - sum_ticket_yen(scaled)))
    while remain >= 100:
        scaled.sort(key=lambda x: (_safe_int(x.get("_orig"), 0) - _safe_int(x.get("bet_yen"), 0), _safe_int(x.get("_orig"), 0)), reverse=True)
        scaled[0]["bet_yen"] = _safe_int(scaled[0].get("bet_yen"), 0) + 100
        remain -= 100

    for row in scaled:
        row.pop("_orig", None)
    return scaled


def apply_entry_rules(
    tickets: List[Dict[str, Any]],
    ratio_pct: float = 100.0,
    min_ticket_yen: int = 100,
    ticket_cap_yen: int = 0,
    race_cap_yen: int = 0,
    max_tickets: int = 0,
) -> List[Dict[str, Any]]:
    ratio = max(0.0, float(_safe_float(ratio_pct, 100.0))) / 100.0
    ticket_min = max(100, _safe_int(min_ticket_yen, 100))

    rows: List[Dict[str, Any]] = []
    for t in tickets or []:
        market = str(t.get("market", "") or "").strip()
        combo = str(t.get("combo", "") or "").strip()
        base = max(0, _safe_int(t.get("bet_yen"), 0))
        if (not market) or (not combo) or base <= 0:
            continue
        val = floor_100(float(base) * ratio)
        if val < ticket_min:
            continue
        if ticket_cap_yen > 0:
            val = min(int(val), int(ticket_cap_yen))
            val = floor_100(float(val))
        if val <= 0:
            continue
        row = {"market": market, "combo": combo, "bet_yen": int(val)}
        odds = _safe_odds(t.get("odds"))
        if odds > 0:
            row["odds"] = float(odds)
        rows.append(row)

    if max_tickets > 0 and len(rows) > max_tickets:
        rows = rows[: max(0, int(max_tickets))]

    if race_cap_yen > 0:
        rows = scale_to_budget(rows, int(race_cap_yen))

    return [r for r in rows if _safe_int(r.get("bet_yen"), 0) >= ticket_min]
