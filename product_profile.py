from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# 取り扱う券種（GOLD/SILVER/BRONZE で選べる対象）。2連単は本商品ラインでは扱わない。
BET_TYPES: tuple[str, ...] = ("2連複", "3連複", "3連単")

# ---------------------------------------------------------------------------
# エディション定義
#   - GOLD/SILVER/BRONZE はクリアイズム様向けの選択上限。
#   - TRADE は通常向け。最大3券種でグレード表示はしない。
#   - DEMO(KYOUTEI) は自分用。認証なし・全券種選択可。
#   - テーマは現行の水色(アクア)を基調に、グレード色をアクセントとして重ねる。
# ---------------------------------------------------------------------------
EDITIONS: dict[str, dict[str, Any]] = {
    "GOLD": {
        "name": "AQUA EDGE AI GOLD",
        "exe_basename": "AQUA EDGE AI_GOLD",
        "log_basename": "aqua_edge_ai_gold",
        "max_bet_types": 3,
        "require_auth": True,
        # (light, dark) のアクセント。アクア基調にゴールドを重ねる。
        "tier_accent": ("#C8A22B", "#F4D469"),
        "tier_label": "GOLD",
    },
    "SILVER": {
        "name": "AQUA EDGE AI SILVER",
        "exe_basename": "AQUA EDGE AI_SILVER",
        "log_basename": "aqua_edge_ai_silver",
        "max_bet_types": 2,
        "require_auth": True,
        "tier_accent": ("#7C879A", "#C5D6E2"),
        "tier_label": "SILVER",
    },
    "BRONZE": {
        "name": "AQUA EDGE AI BRONZE",
        "exe_basename": "AQUA EDGE AI_BRONZE",
        "log_basename": "aqua_edge_ai_bronze",
        "max_bet_types": 1,
        "require_auth": True,
        "tier_accent": ("#A9692E", "#DFA468"),
        "tier_label": "BRONZE",
    },
    "DEMO": {
        "name": "KYOUTEI",
        "exe_basename": "KYOUTEI",
        "log_basename": "kyoutei",
        "max_bet_types": 3,
        "require_auth": True,
        # 自分用デモは master 認証シート(auth_master)。
        "auth_module": "auth_master",
        "tier_accent": ("#008BC7", "#4FD8FF"),
        "tier_label": "DEMO",
    },
    "TRADE": {
        "name": "kyoutei_auto_trade",
        "exe_basename": "kyoutei_auto_trade",
        "log_basename": "kyoutei_auto_trade",
        "max_bet_types": 3,
        "require_auth": True,
        "tier_accent": ("#008BC7", "#4FD8FF"),
        "tier_label": "",
    },
}
DEFAULT_EDITION = "GOLD"

# ---------------------------------------------------------------------------
# 製品ライン（配信チャンネル・グレードの意味・配信戦略が異なる）
#   - aqua      : 通常向け。GOLD相当の内容を kyoutei_auto_trade として配布。ch1521。
#                 認証は master シート(auth_master)。
#   - clearism  : クリアイズム様向け。前の3連複(stable3f)。GOLD/SILVER/BRONZE は
#                 「選べる日区分(モーニング/日中/ナイター)数」を制限。ch1490。
#                 認証は AQUA_EDGE_AI シート(auth_clear)。
# ---------------------------------------------------------------------------
PRODUCT_LINES: dict[str, dict[str, Any]] = {
    "aqua": {
        "brand": "kyoutei_auto_trade",
        "log_brand": "kyoutei_auto_trade",
        "cap_axis": "bet_type",
        "channel_id": "1521839594860187649",
        "dispatch_strategy": "aqua3",
        "webhook_config": "configs/local/discord_webhook_aqua.txt",
        "auth_module": "auth_master",
        "show_tier": False,
    },
    "clearism": {
        "brand": "AQUA EDGE AI CLEARISM",
        "log_brand": "aqua_edge_ai_clearism",
        "cap_axis": "daypart",
        "channel_id": "1490297331839664290",
        "dispatch_strategy": "stable3f",
        "webhook_config": "configs/local/discord_webhook_clearism.txt",
        "auth_module": "auth_clear",
        "show_tier": True,
    },
}
DEFAULT_LINE = "aqua"

