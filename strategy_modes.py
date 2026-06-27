from __future__ import annotations

from typing import Any

DEFAULT_STRATEGY_CODE = "midnight_base"

STRATEGY_CHOICES: tuple[tuple[str, str], ...] = (
    ("midnight_attack", "ミッド勝負"),
    ("midnight_base", "ミッド基準"),
    ("midnight_stable", "ミッド安定"),
    ("all_attack", "全帯勝負"),
    ("all_base", "全帯基準"),
    ("all_stable", "全帯安定"),
)

_CODE_TO_DISPLAY = {code: label for code, label in STRATEGY_CHOICES}
_DISPLAY_TO_CODE = {label: code for code, label in STRATEGY_CHOICES}
_VALID_CODES = set(_CODE_TO_DISPLAY)

_ALIASES = {
    "midnight_attack": "midnight_attack",
    "mid_attack": "midnight_attack",
    "mid-attack": "midnight_attack",
    "night_attack": "midnight_attack",
    "ミッド勝負": "midnight_attack",
    "ミッドナイト勝負": "midnight_attack",
    "midnight_base": "midnight_base",
    "midnight_average": "midnight_base",
    "mid_average": "midnight_base",
    "mid-average": "midnight_base",
    "midnight_baseline": "midnight_base",
    "mid_baseline": "midnight_base",
    "midnight_standard": "midnight_base",
    "ミッド基準": "midnight_base",
    "ミッドナイト基準": "midnight_base",
    "ミッド平均": "midnight_base",
    "midnight_stable": "midnight_stable",
    "midnight_defense": "midnight_stable",
    "mid_defense": "midnight_stable",
    "mid-defense": "midnight_stable",
    "midnight_guard": "midnight_stable",
    "midnight_safety": "midnight_stable",
    "ミッド安定": "midnight_stable",
    "ミッドナイト安定": "midnight_stable",
    "ミッド守り": "midnight_stable",
    "all_attack": "all_attack",
    "full_attack": "all_attack",
    "full-attack": "all_attack",
    "all_day_attack": "all_attack",
    "all-day-attack": "all_attack",
    "zen_attack": "all_attack",
    "全帯勝負": "all_attack",
    "全日勝負": "all_attack",
    "all_base": "all_base",
    "all_average": "all_base",
    "full_average": "all_base",
    "all_baseline": "all_base",
    "full_baseline": "all_base",
    "all_standard": "all_base",
    "all_day_base": "all_base",
    "all-day-base": "all_base",
    "全帯基準": "all_base",
    "全日基準": "all_base",
    "全帯平均": "all_base",
    "all_stable": "all_stable",
    "all_defense": "all_stable",
    "full_defense": "all_stable",
    "all_guard": "all_stable",
    "all_safety": "all_stable",
    "all_day_stable": "all_stable",
    "all-day-stable": "all_stable",
    "全帯安定": "all_stable",
    "全日安定": "all_stable",
    "全帯守り": "all_stable",
    # 旧3モード互換: 現運用はミッドナイト通知のみのため、ミッド系へ寄せる。
    "attack": "midnight_attack",
    "aggressive": "midnight_attack",
    "勝負": "midnight_attack",
    "average": "midnight_base",
    "balance": "midnight_base",
    "balanced": "midnight_base",
    "base": "midnight_base",
    "baseline": "midnight_base",
    "standard": "midnight_base",
    "平均": "midnight_base",
    "基準": "midnight_base",
    "defense": "midnight_stable",
    "defensive": "midnight_stable",
    "guard": "midnight_stable",
    "stable": "midnight_stable",
    "safety": "midnight_stable",
    "守り": "midnight_stable",
    "安定": "midnight_stable",
    # 廃止済み互換: 「全部」は default に寄せる。
    "all": DEFAULT_STRATEGY_CODE,
    "any": DEFAULT_STRATEGY_CODE,
}


def normalize_strategy_code(value: Any, *, default: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        text = str(default or "").strip()
    if not text:
        return ""
    normalized = _ALIASES.get(text.lower(), _ALIASES.get(text, text.lower()))
    return str(normalized or "")


def is_known_strategy_code(value: Any) -> bool:
    return normalize_strategy_code(value) in _VALID_CODES


def strategy_display_to_code(display: Any, *, default: str = DEFAULT_STRATEGY_CODE) -> str:
    text = str(display or "").strip()
    if not text:
        return default
    if text in _DISPLAY_TO_CODE:
        return _DISPLAY_TO_CODE[text]
    normalized = normalize_strategy_code(text, default=default)
    if normalized in _VALID_CODES:
        return normalized
    return default


def strategy_code_to_display(code: Any, *, default: str = DEFAULT_STRATEGY_CODE) -> str:
    normalized = normalize_strategy_code(code, default=default)
    return _CODE_TO_DISPLAY.get(normalized, _CODE_TO_DISPLAY[DEFAULT_STRATEGY_CODE])


def known_strategy_codes() -> tuple[str, ...]:
    return tuple(code for code, _label in STRATEGY_CHOICES)


def strategy_choice_labels() -> tuple[str, ...]:
    return tuple(label for _code, label in STRATEGY_CHOICES)
