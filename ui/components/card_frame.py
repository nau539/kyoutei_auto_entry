from __future__ import annotations

import customtkinter as ctk

from ui.theme import COLOR_CARD_BG, COLOR_SEPARATOR, FONT_HEADING


class CardFrame(ctk.CTkFrame):
    """Rounded card container with an optional title and separator."""

    def __init__(self, master: ctk.CTkBaseClass, title: str = "", **kwargs) -> None:
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("fg_color", COLOR_CARD_BG)
        super().__init__(master, **kwargs)

        if title:
            self._title_label = ctk.CTkLabel(self, text=title, font=FONT_HEADING, anchor="w")
            self._title_label.pack(fill="x", padx=16, pady=(12, 4))
            sep = ctk.CTkFrame(self, height=1, fg_color=COLOR_SEPARATOR)
            sep.pack(fill="x", padx=16, pady=(0, 8))

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=16, pady=(0, 12))
