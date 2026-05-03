from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List

from product_profile import (
    infer_tool_slot_from_candidate_payload,
    infer_tool_slot_from_entry_payload,
)
from strategy_modes import normalize_strategy_code

JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.IGNORECASE | re.DOTALL)
KYOUTEI_BLOCK_HEADER_PATTERN = re.compile(r"(?m)^\[(?:競艇候補|競艇通知)\][^\n]*$")
KYOUTEI_CANDIDATE_HEADER_PATTERN = re.compile(r"^\[競艇候補\]\s*(?P<date8>\d{8})\s*$")
KYOUTEI_ENTRY_HEADER_PATTERN = re.compile(r"^\[競艇通知\]\s*(?P<venue>\S+)\s+(?P<race_num>\d{1,2})R\s*$")
KYOUTEI_CANDIDATE_COUNT_PATTERN = re.compile(r"^候補\s+(?P<count>\d+)件(?:\s*/\s*方式\s+(?P<strategy>\S+))?")
KYOUTEI_CANDIDATE_LINE_PATTERN = re.compile(
    r"^(?P<hhmm>\d{1,2}:\d{2})\s+(?P<venue>\S+)\s+(?P<race_num>\d{1,2})R"
    r"(?:\s+(?P<market>\S+)\s+(?P<combo>[0-9=\-]+)\s+conf=(?P<conf>[0-9.]+))?"
)
KYOUTEI_DEADLINE_PATTERN = re.compile(
    r"^締切\s+(?P<deadline>\d{1,2}:\d{2}|-)\s*/\s*オッズ更新\s+(?P<odds_updated>\d{1,2}:\d{2}|-)"
)
KYOUTEI_TICKET_PATTERN = re.compile(
    r"^(?P<market>\S+)\s+(?P<combo>[0-9=\-]+)\s+conf=(?P<conf>[0-9.]+)\s+odds=(?P<odds>[0-9.]+|N/A|-)"
)
KYOUTEI_AMOUNT_PATTERN = re.compile(
    r"投資[= ](?P<bet>[0-9,]+)円(?:\s*/)?\s*想定払戻[= ](?P<payout>[0-9,]+)円|投資[= ](?P<bet_na>[0-9,]+)円(?:\s*/)?\s*想定払戻[= ]N/A"
)


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


def _today_date8() -> str:
    return datetime.now().strftime("%Y%m%d")


def _combine_date_hhmm(date8: str, hhmm: str) -> str:
    text = str(date8 or "").strip()
    clock = str(hhmm or "").strip()
    if len(text) != 8 or not text.isdigit() or not re.fullmatch(r"\d{1,2}:\d{2}", clock):
        return ""
    hour, minute = clock.split(":", 1)
    return f"{text[:4]}-{text[4:6]}-{text[6:8]} {int(hour):02d}:{minute}:00"


def _infer_tool_slot_from_hhmm(hhmm: str) -> str:
    text = str(hhmm or "").strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}", text):
        return ""
    try:
        hour = int(text.split(":", 1)[0])
    except Exception:
        return ""
    if hour < 10:
        return "morning"
    if hour < 18:
        return "daytime"
    return "midnight"


