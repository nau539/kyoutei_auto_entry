from __future__ import annotations

import customtkinter as ctk

from ui.theme import COLOR_DRY_RUN_BG, COLOR_DRY_RUN_FG, COLOR_LIVE_BG, COLOR_LIVE_FG, FONT_BADGE


class ModeBadge(ctk.CTkFrame):
    """Colored badge always visible in the sidebar showing DRY-RUN or LIVE."""

    def __init__(self, master: ctk.CTkBaseClass, **kwargs) -> None:
        kwargs.setdefault("corner_radius", 8)
        super().__init__(master, **kwargs)
        self._label = ctk.CTkLabel(self, text="DRY-RUN", font=FONT_BADGE)
        self._label.pack(padx=16, pady=8)
        self.set_dry_run(True)

    def set_dry_run(self, is_dry: bool) -> None:
        if is_dry:
            self.configure(fg_color=COLOR_DRY_RUN_BG)
            self._label.configure(text="DRY-RUN", text_color=COLOR_DRY_RUN_FG)
        else:
            self.configure(fg_color=COLOR_LIVE_BG)
            self._label.configure(text="LIVE", text_color=COLOR_LIVE_FG)
