from __future__ import annotations

from typing import Any, Callable, List

import customtkinter as ctk

from config import DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME, DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME, AppSettings
from product_profile import (
    BET_TYPES,
    DAYPARTS,
    PRODUCT_NAME,
    app_palette,
    clamp_enabled_bet_types,
    clamp_enabled_dayparts,
    default_enabled_bet_types,
    default_enabled_dayparts,
    line_cap_axis,
    max_selections,
    tier_label,
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
    FONT_HERO,
    FONT_MONO_SM,
    FONT_SMALL,
    FONT_STAT_VAL,
)


class DashboardView(ctk.CTkFrame):
    """Product-style operator dashboard for AQUA EDGE AI."""

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
        scroll.pack(fill="both", expand=True, padx=16, pady=16)

        self._hero_card = ctk.CTkFrame(scroll, corner_radius=14, fg_color=COLOR_CARD_BG)
        self._hero_card.pack(fill="x", pady=(0, 12))
        self._hero_card.grid_columnconfigure(0, weight=1)
        self._hero_card.grid_columnconfigure(1, weight=0)

        hero_left = ctk.CTkFrame(self._hero_card, fg_color="transparent")
        hero_left.grid(row=0, column=0, sticky="nsew", padx=(20, 12), pady=20)

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
            text="Discord連携と BOAT RACE 自動入力を管理します。",
            font=FONT_BODY,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self._hero_subtitle.pack(anchor="w", pady=(4, 10))

        hero_status = ctk.CTkFrame(hero_left, fg_color="transparent")
        hero_status.pack(fill="x", pady=(4, 0))
        hero_status.grid_columnconfigure((0, 1), weight=1)

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

        stats_row = ctk.CTkFrame(scroll, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 12))
        stats_row.grid_columnconfigure((0, 1, 2), weight=1)

        self._stat_received_label = self._make_stat_tile(stats_row, "本日受信", "0", 0)
        self._stat_ordered_label = self._make_stat_tile(stats_row, "本日発注", "0", 1)
        self._stat_skipped_label = self._make_stat_tile(stats_row, "本日見送り", "0", 2)

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
        self._add_entry_row(setting_card.body, "目標払戻(円)", self._vars["target_payout_yen"])
        self._add_entry_row(
            setting_card.body,
            "エントリー中止金額",
            self._vars["entry_abort_total_yen"],
            hint="円以上で見送り / 0で無効",
        )

        self._rule_note = ctk.CTkLabel(
            setting_card.body,
            text="固定配当で再計算し、条件に合う通知を取り込みます。",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
            justify="left",
        )
        self._rule_note.pack(anchor="w", pady=(6, 0))

        # 通知の選択（グレードで上限件数が決まる）。
        # aquaライン=券種(2連複/3連複/3連単)、clearismライン=日区分(モーニング/日中/ナイター)。
        self._sel_axis = line_cap_axis()
        self._sel_items = list(DAYPARTS) if self._sel_axis == "daypart" else list(BET_TYPES)
        axis_word = "日区分" if self._sel_axis == "daypart" else "券種"
        cap = max_selections()
        bet_card = CardFrame(scroll, title=f"通知{axis_word}（{tier_label()}：最大{cap}）")
        bet_card.pack(fill="x", pady=(0, 12))
        self._bet_type_vars: dict[str, ctk.BooleanVar] = {}
        self._bet_type_boxes: dict[str, ctk.CTkCheckBox] = {}
        row = ctk.CTkFrame(bet_card.body, fg_color="transparent")
        row.pack(fill="x")
        for bt in self._sel_items:
            var = ctk.BooleanVar(value=False)
            box = ctk.CTkCheckBox(
                row, text=bt, variable=var, font=FONT_BODY,
                command=lambda b=bt: self._on_bet_type_toggle(b),
            )
            box.pack(side="left", padx=(0, 18), pady=4)
            self._bet_type_vars[bt] = var
            self._bet_type_boxes[bt] = box
        self._bet_type_note = ctk.CTkLabel(
            bet_card.body,
            text=f"選択した{axis_word}の通知だけを取り込みます（最大{cap}）。",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
            justify="left",
        )
        self._bet_type_note.pack(anchor="w", pady=(6, 0))

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

        self._apply_palette()
        self._refresh_button_states()

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

    def _apply_palette(self) -> None:
        palette = app_palette()
        accent = palette["accent"]
        accent_hover = palette["accent_hover"]
        self._hero_card.configure(fg_color=palette["soft"])
        self._btn_save.configure(fg_color=accent, hover_color=accent_hover)

    def load_from_settings(self, settings: AppSettings) -> None:
        self._vars["login_url"].set(str(getattr(settings.ipat, "login_url", "") or ""))
        self._vars["inet_id"].set(str(getattr(settings.ipat, "inet_id", "") or ""))
        self._vars["pars_no"].set(str(getattr(settings.ipat, "pars_no", "") or ""))
        self._vars["password"].set(str(getattr(settings.ipat, "password", "") or ""))
        self._vars["login_id"].set(str(getattr(settings.ipat, "login_id", "") or ""))
        self._vars["headless"].set("ON" if bool(getattr(settings.ipat, "headless", True)) else "OFF")
        self._vars["target_payout_yen"].set(str(int(getattr(settings.entry, "target_payout_yen", 10000) or 10000)))
        self._vars["entry_abort_total_yen"].set(str(int(getattr(settings.entry, "entry_abort_total_yen", 10000) or 0)))

        if getattr(self, "_sel_axis", "bet_type") == "daypart":
            enabled = getattr(settings.entry, "enabled_dayparts", None)
            enabled = clamp_enabled_dayparts(enabled) if enabled is not None else default_enabled_dayparts()
        else:
            enabled = getattr(settings.entry, "enabled_bet_types", None)
            enabled = clamp_enabled_bet_types(enabled) if enabled is not None else default_enabled_bet_types()
        for bt, var in getattr(self, "_bet_type_vars", {}).items():
            var.set(bt in enabled)
        self._apply_bet_type_cap_state()

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
        if getattr(self, "_sel_axis", "bet_type") == "daypart":
            settings.entry.enabled_dayparts = self._selected_bet_types()
        else:
            settings.entry.enabled_bet_types = self._selected_bet_types()

    # --- 通知の選択（グレード上限。券種 or 日区分） --------------------
    def _selected_bet_types(self) -> list:
        chosen = [bt for bt in self._sel_items if self._bet_type_vars.get(bt) and self._bet_type_vars[bt].get()]
        if self._sel_axis == "daypart":
            return clamp_enabled_dayparts(chosen)
        return clamp_enabled_bet_types(chosen)

    def _on_bet_type_toggle(self, bet_type: str) -> None:
        cap = max_selections()
        chosen = [bt for bt in self._sel_items if self._bet_type_vars[bt].get()]
        if len(chosen) > cap:
            # 上限超過: 今押したものを取り消す
            self._bet_type_vars[bet_type].set(False)
        self._apply_bet_type_cap_state()

    def _apply_bet_type_cap_state(self) -> None:
        cap = max_selections()
        chosen = [bt for bt in self._sel_items if self._bet_type_vars[bt].get()]
        at_cap = len(chosen) >= cap
        for bt, box in self._bet_type_boxes.items():
            # 上限に達したら未選択のものは押せないようにする
            if at_cap and not self._bet_type_vars[bt].get():
                box.configure(state="disabled")
            else:
                box.configure(state="normal")
        self._bet_type_note.configure(
            text=f"選択中 {len(chosen)}/{cap}：{'・'.join(chosen) or 'なし'}"
        )

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
        palette = app_palette()
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
