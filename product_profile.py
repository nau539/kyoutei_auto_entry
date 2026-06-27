from __future__ import annotations

import os
from typing import Any, Iterable

PRODUCT_NAME = "KYOUTEI AI ZERO"
PRODUCT_TAGLINE = "Discord連携で競艇エントリーを整える商品版ダッシュボード"
PRODUCT_EXE_BASENAME = "KYOUTEI AI ZERO"
PRODUCT_LOG_BASENAME = "kyoutei_ai_zero"
FIXED_PLAN_TIER_ENV = "KYOUTEI_AI_ZERO_FIXED_PLAN_TIER"
UI_VARIANT_ENV = "KYOUTEI_AI_ZERO_UI_VARIANT"

TRIAL_PRODUCT_NAME = "kyoutei_auto_entry"
TRIAL_EXE_BASENAME = "kyoutei_auto_entry_trial"
TRIAL_LOG_BASENAME = "kyoutei_auto_entry_trial"

UI_VARIANT_PRODUCT = "product"
UI_VARIANT_CLASSIC_TRIAL = "classic_trial"

DEFAULT_PLAN_TIER = "gold"

PLAN_ORDER: tuple[str, ...] = ("bronze", "silver", "gold")
PLAN_LABELS = {
    "bronze": "BRONZE",
    "silver": "SILVER",
    "gold": "GOLD",
}
PLAN_SLOT_LIMITS = {
    "bronze": 1,
    "silver": 2,
    "gold": 3,
}
PLAN_DESCRIPTIONS = {
    "bronze": "1つまで選べるライトプラン",
    "silver": "2つまで選べる標準プラン",
    "gold": "どれでも選べるフルプラン",
}

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

PLAN_PALETTES = {
    "bronze": {
        "accent": ("#A85B28", "#E39A63"),
        "accent_hover": ("#8D481C", "#CC7F44"),
        "soft": ("#F4E4D8", "#3A2418"),
        "strong": ("#6B3B18", "#F5C39A"),
        "sidebar_active": ("#F0D0BA", "#5A3117"),
        "sidebar_hover": ("#F7E4D7", "#452819"),
        "badge_fg": ("#5D2E11", "#2A160C"),
        "badge_text": ("#FFE3D1", "#FFD3AE"),
    },
    "silver": {
        "accent": ("#7A8CA6", "#B8C6D9"),
        "accent_hover": ("#627389", "#9FB0C7"),
        "soft": ("#E6ECF3", "#232D38"),
        "strong": ("#344251", "#E3EDF8"),
        "sidebar_active": ("#D7E0EB", "#33404F"),
        "sidebar_hover": ("#ECF1F6", "#283240"),
        "badge_fg": ("#26313F", "#1A212B"),
        "badge_text": ("#EAF1F8", "#D8E2EE"),
    },
    "gold": {
        "accent": ("#C9960A", "#F5C95B"),
        "accent_hover": ("#AE8100", "#E4B63C"),
        "soft": ("#FAF0CF", "#3D3011"),
        "strong": ("#6E5300", "#FFE69A"),
        "sidebar_active": ("#F2E0A0", "#564314"),
        "sidebar_hover": ("#FAF1CF", "#433615"),
        "badge_fg": ("#5A4300", "#2F2404"),
        "badge_text": ("#FFF0BF", "#FFE5A6"),
    },
}


def normalize_plan_tier(value: Any, *, default: str = DEFAULT_PLAN_TIER) -> str:
    text = str(value or "").strip().lower()
    if text not in PLAN_ORDER:
        text = str(default or DEFAULT_PLAN_TIER).strip().lower()
    if text not in PLAN_ORDER:
        text = DEFAULT_PLAN_TIER
    return text


def fixed_plan_tier() -> str:
    text = str(os.environ.get(FIXED_PLAN_TIER_ENV, "") or "").strip().lower()
    return text if text in PLAN_ORDER else ""