# クリアイズム様ラインで選べる日区分
DAYPARTS: tuple[str, ...] = ("モーニング", "日中", "ナイター")
DAYPART_CODES = {"モーニング": "morning", "日中": "daytime", "ナイター": "night"}
DEFAULT_DAYPART_PRIORITY: tuple[str, ...] = ("ナイター", "日中", "モーニング")


def detect_line() -> str:
    """実行中の製品ラインを判定する（環境変数 APP_LINE → EXE名の CLEARISM 有無）。"""
    env = str(os.environ.get("APP_LINE", "") or "").strip().lower()
    if env in PRODUCT_LINES:
        return env
    try:
        if getattr(sys, "frozen", False):
            stem = Path(sys.executable).stem.upper()
            if "CLEARISM" in stem:
                return "clearism"
    except Exception:
        pass
    return DEFAULT_LINE


def line_profile(line: str | None = None) -> dict[str, Any]:
    ln = str(line or detect_line() or DEFAULT_LINE).lower()
    return dict(PRODUCT_LINES.get(ln, PRODUCT_LINES[DEFAULT_LINE]))


def line_channel_id(line: str | None = None) -> str:
    return str(line_profile(line).get("channel_id", ""))


def active_line_channel_id() -> str:
    """実配布(frozen)または APP_LINE 明示時のみ、ラインの配信チャンネルを返す。

    dev/テストでは空を返し、secrets_local の設定を尊重する。
    """
    explicit = bool(str(os.environ.get("APP_LINE", "") or "").strip())
    frozen = bool(getattr(sys, "frozen", False))
    if explicit or frozen:
        return line_channel_id()
    return ""


def line_cap_axis(line: str | None = None) -> str:
    return str(line_profile(line).get("cap_axis", "bet_type"))


def line_dispatch_strategy(line: str | None = None) -> str:
    return str(line_profile(line).get("dispatch_strategy", "aqua3"))


def line_shows_tier(line: str | None = None) -> bool:
    return bool(line_profile(line).get("show_tier", True))


def detect_edition() -> str:
    """実行中エディションを判定する。

    優先順位: 環境変数 APP_EDITION → 凍結EXEのファイル名 → 既定(GOLD)。
    EXE名は build 時に `AQUA EDGE AI_GOLD_v0.3.27.exe` のように付くため、
    名前に含まれるグレード語で判定する（KYOUTEI はデモ=認証なし）。
    """
    env = str(os.environ.get("APP_EDITION", "") or "").strip().upper()
    if env in EDITIONS:
        return env
    try:
        if getattr(sys, "frozen", False):
            stem = Path(sys.executable).stem.upper()
            if "KYOUTEI_AUTO_TRADE" in stem:
                return "TRADE"
            if "KYOUTEI" in stem:
                return "DEMO"
            for ed in ("GOLD", "SILVER", "BRONZE"):
                if ed in stem:
                    return ed
    except Exception:
        pass
    return DEFAULT_EDITION


def edition_profile(edition: str | None = None) -> dict[str, Any]:
    ed = str(edition or detect_edition() or DEFAULT_EDITION).upper()
    return dict(EDITIONS.get(ed, EDITIONS[DEFAULT_EDITION]))


def edition_name(edition: str | None = None, line: str | None = None) -> str:
    ed = str(edition or detect_edition()).upper()
    if ed == "DEMO":
        return "KYOUTEI"
    profile = line_profile(line)
    if not line_shows_tier(line):
        return str(profile["brand"])
    return f"{profile['brand']} {ed}"


def edition_exe_basename(edition: str | None = None, line: str | None = None) -> str:
    ed = str(edition or detect_edition()).upper()
    if ed == "DEMO":
        return "KYOUTEI"
    profile = line_profile(line)
    if not line_shows_tier(line):
        return str(profile["brand"])
    return f"{profile['brand']}_{ed}"


def edition_log_basename(edition: str | None = None, line: str | None = None) -> str:
    ed = str(edition or detect_edition()).upper()
    if ed == "DEMO":
        return "kyoutei"
    profile = line_profile(line)
    if not line_shows_tier(line):
        return str(profile["log_brand"])
    return f"{profile['log_brand']}_{ed.lower()}"


PRODUCT_NAME = edition_name()
PRODUCT_TAGLINE = "Discord連携で競艇エントリーを整える商品版ダッシュボード"
PRODUCT_EXE_BASENAME = edition_exe_basename()
PRODUCT_LOG_BASENAME = edition_log_basename()


