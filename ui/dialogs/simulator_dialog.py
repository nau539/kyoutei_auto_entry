from __future__ import annotations

import math
import unicodedata
from typing import Any, Dict, List

import customtkinter as ctk

from config import AppSettings
from ui.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_CARD_BG,
    COLOR_CARD_ELEVATED,
    COLOR_DRY_RUN_FG,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_LIVE_WARN,
    COLOR_SEG_SELECTED,
    COLOR_SEG_SELECTED_HOVER,
    COLOR_SEG_TEXT,
    COLOR_SEG_UNSELECTED,
    COLOR_SEG_UNSELECTED_HOVER,
    COLOR_SEPARATOR,
    COLOR_TABLE_ALT,
    COLOR_TEXT_ON_ACCENT,
    COLOR_TEXT_PRIMARY,
    FONT_BODY,
    FONT_HEADING,
    FONT_MONO,
    FONT_SMALL,
    fmt_multiple,
    fmt_odds,
    fmt_yen,
)

# ---------------------------------------------------------------------------
# Shared helpers (used by main_window for confirm-only preview)
# ---------------------------------------------------------------------------


def _safe_odds(value: Any) -> float:
    try:
        odds = float(value)
    except Exception:
        return -1.0
    return odds if odds > 0 else -1.0


def _ticket_payout(odds: float, bet_yen: int) -> float:
    if odds <= 0:
        return 0.0
    return float(odds) * float(max(0, int(bet_yen)))


