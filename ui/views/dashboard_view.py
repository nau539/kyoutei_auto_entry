from __future__ import annotations

from typing import Any, Callable, List

import customtkinter as ctk

from config import DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME, DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME, AppSettings
from product_profile import (
    DEFAULT_PLAN_TIER,
    PLAN_ORDER,
    PRODUCT_NAME,
    TOOL_SLOT_ORDER,
    fixed_plan_tier,
    manual_review_enabled,
    normalize_plan_tier,
    normalize_tool_slots,
    plan_label,
    plan_palette,
    plan_slot_limit,
    raw_plan_label,
    selected_tool_slots,
    tool_slot_label,
    update_tool_slot_selection,
)
from ui.components.card_frame import CardFrame
from ui.theme import (
    COLOR_CARD_BG,
    COLOR_CARD_ELEVATED,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_TEXT_ON_ACCENT,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    FONT_BODY,
    FONT_HEADING,
    FONT_HERO,
    FONT_MONO_SM,
    FONT_SMALL,
    FONT_STAT_VAL,
    FONT_TINY,
)


class DashboardView(ctk.CTkFrame):
    """Product-style operator dashboard for KYOUTEI AI ZERO."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        settings: AppSettings,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_save: Callable[[], None],
        on_profile_change: Callable[[str, list[str]], None] | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_save = on_save
        self._on_profile_change = on_profile_change
        self._is_running = False
        self._is_busy = False
        self._activity_lines: List[str] = []
        self._activity_refresh_job: str | None = None
        self._vars: dict[str, ctk.StringVar] = {}
        self._plan_buttons: dict[str, ctk.CTkButton] = {}
        self._slot_buttons: dict[str, ctk.CTkButton] = {}
        self._fixed_plan_tier = fixed_plan_tier()
        self._plan_tier = self._fixed_plan_tier or DEFAULT_PLAN_TIER
        self._selected_slots = list(TOOL_SLOT_ORDER)
        self._build_ui()
        self.load_from_settings(settings)

    def _build_ui(self) -> None:
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=16)

        self._hero_card = ctk.CTkFrame(scroll, corner_radius=22, fg_color=COLOR_CARD_BG)
        self._hero_card.pack(fill="x", pady=(0, 12))
        self._hero_card.grid_columnconfigure(0, weight=1)
        self._hero_card.grid_columnconfigure(1, weight=0)

        hero_left = ctk.CTkFrame(self._hero_card, fg_color="transparent")
        hero_left.grid(row=0, column=0, sticky="nsew", padx=(20, 12), pady=20)

        self._hero_badge = ctk.CTkLabel(
            hero_left,
            text=plan_label(self._plan_tier),
            font=(FONT_HEADING[0], 11, "bold"),
            corner_radius=999,
            padx=12,
            pady=5,
        )
        self._hero_badge.pack(anchor="w", pady=(0, 10))

        self._hero_title = ctk.CTkLabel(
            hero_left,
            text=PRODUCT_NAME,
            font=FONT_HERO,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        self._hero_title.pack(anchor="w")

        self._hero_subtitle = ctk.CTkLabel(
            hero_left,
            text="プラン別の利用枠と Discord 受信を1画面で管理します。",
            font=FONT_BODY,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self._hero_subtitle.pack(anchor="w", pady=(4, 10))

        self._hero_slot_summary = ctk.CTkLabel(
            hero_left,
            text="",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
            justify="left",
        )
        self._hero_slot_summary.pack(anchor="w")

        self._hero_schedule_summary = ctk.CTkLabel(
            hero_left,
            text="",
            font=FONT_TINY,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
            justify="left",
        )
        self._hero_schedule_summary.pack(anchor="w", pady=(4, 0))

        hero_right = ctk.CTkFrame(self._hero_card, fg_color="transparent")
        hero_right.grid(row=0, column=1, sticky="ne", padx=(0, 20), pady=20)

        self._btn_run_toggle = ctk.CTkButton(
            hero_right,
            text="開始する",
            width=150,
            height=42,
            fg_color=COLOR_ERROR,
            text_color=COLOR_TEXT_ON_ACCENT,
            command=self._on_toggle_run,
        )
        self._btn_run_toggle.pack(fill="x", pady=(0, 10))

        self._btn_save = ctk.CTkButton(
            hero_right,
            text="設定保存",
            width=150,
            height=42,
            fg_color=COLOR_INFO,
            text_color=COLOR_TEXT_ON_ACCENT,
            command=self._on_save,
        )
        self._btn_save.pack(fill="x")

        hero_status = ctk.CTkFrame(self._hero_card, fg_color="transparent")
        hero_status.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 18))
        hero_status.grid_columnconfigure((0, 1, 2), weight=1)

        self._discord_status = ctk.CTkLabel(
            hero_status,
            text="連携: 未接続",
            font=FONT_BODY,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self._discord_status.grid(row=0, column=0, sticky="w")

        self._running_status = ctk.CTkLabel(
            hero_status,
            text="監視: 停止中",
            font=FONT_BODY,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self._running_status.grid(row=0, column=1, sticky="w")

        self._profile_status = ctk.CTkLabel(
            hero_status,
            text="",
            font=FONT_BODY,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self._profile_status.grid(row=0, column=2, sticky="w")

        stats_row = ctk.CTkFrame(scroll, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 12))
        stats_row.grid_columnconfigure((0, 1, 2), weight=1)

        self._stat_received_label = self._make_stat_tile(stats_row, "本日受信", "0", 0)
        self._stat_ordered_label = self._make_stat_tile(stats_row, "本日発注", "0", 1)
        self._stat_skipped_label = self._make_stat_tile(stats_row, "本日見送り", "0", 2)

        plan_card = CardFrame(scroll, title="プラン")
        plan_card.pack(fill="x", pady=(0, 12))
        plan_wrap = ctk.CTkFrame(plan_card.body, fg_color="transparent")
        plan_wrap.pack(fill="x")
        plan_wrap.grid_columnconfigure((0, 1, 2), weight=1)
        for idx, tier in enumerate(PLAN_ORDER):
            btn = ctk.CTkButton(
                plan_wrap,
                text=raw_plan_label(tier),
                height=78,
                command=lambda t=tier: self._select_plan_tier(t),
                text_color=COLOR_TEXT_PRIMARY,
            )
            btn.grid(row=0, column=idx, sticky="nsew", padx=4, pady=2)
            self._plan_buttons[tier] = btn
        self._plan_hint_label = ctk.CTkLabel(
            plan_card.body,
            text="BRONZE は1つまで、SILVER は2つまで、GOLD はどれでも選べます。",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self._plan_hint_label.pack(anchor="w", pady=(8, 0))

        slot_card = CardFrame(scroll, title="利用ツール")
        slot_card.pack(fill="x", pady=(0, 12))
        slot_wrap = ctk.CTkFrame(slot_card.body, fg_color="transparent")
        slot_wrap.pack(fill="x")
        slot_wrap.grid_columnconfigure((0, 1, 2), weight=1)
        for idx, slot in enumerate(TOOL_SLOT_ORDER):
            btn = ctk.CTkButton(
                slot_wrap,
                text=tool_slot_label(slot),
                height=72,
                command=lambda s=slot: self._select_tool_slot(s),
                text_color=COLOR_TEXT_PRIMARY,
            )
            btn.grid(row=0, column=idx, sticky="nsew", padx=4, pady=2)
            self._slot_buttons[slot] = btn
        self._slot_hint_label = ctk.CTkLabel(
            slot_card.body,
            text="",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self._slot_hint_label.pack(anchor="w", pady=(8, 0))

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
        self._add_onoff_row(connect_card.body, label_text="headlessで起動", variable=self._vars["headless"])

        setting_card = CardFrame(scroll, title="投票ルール")
        setting_card.pack(fill="x", pady=(0, 12))

        self._vars["target_payout_yen"] = ctk.StringVar()
        self._vars["entry_abort_total_yen"] = ctk.StringVar()
        self._vars["execution_mode"] = ctk.StringVar(value="手動")
        self._execution_mode_buttons: list[ctk.CTkRadioButton] = []
        self._add_entry_row(setting_card.body, "目標払戻(円)", self._vars["target_payout_yen"])
        self._add_entry_row(
            setting_card.body,
            "エントリー中止金額",
            self._vars["entry_abort_total_yen"],
            hint="円以上で見送り / 0で無効",
        )
        if self._fixed_plan_tier:
            mode_row = ctk.CTkFrame(setting_card.body, fg_color="transparent")
            mode_row.pack(fill="x", pady=4)

            ctk.CTkLabel(mode_row, text="実行方法", font=FONT_BODY, width=210, anchor="w").pack(side="left")
            mode_options = ctk.CTkFrame(mode_row, fg_color="transparent")
            mode_options.pack(side="left", padx=(8, 0))
            for idx, label in enumerate(("自動", "手動")):
                radio = ctk.CTkRadioButton(
                    mode_options,
                    text=label,
                    value=label,
                    variable=self._vars["execution_mode"],
                    command=self._apply_plan_palette,
                    font=FONT_BODY,
                    text_color=COLOR_TEXT_PRIMARY,
                )
                radio.grid(row=0, column=idx, sticky="w", padx=(0 if idx == 0 else 18, 0))
                self._execution_mode_buttons.append(radio)

        self._rule_note = ctk.CTkLabel(
            setting_card.body,
            text="固定配当で再計算し、選択した利用枠だけを取り込みます。",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
            justify="left",
        )
        self._rule_note.pack(anchor="w", pady=(6, 0))

        activity_card = CardFrame(scroll, title="最近のログ")
        activity_card.pack(fill="x", pady=(0, 8))

        self._activity_textbox = ctk.CTkTextbox(
            activity_card.body,
            font=FONT_MONO_SM,
            height=170,
            state="disabled",
            wrap="none",
            fg_color=COLOR_CARD_ELEVATED,
        )
        self._activity_textbox.pack(fill="x")

        self._refresh_button_states()
        self._apply_plan_palette()

    def _make_stat_tile(
        self,
        parent: ctk.CTkFrame,
        label: str,
        initial: str,
        col: int,
    ) -> ctk.CTkLabel:
        tile = ctk.CTkFrame(parent, corner_radius=14, fg_color=COLOR_CARD_BG)
        tile.grid(row=0, column=col, sticky="nsew", padx=4)

        value_label = ctk.CTkLabel(tile, text=initial, font=FONT_STAT_VAL, text_color=COLOR_TEXT_PRIMARY)
        value_label.pack(padx=16, pady=(12, 0))

        ctk.CTkLabel(tile, text=label, font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).pack(
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

        ctk.CTkLabel(row, text=label_text, font=FONT_BODY, width=210, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, textvariable=variable, font=FONT_BODY, show=show)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        if hint:
            ctk.CTkLabel(row, text=hint, font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(8, 0))

    def _add_onoff_row(
        self,
        parent: ctk.CTkBaseClass,
        *,
        label_text: str,
        variable: ctk.StringVar,
    ) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)

        ctk.CTkLabel(row, text=label_text, font=FONT_BODY, width=210, anchor="w").pack(side="left")
        seg = ctk.CTkSegmentedButton(row, values=["ON", "OFF"], variable=variable, width=120)
        seg.pack(side="left", padx=(8, 0))

    def _review_mode_available(self) -> bool:
        return manual_review_enabled(
            fixed_tier=self._fixed_plan_tier,
            classic_trial=False,
        )

    def _manual_review_selected(self) -> bool:
        if not self._review_mode_available():
            return False
        return str(self._vars["execution_mode"].get() or "手動").strip() == "手動"

    def _normalize_profile_slots(self, slots: list[str] | None = None, tier: str | None = None) -> list[str]:
        plan = normalize_plan_tier(tier or self._plan_tier)
        source = self._selected_slots if slots is None else slots
        return normalize_tool_slots(source, plan, default=TOOL_SLOT_ORDER)

    def _select_plan_tier(self, tier: str) -> None:
        if self._fixed_plan_tier:
            return
        self._plan_tier = normalize_plan_tier(tier)
        self._selected_slots = self._normalize_profile_slots(tier=self._plan_tier)
        self._apply_plan_palette()
        self._notify_profile_change()

    def _select_tool_slot(self, slot: str) -> None:
        self._selected_slots = update_tool_slot_selection(self._selected_slots, slot, self._plan_tier)
        self._apply_plan_palette()
        self._notify_profile_change()

    def _notify_profile_change(self) -> None:
        if self._on_profile_change is None:
            return
        self._on_profile_change(self._plan_tier, list(self._selected_slots))

    def _apply_plan_palette(self) -> None:
        palette = plan_palette(self._plan_tier)
        accent = palette["accent"]
        accent_hover = palette["accent_hover"]
        soft = palette["soft"]
        strong = palette["strong"]
        sidebar_active = palette["sidebar_active"]
        sidebar_hover = palette["sidebar_hover"]

        self._hero_card.configure(fg_color=soft)
        self._hero_badge.configure(
            text=plan_label(self._plan_tier),
            fg_color=palette["badge_fg"],
            text_color=palette["badge_text"],
        )

        self._btn_save.configure(fg_color=accent, hover_color=accent_hover)

        for tier, btn in self._plan_buttons.items():
            if self._fixed_plan_tier:
                btn.configure(state="disabled")
            if tier == self._plan_tier:
                btn.configure(fg_color=accent, hover_color=accent_hover, text_color=COLOR_TEXT_ON_ACCENT)
            else:
                btn.configure(fg_color=soft, hover_color=sidebar_hover, text_color=COLOR_TEXT_PRIMARY)

        for slot, btn in self._slot_buttons.items():
            if slot in self._selected_slots:
                btn.configure(fg_color=accent, hover_color=accent_hover, text_color=COLOR_TEXT_ON_ACCENT)
            else:
                btn.configure(fg_color=sidebar_active, hover_color=sidebar_hover, text_color=COLOR_TEXT_PRIMARY)

        for radio in self._execution_mode_buttons:
            radio.configure(
                fg_color=accent,
                hover_color=accent_hover,
                border_color=strong,
                text_color=COLOR_TEXT_PRIMARY,
            )

        display_slots = [slot for slot in TOOL_SLOT_ORDER if slot in self._selected_slots]
        slot_labels = [tool_slot_label(slot) for slot in display_slots]
        self._hero_slot_summary.configure(
            text=f"利用枠: {' / '.join(slot_labels) or '未選択'}"
        )
        if self._review_mode_available():
            if self._manual_review_selected():
                self._hero_schedule_summary.configure(text="実行方法: 手動確認")
                self._rule_note.configure(
                    text="固定配当で再計算し、各レースは確認ダイアログで投票可否を選べます。"
                )
            else:
                self._hero_schedule_summary.configure(text="実行方法: 自動実行")
                self._rule_note.configure(
                    text="固定配当で再計算し、確認なしで最終確定まで自動実行します。"
                )
        else:
            self._hero_schedule_summary.configure(text="")
            self._rule_note.configure(text="固定配当で再計算し、選択した利用枠だけを取り込みます。")
        self._profile_status.configure(
            text=f"プラン: {plan_label(self._plan_tier)} / 利用枠 {len(self._selected_slots)}"
        )
        if self._fixed_plan_tier:
            self._plan_hint_label.configure(text=f"このEXEは {plan_label(self._fixed_plan_tier)} 固定版です。プラン変更はできません。")
        else:
            self._plan_hint_label.configure(text="BRONZE は1つまで、SILVER は2つまで、GOLD はどれでも選べます。")
        if self._plan_tier == "gold":
            self._slot_hint_label.configure(text="GOLD はどれでも選べます。")
        elif self._plan_tier == "silver":
            self._slot_hint_label.configure(text="SILVER は2つまで選べます。")
        else:
            self._slot_hint_label.configure(text="BRONZE は1つまで選べます。")

        self._refresh_button_states()

    def load_from_settings(self, settings: AppSettings) -> None:
        self._vars["login_url"].set(str(getattr(settings.ipat, "login_url", "") or ""))
        self._vars["inet_id"].set(str(getattr(settings.ipat, "inet_id", "") or ""))
        self._vars["pars_no"].set(str(getattr(settings.ipat, "pars_no", "") or ""))
        self._vars["password"].set(str(getattr(settings.ipat, "password", "") or ""))
        self._vars["login_id"].set(str(getattr(settings.ipat, "login_id", "") or ""))
        self._vars["headless"].set("ON" if bool(getattr(settings.ipat, "headless", True)) else "OFF")
        self._vars["target_payout_yen"].set(str(int(getattr(settings.entry, "target_payout_yen", 10000) or 10000)))
        self._vars["entry_abort_total_yen"].set(str(int(getattr(settings.entry, "entry_abort_total_yen", 10000) or 0)))
        self._vars["execution_mode"].set("手動" if bool(getattr(settings.entry, "confirm_each_race", False)) else "自動")
        self._plan_tier = self._fixed_plan_tier or normalize_plan_tier(getattr(settings.entry, "plan_tier", DEFAULT_PLAN_TIER))
        self._selected_slots = self._normalize_profile_slots(selected_tool_slots(settings.entry), self._plan_tier)
        self._apply_plan_palette()

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
        settings.entry.confirm_each_race = self._manual_review_selected()
        settings.entry.show_ticket_preview_window = False
        settings.entry.allocation_mode = "target_payout"
        settings.entry.enable_central = True
        settings.entry.enable_local = False
        settings.entry.central_schedule_enabled = True
        settings.entry.plan_tier = self._plan_tier
        settings.entry.tool_slots = list(normalize_tool_slots(self._selected_slots, self._plan_tier))
        settings.entry.central_schedule_open_time = DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME
        settings.entry.central_schedule_close_time = DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME

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
        palette = plan_palette(self._plan_tier)
        if self._is_running:
            self._btn_run_toggle.configure(
                text="停止する",
                fg_color=COLOR_SUCCESS,
                hover_color=palette["accent_hover"],
                text_color=COLOR_TEXT_ON_ACCENT,
            )
        else:
            self._btn_run_toggle.configure(
                text="開始する",
                fg_color=palette["strong"],
                hover_color=palette["accent_hover"],
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
