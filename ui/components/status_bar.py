from __future__ import annotations

import customtkinter as ctk

from ui.theme import (
    COLOR_DIMMED,
    COLOR_DRY_RUN_FG,
    COLOR_LIVE_FG,
    COLOR_SEPARATOR,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    FONT_SMALL,
)


class StatusBar(ctk.CTkFrame):
    """Thin status strip at the bottom of the content area."""

    def __init__(self, master: ctk.CTkBaseClass, version: str = "", **kwargs) -> None:
        kwargs.setdefault("height", 32)
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)
        self.grid_propagate(False)
        self.pack_propagate(False)

        sep = ctk.CTkFrame(self, height=1, fg_color=COLOR_SEPARATOR)
        sep.pack(fill="x", side="top")

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="both", expand=True)

        self._discord_label = ctk.CTkLabel(
            inner, text="連携: 未接続", font=FONT_SMALL, text_color=COLOR_DIMMED
        )
        self._discord_label.pack(side="left", padx=(12, 20))

        self._mode_label = ctk.CTkLabel(
            inner, text="LIVE", font=("", 11, "bold"), text_color=COLOR_LIVE_FG
        )
        self._mode_label.pack(side="left", padx=(0, 20))

        self._profile_label = ctk.CTkLabel(
            inner, text="-", font=FONT_SMALL, text_color=COLOR_DIMMED
        )
        self._profile_label.pack(side="left", padx=(0, 20))
        self._profile_visible = True

        if version:
            ver_label = ctk.CTkLabel(inner, text=f"v{version}", font=FONT_SMALL, text_color=COLOR_DIMMED)
            ver_label.pack(side="right", padx=(0, 12))

    def update_discord(self, connected: bool) -> None:
        if connected:
            self._discord_label.configure(text="連携: 接続中", text_color=COLOR_SUCCESS)
        else:
            self._discord_label.configure(text="連携: 未接続", text_color=COLOR_TEXT_MUTED)

    def update_mode(self, is_live: bool) -> None:
        if is_live:
            self._mode_label.configure(text="LIVE", text_color=COLOR_LIVE_FG)
        else:
            self._mode_label.configure(text="DRY-RUN", text_color=COLOR_DRY_RUN_FG)

    def update_profile(self, text: str, *, text_color: str | tuple[str, str] = COLOR_DIMMED) -> None:
        self._profile_label.configure(text=str(text or "-"), text_color=text_color)

    def set_profile_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if visible == self._profile_visible:
            return
        self._profile_visible = visible
        if visible:
            self._profile_label.pack(side="left", padx=(0, 20))
        else:
            self._profile_label.pack_forget()