def normalize_ticket(ticket: Dict[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(ticket, dict):
        return None
    market = str(ticket.get("market", "") or "").strip()
    combo = str(ticket.get("combo", "") or "").strip()
    bet_yen = _safe_int(ticket.get("bet_yen"), 0)
    if (not market) or (not combo) or bet_yen <= 0:
        return None
    row = {
        "market": market,
        "combo": combo,
        "bet_yen": bet_yen,
    }
    odds = _safe_float(ticket.get("odds"), -1.0)
    if odds > 0:
        row["odds"] = float(odds)
    return row


def normalize_payload(obj: Dict[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    message_type = str(obj.get("message_type", "") or "").strip().lower()
    if message_type == "pre_race_candidates":
        return _normalize_pre_race_candidates_payload(obj)

    race = obj.get("race") if isinstance(obj.get("race"), dict) else {}
    tickets = obj.get("tickets") if isinstance(obj.get("tickets"), list) else []
    if not race or not tickets:
        return None

    date8 = str(race.get("date", "") or "").strip()
    venue_name = str(race.get("venue_name", "") or "").strip()
    race_num = _safe_int(race.get("race_num"), 0)
    if len(date8) != 8 or not date8.isdigit() or (not venue_name) or race_num <= 0:
        return None

    out_tickets: List[Dict[str, Any]] = []
    for t in tickets:
        row = normalize_ticket(t)
        if row is not None:
            out_tickets.append(row)
    if not out_tickets:
        return None

    strategy_obj = obj.get("strategy") if isinstance(obj.get("strategy"), dict) else {}
    strategy_name = str(
        obj.get("strategy_name", "") or strategy_obj.get("name", "") or ""
    ).strip()
    strategy_code = normalize_strategy_code(
        obj.get("strategy_code", "") or strategy_obj.get("code", "") or "",
        default="",
    )
    tool_slot = infer_tool_slot_from_entry_payload(obj)

    return {
        "message_type": "entry_tickets",
        "provider": str(obj.get("provider", "") or ""),
        "source": str(obj.get("source", "") or ""),
        "race": {
            "date": date8,
            "venue_name": venue_name,
            "race_num": race_num,
            "race_id": str(race.get("race_id", "") or ""),
            "race_key16": str(race.get("race_key16", "") or ""),
            "start_time": str(race.get("start_time", "") or ""),
        },
        "strategy_name": strategy_name,
        "strategy_code": strategy_code,
        "tool_slot": tool_slot,
        "tickets": out_tickets,
    }


def _normalize_pre_race_candidates_payload(obj: Dict[str, Any]) -> Dict[str, Any] | None:
    candidates = obj.get("candidates") if isinstance(obj.get("candidates"), list) else []
    obj_date = str(obj.get("date", "") or "").strip()
    out_candidates: List[Dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        date8 = str(item.get("date", "") or "").strip() or obj_date
        venue_name = str(item.get("venue_name", "") or "").strip()
        race_num = _safe_int(item.get("race_num"), 0)
        if len(date8) != 8 or not date8.isdigit() or (not venue_name) or race_num <= 0:
            continue
        out_candidates.append({
            "date": date8,
            "race_id": str(item.get("race_id", "") or ""),
            "venue_name": venue_name,
            "race_num": race_num,
            "race_key16": str(item.get("race_key16", "") or ""),
            "start_time": str(item.get("start_time", "") or ""),
        })

    if candidates and not out_candidates:
        return None

    if out_candidates:
        payload_date = obj_date if len(obj_date) == 8 and obj_date.isdigit() else str(out_candidates[0].get("date", ""))
    else:
        payload_date = obj_date if len(obj_date) == 8 and obj_date.isdigit() else ""
    return {
        "message_type": "pre_race_candidates",
        "is_provisional": bool(obj.get("is_provisional", False)),
        "advisory": str(obj.get("advisory", "") or ""),
        "provider": str(obj.get("provider", "") or ""),
        "requested_at": str(obj.get("requested_at", "") or ""),
        "source": str(obj.get("source", "") or ""),
        "date": payload_date,
        "odds_provider": str(obj.get("odds_provider", "") or ""),
        "filters": obj.get("filters") if isinstance(obj.get("filters"), dict) else {},
        "tool_slot": infer_tool_slot_from_candidate_payload(obj),
        "candidate_count": _safe_int(obj.get("candidate_count"), len(out_candidates)),
        "candidates": out_candidates,
    }



def _extract_json_chunks(text: str) -> List[str]:
    content = str(text or "")
    chunks: List[str] = []
    for m in JSON_FENCE_PATTERN.finditer(content):
        chunks.append(m.group(1).strip())
    if chunks:
        return chunks
    trimmed = content.strip()
    if trimmed.startswith("{") or trimmed.startswith("["):
        return [trimmed]
    return []



def _expand_candidate_json(raw: str) -> List[Dict[str, Any]]:
    try:
        parsed = json.loads(raw)
    except Exception:
        return []

    if isinstance(parsed, dict):
        payload = normalize_payload(parsed)
        return [payload] if payload else []

    out: List[Dict[str, Any]] = []
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                p = normalize_payload(item)
                if p is not None:
                    out.append(p)
    return out


def _extract_kyoutei_text_blocks(text: str) -> List[str]:
    content = str(text or "").strip()
    if not content:
        return []
    matches = list(KYOUTEI_BLOCK_HEADER_PATTERN.finditer(content))
    if not matches:
        return []
    blocks: List[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        block = content[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


def _parse_kyoutei_candidate_block(block: str) -> Dict[str, Any] | None:
    lines = [str(line or "").strip() for line in str(block or "").splitlines() if str(line or "").strip()]
    if not lines:
        return None
    header_match = KYOUTEI_CANDIDATE_HEADER_PATTERN.match(lines[0])
    if header_match is None:
        return None
    date8 = str(header_match.group("date8") or "").strip()
    candidate_count = 0
    strategy = ""
    out_candidates: List[Dict[str, Any]] = []
    for line in lines[1:]:
        count_match = KYOUTEI_CANDIDATE_COUNT_PATTERN.match(line)
        if count_match is not None:
            candidate_count = _safe_int(count_match.group("count"), 0)
            strategy = str(count_match.group("strategy") or "").strip()
            continue
        if line == "候補なし":
            candidate_count = 0
            continue
        item_match = KYOUTEI_CANDIDATE_LINE_PATTERN.match(line)
        if item_match is None:
            continue
        venue_name = str(item_match.group("venue") or "").strip()
        race_num = _safe_int(item_match.group("race_num"), 0)
        hhmm = str(item_match.group("hhmm") or "").strip()
        if not venue_name or race_num <= 0:
            continue
        out_row = {
            "date": date8,
            "race_id": f"{date8}_{venue_name}_{race_num:02d}R",
            "venue_name": venue_name,
            "race_num": race_num,
            "start_time": _combine_date_hhmm(date8, hhmm),
        }
        market = str(item_match.group("market") or "").strip()
        combo = str(item_match.group("combo") or "").strip()
        conf = str(item_match.group("conf") or "").strip()
        if market:
            out_row["market"] = market
        if combo:
            out_row["combo"] = combo
        if conf:
            out_row["confidence"] = _safe_float(conf, 0.0)
        out_candidates.append(out_row)
    payload_date = date8 if len(date8) == 8 and date8.isdigit() else ""
    requested_at = _combine_date_hhmm(payload_date, "08:00") if payload_date else ""
    return {
        "message_type": "pre_race_candidates",
        "is_provisional": True,
        "advisory": "",
        "provider": "kyoutei",
        "requested_at": requested_at,
        "source": "discord_text",
        "date": payload_date,
        "odds_provider": "official",
        "filters": {"exclude_midnight": True},
        "tool_slot": "morning",
        "strategy_name": strategy,
        "candidate_count": max(candidate_count, len(out_candidates)),
        "candidates": out_candidates,
    }


def _parse_kyoutei_entry_block(block: str) -> Dict[str, Any] | None:
    lines = [str(line or "").strip() for line in str(block or "").splitlines() if str(line or "").strip()]
    if not lines:
        return None
    header_match = KYOUTEI_ENTRY_HEADER_PATTERN.match(lines[0])
    if header_match is None:
        return None
    venue_name = str(header_match.group("venue") or "").strip()
    race_num = _safe_int(header_match.group("race_num"), 0)
    if not venue_name or race_num <= 0:
        return None

    date8 = _today_date8()
    deadline_hhmm = ""
    strategy_name = ""
    ticket: Dict[str, Any] | None = None
    bet_yen = 0
    for line in lines[1:]:
        deadline_match = KYOUTEI_DEADLINE_PATTERN.match(line)
        if deadline_match is not None:
            deadline_hhmm = str(deadline_match.group("deadline") or "").strip()
            continue
        if line.startswith("方式 "):
            strategy_name = str(line.replace("方式 ", "", 1) or "").strip()
            continue
        ticket_match = KYOUTEI_TICKET_PATTERN.match(line)
        if ticket_match is not None:
            odds_text = str(ticket_match.group("odds") or "").strip()
            odds_value = None
            if odds_text not in {"", "-", "N/A"}:
                odds_value = _safe_float(odds_text, -1.0)
                if odds_value <= 0:
                    odds_value = None
            ticket = {
                "market": str(ticket_match.group("market") or "").strip(),
                "combo": str(ticket_match.group("combo") or "").strip(),
                "bet_yen": 0,
            }
            if odds_value is not None:
                ticket["odds"] = odds_value
            continue
        amount_match = KYOUTEI_AMOUNT_PATTERN.search(line)
        if amount_match is not None:
            bet_text = str(amount_match.group("bet") or amount_match.group("bet_na") or "").strip()
            bet_yen = _safe_int(bet_text.replace(",", ""), 0)
    if ticket is None:
        return None
    ticket["bet_yen"] = max(100, bet_yen or 100)
    return {
        "message_type": "entry_tickets",
        "provider": "kyoutei",
        "source": "discord_text",
        "race": {
            "date": date8,
            "venue_name": venue_name,
            "race_num": race_num,
            "race_id": f"{date8}_{venue_name}_{race_num:02d}R",
            "race_key16": "",
            "start_time": _combine_date_hhmm(date8, deadline_hhmm),
        },
        "strategy_name": strategy_name,
        "strategy_code": "",
        "tool_slot": _infer_tool_slot_from_hhmm(deadline_hhmm),
        "tickets": [ticket],
    }


def _extract_kyoutei_text_payloads(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for block in _extract_kyoutei_text_blocks(text):
        parsed = _parse_kyoutei_candidate_block(block)
        if parsed is None:
            parsed = _parse_kyoutei_entry_block(block)
        if parsed is not None:
            out.append(parsed)
    return out



def extract_payloads_from_text(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in _extract_json_chunks(text):
        out.extend(_expand_candidate_json(raw))
    if out:
        return out
    out.extend(_extract_kyoutei_text_payloads(text))
    return out
