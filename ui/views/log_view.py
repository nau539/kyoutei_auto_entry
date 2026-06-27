from __future__ import annotations

from typing import Any, List

import customtkinter as ctk

from ui.theme import (
    COLOR_CARD_ELEVATED,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_ORANGE,
    COLOR_SEG_SELECTED,
    COLOR_SEG_SELECTED_HOVER,
    COLOR_SEG_TEXT,
    COLOR_SEG_UNSELECTED,
    COLOR_SEG_UNSELECTED_HOVER,
    COLOR_SUCCESS,
    COLOR_TEXT_PRIMARY,
    FONT_BODY,
    FONT_MONO,
    FONT_SMALL,
    resolve_color,
)


class LogView(ctk.CTkFrame):
    """Enhanced log viewer with filtering and color-coded lines."""

    def __init__(self, master: ctk.CTkBaseClass, **kwargs: Any) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._all_lines: List[str] = []
        self._pending_visible_lines: List[str] = []
        self._current_filter = "全て"
        self._search_text = ""
        self._refresh_job: str | None = None
        self._append_flush_job: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        # Top bar: search + filter
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(top, text="検索:", font=FONT_BODY).pack(side="left")
        self._search_var = ctk.StringVar()
        self._search_entry = ctk.CTkEntry(
            top, textvariable=self._search_var, font=FONT_BODY, width=200,
            placeholder_text="キーワードで絞り込み"
        )
        self._search_entry.pack(side="left", padx=(8, 16))
        self._search_entry.bind("<KeyRelease>", self._on_search_change)

        self._filter_seg = ctk.CTkSegmentedButton(
            top,
            values=["全て", "受信", "発注", "エラー"],
            command=self._on_filter_change,
            selected_color=COLOR_SEG_SELECTED,
            selected_hover_color=COLOR_SEG_SELECTED_HOVER,
            unselected_color=COLOR_SEG_UNSELECTED,
            unselected_hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_SEG_TEXT,
        )
        self._filter_seg.set("全て")
        self._filter_seg.pack(side="left")

        # Log textbox
        self._textbox = ctk.CTkTextbox(
            self,
            font=FONT_MONO,
            state="disabled",
            wrap="none",
            fg_color=COLOR_CARD_ELEVATED,
        )
        self._textbox.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self._apply_tag_colors()

        # Bottom bar
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkButton(
            bottom,
            text="ログクリア",
            width=100,
            height=30,
            fg_color=COLOR_CARD_ELEVATED,
            hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self._clear_log,
        ).pack(side="left")

        self._count_label = ctk.CTkLabel(bottom, text="0 行", font=FONT_SMALL)
        self._count_label.pack(side="right")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_line(self, line: str) -> None:
        self._all_lines.append(line)
        if self._matches_filter(line):
            self._pending_visible_lines.append(line)
            if self._append_flush_job is None:
                self._append_flush_job = self.after(100, self._flush_pending_lines)
        self._count_label.configure(text=f"{len(self._all_lines)} 行")

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _on_filter_change(self, value: str) -> None:
        self._current_filter = value
        self._rebuild_display()

    def _on_search_change(self, _event: Any = None) -> None:
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = self.after(150, self._do_search_refresh)

    def _do_search_refresh(self) -> None:
        self._refresh_job = None
        new_text = str(self._search_var.get() or "").strip()
        if new_text != self._search_text:
            self._search_text = new_text
            self._rebuild_display()

    def _matches_filter(self, line: str) -> bool:
        # Category filter
        if self._current_filter == "受信":
            if ("受信:" not in line) and ("指示受信:" not in line):
                return False
        elif self._current_filter == "発注":
            if "DRY-RUN:" not in line and "発注結果:" not in line:
                return False
        elif self._current_filter == "エラー":
            if "エラー" not in line and "失敗" not in line and "例外" not in line:
                return False
        # Search text
        if self._search_text and self._search_text not in line:
            return False
        return True

    def _rebuild_display(self) -> None:
        if self._append_flush_job is not None:
            try:
                self.after_cancel(self._append_flush_job)
            except Exception:
                pass
            self._append_flush_job = None
        self._pending_visible_lines.clear()
        self._apply_tag_colors()
        self._textbox.configure(state="normal")
        self._textbox._textbox.delete("1.0", "end")
        for line in self._all_lines:
            if self._matches_filter(line):
                self._insert_colored_line(line)
        self._textbox.configure(state="disabled")
        self._textbox.see("end")

    # ------------------------------------------------------------------
    # Text insertion with color
    # ------------------------------------------------------------------

    def _append_to_textbox(self, line: str) -> None:
        self._textbox.configure(state="normal")
        self._insert_colored_line(line)
        self._textbox.configure(state="disabled")
        self._textbox.see("end")

    def _flush_pending_lines(self) -> None:
        self._append_flush_job = None
        if not self._pending_visible_lines:
            return
        self._textbox.configure(state="normal")
        for line in self._pending_visible_lines:
            self._insert_colored_line(line)
        self._textbox.configure(state="disabled")
        self._textbox.see("end")
        self._pending_visible_lines.clear()

    def _insert_colored_line(self, line: str) -> None:
        inner = self._textbox._textbox
        tag = self._detect_tag(line)
        if tag:
            inner.insert("end", line + "\n", tag)
        else:
            inner.insert("end", line + "\n")

    def _apply_tag_colors(self) -> None:
        inner = self._textbox._textbox
        inner.tag_configure("dry_run", foreground=resolve_color(COLOR_SUCCESS))
        inner.tag_configure("order", foreground=resolve_color(COLOR_ORANGE))
        inner.tag_configure("error", foreground=resolve_color(COLOR_ERROR))
        inner.tag_configure("received", foreground=resolve_color(COLOR_INFO))

    @staticmethod
    def _detect_tag(line: str) -> str:
        if "DRY-RUN:" in line:
            return "dry_run"
        if "発注結果:" in line:
            return "order"
        if "エラー" in line or "失敗" in line or "例外" in line:
            return "error"
        if (("受信:" in line) or ("指示受信:" in line)) and "payload=" in line:
            return "received"
        return ""

    def _clear_log(self) -> None:
        self._all_lines.clear()
        self._textbox.configure(state="normal")
        self._textbox._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")
        self._count_label.configure(text="0 行")
