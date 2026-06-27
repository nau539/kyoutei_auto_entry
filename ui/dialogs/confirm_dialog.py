from __future__ import annotations

from typing import Any

import customtkinter as ctk

from ui.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_CARD_ELEVATED,
    COLOR_SEG_UNSELECTED_HOVER,
    COLOR_TEXT_ON_ACCENT,
    COLOR_TEXT_PRIMARY,
    FONT_BODY,
    FONT_MONO_SM,
)


class ConfirmDialog(ctk.CTkToplevel):
    """Themed yes/no confirmation dialog replacing messagebox."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        title: str = "確認",
        message: str = "",
        confirm_text: str = "はい",
        cancel_text: str = "いいえ",
        **kwargs: Any,
    ) -> None:
        super().__init__(master, **kwargs)
        self.title(title)
        self.geometry("520x420")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result: bool = False

        # Message
        textbox = ctk.CTkTextbox(self, font=FONT_MONO_SM, wrap="word")
        textbox.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        textbox.insert("end", message)
        textbox.configure(state="disabled")

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkButton(
            btn_frame,
            text=cancel_text,
            width=120,
            height=36,
            fg_color=COLOR_CARD_ELEVATED,
            hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=lambda: self._close(False),
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_frame,
            text=confirm_text,
            width=120,
            height=36,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_ON_ACCENT,
            command=lambda: self._close(True),
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", lambda: self._close(False))

    def _close(self, ok: bool) -> None:
        self.result = ok
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
