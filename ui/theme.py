from __future__ import annotations

import customtkinter as ctk

# ---------------------------------------------------------------------------
# Domain-specific colors -- (light, dark) tuples resolved by customtkinter
# ---------------------------------------------------------------------------

COLOR_BG = ("#F3F6FB", "#0F1724")
COLOR_CARD_BG = ("#FFFFFF", "#1A2434")
COLOR_CARD_ELEVATED = ("#F7FAFD", "#202D42")

COLOR_TEXT_PRIMARY = ("#162032", "#E7EEF9")
COLOR_TEXT_MUTED = ("#000000", "#A4B1C5")
COLOR_TEXT_ON_ACCENT = ("#FFFFFF", "#0D2138")
COLOR_TEXT_ON_NEUTRAL = ("#FFFFFF", "#EAF1FC")

COLOR_ACCENT = ("#1F5FAE", "#66A3FF")
COLOR_ACCENT_HOVER = ("#184F95", "#4B8AE8")
COLOR_BUTTON_NEUTRAL = ("#6E7F98", "#4A5970")
COLOR_BUTTON_NEUTRAL_HOVER = ("#5D6E86", "#566980")

COLOR_SEG_SELECTED = ("#BED7FA", "#2A4D79")
COLOR_SEG_SELECTED_HOVER = ("#AACBF7", "#345D90")
COLOR_SEG_UNSELECTED = ("#E8F0FA", "#24344A")
COLOR_SEG_UNSELECTED_HOVER = ("#DBE8F8", "#2D3F59")
COLOR_SEG_TEXT = ("#10253D", "#E8F0FC")

COLOR_DRY_RUN_BG = ("#E8F6ED", "#173628")
COLOR_DRY_RUN_FG = ("#1E7B4A", "#89E8B8")
COLOR_LIVE_BG = ("#FCEDEA", "#3D1E1A")
COLOR_LIVE_FG = ("#B8412D", "#FFAA9E")
COLOR_LIVE_WARN = ("#BD3A2F", "#FF9487")

COLOR_SUCCESS = ("#22864F", "#66D895")
COLOR_ERROR = ("#C34538", "#FF8E83")
COLOR_ORANGE = ("#B96D00", "#F3B04E")
COLOR_INFO = ("#1B79D0", "#79B8FF")
COLOR_DIMMED = COLOR_TEXT_MUTED

COLOR_SEPARATOR = ("#D7DEE8", "#2B384F")
COLOR_SIDEBAR_BG = ("#EAF0F8", "#121C2D")
COLOR_SIDEBAR_HOVER = ("#DDE8F6", "#1A2A41")
COLOR_SIDEBAR_ACTIVE = ("#CFE0F7", "#243958")
COLOR_TABLE_ALT = ("#F5F9FE", "#152235")

# ---------------------------------------------------------------------------
# Font definitions
# ---------------------------------------------------------------------------

FONT_FAMILY = "Yu Gothic UI"
FONT_MONO_FAMILY = "Consolas"

FONT_TITLE = (FONT_FAMILY, 22, "bold")
FONT_HERO = (FONT_FAMILY, 28, "bold")
FONT_HEADING = (FONT_FAMILY, 15, "bold")
FONT_BODY = (FONT_FAMILY, 13)
FONT_SMALL = (FONT_FAMILY, 11)
FONT_TINY = (FONT_FAMILY, 10)
FONT_MONO = (FONT_MONO_FAMILY, 11)
FONT_MONO_SM = (FONT_MONO_FAMILY, 10)
FONT_STAT_VAL = (FONT_FAMILY, 30, "bold")
FONT_BADGE = (FONT_FAMILY, 12, "bold")
FONT_NAV = (FONT_FAMILY, 13)
FONT_NAV_ACTIVE = (FONT_FAMILY, 13, "bold")

# ---------------------------------------------------------------------------
# Theme helpers
# ---------------------------------------------------------------------------


def set_theme(mode: str) -> None:
    ctk.set_appearance_mode(mode)


def get_theme() -> str:
    return ctk.get_appearance_mode()


def resolve_color(color: str | tuple[str, str]) -> str:
    if isinstance(color, tuple):
        return color[1] if get_theme().lower() == "dark" else color[0]
    return str(color)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def fmt_yen(value: int) -> str:
    return f"{int(value):,}円"


def fmt_odds(value: float) -> str:
    return f"{value:.1f}" if value > 0 else "-"


def fmt_multiple(value: float) -> str:
    return f"{value:.2f}倍" if value > 0 else "-"
