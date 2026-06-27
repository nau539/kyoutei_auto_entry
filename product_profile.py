from __future__ import annotations

from typing import Any

PRODUCT_NAME = "AQUA EDGE AI"
PRODUCT_TAGLINE = "Discord連携で競艇エントリーを整える商品版ダッシュボード"
PRODUCT_EXE_BASENAME = "AQUA EDGE AI"
PRODUCT_LOG_BASENAME = "aqua_edge_ai"

TOOL_SLOT_ORDER: tuple[str, ...] = ("morning", "daytime", "midnight")
TOOL_SLOT_LABELS = {
    "morning": "モーニング",
    "daytime": "日中",
    "midnight": "ミッドナイト",
}
TOOL_SLOT_TIMES = {
    "morning": "08:00",
    "daytime": "10:00",
    "midnight": "18:00",
}

TOOL_SLOT_ALIASES = {
    "morning": "morning",
    "モーニング": "morning",
    "morning_consistent_earnings": "morning",
    "morning_consistent": "morning",
    "morning_main": "morning",
    "daytime": "daytime",
    "日中": "daytime",
    "daytime_consistent_earnings": "daytime",
    "daytime_consistent": "daytime",
    "day": "daytime",
    "midnight": "midnight",
    "night": "midnight",
    "mid": "midnight",
    "ミッド": "midnight",
    "ミッドナイト": "midnight",
    "midnight_consistent_earnings": "midnight",
    "midnight_consistent": "midnight",
    "midnight_attack": "midnight",
    "midnight_base": "midnight",
    "midnight_stable": "midnight",
    "attack": "midnight",
    "average": "midnight",
    "defense": "midnight",
    "勝負": "midnight",
    "平均": "midnight",
    "守り": "midnight",
}

APP_PALETTE = {
    "accent": ("#008BC7", "#4FD8FF"),
    "accent_hover": ("#0074AA", "#2EC5EF"),
    "soft": ("#E0F7FD", "#102F44"),
    "strong": ("#004D78", "#B2F0FF"),
    "sidebar_active": ("#C6EDF8", "#17435C"),
    "sidebar_hover": ("#E8FAFE", "#18364A"),
    "badge_fg": ("#004568", "#0B2C40"),
    "badge_text": ("#D4F6FF", "#BDEFFF"),
}


def runtime_product_name() -> str:
    return PRODUCT_NAME


def runtime_log_basename() -> str:
    return PRODUCT_LOG_BASENAME


def app_palette() -> dict[str, tuple[str, str]]:
    return dict(APP_PALETTE)


def normalize_tool_slot(value: Any, *, default: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        text = str(default or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in TOOL_SLOT_ALIASES:
        return TOOL_SLOT_ALIASES[lowered]
    if text in TOOL_SLOT_ALIASES:
        return TOOL_SLOT_ALIASES[text]
    if ("モーニング" in text) or ("morning" in lowered):
        return "morning"
    if ("日中" in text) or ("daytime" in lowered):
        return "daytime"
    if ("ミッド" in text) or ("ミッドナイト" in text) or ("midnight" in lowered):
        return "midnight"
    return ""


def tool_slot_label(value: Any) -> str:
    return TOOL_SLOT_LABELS.get(normalize_tool_slot(value), "")


def tool_slot_time(value: Any) -> str:
    return TOOL_SLOT_TIMES.get(normalize_tool_slot(value), "")


def tool_slot_hour(value: Any) -> int | None:
    text = tool_slot_time(value)
    if not text:
        return None
    try:
        return int(text.split(":", 1)[0])
    except Exception:
        return None


def infer_tool_slot_from_strategy(strategy_code: Any = None, strategy_name: Any = None) -> str:
    for candidate in [strategy_code, strategy_name]:
        slot = normalize_tool_slot(candidate)
        if slot:
            return slot
    return ""


def infer_tool_slot_from_candidate_payload(payload: dict[str, Any]) -> str:
    for key in ("tool_slot", "time_slot", "delivery_slot", "slot"):
        slot = normalize_tool_slot(payload.get(key))
        if slot:
            return slot

    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    if bool(filters.get("midnight_only", False)):
        return "midnight"

    requested_at = str(payload.get("requested_at", "") or "").strip()
    hour = None
    if requested_at:
        try:
            hour = int(str(requested_at).split("T")[-1].split(" ")[-1].split(":", 1)[0])
        except Exception:
            hour = None
    if hour == 8:
        return "morning"
    if hour == 10:
        return "daytime"
    if hour == 18:
        return "midnight"

    if bool(filters.get("exclude_midnight", False)):
        return "daytime"
    return ""


def infer_tool_slot_from_entry_payload(payload: dict[str, Any]) -> str:
    for key in ("tool_slot", "time_slot", "delivery_slot", "slot"):
        slot = normalize_tool_slot(payload.get(key))
        if slot:
            return slot

    strategy = payload.get("strategy") if isinstance(payload.get("strategy"), dict) else {}
    return infer_tool_slot_from_strategy(
        payload.get("strategy_code", "") or strategy.get("code", "") or "",
        payload.get("strategy_name", "") or strategy.get("name", "") or "",
    )


def infer_tool_slot_from_payload(payload: dict[str, Any]) -> str:
    message_type = str(payload.get("message_type", "entry_tickets") or "entry_tickets").strip().lower()
    if message_type == "pre_race_candidates":
        return infer_tool_slot_from_candidate_payload(payload)
    return infer_tool_slot_from_entry_payload(payload)
