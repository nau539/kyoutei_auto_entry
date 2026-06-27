from __future__ import annotations

import re
from typing import Any, Callable

import customtkinter as ctk

from config import (
    DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME,
    DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME,
    AppSettings,
)
from ui.components.card_frame import CardFrame
from ui.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_LIVE_WARN,
    COLOR_SEG_SELECTED,
    COLOR_SEG_SELECTED_HOVER,
    COLOR_SEG_TEXT,
    COLOR_SEG_UNSELECTED,
    COLOR_SEG_UNSELECTED_HOVER,
    COLOR_TEXT_ON_ACCENT,
    COLOR_TEXT_MUTED,
    FONT_BODY,
    FONT_SMALL,
)


class SettingsView(ctk.CTkFrame):
    """Settings panel with BOAT RACE credentials and betting rules."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        settings: AppSettings,
        on_save: Callable[[], None],
        on_toggle_save: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._on_save = on_save
        self._on_toggle_save = on_toggle_save
        self._vars: dict[str, ctk.StringVar] = {}
        self._build_ui()
        self.load_from_settings(settings)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=16)

        # ----- BOAT RACE Card -----
        ipat_card = CardFrame(scroll, title="競艇接続設定")
        ipat_card.pack(fill="x", pady=(0, 16))

        self._vars["login_url"] = ctk.StringVar()
        self._vars["inet_id"] = ctk.StringVar()
        self._vars["login_id"] = ctk.StringVar()
        self._vars["password"] = ctk.StringVar()
        self._vars["pars_no"] = ctk.StringVar()

        for label_text, var_key, show in [
            ("ログインURL", "login_url", ""),
            ("加入者番号", "inet_id", ""),
            ("暗証番号", "pars_no", "*"),
            ("認証用パスワード", "password", "*"),
            ("投票用パスワード", "login_id", "*"),
        ]:
            self._add_entry_row(ipat_card.body, label_text, self._vars[var_key], show=show)

        # Advanced section
        adv_label = ctk.CTkLabel(
            ipat_card.body, text="詳細設定", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED
        )
        adv_label.pack(anchor="w", pady=(12, 4))

        self._vars["headless"] = ctk.StringVar(value="OFF")
        self._add_onoff_row(
            ipat_card.body,
            label_text="headlessで起動",
            variable=self._vars["headless"],
            command=self._on_toggle_save,
        )

        self._vars["submit_enabled"] = ctk.StringVar(value="OFF")
        self._add_onoff_row(
            ipat_card.body,
            label_text="最終確定まで実行する",
            variable=self._vars["submit_enabled"],
            command=self._on_submit_toggle,
        )

        self._submit_warn = ctk.CTkLabel(
            ipat_card.body,
            text="BOAT RACE投票サイト上で実際に確定処理が実行されます",
            font=FONT_SMALL,
            text_color=COLOR_LIVE_WARN,
        )
        # Initially hidden, shown when submit_enabled ON

        # ----- Entry Rules Card -----
        entry_card = CardFrame(scroll, title="投票ルール")
        entry_card.pack(fill="x", pady=(0, 16))

        self._vars["fixed_ticket_yen"] = ctk.StringVar()
        self._vars["raffine_budget_yen"] = ctk.StringVar()
        self._vars["entry_abort_total_yen"] = ctk.StringVar()
        self._vars["entry_abort_mode"] = ctk.StringVar(value="円")
        self._vars["entry_abort_ratio_pct"] = ctk.StringVar()
        self._vars["race_cap_yen"] = ctk.StringVar()
        self._vars["ticket_cap_yen"] = ctk.StringVar()
        self._vars["max_tickets"] = ctk.StringVar()
        self._vars["min_ticket_yen"] = ctk.StringVar()
        self._vars["target_payout_mode"] = ctk.StringVar(value="円")
        self._vars["target_payout_ratio_pct"] = ctk.StringVar()
        self._vars["target_payout_yen"] = ctk.StringVar()

        abort_mode_row = ctk.CTkFrame(entry_card.body, fg_color="transparent")
        abort_mode_row.pack(fill="x", pady=4)
        ctk.CTkLabel(abort_mode_row, text="中止金額の基準", font=FONT_BODY, width=140, anchor="w").pack(side="left")
        self._abort_mode_seg = ctk.CTkSegmentedButton(
            abort_mode_row,
            values=["円", "割合"],
            variable=self._vars["entry_abort_mode"],
            command=lambda _v: self._on_toggle_save(),
            width=160,
            selected_color=COLOR_SEG_SELECTED,
            selected_hover_color=COLOR_SEG_SELECTED_HOVER,
            unselected_color=COLOR_SEG_UNSELECTED,
            unselected_hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_SEG_TEXT,
        )
        self._abort_mode_seg.pack(side="left", padx=(8, 0))

        for label_text, var_key, hint in [
            ("エントリー中止金額(円)", "entry_abort_total_yen", "円以上で見送り (0=無効/基準=円)"),
            ("エントリー中止割合", "entry_abort_ratio_pct", "% (基準=割合。目標払戻に対する割合。0=無効)"),
            ("1レース上限", "race_cap_yen", "円 (0=無制限)"),
            ("1点上限", "ticket_cap_yen", "円 (0=無制限)"),
            ("最大点数", "max_tickets", "(0=無制限)"),
            ("最小金額", "min_ticket_yen", "円 (100以上)"),
        ]:
            self._add_entry_row(entry_card.body, label_text, self._vars[var_key], hint=hint)

        # Allocation mode and parameters
        alloc_label = ctk.CTkLabel(entry_card.body, text="配分方式設定", font=FONT_BODY, anchor="w")
        alloc_label.pack(anchor="w", pady=(12, 4))

        alloc_desc = ctk.CTkLabel(
            entry_card.body,
            text="固定投票・分配投票・配当固定の設定をまとめて変更できます",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        alloc_desc.pack(anchor="w", pady=(0, 6))

        self._vars["allocation_mode"] = ctk.StringVar(value="配当固定")
        self._alloc_seg = ctk.CTkSegmentedButton(
            entry_card.body,
            values=["固定投票", "分配投票", "配当固定"],
            variable=self._vars["allocation_mode"],
            command=lambda _: self._on_toggle_save(),
            selected_color=COLOR_SEG_SELECTED,
            selected_hover_color=COLOR_SEG_SELECTED_HOVER,
            unselected_color=COLOR_SEG_UNSELECTED,
            unselected_hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_SEG_TEXT,
        )
        self._alloc_seg.pack(anchor="w", pady=(0, 8))

        target_mode_row = ctk.CTkFrame(entry_card.body, fg_color="transparent")
        target_mode_row.pack(fill="x", pady=4)
        ctk.CTkLabel(target_mode_row, text="配当固定の基準", font=FONT_BODY, width=140, anchor="w").pack(side="left")
        self._target_mode_seg = ctk.CTkSegmentedButton(
            target_mode_row,
            values=["円", "割合"],
            variable=self._vars["target_payout_mode"],
            command=lambda _v: self._on_toggle_save(),
            width=160,
            selected_color=COLOR_SEG_SELECTED,
            selected_hover_color=COLOR_SEG_SELECTED_HOVER,
            unselected_color=COLOR_SEG_UNSELECTED,
            unselected_hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_SEG_TEXT,
        )
        self._target_mode_seg.pack(side="left", padx=(8, 0))

        for label_text, var_key, hint in [
            ("固定投票金額", "fixed_ticket_yen", "円 (固定投票)"),
            ("分配投票予算", "raffine_budget_yen", "円 (分配投票)"),
            ("目標払戻(円)", "target_payout_yen", "円 (配当固定:円)"),
            ("目標払戻割合", "target_payout_ratio_pct", "% (配当固定:割合)"),
        ]:
            self._add_entry_row(entry_card.body, label_text, self._vars[var_key], hint=hint)

        self._vars["confirm_each_race"] = ctk.StringVar(value="ON")
        self._add_onoff_row(
            entry_card.body,
            label_text="1レースごとに実行前確認する",
            variable=self._vars["confirm_each_race"],
            command=self._on_toggle_save,
        )

        self._vars["show_ticket_preview_window"] = ctk.StringVar(value="ON")
        self._add_onoff_row(
            entry_card.body,
            label_text="買い目シミュレーター画面を表示する",
            variable=self._vars["show_ticket_preview_window"],
            command=self._on_toggle_save,
        )

        sched_label = ctk.CTkLabel(
            entry_card.body,
            text="待機スケジュール（中央）",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
        )
        sched_label.pack(anchor="w", pady=(12, 4))

        self._vars["central_schedule_enabled"] = ctk.StringVar(value="ON")
        self._add_onoff_row(
            entry_card.body,
            label_text="スケジュールで自動開閉する",
            variable=self._vars["central_schedule_enabled"],
            command=self._on_toggle_save,
        )
        self._vars["central_schedule_open_time"] = ctk.StringVar()
        self._vars["central_schedule_close_time"] = ctk.StringVar()
        self._add_entry_row(
            entry_card.body,
            "自動起動時刻",
            self._vars["central_schedule_open_time"],
            hint=f"HH:MM (例 {DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME})",
        )
        self._add_entry_row(
            entry_card.body,
            "自動停止時刻",
            self._vars["central_schedule_close_time"],
            hint=f"HH:MM (例 {DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME})",
        )

        # Save button
        ctk.CTkButton(
            scroll,
            text="設定を保存",
            width=200,
            height=40,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_ON_ACCENT,
            command=self._on_save,
        ).pack(pady=(8, 16))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_entry_row(
        self,
        parent: ctk.CTkBaseClass,
        label_text: str,
        variable: ctk.StringVar,
        show: str = "",
        hint: str = "",
    ) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)

        lbl = ctk.CTkLabel(row, text=label_text, font=FONT_BODY, width=140, anchor="w")
        lbl.pack(side="left")

        entry = ctk.CTkEntry(row, textvariable=variable, font=FONT_BODY, show=show)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        if hint:
            hint_lbl = ctk.CTkLabel(row, text=hint, font=FONT_SMALL, text_color=COLOR_TEXT_MUTED)
            hint_lbl.pack(side="left", padx=(8, 0))

    def _add_onoff_row(
        self,
        parent: ctk.CTkBaseClass,
        label_text: str,
        variable: ctk.StringVar,
        command: Callable[[], None],
    ) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)

        ctk.CTkLabel(row, text=label_text, font=FONT_BODY, width=220, anchor="w").pack(side="left")
        seg = ctk.CTkSegmentedButton(
            row,
            values=["ON", "OFF"],
            variable=variable,
            command=lambda _v: command(),
            width=120,
            selected_color=COLOR_SEG_SELECTED,
            selected_hover_color=COLOR_SEG_SELECTED_HOVER,
            unselected_color=COLOR_SEG_UNSELECTED,
            unselected_hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_SEG_TEXT,
        )
        seg.pack(side="left", padx=(8, 0))

    def _on_submit_toggle(self) -> None:
        if self._is_on("submit_enabled"):
            self._submit_warn.pack(anchor="w", padx=(24, 0), pady=(0, 4))
        else:
            self._submit_warn.pack_forget()
        self._on_toggle_save()

    # ------------------------------------------------------------------
    # Data binding
    # ------------------------------------------------------------------

    def load_from_settings(self, s: AppSettings) -> None:
        self._vars["login_url"].set(str(getattr(s.ipat, "login_url", "") or ""))
        self._vars["inet_id"].set(s.ipat.inet_id)
        self._vars["login_id"].set(s.ipat.login_id)
        self._vars["password"].set(s.ipat.password)
        self._vars["pars_no"].set(s.ipat.pars_no)
        self._vars["headless"].set("ON" if s.ipat.headless else "OFF")
        self._vars["submit_enabled"].set("ON" if s.ipat.submit_enabled else "OFF")
        if s.ipat.submit_enabled:
            self._submit_warn.pack(anchor="w", padx=(24, 0), pady=(0, 4))

        self._vars["fixed_ticket_yen"].set(str(getattr(s.entry, "fixed_ticket_yen", 100)))
        self._vars["raffine_budget_yen"].set(str(getattr(s.entry, "raffine_budget_yen", 10000)))
        self._vars["entry_abort_total_yen"].set(str(getattr(s.entry, "entry_abort_total_yen", 10000)))
        abort_mode = self._abort_mode_code_to_display(getattr(s.entry, "entry_abort_mode", "yen"))
        self._vars["entry_abort_mode"].set(abort_mode)
        self._abort_mode_seg.set(abort_mode)
        self._vars["entry_abort_ratio_pct"].set(str(getattr(s.entry, "entry_abort_ratio_pct", 100.0)))
        self._vars["race_cap_yen"].set(str(s.entry.race_cap_yen))
        self._vars["ticket_cap_yen"].set(str(s.entry.ticket_cap_yen))
        self._vars["max_tickets"].set(str(s.entry.max_tickets))
        self._vars["min_ticket_yen"].set(str(s.entry.min_ticket_yen))
        target_mode = self._target_mode_code_to_display(getattr(s.entry, "target_payout_mode", "yen"))
        self._vars["target_payout_mode"].set(target_mode)
        self._target_mode_seg.set(target_mode)
        self._vars["target_payout_ratio_pct"].set(str(getattr(s.entry, "target_payout_ratio_pct", 1000.0)))
        self._vars["target_payout_yen"].set(str(getattr(s.entry, "target_payout_yen", 10000)))

        alloc = self._alloc_code_to_display(getattr(s.entry, "allocation_mode", "target_payout"))
        self._vars["allocation_mode"].set(alloc)
        self._alloc_seg.set(alloc)

        self._vars["confirm_each_race"].set("ON" if s.entry.confirm_each_race else "OFF")
        self._vars["show_ticket_preview_window"].set("ON" if s.entry.show_ticket_preview_window else "OFF")
        self._vars["central_schedule_enabled"].set("ON" if getattr(s.entry, "central_schedule_enabled", True) else "OFF")
        self._vars["central_schedule_open_time"].set(
            str(
                getattr(s.entry, "central_schedule_open_time", DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME)
                or DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME
            )
        )
        self._vars["central_schedule_close_time"].set(
            str(
                getattr(s.entry, "central_schedule_close_time", DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME)
                or DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME
            )
        )

    def collect_to_settings(self, s: AppSettings) -> None:
        """Write form fields to settings. Non-displayed advanced fields are preserved."""
        s.ipat.login_url = str(self._vars["login_url"].get() or "").strip()
        s.ipat.inet_id = str(self._vars["inet_id"].get() or "").strip()
        s.ipat.login_id = str(self._vars["login_id"].get() or "").strip()
        s.ipat.password = str(self._vars["password"].get() or "").strip()
        s.ipat.pars_no = str(self._vars["pars_no"].get() or "").strip()
        s.ipat.headless = self._is_on("headless")
        s.ipat.submit_enabled = self._is_on("submit_enabled")

        s.entry.fixed_ticket_yen = self._safe_int(
            "fixed_ticket_yen", getattr(s.entry, "fixed_ticket_yen", 100), min_val=100
        )
        s.entry.raffine_budget_yen = self._safe_int(
            "raffine_budget_yen", getattr(s.entry, "raffine_budget_yen", 10000), min_val=100
        )
        s.entry.entry_abort_total_yen = self._safe_int(
            "entry_abort_total_yen", getattr(s.entry, "entry_abort_total_yen", 10000), min_val=0
        )
        s.entry.entry_abort_mode = self._abort_mode_display_to_code(str(self._vars["entry_abort_mode"].get() or "円"))
        s.entry.entry_abort_ratio_pct = self._safe_float(
            "entry_abort_ratio_pct", getattr(s.entry, "entry_abort_ratio_pct", 100.0), min_val=0.0
        )
        s.entry.race_cap_yen = self._safe_int("race_cap_yen", s.entry.race_cap_yen, min_val=0)
        s.entry.ticket_cap_yen = self._safe_int("ticket_cap_yen", s.entry.ticket_cap_yen, min_val=0)
        s.entry.max_tickets = self._safe_int("max_tickets", s.entry.max_tickets, min_val=0)
        s.entry.min_ticket_yen = self._safe_int("min_ticket_yen", s.entry.min_ticket_yen, min_val=100)
        s.entry.target_payout_mode = self._target_mode_display_to_code(str(self._vars["target_payout_mode"].get() or "円"))
        s.entry.target_payout_ratio_pct = self._safe_float(
            "target_payout_ratio_pct", getattr(s.entry, "target_payout_ratio_pct", 1000.0), min_val=1.0
        )
        s.entry.target_payout_yen = self._safe_int(
            "target_payout_yen", getattr(s.entry, "target_payout_yen", 10000), min_val=100
        )

        alloc_display = str(self._vars["allocation_mode"].get() or "配当固定")
        s.entry.allocation_mode = self._alloc_display_to_code(alloc_display)
        s.entry.enable_central = True
        s.entry.enable_local = False

        s.entry.confirm_each_race = self._is_on("confirm_each_race")
        s.entry.show_ticket_preview_window = self._is_on("show_ticket_preview_window")
        s.entry.central_schedule_enabled = self._is_on("central_schedule_enabled")
        s.entry.central_schedule_open_time = self._normalize_hhmm(
            self._vars["central_schedule_open_time"].get(),
            getattr(s.entry, "central_schedule_open_time", DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME),
        )
        s.entry.central_schedule_close_time = self._normalize_hhmm(
            self._vars["central_schedule_close_time"].get(),
            getattr(s.entry, "central_schedule_close_time", DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME),
        )

    def collect_toggles(self, s: AppSettings) -> None:
        """Save only toggle/switch values (auto-save on change)."""
        s.ipat.headless = self._is_on("headless")
        s.ipat.submit_enabled = self._is_on("submit_enabled")
        s.entry.confirm_each_race = self._is_on("confirm_each_race")
        s.entry.show_ticket_preview_window = self._is_on("show_ticket_preview_window")
        s.entry.central_schedule_enabled = self._is_on("central_schedule_enabled")
        s.entry.enable_central = True
        s.entry.enable_local = False
        alloc_display = str(self._vars["allocation_mode"].get() or "配当固定")
        s.entry.allocation_mode = self._alloc_display_to_code(alloc_display)
        s.entry.entry_abort_mode = self._abort_mode_display_to_code(str(self._vars["entry_abort_mode"].get() or "円"))
        s.entry.target_payout_mode = self._target_mode_display_to_code(str(self._vars["target_payout_mode"].get() or "円"))

    def _is_on(self, key: str) -> bool:
        return str(self._vars[key].get() or "").strip().upper() == "ON"

    def _safe_int(self, key: str, default: int, min_val: int = 0) -> int:
        raw = str(self._vars[key].get() or "").replace(",", "").strip()
        try:
            val = int(raw)
        except Exception:
            val = int(default)
        return max(min_val, val)

    def _safe_float(self, key: str, default: float, min_val: float = 0.0) -> float:
        raw = str(self._vars[key].get() or "").replace(",", "").strip()
        try:
            val = float(raw)
        except Exception:
            val = float(default)
        return max(min_val, val)

    def _normalize_hhmm(self, value: Any, fallback: Any) -> str:
        text = str(value or "").strip().replace("：", ":")
        if not text:
            text = str(fallback or "").strip().replace("：", ":")
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
        if not m:
            return str(fallback or DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME)
        try:
            hour = int(m.group(1))
            minute = int(m.group(2))
        except Exception:
            return str(fallback or DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return str(fallback or DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME)
        return f"{hour:02d}:{minute:02d}"

    def _alloc_display_to_code(self, display: str) -> str:
        value = str(display or "").strip()
        if value in {"分配投票", "ラフィーネ法"}:
            return "raffine"
        if value in {"配当固定", "配当固定法"}:
            return "target_payout"
        return "target_payout"

    def _alloc_code_to_display(self, code: str) -> str:
        value = str(code or "").strip().lower()
        if value == "raffine":
            return "分配投票"
        if value in {"target_payout", "payout_target"}:
            return "配当固定"
        return "配当固定"

    def _target_mode_display_to_code(self, display: str) -> str:
        value = str(display or "").strip()
        if value in {"割合", "ratio"}:
            return "ratio"
        return "yen"

    def _target_mode_code_to_display(self, code: str) -> str:
        value = str(code or "").strip().lower()
        if value in {"ratio", "rate", "pct", "percent", "割合"}:
            return "割合"
        return "円"

    def _abort_mode_display_to_code(self, display: str) -> str:
        value = str(display or "").strip()
        if value in {"割合", "ratio"}:
            return "ratio"
        return "yen"

    def _abort_mode_code_to_display(self, code: str) -> str:
        value = str(code or "").strip().lower()
        if value in {"ratio", "rate", "pct", "percent", "割合"}:
            return "割合"
        return "円"
