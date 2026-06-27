from __future__ import annotations

from typing import Any, Callable, List

import customtkinter as ctk

from config import DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME, DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME, AppSettings
from product_profile import TOOL_SLOT_ORDER
from ui.components.card_frame import CardFrame
from ui.theme import (
    COLOR_ACCENT_HOVER,
    COLOR_CARD_BG,
    COLOR_DIMMED,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_SEG_SELECTED,
    COLOR_SEG_SELECTED_HOVER,
    COLOR_SEG_TEXT,
    COLOR_SEG_UNSELECTED,
    COLOR_SEG_UNSELECTED_HOVER,
    COLOR_SUCCESS,
    COLOR_TEXT_ON_ACCENT,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    FONT_BODY,
    FONT_HEADING,
    FONT_MONO_SM,
    FONT_SMALL,
    FONT_STAT_VAL,
)


class ClassicDashboardView(ctk.CTkFrame):
    """Legacy-style operator view used by the trial build."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        settings: AppSettings,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_save: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_save = on_save
        self._is_running = False
        self._is_busy = False
        self._activity_lines: List[str] = []
        self._activity_refresh_job: str | None = None
        self._vars: dict[str, ctk.StringVar] = {}
        self._build_ui()
        self.load_from_settings(settings)

    def _build_ui(self) -> None:
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=14)

        status_card = CardFrame(scroll, title="運用状態")
        status_card.pack(fill="x", pady=(0, 12))

        self._discord_status = ctk.CTkLabel(
            status_card.body,
            text="連携: 未接続",
            font=FONT_BODY,
            text_color=COLOR_TEXT_MUTED,
        )
        self._discord_status.pack(anchor="w", pady=2)

        self._running_status = ctk.CTkLabel(
            status_card.body,
            text="監視: 停止中",
            font=FONT_BODY,
            text_color=COLOR_TEXT_MUTED,
        )
        self._running_status.pack(anchor="w", pady=2)

        ctk.CTkLabel(
            status_card.body,
            text=(
                "LIVE固定 / 最終確定ON / "
                f"自動開閉 {DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME}-{DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME}"
            ),
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", pady=(4, 0))

        stats_row = ctk.CTkFrame(scroll, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 12))
        stats_row.grid_columnconfigure((0, 1, 2), weight=1)

        self._stat_received_label = self._make_stat_tile(stats_row, "本日受信", "0", 0)
        self._stat_ordered_label = self._make_stat_tile(stats_row, "本日発注", "0", 1)
        self._stat_skipped_label = self._make_stat_tile(stats_row, "本日見送り", "0", 2)

        action_card = CardFrame(scroll, title="操作")
        action_card.pack(fill="x", pady=(0, 12))

        btn_row = ctk.CTkFrame(action_card.body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(2, 8))

        self._btn_run_toggle = ctk.CTkButton(
            btn_row,
            text="開始する",
            width=132,
            height=40,
            fg_color=COLOR_ERROR,
            hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_ON_ACCENT,
            command=self._on_toggle_run,
        )
        self._btn_run_toggle.pack(side="left", padx=(0, 8))

        self._btn_save = ctk.CTkButton(
            btn_row,
            text="設定保存",
            width=132,
            height=40,
            fg_color=COLOR_INFO,
            hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_ON_ACCENT,
            command=self._on_save,
        )
        self._btn_save.pack(side="left")

        ctk.CTkLabel(
            action_card.body,
            text="レビュー画面とDRY-RUNは非表示です。保存内容は開始時にも反映されます。",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w")

        connect_card = CardFrame(scroll, title="競艇接続")
        connect_card.pack(fill="x", pady=(0, 12))

        self._vars["login_url"] = ctk.StringVar()
        self._vars["inet_id"] = ctk.StringVar()
        self._vars["login_id"] = ctk.StringVar()
        self._vars["password"] = ctk.StringVar()
        self._vars["pars_no"] = ctk.StringVar()
        self._vars["headless"] = ctk.StringVar(value="ON")

        for label_text, var_key, show in [
            ("ログインURL", "login_url", ""),
            ("加入者番号", "inet_id", ""),
            ("暗証番号", "pars_no", "*"),
            ("認証用パスワード", "password", "*"),
            ("投票用パスワード", "login_id", "*"),
        ]:
            self._add_entry_row(connect_card.body, label_text, self._vars[var_key], show=show)

        self._add_onoff_row(
            connect_card.body,
            label_text="headlessで起動",
            variable=self._vars["headless"],
        )

        setting_card = CardFrame(scroll, title="投票設定")
        setting_card.pack(fill="x", pady=(0, 12))

        self._vars["target_payout_yen"] = ctk.StringVar()
        self._vars["entry_abort_total_yen"] = ctk.StringVar()

        self._add_entry_row(setting_card.body, "目標払戻(円)", self._vars["target_payout_yen"])
        self._add_entry_row(
            setting_card.body,
            "エントリー中止金額",
            self._vars["entry_abort_total_yen"],
            hint="円以上で見送り / 0で無効",
        )

        ctk.CTkLabel(
            setting_card.body,
            text="固定配当のみを使用し、目標払戻額を円で指定します。",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", pady=(6, 0))

        activity_card = CardFrame(scroll, title="最近のログ")
        activity_card.pack(fill="x", pady=(0, 8))

        self._activity_textbox = ctk.CTkTextbox(
            activity_card.body,
            font=FONT_MONO_SM,
            height=160,
            state="disabled",
            wrap="none",
        )
        self._activity_textbox.pack(fill="x")

        self._refresh_button_states()

    def _make_stat_tile(self, parent: ctk.CTkFrame, label: str, initial: str, col: int) -> ctk.CTkLabel:
        tile = ctk.CTkFrame(parent, corner_radius=12, fg_color=COLOR_CARD_BG)
        tile.grid(row=0, column=col, sticky="nsew", padx=4)

        value_label = ctk.CTkLabel(tile, text=initial, font=FONT_STAT_VAL, text_color=COLOR_TEXT_PRIMARY)
        value_label.pack(padx=16, pady=(12, 0))

        ctk.CTkLabel(tile, text=label, font=FONT_SMALL, text_color=COLOR_DIMMED).pack(
            padx=16,
            pady=(0, 12),
        )
        return value_label

    def _add_entry_row(
        self,
        parent: ctk.CTkBaseClass,
        label_text: str,
        variable: ctk.StringVar,
        *,
        show: str = "",
        hint: str = "",
    ) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)

        ctk.CTkLabel(row, text=label_text, font=FONT_BODY, width=190, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, textvariable=variable, font=FONT_BODY, show=show)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        if hint:
            ctk.CTkLabel(row, text=hint, font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(8, 0))

    def _add_onoff_row(self, parent: ctk.CTkBaseClass, *, label_text: str, variable: ctk.StringVar) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)

        ctk.CTkLabel(row, text=label_text, font=FONT_BODY, width=190, anchor="w").pack(side="left")
        seg = ctk.CTkSegmentedButton(
            row,
            values=["ON", "OFF"],
            variable=variable,
            selected_color=COLOR_SEG_SELECTED,
            selected_hover_color=COLOR_SEG_SELECTED_HOVER,
            unselected_color=COLOR_SEG_UNSELECTED,
            unselected_hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_SEG_TEXT,
            width=120,
        )
        seg.pack(side="left", padx=(8, 0))

    def load_from_settings(self, settings: AppSettings) -> None:
        self._vars["login_url"].set(str(getattr(settings.ipat, "login_url", "") or ""))
        self._vars["inet_id"].set(str(getattr(settings.ipat, "inet_id", "") or ""))
        self._vars["pars_no"].set(str(getattr(settings.ipat, "pars_no", "") or ""))
        self._vars["password"].set(str(getattr(settings.ipat, "password", "") or ""))
        self._vars["login_id"].set(str(getattr(settings.ipat, "login_id", "") or ""))
        self._vars["headless"].set("ON" if bool(getattr(settings.ipat, "headless", True)) else "OFF")
        self._vars["target_payout_yen"].set(str(int(getattr(settings.entry, "target_payout_yen", 10000) or 10000)))
        self._vars["entry_abort_total_yen"].set(str(int(getattr(settings.entry, "entry_abort_total_yen", 10000) or 0)))

    def collect_to_settings(self, settings: AppSettings) -> None:
        settings.ipat.login_url = str(self._vars["login_url"].get() or "").strip()
        settings.ipat.inet_id = str(self._vars["inet_id"].get() or "").strip()
        settings.ipat.pars_no = str(self._vars["pars_no"].get() or "").strip()
        settings.ipat.password = str(self._vars["password"].get() or "").strip()
        settings.ipat.login_id = str(self._vars["login_id"].get() or "").strip()
        settings.ipat.headless = self._is_on("headless")
        settings.ipat.submit_enabled = True

        settings.entry.fixed_ticket_yen = 100
        settings.entry.entry_abort_total_yen = self._safe_int(
            "entry_abort_total_yen",
            getattr(settings.entry, "entry_abort_total_yen", 10000),
            min_val=0,
        )
        settings.entry.entry_abort_mode = "yen"
        settings.entry.entry_abort_ratio_pct = 100.0
        settings.entry.ratio_pct = 100.0
        settings.entry.race_cap_yen = 0
        settings.entry.ticket_cap_yen = 0
        settings.entry.max_tickets = 0
        settings.entry.min_ticket_yen = 100
        settings.entry.target_payout_mode = "yen"
        settings.entry.target_payout_ratio_pct = 1000.0
        settings.entry.target_payout_yen = self._safe_int(
            "target_payout_yen",
            getattr(settings.entry, "target_payout_yen", 10000),
            min_val=100,
        )
        settings.entry.dry_run = False
        settings.entry.confirm_each_race = False
        settings.entry.show_ticket_preview_window = False
        settings.entry.allocation_mode = "target_payout"
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.central_schedule_enabled = True
        settings.entry.central_schedule_open_time = DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME
        settings.entry.central_schedule_close_time = DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME
        settings.entry.plan_tier = "gold"
        settings.entry.tool_slots = list(TOOL_SLOT_ORDER)

    def sync_mode(self, _is_dry_run: bool) -> None:
        return

    def set_running(self, running: bool) -> None:
        self._is_running = bool(running)
        if self._is_running:
            self._running_status.configure(text="監視: 実行中", text_color=COLOR_SUCCESS)
        else:
            self._running_status.configure(text="監視: 停止中", text_color=COLOR_TEXT_MUTED)
        self._refresh_button_states()

    def set_busy(self, busy: bool) -> None:
        self._is_busy = bool(busy)
        self._refresh_button_states()

    def update_discord(self, connected: bool) -> None:
        if connected:
            self._discord_status.configure(text="連携: 接続中", text_color=COLOR_SUCCESS)
        else:
            self._discord_status.configure(text="連携: 未接続", text_color=COLOR_TEXT_MUTED)

    def update_stats(self, received: int, ordered: int, skipped: int) -> None:
        self._stat_received_label.configure(text=str(received))
        self._stat_ordered_label.configure(text=str(ordered))
        self._stat_skipped_label.configure(text=str(skipped))

    def append_activity(self, line: str) -> None:
        self._activity_lines.append(line)
        if len(self._activity_lines) > 50:
            self._activity_lines = self._activity_lines[-50:]
        if self._activity_refresh_job is None:
            self._activity_refresh_job = self.after(120, self._flush_activity)

    def _flush_activity(self) -> None:
        self._activity_refresh_job = None
        recent = self._activity_lines[-8:]
        self._activity_textbox.configure(state="normal")
        self._activity_textbox.delete("1.0", "end")
        self._activity_textbox.insert("end", "\n".join(recent))
        self._activity_textbox.configure(state="disabled")

    def _refresh_button_states(self) -> None:
        if self._is_running:
            self._btn_run_toggle.configure(
                text="停止する",
                fg_color=COLOR_SUCCESS,
                hover_color=COLOR_ACCENT_HOVER,
                text_color=COLOR_TEXT_ON_ACCENT,
            )
        else:
            self._btn_run_toggle.configure(
                text="開始する",
                fg_color=COLOR_ERROR,
                hover_color=COLOR_ACCENT_HOVER,
                text_color=COLOR_TEXT_ON_ACCENT,
            )

        if self._is_busy:
            self._btn_run_toggle.configure(state="disabled")
            self._btn_save.configure(state="disabled")
            return

        self._btn_run_toggle.configure(state="normal")
        self._btn_save.configure(state="normal")

    def _on_toggle_run(self) -> None:
        if self._is_running:
            self._on_stop()
        else:
            self._on_start()

    def _is_on(self, key: str) -> bool:
        return str(self._vars[key].get() or "").strip().upper() == "ON"

    def _safe_int(self, key: str, default: int, *, min_val: int = 0) -> int:
        raw = str(self._vars[key].get() or "").replace(",", "").strip()
        try:
            value = int(raw)
        except Exception:
            value = int(default)
        return max(int(min_val), int(value))