def normalize_ui_variant(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == UI_VARIANT_CLASSIC_TRIAL:
        return UI_VARIANT_CLASSIC_TRIAL
    return UI_VARIANT_PRODUCT


def ui_variant() -> str:
    return normalize_ui_variant(os.environ.get(UI_VARIANT_ENV, ""))


def is_classic_trial() -> bool:
    return ui_variant() == UI_VARIANT_CLASSIC_TRIAL


def manual_review_enabled(*, fixed_tier: Any = None, classic_trial: bool | None = None) -> bool:
    if classic_trial is None:
        classic_trial = is_classic_trial()
    if classic_trial:
        return False
    tier = str(fixed_tier if fixed_tier is not None else fixed_plan_tier() or "").strip().lower()
    return tier in PLAN_ORDER


def runtime_product_name() -> str:
    return TRIAL_PRODUCT_NAME if is_classic_trial() else PRODUCT_NAME


def runtime_log_basename() -> str:
    return TRIAL_LOG_BASENAME if is_classic_trial() else PRODUCT_LOG_BASENAME


def effective_plan_tier(value: Any, *, default: str = DEFAULT_PLAN_TIER) -> str:
    fixed = fixed_plan_tier()
    if fixed:
        return fixed
    return normalize_plan_tier(value, default=default)


def raw_plan_label(value: Any) -> str:
    return PLAN_LABELS.get(normalize_plan_tier(value), PLAN_LABELS[DEFAULT_PLAN_TIER])


def plan_label(value: Any) -> str:
    return PLAN_LABELS.get(effective_plan_tier(value), PLAN_LABELS[DEFAULT_PLAN_TIER])


def plan_description(value: Any) -> str:
    return PLAN_DESCRIPTIONS.get(effective_plan_tier(value), PLAN_DESCRIPTIONS[DEFAULT_PLAN_TIER])


def plan_slot_limit(value: Any) -> int:
    return int(PLAN_SLOT_LIMITS.get(effective_plan_tier(value), PLAN_SLOT_LIMITS[DEFAULT_PLAN_TIER]))


def build_plan_app_name(plan_tier: Any) -> str:
    tier = str(plan_tier or "").strip().lower()
    if tier not in PLAN_ORDER:
        return PRODUCT_EXE_BASENAME
    return f"{PRODUCT_EXE_BASENAME} {raw_plan_label(tier)}"


def build_trial_app_name() -> str:
    return TRIAL_EXE_BASENAME


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


def _iter_tool_slot_values(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw = str(values or "").replace("、", ",").replace(" ", ",")
        return [part for part in raw.split(",") if str(part or "").strip()]
    if isinstance(values, Iterable):
        out: list[str] = []
        for item in values:
            text = str(item or "").strip()
            if text:
                out.append(text)
        return out
    text = str(values or "").strip()
    return [text] if text else []


def normalize_tool_slots(
    values: Any,
    tier: Any,
    *,
    default: Any = None,
) -> list[str]:
    plan = effective_plan_tier(tier)
    raw_values = _iter_tool_slot_values(values)
    use_default = default is not None and values is None
    if isinstance(values, str) and not str(values or "").strip():
        use_default = default is not None
    if not raw_values and use_default:
        raw_values = _iter_tool_slot_values(default)

    normalized: list[str] = []
    for raw in raw_values:
        slot = normalize_tool_slot(raw)
        if slot and slot not in normalized:
            normalized.append(slot)

    limit = plan_slot_limit(plan)
    if len(normalized) > limit:
        normalized = normalized[:limit]

    ordered = [slot for slot in TOOL_SLOT_ORDER if slot in normalized]
    return ordered


def selected_tool_slots(entry: Any) -> list[str]:
    tier = effective_plan_tier(getattr(entry, "plan_tier", DEFAULT_PLAN_TIER))
    values = getattr(entry, "tool_slots", None)
    return normalize_tool_slots(values, tier, default=TOOL_SLOT_ORDER)


def update_tool_slot_selection(values: Any, clicked_slot: Any, tier: Any) -> list[str]:
    plan = effective_plan_tier(tier)
    slot = normalize_tool_slot(clicked_slot)
    if not slot:
        return normalize_tool_slots(values, plan, default=TOOL_SLOT_ORDER)

    current: list[str] = []
    for raw in _iter_tool_slot_values(values):
        normalized = normalize_tool_slot(raw)
        if normalized and normalized not in current:
            current.append(normalized)

    if slot in current:
        return [value for value in current if value != slot]

    limit = plan_slot_limit(plan)
    if len(current) >= limit:
        if limit == 1:
            return [slot]
        return list(current)
    current.append(slot)
    return list(current)


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


def plan_palette(value: Any) -> dict[str, tuple[str, str]]:
    tier = effective_plan_tier(value)
    return dict(PLAN_PALETTES.get(tier, PLAN_PALETTES[DEFAULT_PLAN_TIER]))
