from __future__ import annotations

import customtkinter as ctk

# ---------------------------------------------------------------------------
# Domain-specific colors -- (light, dark) tuples resolved by customtkinter
# ---------------------------------------------------------------------------

COLOR_BG = ("#F0F8FA", "#0B1720")
COLOR_CARD_BG = ("#FFFFFF", "#142331")
COLOR_CARD_ELEVATED = ("#F5FBFC", "#1A2C3A")

COLOR_TEXT_PRIMARY = ("#102532", "#E8F6FA")
COLOR_TEXT_MUTED = ("#000000", "#A8BCC6")
COLOR_TEXT_ON_ACCENT = ("#FFFFFF", "#082331")
COLOR_TEXT_ON_NEUTRAL = ("#FFFFFF", "#E8F6FA")

COLOR_ACCENT = ("#007E8A", "#57D2DA")
COLOR_ACCENT_HOVER = ("#006B76", "#37BBC6")
COLOR_BUTTON_NEUTRAL = ("#617A88", "#475D68")
COLOR_BUTTON_NEUTRAL_HOVER = ("#526B78", "#536B76")

COLOR_SEG_SELECTED = ("#BEEFF2", "#1B5560")
COLOR_SEG_SELECTED_HOVER = ("#A8E5EA", "#246774")
COLOR_SEG_UNSELECTED = ("#E5F4F7", "#203646")
COLOR_SEG_UNSELECTED_HOVER = ("#D8EEF2", "#28465A")
COLOR_SEG_TEXT = ("#0E3440", "#E6F7FA")

COLOR_DRY_RUN_BG = ("#E8F6ED", "#173628")
COLOR_DRY_RUN_FG = ("#1E7B4A", "#89E8B8")
COLOR_LIVE_BG = ("#FCEDEA", "#3D1E1A")
COLOR_LIVE_FG = ("#B8412D", "#FFAA9E")
COLOR_LIVE_WARN = ("#BD3A2F", "#FF9487")

COLOR_SUCCESS = ("#22864F", "#66D895")
COLOR_ERROR = ("#C34538", "#FF8E83")
COLOR_ORANGE = ("#B96D00", "#F3B04E")
COLOR_INFO = ("#1769A6", "#72C8FF")
COLOR_DIMMED = COLOR_TEXT_MUTED

COLOR_SEPARATOR = ("#D1E2E8", "#29404D")
COLOR_SIDEBAR_BG = ("#E7F4F7", "#0F1D29")
COLOR_SIDEBAR_HOVER = ("#D8EEF2", "#183041")
COLOR_SIDEBAR_ACTIVE = ("#C6E8EE", "#20465C")
COLOR_TABLE_ALT = ("#F2FAFC", "#102434")

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