def _normalize_bet_yen(value: Any) -> int:
    try:
        val = int(str(value or "").replace(",", "").strip())
    except Exception:
        val = 0
    if val <= 0:
        return 0
    return int(val // 100) * 100


def _normalize_digits_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return ""
    return str(int(digits))


def _yen_to_units(value: Any) -> int:
    try:
        yen = int(value)
    except Exception:
        yen = 0
    return max(0, int(yen // 100))


def _units_to_yen(value: Any) -> int:
    try:
        units = int(value)
    except Exception:
        units = 0
    return max(0, int(units)) * 100


def _race_tag(payload: Dict[str, Any]) -> str:
    race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
    date8 = str(race.get("date", "-") or "-")
    venue = str(race.get("venue_name", "-") or "-")
    race_no = int(race.get("race_num", 0) or 0)
    return f"{date8}_{venue}_{race_no:02d}R"


def _market_filters(tickets: List[Dict[str, Any]]) -> List[str]:
    present = {str(t.get("market", "") or "").strip() for t in tickets}
    base = ["全体", "単勝", "馬連", "ワイド", "枠連"]
    return [v for v in base if v == "全体" or v in present]


def _calc_raffine_bets(rows: List[Dict[str, Any]], budget_yen: int) -> Dict[int, int]:
    if not rows:
        return {}
    budget = max(0, int(budget_yen))
    odds_list = [_safe_odds(r.get("odds")) for r in rows]
    valid_indexes = [i for i, o in enumerate(odds_list) if o > 0]
    if not valid_indexes:
        return {i: int(r.get("bet_yen", 0) or 0) for i, r in enumerate(rows)}

    inv_sum = sum(1.0 / max(1e-9, odds_list[i]) for i in valid_indexes)
    target_return = float(budget) / inv_sum if inv_sum > 0 else 0.0
    bets = [0] * len(rows)
    for i in valid_indexes:
        raw = target_return / odds_list[i]
        bets[i] = max(0, int(raw // 100.0) * 100)

    remain = budget - sum(bets)
    while remain >= 100:
        pick = min(valid_indexes, key=lambda i: _ticket_payout(odds_list[i], bets[i]))
        bets[pick] += 100
        remain -= 100
    return {i: int(bets[i]) for i in range(len(rows))}


def _resolve_target_payout_yen(
    rows: List[Dict[str, Any]],
    target_payout_yen: int = 10000,
    target_payout_mode: str = "yen",
    target_payout_ratio_pct: float = 1000.0,
) -> int:
    mode = str(target_payout_mode or "yen").strip().lower()
    if mode in {"rate", "pct", "percent", "割合"}:
        mode = "ratio"
    if mode == "ratio":
        ratio_pct = max(1.0, float(target_payout_ratio_pct))
        base_total = int(sum(int(r.get("bet_yen", 0) or 0) for r in rows or []))
        return max(100, int(round(float(base_total) * ratio_pct / 100.0)))
    return max(100, int(target_payout_yen))


def _calc_target_payout_bets(
    rows: List[Dict[str, Any]],
    target_payout_yen: int = 10000,
    target_payout_mode: str = "yen",
    target_payout_ratio_pct: float = 1000.0,
) -> Dict[int, int]:
    target = _resolve_target_payout_yen(
        rows,
        target_payout_yen=target_payout_yen,
        target_payout_mode=target_payout_mode,
        target_payout_ratio_pct=target_payout_ratio_pct,
    )
    bets: Dict[int, int] = {}
    for idx, row in enumerate(rows):
        odds = _safe_odds(row.get("odds"))
        if odds <= 0:
            bets[idx] = int(row.get("bet_yen", 0) or 0)
            continue
        raw = float(target) / max(1e-9, odds)
        rounded = int(math.ceil(raw / 100.0)) * 100
        while float(odds) * float(rounded) <= float(target):
            rounded += 100
        bets[idx] = max(100, int(rounded))
    return bets


def _apply_review_mode(
    tickets: List[Dict[str, Any]],
    market_filter: str,
    mode: str,
    budget_override_yen: int | None = None,
    target_payout_yen: int | None = None,
    target_payout_mode: str | None = None,
    target_payout_ratio_pct: float | None = None,
) -> List[Dict[str, Any]]:
    rows = [dict(t) for t in tickets or []]
    if mode in {"current", "ratio", "flat"}:
        return rows

    target_indexes = [
        i
        for i, t in enumerate(rows)
        if market_filter == "全体" or str(t.get("market", "") or "").strip() == market_filter
    ]
    if not target_indexes:
        return rows
    target = [rows[i] for i in target_indexes]
    if mode == "raffine":
        if market_filter == "全体" and budget_override_yen and int(budget_override_yen) > 0:
            budget = int(budget_override_yen)
        else:
            budget = int(sum(int(t.get("bet_yen", 0) or 0) for t in target))
        bet_by_index = _calc_raffine_bets(target, budget)
    elif mode == "target_payout":
        target_payout = int(target_payout_yen) if target_payout_yen and int(target_payout_yen) > 0 else 10000
        target_mode = str(target_payout_mode or "yen")
        try:
            ratio_pct = float(target_payout_ratio_pct) if target_payout_ratio_pct is not None else 1000.0
        except Exception:
            ratio_pct = 1000.0
        bet_by_index = _calc_target_payout_bets(
            target,
            target_payout_yen=target_payout,
            target_payout_mode=target_mode,
            target_payout_ratio_pct=ratio_pct,
        )
    else:
        return rows

    for local_idx, global_idx in enumerate(target_indexes):
        rows[global_idx]["bet_yen"] = int(
            bet_by_index.get(local_idx, int(rows[global_idx].get("bet_yen", 0) or 0))
        )
    return rows


def build_preview_text(
    payload: Dict[str, Any],
    tickets: List[Dict[str, Any]],
    mode: str,
    target_payout_yen: int = 10000,
    target_payout_mode: str = "yen",
    target_payout_ratio_pct: float = 1000.0,
) -> str:
    effective = _apply_review_mode(
        tickets,
        "全体",
        mode,
        target_payout_yen=target_payout_yen,
        target_payout_mode=target_payout_mode,
        target_payout_ratio_pct=target_payout_ratio_pct,
    )
    budget = int(sum(int(t.get("bet_yen", 0) or 0) for t in effective))
    lines = [
        f"レース: {_race_tag(payload)}",
        f"件数: {len(effective)}件 / 合計投資: {budget:,}円",
        "",
    ]
    for idx, row in enumerate(effective, start=1):
        market = str(row.get("market", "") or "")
        combo = str(row.get("combo", "") or "")
        bet = int(row.get("bet_yen", 0) or 0)
        odds = _safe_odds(row.get("odds"))
        odds_t = fmt_odds(odds)
        payout_t = f"{int(round(_ticket_payout(odds, bet))):,}円" if odds > 0 else "-"
        lines.append(f"{idx:02d}  {market:<4}  {combo:<10}  {bet:>7,}円  {odds_t:>6}  {payout_t:>10}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Simulator Dialog
# ---------------------------------------------------------------------------


class SimulatorDialog(ctk.CTkToplevel):
    """Full bet review/edit simulator."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        payload: Dict[str, Any],
        tickets: List[Dict[str, Any]],
        settings: AppSettings,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, **kwargs)
        self.title(f"買い目シミュレーター - {_race_tag(payload)}")
        self.geometry("1020x720")
        self.minsize(920, 600)
        self.transient(master)
        self.grab_set()

        self.result: bool = False
        self._payload = payload
        self._tickets = tickets  # mutable reference from service
        self._settings = settings
        self._editable_rows = [dict(t) for t in tickets or []]
        self._base_rows = [dict(t) for t in tickets or []]
        self._bet_vars: List[ctk.StringVar] = []
        self._bet_entries: List[ctk.CTkEntry] = []
        self._bet_spin_frames: List[ctk.CTkFrame] = []
        self._calc_labels: List[ctk.CTkLabel] = []
        self._payout_labels: List[ctk.CTkLabel] = []
        self._refresh_job: str | None = None

        self._build_ui()
        self._schedule_refresh()

        self.protocol("WM_DELETE_WINDOW", lambda: self._close(False))

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ----- Race info bar -----
        info_bar = ctk.CTkFrame(self, fg_color="transparent")
        info_bar.pack(fill="x", padx=16, pady=(12, 4))

        race = self._payload.get("race") if isinstance(self._payload.get("race"), dict) else {}
        race_text = f"レース: {race.get('date', '-')} {race.get('venue_name', '-')} {race.get('race_num', 0)}R"
        ctk.CTkLabel(info_bar, text=race_text, font=FONT_HEADING).pack(side="left")

        # ----- Controls Row -----
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=16, pady=(4, 8))

        # Market filter
        ctk.CTkLabel(ctrl_frame, text="券種:", font=FONT_BODY).pack(side="left")
        filters = _market_filters(self._editable_rows)
        self._market_var = ctk.StringVar(value="全体")
        self._market_seg = ctk.CTkSegmentedButton(
            ctrl_frame,
            values=filters,
            variable=self._market_var,
            command=lambda _: self._schedule_refresh(),
            selected_color=COLOR_SEG_SELECTED,
            selected_hover_color=COLOR_SEG_SELECTED_HOVER,
            unselected_color=COLOR_SEG_UNSELECTED,
            unselected_hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_SEG_TEXT,
        )
        self._market_seg.pack(side="left", padx=(4, 16))

        # Allocation mode
        ctk.CTkLabel(ctrl_frame, text="配分:", font=FONT_BODY).pack(side="left")
        default_mode = getattr(self._settings.entry, "allocation_mode", "target_payout") or "target_payout"
        mode_display = self._mode_code_to_display(default_mode)
        self._mode_var = ctk.StringVar(value=mode_display)
        self._mode_seg = ctk.CTkSegmentedButton(
            ctrl_frame,
            values=["固定投票", "分配投票", "配当固定"],
            variable=self._mode_var,
            command=lambda _: self._on_mode_changed(),
            selected_color=COLOR_SEG_SELECTED,
            selected_hover_color=COLOR_SEG_SELECTED_HOVER,
            unselected_color=COLOR_SEG_UNSELECTED,
            unselected_hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_SEG_TEXT,
        )
        self._mode_seg.pack(side="left", padx=(4, 16))

        # Mode parameter (fixed units / budget / target payout)
        self._amount_wrap = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        self._amount_wrap.pack(side="left")
        self._amount_label = ctk.CTkLabel(self._amount_wrap, text="", font=FONT_BODY)
        self._amount_label.pack(side="left")
        total = int(sum(int(t.get("bet_yen", 0) or 0) for t in self._editable_rows))
        default_raffine_budget = int(getattr(self._settings.entry, "raffine_budget_yen", 10000) or 10000)
        default_target_payout = self._default_target_payout()
        default_target_mode = self._target_payout_mode_code()
        default_target_ratio_pct = int(round(self._default_target_payout_ratio_pct()))
        if default_mode == "target_payout":
            initial_amount = default_target_ratio_pct if default_target_mode == "ratio" else default_target_payout
        elif default_mode == "raffine":
            initial_amount = default_raffine_budget
        else:
            initial_amount = total
        self._budget_var = ctk.StringVar(value=str(initial_amount))
        self._budget_entry = ctk.CTkEntry(self._amount_wrap, textvariable=self._budget_var, width=100, font=FONT_BODY)
        self._budget_entry.pack(side="left", padx=(4, 0))
        self._budget_unit_label = ctk.CTkLabel(self._amount_wrap, text="円", font=FONT_BODY)
        self._budget_unit_label.pack(side="left", padx=(4, 0))
        self._budget_entry.bind("<KeyRelease>", lambda _: self._schedule_refresh())

        self._fixed_wrap = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        self._fixed_label = ctk.CTkLabel(self._fixed_wrap, text="入力口数:", font=FONT_BODY)
        self._fixed_label.pack(side="left")
        default_units = _yen_to_units(int(getattr(self._settings.entry, "fixed_ticket_yen", 100) or 100))
        self._fixed_units_var = ctk.StringVar(value=str(max(1, default_units)))
        self._fixed_units_entry = ctk.CTkEntry(self._fixed_wrap, textvariable=self._fixed_units_var, width=100, font=FONT_BODY)
        self._fixed_units_entry.pack(side="left", padx=(4, 0))
        self._fixed_units_unit_label = ctk.CTkLabel(self._fixed_wrap, text="口", font=FONT_BODY)
        self._fixed_units_unit_label.pack(side="left", padx=(4, 0))
        self._fixed_units_entry.bind("<KeyRelease>", lambda _: self._on_fixed_units_changed())
        self._fixed_units_entry.bind("<FocusOut>", lambda _: self._on_fixed_units_changed())
        self._fixed_units_entry.bind("<Up>", lambda _e: self._adjust_fixed_units(1))
        self._fixed_units_entry.bind("<Down>", lambda _e: self._adjust_fixed_units(-1))
        self._fixed_units_entry.bind("<MouseWheel>", self._on_fixed_mouse_wheel)
        self._fixed_units_entry.bind("<Button-4>", lambda _e: self._adjust_fixed_units(1))
        self._fixed_units_entry.bind("<Button-5>", lambda _e: self._adjust_fixed_units(-1))

        # ----- Summary bar -----
        self._summary_frame = ctk.CTkFrame(self, corner_radius=8, fg_color=COLOR_CARD_BG)
        self._summary_frame.pack(fill="x", padx=16, pady=(0, 8))
        self._summary_total_label = ctk.CTkLabel(
            self._summary_frame,
            text="",
            font=FONT_HEADING,
            text_color=COLOR_ACCENT,
            anchor="w",
            justify="left",
        )
        self._summary_total_label.pack(fill="x", padx=16, pady=(8, 2), anchor="w")
        self._summary_detail_label = ctk.CTkLabel(
            self._summary_frame, text="", font=FONT_BODY, wraplength=900, justify="left", anchor="w"
        )
        self._summary_detail_label.pack(fill="x", padx=16, pady=(0, 8), anchor="w")

        # ----- Ticket table -----
        table_frame = ctk.CTkFrame(self, fg_color="transparent")
        table_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Header
        header = ctk.CTkFrame(table_frame, fg_color="transparent")
        header.pack(fill="x")
        cols = [
            ("No", 40),
            ("券種", 60),
            ("組合せ", 90),
            ("オッズ", 60),
            ("入力口数", 100),
            ("試算金額", 90),
            ("想定払戻", 100),
        ]
        for text, width in cols:
            ctk.CTkLabel(header, text=text, font=("", 12, "bold"), width=width, anchor="w").pack(
                side="left", padx=4
            )

        sep = ctk.CTkFrame(table_frame, height=1, fg_color=COLOR_SEPARATOR)
        sep.pack(fill="x", pady=4)

        # Scrollable rows
        self._scroll_frame = ctk.CTkScrollableFrame(table_frame, fg_color="transparent")
        self._scroll_frame.pack(fill="both", expand=True)

        for idx, row in enumerate(self._editable_rows):
            self._build_ticket_row(idx, row)
        self._on_mode_changed()

        # ----- Action buttons -----
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkButton(
            action_frame,
            text="配分結果を反映",
            width=180,
            height=36,
            fg_color=COLOR_INFO,
            hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_ON_ACCENT,
            command=self._apply_mode_to_inputs,
        ).pack(side="left")

        confirm_text = "この内容で投票する"
        confirm_color = COLOR_ACCENT
        confirm_hover = COLOR_ACCENT_HOVER

        ctk.CTkButton(
            action_frame,
            text="このレースを見送る",
            width=160,
            height=40,
            fg_color=COLOR_ERROR,
            hover_color=COLOR_LIVE_WARN,
            text_color=COLOR_TEXT_ON_ACCENT,
            command=lambda: self._close(False),
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            action_frame,
            text=confirm_text,
            width=200,
            height=40,
            fg_color=confirm_color,
            hover_color=confirm_hover,
            text_color=COLOR_TEXT_ON_ACCENT,
            command=lambda: self._close(True),
        ).pack(side="right")

    def _build_ticket_row(self, idx: int, row: Dict[str, Any]) -> None:
        is_alt = idx % 2 == 1
        bg = COLOR_TABLE_ALT if is_alt else "transparent"
        row_frame = ctk.CTkFrame(self._scroll_frame, fg_color=bg, corner_radius=4)
        row_frame.pack(fill="x", pady=1)

        odds = _safe_odds(row.get("odds"))
        odds_text = fmt_odds(odds)
        market = str(row.get("market", "") or "")
        combo = str(row.get("combo", "") or "")
        bet = int(row.get("bet_yen", 0) or 0)

        ctk.CTkLabel(row_frame, text=f"{idx + 1:02d}", font=FONT_BODY, width=40, anchor="w").pack(
            side="left", padx=4, pady=4
        )
        ctk.CTkLabel(row_frame, text=market, font=FONT_BODY, width=60, anchor="w").pack(
            side="left", padx=4, pady=4
        )
        ctk.CTkLabel(row_frame, text=combo, font=FONT_BODY, width=90, anchor="w").pack(
            side="left", padx=4, pady=4
        )
        ctk.CTkLabel(row_frame, text=odds_text, font=FONT_BODY, width=60, anchor="w").pack(
            side="left", padx=4, pady=4
        )

        bet_var = ctk.StringVar(value=str(_yen_to_units(bet)) if _yen_to_units(bet) > 0 else "")
        self._bet_vars.append(bet_var)
        bet_entry = ctk.CTkEntry(row_frame, textvariable=bet_var, width=100, font=FONT_BODY)
        bet_entry.pack(side="left", padx=4, pady=4)
        self._bet_entries.append(bet_entry)
        bet_entry.bind("<KeyRelease>", lambda _e, i=idx: self._on_bet_entry_changed(i))
        bet_entry.bind("<FocusOut>", lambda _e, i=idx: self._on_bet_entry_changed(i))
        bet_entry.bind("<Up>", lambda _e, i=idx: self._adjust_bet_units(i, 1))
        bet_entry.bind("<Down>", lambda _e, i=idx: self._adjust_bet_units(i, -1))
        bet_entry.bind("<MouseWheel>", lambda e, i=idx: self._on_bet_mouse_wheel(i, e))
        bet_entry.bind("<Button-4>", lambda _e, i=idx: self._adjust_bet_units(i, 1))
        bet_entry.bind("<Button-5>", lambda _e, i=idx: self._adjust_bet_units(i, -1))

        spin_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        spin_frame.pack(side="left", padx=(2, 4), pady=4)
        self._bet_spin_frames.append(spin_frame)
        ctk.CTkButton(
            spin_frame,
            text="+",
            width=24,
            height=15,
            fg_color=COLOR_CARD_ELEVATED,
            hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=lambda i=idx: self._adjust_bet_units(i, 1),
        ).pack(pady=(0, 2))
        ctk.CTkButton(
            spin_frame,
            text="-",
            width=24,
            height=15,
            fg_color=COLOR_CARD_ELEVATED,
            hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=lambda i=idx: self._adjust_bet_units(i, -1),
        ).pack()

        calc_label = ctk.CTkLabel(row_frame, text="-", font=FONT_BODY, width=90, anchor="e")
        calc_label.pack(side="left", padx=4, pady=4)
        self._calc_labels.append(calc_label)

        payout_label = ctk.CTkLabel(row_frame, text="-", font=FONT_BODY, width=100, anchor="e")
        payout_label.pack(side="left", padx=4, pady=4)
        self._payout_labels.append(payout_label)

    # ------------------------------------------------------------------
    # Refresh logic
    # ------------------------------------------------------------------

    def _mode_display_to_code(self, value: str) -> str:
        mode = str(value or "").strip()
        if mode in {"分配投票", "ラフィーネ法"}:
            return "raffine"
        if mode in {"配当固定", "配当固定法"}:
            return "target_payout"
        return "target_payout"

    def _mode_code_to_display(self, value: str) -> str:
        mode = str(value or "").strip().lower()
        if mode == "raffine":
            return "分配投票"
        if mode in {"target_payout", "payout_target"}:
            return "配当固定"
        return "配当固定"

    def _default_target_payout(self) -> int:
        return max(100, int(getattr(self._settings.entry, "target_payout_yen", 10000) or 10000))

    def _default_target_payout_ratio_pct(self) -> float:
        try:
            ratio = float(getattr(self._settings.entry, "target_payout_ratio_pct", 1000.0) or 1000.0)
        except Exception:
            ratio = 1000.0
        return max(1.0, ratio)

    def _target_payout_mode_code(self) -> str:
        mode = str(getattr(self._settings.entry, "target_payout_mode", "yen") or "yen").strip().lower()
        if mode in {"rate", "pct", "percent", "割合"}:
            return "ratio"
        return "ratio" if mode == "ratio" else "yen"

    def _default_raffine_budget(self) -> int:
        return max(100, int(getattr(self._settings.entry, "raffine_budget_yen", 10000) or 10000))

    def _default_fixed_units(self) -> int:
        yen = int(getattr(self._settings.entry, "fixed_ticket_yen", 100) or 100)
        return max(1, _yen_to_units(yen))

    def _normalize_fixed_units(self) -> int:
        normalized = _normalize_digits_text(self._fixed_units_var.get())
        if normalized != str(self._fixed_units_var.get() or ""):
            self._fixed_units_var.set(normalized)
        if not normalized:
            return 0
        try:
            return int(normalized)
        except Exception:
            return 0

    def _on_fixed_units_changed(self) -> None:
        units = self._normalize_fixed_units()
        if units <= 0:
            return
        self._schedule_refresh()

    def _adjust_fixed_units(self, delta: int) -> str:
        units = max(1, self._normalize_fixed_units() + int(delta))
        self._fixed_units_var.set(str(units))
        self._schedule_refresh()
        return "break"

    def _on_fixed_mouse_wheel(self, event: Any) -> str:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta > 0:
            return self._adjust_fixed_units(1)
        if delta < 0:
            return self._adjust_fixed_units(-1)
        return "break"

    def _set_per_row_entry_enabled(self, enabled: bool) -> None:
        for idx, entry in enumerate(self._bet_entries):
            calc_anchor = self._calc_labels[idx] if idx < len(self._calc_labels) else None
            if enabled:
                if not entry.winfo_ismapped():
                    if calc_anchor is not None:
                        entry.pack(side="left", padx=4, pady=4, before=calc_anchor)
                    else:
                        entry.pack(side="left", padx=4, pady=4)
                entry.configure(state="normal")
            else:
                if entry.winfo_ismapped():
                    entry.pack_forget()

        for idx, frame in enumerate(self._bet_spin_frames):
            calc_anchor = self._calc_labels[idx] if idx < len(self._calc_labels) else None
            if enabled:
                if not frame.winfo_ismapped():
                    if calc_anchor is not None:
                        frame.pack(side="left", padx=(2, 4), pady=4, before=calc_anchor)
                    else:
                        frame.pack(side="left", padx=(2, 4), pady=4)
                for child in frame.winfo_children():
                    try:
                        child.configure(state="normal")
                    except Exception:
                        pass
            else:
                if frame.winfo_ismapped():
                    frame.pack_forget()

    def _on_mode_changed(self) -> None:
        mode = self._mode_display_to_code(self._mode_var.get())
        prev_mode = str(getattr(self, "_active_mode_code", "") or "")
        if mode == "flat":
            if self._amount_wrap.winfo_ismapped():
                self._amount_wrap.pack_forget()
            if not self._fixed_wrap.winfo_ismapped():
                self._fixed_wrap.pack(side="left")
            if self._normalize_fixed_units() <= 0:
                self._fixed_units_var.set(str(self._default_fixed_units()))
            self._set_per_row_entry_enabled(False)
        else:
            if self._fixed_wrap.winfo_ismapped():
                self._fixed_wrap.pack_forget()
            if not self._amount_wrap.winfo_ismapped():
                self._amount_wrap.pack(side="left")
            self._set_per_row_entry_enabled(True)

        if mode == "target_payout":
            target_mode = self._target_payout_mode_code()
            if target_mode == "ratio":
                self._amount_label.configure(text="目標払戻割合:")
                self._budget_unit_label.configure(text="%")
                default_value = int(round(self._default_target_payout_ratio_pct()))
            else:
                self._amount_label.configure(text="目標払戻:")
                self._budget_unit_label.configure(text="円")
                default_value = self._default_target_payout()
            raw = str(self._budget_var.get() or "").strip()
            if prev_mode != "target_payout":
                self._budget_var.set(str(default_value))
            elif not raw:
                self._budget_var.set(str(default_value))
        elif mode == "raffine":
            self._amount_label.configure(text="全体予算:")
            self._budget_unit_label.configure(text="円")
            raw = str(self._budget_var.get() or "").strip()
            if prev_mode != "raffine":
                self._budget_var.set(str(self._default_raffine_budget()))
            elif not raw:
                self._budget_var.set(str(self._default_raffine_budget()))
        self._active_mode_code = mode
        # 配分モード切替時は、試算だけでなく入力金額欄も同時に更新する。
        self._apply_mode_to_inputs(from_mode_change=True)

    def _schedule_refresh(self, *_args: Any) -> None:
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = self.after(80, self._refresh)

    def _normalize_bet_var(self, idx: int) -> int:
        if idx < 0 or idx >= len(self._bet_vars):
            return 0
        var = self._bet_vars[idx]
        normalized = _normalize_digits_text(var.get())
        if normalized != str(var.get() or ""):
            var.set(normalized)
        try:
            return int(normalized) if normalized else 0
        except Exception:
            return 0

    def _on_bet_entry_changed(self, idx: int) -> None:
        self._normalize_bet_var(idx)
        self._schedule_refresh()

    def _adjust_bet_units(self, idx: int, delta: int) -> str:
        units = self._normalize_bet_var(idx)
        units = max(0, int(units) + int(delta))
        self._bet_vars[idx].set(str(units) if units > 0 else "")
        self._schedule_refresh()
        return "break"

    def _on_bet_mouse_wheel(self, idx: int, event: Any) -> str:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta > 0:
            return self._adjust_bet_units(idx, 1)
        if delta < 0:
            return self._adjust_bet_units(idx, -1)
        return "break"

    def _refresh(self) -> None:
        self._refresh_job = None
        draft = self._collect_rows()
        mode_amount = self._read_budget_override()
        mode = self._mode_display_to_code(self._mode_var.get())
        market_filter = self._market_var.get()
        budget_override = (
            (mode_amount if mode_amount and mode_amount > 0 else self._default_raffine_budget())
            if mode == "raffine"
            else None
        )
        target_mode = self._target_payout_mode_code()
        if mode == "target_payout" and target_mode == "ratio":
            target_ratio_pct = float(mode_amount) if mode_amount and mode_amount > 0 else self._default_target_payout_ratio_pct()
            target_payout = self._default_target_payout()
        elif mode == "target_payout":
            target_ratio_pct = self._default_target_payout_ratio_pct()
            target_payout = mode_amount if mode_amount and mode_amount > 0 else self._default_target_payout()
        else:
            target_ratio_pct = self._default_target_payout_ratio_pct()
            target_payout = self._default_target_payout()

        effective = _apply_review_mode(
            draft,
            "全体",
            mode,
            budget_override_yen=budget_override,
            target_payout_yen=target_payout,
            target_payout_mode=target_mode,
            target_payout_ratio_pct=target_ratio_pct,
        )

        # Update calc and payout labels
        for idx, row in enumerate(effective):
            odds = _safe_odds(row.get("odds"))
            bet = int(row.get("bet_yen", 0) or 0)
            self._calc_labels[idx].configure(text=fmt_yen(bet) if bet > 0 else "-")
            if odds > 0 and bet > 0:
                self._payout_labels[idx].configure(text=fmt_yen(int(round(_ticket_payout(odds, bet)))))
            else:
                self._payout_labels[idx].configure(text="-")

        # Summary
        target = [
            t
            for t in effective
            if market_filter == "全体" or str(t.get("market", "") or "").strip() == market_filter
        ]
        total_bet = int(sum(int(t.get("bet_yen", 0) or 0) for t in target))
        payouts = []
        for t in target:
            o = _safe_odds(t.get("odds"))
            b = int(t.get("bet_yen", 0) or 0)
            if o > 0 and b > 0:
                payouts.append(_ticket_payout(o, b))

        total_text = f"投資合計: {total_bet:,}円"
        detail_text = ""
        if payouts and total_bet > 0:
            mn, mx, av = min(payouts), max(payouts), sum(payouts) / len(payouts)
            detail_text = (
                f"想定払戻  min: {int(mn):,}円 ({mn / total_bet:.2f}倍)  "
                f"max: {int(mx):,}円 ({mx / total_bet:.2f}倍)  "
                f"avg: {int(av):,}円 ({av / total_bet:.2f}倍)"
            )
        elif total_bet > 0:
            detail_text = "オッズ未設定のため想定払戻を計算できません"
        else:
            detail_text = "-"
        self._summary_total_label.configure(text=total_text, text_color=COLOR_ACCENT)
        self._summary_detail_label.configure(text=detail_text)

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _collect_rows(self) -> List[Dict[str, Any]]:
        mode = self._mode_display_to_code(self._mode_var.get())
        rows = []
        common_units = 0
        if mode == "flat":
            common_units = max(1, self._normalize_fixed_units())
        for idx, base in enumerate(self._editable_rows):
            row = dict(base)
            units = common_units if mode == "flat" else self._normalize_bet_var(idx)
            row["bet_yen"] = _units_to_yen(units)
            rows.append(row)
        return rows

    def _read_budget_override(self) -> int | None:
        raw = _normalize_digits_text(self._budget_var.get())
        if raw != str(self._budget_var.get() or ""):
            self._budget_var.set(raw)
        if not raw:
            return None
        try:
            val = int(raw)
        except Exception:
            return None
        return val if val > 0 else None

    def _apply_mode_to_inputs(self, from_mode_change: bool = False) -> None:
        draft = self._collect_rows()
        mode = self._mode_display_to_code(self._mode_var.get())
        mode_amount = self._read_budget_override()
        budget_override = (
            (mode_amount if mode_amount and mode_amount > 0 else self._default_raffine_budget())
            if mode == "raffine"
            else None
        )
        target_mode = self._target_payout_mode_code()
        if mode == "target_payout" and target_mode == "ratio":
            target_ratio_pct = float(mode_amount) if mode_amount and mode_amount > 0 else self._default_target_payout_ratio_pct()
            target_payout = self._default_target_payout()
        elif mode == "target_payout":
            target_ratio_pct = self._default_target_payout_ratio_pct()
            target_payout = mode_amount if mode_amount and mode_amount > 0 else self._default_target_payout()
        else:
            target_ratio_pct = self._default_target_payout_ratio_pct()
            target_payout = self._default_target_payout()
        source_rows = [dict(r) for r in (self._base_rows if from_mode_change else draft)]
        if mode == "flat":
            if from_mode_change:
                self._fixed_units_var.set(str(self._default_fixed_units()))
            common_units = max(1, self._normalize_fixed_units())
            applied = []
            for row in source_rows:
                out = dict(row)
                out["bet_yen"] = _units_to_yen(common_units)
                applied.append(out)
        else:
            applied = _apply_review_mode(
                source_rows,
                "全体",
                mode,
                budget_override_yen=budget_override,
                target_payout_yen=target_payout,
                target_payout_mode=target_mode,
                target_payout_ratio_pct=target_ratio_pct,
            )
        for idx, row in enumerate(applied):
            if idx < len(self._bet_vars):
                units = _yen_to_units(int(row.get("bet_yen", 0) or 0))
                self._bet_vars[idx].set(str(units) if units > 0 else "")
        if mode == "flat":
            total = int(sum(int(t.get("bet_yen", 0) or 0) for t in applied))
            self._budget_var.set(str(total))
        self._schedule_refresh()

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def _close(self, ok: bool) -> None:
        if ok:
            mode = self._mode_display_to_code(self._mode_var.get())
            draft = self._collect_rows()
            mode_amount = self._read_budget_override()
            budget_override = (
                (mode_amount if mode_amount and mode_amount > 0 else self._default_raffine_budget())
                if mode == "raffine"
                else None
            )
            target_mode = self._target_payout_mode_code()
            if mode == "target_payout" and target_mode == "ratio":
                target_ratio_pct = (
                    float(mode_amount) if mode_amount and mode_amount > 0 else self._default_target_payout_ratio_pct()
                )
                target_payout = self._default_target_payout()
            elif mode == "target_payout":
                target_ratio_pct = self._default_target_payout_ratio_pct()
                target_payout = mode_amount if mode_amount and mode_amount > 0 else self._default_target_payout()
            else:
                target_ratio_pct = self._default_target_payout_ratio_pct()
                target_payout = self._default_target_payout()
            applied = _apply_review_mode(
                draft,
                "全体",
                mode,
                budget_override_yen=budget_override,
                target_payout_yen=target_payout,
                target_payout_mode=target_mode,
                target_payout_ratio_pct=target_ratio_pct,
            )
            final: List[Dict[str, Any]] = []
            for row in applied:
                out = dict(row)
                out["bet_yen"] = _normalize_bet_yen(out.get("bet_yen"))
                if int(out.get("bet_yen", 0) or 0) <= 0:
                    continue
                final.append(out)
            if not final:
                # Show inline warning
                self._summary_total_label.configure(text="入力エラー", text_color=COLOR_LIVE_WARN)
                self._summary_detail_label.configure(text="有効な買い目金額がありません（100円以上を入力してください）")
                return
            self._tickets[:] = final

        self.result = ok
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