def max_bet_types(edition: str | None = None) -> int:
    return int(edition_profile(edition).get("max_bet_types", len(BET_TYPES)))


def max_selections(edition: str | None = None) -> int:
    """グレードの選択上限件数（GOLD=3/SILVER=2/BRONZE=1/DEMO=3）。券種にも日区分にも使う。"""
    return max_bet_types(edition)


def edition_requires_auth(edition: str | None = None) -> bool:
    return bool(edition_profile(edition).get("require_auth", True))


def edition_auth_module(edition: str | None = None, line: str | None = None) -> str:
    """エディションと製品ラインが使う認証モジュール名。"""
    override = str(os.environ.get("APP_AUTH_MODULE", "") or "").strip()
    if override:
        return override

    ed = str(edition or detect_edition()).upper()
    if ed == "DEMO":
        return "auth_master"
    return str(line_profile(line).get("auth_module", "auth_clear"))


def tier_accent(edition: str | None = None) -> tuple[str, str]:
    accent = edition_profile(edition).get("tier_accent", APP_PALETTE["accent"])
    return (str(accent[0]), str(accent[1]))


def tier_label(edition: str | None = None) -> str:
    if not line_shows_tier():
        return ""
    return str(edition_profile(edition).get("tier_label", ""))


def normalize_bet_type(value: Any) -> str:
    """券種表記ゆれを正規化（全角・別名 → 2連複/3連複/3連単）。対象外は空文字。"""
    text = str(value or "").strip()
    if not text:
        return ""
    table = {
        "2連複": "2連複", "２連複": "2連複", "二連複": "2連複", "拡連複": "2連複",
        "3連複": "3連複", "３連複": "3連複", "三連複": "3連複",
        "3連単": "3連単", "３連単": "3連単", "三連単": "3連単",
    }
    return table.get(text, "")


def clamp_enabled_bet_types(values: Any, edition: str | None = None) -> list[str]:
    """選択券種を正規化し、エディションの上限件数で切り詰める。"""
    cap = max_bet_types(edition)
    seen: list[str] = []
    if isinstance(values, (list, tuple)):
        for v in values:
            nb = normalize_bet_type(v)
            if nb and nb in BET_TYPES and nb not in seen:
                seen.append(nb)
    # 選択順（＝ユーザーの優先順）を保ったまま上限で切る
    return seen[:cap]


# 既定選択の優先順（cap の範囲で先頭から採用）。
# 3連複=実績ある主力、2連複=高的中、3連単=高ROIの順。
DEFAULT_BET_TYPE_PRIORITY: tuple[str, ...] = ("3連複", "2連複", "3連単")


def default_enabled_bet_types(edition: str | None = None) -> list[str]:
    cap = max_bet_types(edition)
    return list(DEFAULT_BET_TYPE_PRIORITY[:cap])


# --- クリアイズム様ライン: 日区分の選択（モーニング/日中/ナイター） ---------
def normalize_daypart_label(value: Any) -> str:
    """日区分の表記ゆれを DAYPARTS 表記（モーニング/日中/ナイター）へ。対象外は空。"""
    text = str(value or "").strip()
    if not text:
        return ""
    table = {
        "モーニング": "モーニング", "morning": "モーニング", "朝": "モーニング",
        "日中": "日中", "daytime": "日中", "day": "日中", "デイ": "日中",
        "ナイター": "ナイター", "night": "ナイター", "ナイト": "ナイター", "nighter": "ナイター",
    }
    return table.get(text, table.get(text.lower(), ""))


def daypart_code(label: Any) -> str:
    """DAYPARTS 表記 → bunseki の daypart コード（morning/daytime/night）。"""
    return DAYPART_CODES.get(normalize_daypart_label(label), "")


def clamp_enabled_dayparts(values: Any, edition: str | None = None) -> list[str]:
    cap = max_selections(edition)
    seen: list[str] = []
    if isinstance(values, (list, tuple)):
        for v in values:
            nb = normalize_daypart_label(v)
            if nb and nb in DAYPARTS and nb not in seen:
                seen.append(nb)
    return seen[:cap]


def default_enabled_dayparts(edition: str | None = None) -> list[str]:
    cap = max_selections(edition)
    return list(DEFAULT_DAYPART_PRIORITY[:cap])

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
