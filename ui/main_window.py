from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path
from typing import Callable
from tkinter import messagebox

import customtkinter as ctk

from config import AppSettings, CONFIG_FILE, load_settings, save_settings
from product_profile import (
    app_palette,
    runtime_product_name,
    tier_accent,
    tier_label,
)
from service import AutoEntryService
from ui.components.status_bar import StatusBar
from ui.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_BG,
    COLOR_ERROR,
    COLOR_SEG_SELECTED,
    COLOR_SEG_SELECTED_HOVER,
    COLOR_SEG_TEXT,
    COLOR_SEG_UNSELECTED,
    COLOR_SEG_UNSELECTED_HOVER,
    COLOR_SIDEBAR_ACTIVE,
    COLOR_SIDEBAR_BG,
    COLOR_SIDEBAR_HOVER,
    COLOR_SUCCESS,
    COLOR_TEXT_ON_ACCENT,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    FONT_NAV,
    FONT_NAV_ACTIVE,
    FONT_SMALL,
    FONT_TITLE,
    get_theme,
    set_theme,
)
from ui.views.dashboard_view import DashboardView
from ui.views.log_view import LogView

try:
    import importlib

    from product_profile import edition_auth_module as _edition_auth_module

    # ビルド時に固定した製品ラインに応じて認証バックエンドを切り替える。
    #   clearism -> auth_clear
    #   aqua/DEMO -> auth_master
    auth_module = importlib.import_module(_edition_auth_module())
except Exception as _auth_import_exc:  # pragma: no cover
    auth_module = None
else:
    _auth_import_exc = None

logger = logging.getLogger(__name__)

VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION.txt"


def _read_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return "?"


class AutoEntryApp(ctk.CTk):
    _LOG_DRAIN_MAX_PER_TICK = 120
    _LOG_DRAIN_IDLE_MS = 200
    _LOG_DRAIN_BUSY_MS = 30

    def __init__(self) -> None:
        ctk.set_default_color_theme("blue")
        ctk.set_appearance_mode("System")
        super().__init__()

        self.title(runtime_product_name())
        self.geometry("980x680")
        self.minsize(860, 580)
        self.configure(fg_color=COLOR_BG)

        self._settings_file_exists_at_start = Path(CONFIG_FILE).exists()
        self.settings: AppSettings = load_settings()
        saved_theme_mode = str(getattr(self.settings, "theme_mode", "system") or "system").strip().lower()
        if saved_theme_mode not in {"light", "dark", "system"}:
            saved_theme_mode = "system"
        set_theme(saved_theme_mode)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.service: AutoEntryService | None = None
        self._version = _read_version()

        # Counters for dashboard stats
        self._stat_received = 0
        self._stat_ordered = 0
        self._stat_skipped = 0
        self._discord_connected = False
        self._auth_in_progress = False
        self._is_authenticated = False
        self._service_op_in_progress = False

        self._build_layout()
        self._sync_mode_badge()
        self._apply_app_palette()
        saved_auth_user = str(getattr(getattr(self.settings, "auth", None), "user_id", "") or "").strip()
        if saved_auth_user:
            self._auth_user_var.set(saved_auth_user)
        self._show_view("dashboard")
        self._apply_auth_lock_state()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._try_auto_auth_on_startup)
        self.after(200, self._drain_log_queue)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Sidebar
        self._sidebar = ctk.CTkFrame(self, width=168, corner_radius=0, fg_color=COLOR_SIDEBAR_BG)
        self._sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self._sidebar.grid_propagate(False)

        # Content area
        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color=COLOR_BG)
        self._content.grid(row=0, column=1, sticky="nsew")

        # Status bar
        self._status_bar = StatusBar(self, version=self._version)
        self._status_bar.grid(row=1, column=1, sticky="ew")
        self._status_bar.set_profile_visible(False)

        self._build_sidebar()

        # Views
        self._views: Dict[str, ctk.CTkFrame] = {}
        self._current_view: str | None = None

        self._dashboard_view = DashboardView(
            self._content,
            settings=self.settings,
            on_start=self._start_service,
            on_stop=self._stop_service,
            on_save=self._save_from_ui,
        )
        self._views["dashboard"] = self._dashboard_view

        self._log_view = LogView(self._content)
        self._views["log"] = self._log_view

    def _build_sidebar(self) -> None:
        # Title
        self._sidebar_title = ctk.CTkLabel(
            self._sidebar, text=runtime_product_name(), font=FONT_TITLE, text_color=COLOR_ACCENT
        )
        self._sidebar_title.pack(padx=16, pady=(20, 2))
        self._sidebar_subtitle = ctk.CTkLabel(
            self._sidebar, text="連携 → BOAT RACE", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED
        )
        self._sidebar_subtitle.pack(padx=16, pady=(0, 6))

        tier = tier_label()
        if tier:
            self._tier_badge = ctk.CTkLabel(
                self._sidebar,
                text=f"  {tier}  ",
                font=FONT_SMALL,
                corner_radius=8,
                fg_color=tier_accent(),
                text_color=("#1A1A1A", "#1A1A1A"),
            )
            self._tier_badge.pack(padx=16, pady=(0, 18))
        else:
            self._sidebar_subtitle.pack_configure(pady=(0, 18))

        auth_wrap = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        auth_wrap.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkLabel(auth_wrap, text="利用者ID認証", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).pack(
            anchor="w", pady=(0, 4)
        )

        self._auth_user_var = ctk.StringVar()
        self._auth_user_entry = ctk.CTkEntry(
            auth_wrap,
            textvariable=self._auth_user_var,
            placeholder_text="ユーザーID",
        )
        self._auth_user_entry.pack(fill="x", pady=(0, 6))

        self._auth_button = ctk.CTkButton(
            auth_wrap,
            text="認証",
            height=34,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_ON_ACCENT,
            command=self._authenticate_action,
        )
        self._auth_button.pack(fill="x", pady=(0, 4))

        self._auth_status_label = ctk.CTkLabel(
            auth_wrap,
            text="未認証",
            font=FONT_SMALL,
            text_color=COLOR_ERROR,
        )
        self._auth_status_label.pack(anchor="w")

        self._nav_buttons: Dict[str, ctk.CTkButton] = {}
        for key, label in [("dashboard", "運用"), ("log", "ログ")]:
            btn = ctk.CTkButton(
                self._sidebar,
                text=f"  {label}",
                font=FONT_NAV,
                fg_color="transparent",
                text_color=COLOR_TEXT_PRIMARY,
                hover_color=COLOR_SIDEBAR_HOVER,
                anchor="w",
                height=42,
                corner_radius=10,
                command=lambda k=key: self._show_view(k),
            )
            btn.pack(fill="x", padx=12, pady=2)
            self._nav_buttons[key] = btn

        # Spacer
        spacer = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # Theme toggle
        theme_wrap = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        theme_wrap.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(theme_wrap, text="テーマ", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).pack(
            anchor="w", pady=(0, 4)
        )
        saved_theme_mode = str(getattr(self.settings, "theme_mode", "system") or "system").strip().lower()
        if saved_theme_mode == "dark":
            current_theme = "ダーク"
        elif saved_theme_mode == "light":
            current_theme = "ライト"
        else:
            current_theme = "ダーク" if get_theme().lower() == "dark" else "ライト"
        self._theme_var = ctk.StringVar(value=current_theme)
        self._theme_seg = ctk.CTkSegmentedButton(
            theme_wrap,
            values=["ライト", "ダーク"],
            variable=self._theme_var,
            command=self._toggle_theme,
            selected_color=COLOR_SEG_SELECTED,
            selected_hover_color=COLOR_SEG_SELECTED_HOVER,
            unselected_color=COLOR_SEG_UNSELECTED,
            unselected_hover_color=COLOR_SEG_UNSELECTED_HOVER,
            text_color=COLOR_SEG_TEXT,
        )
        self._theme_seg.pack(fill="x")
        self._theme_seg.set(current_theme)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _show_view(self, name: str) -> None:
        if (not self._is_authenticated) and name != "dashboard":
            return
        if self._current_view == name:
            return
        palette = app_palette()
        sidebar_active = palette["sidebar_active"]
        sidebar_hover = palette["sidebar_hover"]
        # Hide current
        if self._current_view and self._current_view in self._views:
            self._views[self._current_view].pack_forget()
        # Update button styles
        for key, btn in self._nav_buttons.items():
            if key == name:
                btn.configure(
                    fg_color=sidebar_active,
                    hover_color=sidebar_hover,
                    font=FONT_NAV_ACTIVE,
                    text_color=COLOR_TEXT_PRIMARY,
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    hover_color=sidebar_hover,
                    font=FONT_NAV,
                    text_color=COLOR_TEXT_PRIMARY,
                )
        # Show new
        self._views[name].pack(in_=self._content, fill="both", expand=True)
        self._current_view = name

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _toggle_theme(self, _value: str | None = None) -> None:
        selected = str(self._theme_var.get() or "ライト")
        theme_mode = "dark" if selected == "ダーク" else "light"
        set_theme(theme_mode)
        self.settings.theme_mode = theme_mode
        save_settings(self.settings)

    # ------------------------------------------------------------------
    # Mode sync
    # ------------------------------------------------------------------

    def _sync_mode_badge(self) -> None:
        is_dry = bool(self.settings.entry.dry_run)
        if hasattr(self, "_status_bar") and self._status_bar is not None:
            self._status_bar.update_mode(not is_dry)
        if hasattr(self, "_dashboard_view"):
            self._dashboard_view.sync_mode(is_dry)

    def _apply_app_palette(self) -> None:
        palette = app_palette()
        accent = palette["accent"]
        accent_hover = palette["accent_hover"]
        sidebar_active = palette["sidebar_active"]
        sidebar_hover = palette["sidebar_hover"]

        if hasattr(self, "_sidebar_title"):
            self._sidebar_title.configure(text_color=accent)
        if hasattr(self, "_auth_button"):
            self._auth_button.configure(
                fg_color=accent,
                hover_color=accent_hover,
                text_color=COLOR_TEXT_ON_ACCENT,
            )
        if hasattr(self, "_theme_seg"):
            self._theme_seg.configure(
                selected_color=accent,
                selected_hover_color=accent_hover,
                unselected_color=COLOR_SEG_UNSELECTED,
                unselected_hover_color=COLOR_SEG_UNSELECTED_HOVER,
                text_color=COLOR_SEG_TEXT,
            )
        for key, btn in getattr(self, "_nav_buttons", {}).items():
            if key == self._current_view:
                btn.configure(fg_color=sidebar_active, hover_color=sidebar_hover)
            else:
                btn.configure(hover_color=sidebar_hover)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _set_buttons_enabled(self, root: ctk.CTkBaseClass, enabled: bool, exclude: set[ctk.CTkBaseClass]) -> None:
        for child in root.winfo_children():
            try:
                if child not in exclude and isinstance(child, (ctk.CTkButton, ctk.CTkSegmentedButton)):
                    child.configure(state="normal" if enabled else "disabled")
            except Exception:
                pass
            self._set_buttons_enabled(child, enabled, exclude)

    def _apply_auth_lock_state(self) -> None:
        enabled = bool(self._is_authenticated)
        exclude = {self._auth_button}
        self._set_buttons_enabled(self, enabled, exclude)
        # 認証ID入力は常時可
        self._auth_user_entry.configure(state="normal")
        if self._auth_in_progress:
            self._auth_button.configure(state="disabled")
        else:
            self._auth_button.configure(state="normal")
        if enabled:
            self._dashboard_view.set_running(bool(self.service and self.service.running))

    def _auth_reason_text(self, reason: str) -> str:
        mapping = {
            "unregistered": "未登録IDです",
            "expired": "利用期限切れです",
            "device_mismatch": "この端末は許可されていません",
            "bad_expiry_format": "期限フォーマット不正です",
            "client_init_failed": "認証クライアント初期化失敗",
            "sheet_read_failed": "認証データ読込失敗",
            "sheet_read_http_error": "認証データ読込HTTPエラー",
            "sheet_write_failed": "認証データ書込失敗",
            "sheet_write_http_error": "認証データ書込HTTPエラー",
        }
        return mapping.get(reason, reason or "unknown")

    def _can_auto_start_after_auth(self) -> bool:
        if not self._settings_file_exists_at_start:
            self._log_line("初回起動のため、自動開始は行いません。開始ボタンを押してください。")
            return False

        ipat = self.settings.ipat
        required_fields: list[tuple[str, str]] = [
            ("競艇ログインURL", str(getattr(ipat, "login_url", "") or "").strip()),
            ("競艇 加入者番号", str(getattr(ipat, "inet_id", "") or "").strip()),
            ("競艇 暗証番号", str(getattr(ipat, "pars_no", "") or "").strip()),
            ("競艇 認証用パスワード", str(getattr(ipat, "password", "") or "").strip()),
            ("競艇 投票用パスワード", str(getattr(ipat, "login_id", "") or "").strip()),
        ]

        missing_names = [name for name, value in required_fields if not value]
        if missing_names:
            self._log_line(
                "競艇接続設定に未入力があるため、自動開始は行いません。"
                f"開始ボタンを押してください。未入力: {', '.join(missing_names)}"
            )
            return False
        return True

    def _try_auto_auth_on_startup(self) -> None:
        if self._is_authenticated or self._auth_in_progress:
            return
        auth_settings = getattr(self.settings, "auth", None)
        if auth_settings is None:
            return
        if not bool(getattr(auth_settings, "auto_login", True)):
            return
        user_id = str(getattr(auth_settings, "user_id", "") or "").strip()
        if not user_id:
            return
        self._auth_user_var.set(user_id)
        self._log_line(f"保存済み認証IDで自動認証を実行します: user={user_id}")
        self._authenticate_action(auto_trigger=True)

    def _authenticate_action(self, auto_trigger: bool = False) -> None:
        user_id = str(self._auth_user_var.get() or "").strip()
        if not user_id:
            if not auto_trigger:
                self._log_line("認証IDを入力してください")
            return
        if self._auth_in_progress:
            return

        if auth_module is None:
            self._log_line(f"認証モジュール初期化失敗: {_auth_import_exc}")
            self._auth_status_label.configure(text="認証失敗", text_color=COLOR_ERROR)
            return

        self._auth_in_progress = True
        self._auth_status_label.configure(text="認証中...", text_color=COLOR_TEXT_MUTED)
        self._apply_auth_lock_state()

        def _worker() -> None:
            try:
                result = auth_module.authenticate_user(user_id)
            except Exception as exc:
                logger.exception("auth failed")
                result = {"ok": False, "reason": str(exc), "expiry": None}

            self.after(0, lambda: self._on_auth_result(user_id, result, auto_trigger))

        threading.Thread(target=_worker, name="auth-worker", daemon=True).start()

    def _on_auth_result(self, user_id: str, result: Dict[str, Any], auto_trigger: bool = False) -> None:
        self._auth_in_progress = False
        ok = bool(result.get("ok"))
        reason = str(result.get("reason", "") or "")
        expiry = result.get("expiry")

        if ok:
            self._is_authenticated = True
            exp_text = str(expiry or "-")
            self._auth_status_label.configure(text=f"認証済み 期限:{exp_text}", text_color=COLOR_SUCCESS)
            auth_settings = getattr(self.settings, "auth", None)
            if auth_settings is not None:
                auth_settings.user_id = user_id
                save_settings(self.settings)
            if auto_trigger:
                self._log_line(f"自動認証成功: user={user_id} expiry={exp_text}")
            else:
                self._log_line(f"認証成功: user={user_id} expiry={exp_text}")
        else:
            self._is_authenticated = False
            msg = self._auth_reason_text(reason)
            self._auth_status_label.configure(text=f"認証失敗: {msg}", text_color=COLOR_ERROR)
            if auto_trigger:
                self._log_line(f"自動認証失敗: user={user_id} reason={msg}")
            else:
                self._log_line(f"認証失敗: user={user_id} reason={msg}")

        self._apply_auth_lock_state()
        if ok and not (self.service and self.service.running):
            if self._can_auto_start_after_auth():
                self._start_service(auto_trigger=True)

    # ------------------------------------------------------------------
    # Settings save
    # ------------------------------------------------------------------

    def _save_from_ui(self, show_log: bool = True, show_dialog: bool = True) -> None:
        self._dashboard_view.collect_to_settings(self.settings)
        save_settings(self.settings)
        self._sync_mode_badge()
        self._apply_app_palette()
        if show_log:
            self._log_line("設定を保存しました")
        if show_dialog:
            messagebox.showinfo("設定保存", "設定を保存しました。")

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def _ensure_service_instance(self) -> AutoEntryService:
        review_func = None
        if self.service is None:
            self.service = AutoEntryService(
                self.settings,
                self._service_log,
                review_func=review_func,
            )
        else:
            self.service.settings = self.settings
            self.service.log_func = self._service_log
            self.service.review_func = review_func
        return self.service

    def _set_service_busy(self, busy: bool) -> None:
        self._service_op_in_progress = bool(busy)
        self._dashboard_view.set_busy(bool(busy))

    def _start_service(self, auto_trigger: bool = False) -> None:
        if not self._is_authenticated:
            self._log_line("先に認証を実行してください")
            return
        if self._service_op_in_progress:
            if not auto_trigger:
                self._log_line("開始/停止処理中です。しばらく待ってください")
            return
        if self.service and self.service.running:
            if not auto_trigger:
                self._log_line("すでに監視中です")
            return

        self._save_from_ui(show_log=False, show_dialog=False)

        try:
            service = self._ensure_service_instance()
        except Exception:
            logger.exception("failed to start service")
            self._log_line("開始失敗: 監視サービスの初期化に失敗しました")
            return

        self._set_service_busy(True)

        def _worker() -> None:
            error_message: str | None = None
            try:
                service.start()
                if not self.settings.entry.dry_run:
                    service.request_prepare_ipat()
            except Exception as exc:
                logger.exception("failed to start service")
                error_message = str(exc)
            self.after(0, lambda: self._on_start_service_finished(error_message))

        threading.Thread(target=_worker, name="service-start", daemon=True).start()

    def _on_start_service_finished(self, error_message: str | None) -> None:
        self._set_service_busy(False)
        if error_message:
            self._dashboard_view.set_running(False)
            self._log_line("開始失敗: 監視開始に失敗しました。設定を確認してください")
            return
        self._dashboard_view.set_running(bool(self.service and self.service.running))

    def _stop_service(self, sync: bool = False) -> None:
        if (not sync) and self._service_op_in_progress:
            self._log_line("開始/停止処理中です。しばらく待ってください")
            return

        service = self.service
        if service is None:
            self._dashboard_view.set_running(False)
            self._discord_connected = False
            self._status_bar.update_discord(False)
            if hasattr(self, "_dashboard_view"):
                self._dashboard_view.update_discord(False)
            return

        def _do_stop() -> str | None:
            try:
                service.stop()
                return None
            except Exception as exc:
                logger.exception("failed to stop service")
                return str(exc)

        if sync:
            error_message = _do_stop()
            if error_message:
                self._log_line("停止失敗: 停止処理でエラーが発生しました")
            self._dashboard_view.set_running(False)
            self._discord_connected = False
            self._status_bar.update_discord(False)
            if hasattr(self, "_dashboard_view"):
                self._dashboard_view.update_discord(False)
            return

        self._set_service_busy(True)

        def _worker() -> None:
            error_message = _do_stop()
            self.after(0, lambda: self._on_stop_service_finished(error_message))

        threading.Thread(target=_worker, name="service-stop", daemon=True).start()

    def _on_stop_service_finished(self, error_message: str | None) -> None:
        self._set_service_busy(False)
        if error_message:
            self._log_line("停止失敗: 停止処理でエラーが発生しました")
        self._dashboard_view.set_running(False)
        self._discord_connected = False
        self._status_bar.update_discord(False)
        if hasattr(self, "_dashboard_view"):
            self._dashboard_view.update_discord(False)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _service_log(self, text: str) -> None:
        self.log_queue.put(text)

    def _log_line(self, line: str) -> None:
        from datetime import datetime

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_queue.put(f"[{ts}] {line}")

    def _drain_log_queue(self) -> None:
        processed = 0
        try:
            while processed < self._LOG_DRAIN_MAX_PER_TICK:
                line = self.log_queue.get_nowait()
                self._process_log_line(line)
                processed += 1
        except queue.Empty:
            pass
        delay = self._LOG_DRAIN_BUSY_MS if (not self.log_queue.empty()) else self._LOG_DRAIN_IDLE_MS
        self.after(delay, self._drain_log_queue)

    @staticmethod
    def _should_hide_log_line(line: str) -> bool:
        body = str(line or "")
        if "] " in body:
            body = body.split("] ", 1)[1]
        hidden_prefixes = (
            "連携設定:",
            "連携設定注意:",
            "連携接続完了",
            "連携切断",
            "連携再接続を試行します",
            "連携再接続を開始しました",
            "連携デバッグ:",
            "受信デバッグ:",
            "待機維持:",
            "待機維持デバッグ:",
            "KEIRIN.JP待機維持:",
            "BOAT RACE待機維持:",
            "KEIRIN.JPログイン状態を確認済み",
            "競輪ログイン状態を確認済み",
            "競輪: KEIRIN.JPログイン状態を確認済み",
            "競艇ログイン状態を確認済み",
            "iPAT事前準備が完了しました",
        )
        return body.startswith(hidden_prefixes)

    def _process_log_line(self, line: str) -> None:
        line_lower = str(line or "").lower()

        # Discord由来の露出ログは表示しない
        if "discord:" in line_lower or "discordエラー:" in line_lower:
            return

        # Update stats
        if ("受信:" in line and "payload=" in line) or ("指示受信:" in line and "payload=" in line):
            self._stat_received += 1
            self._dashboard_view.update_stats(
                self._stat_received, self._stat_ordered, self._stat_skipped
            )
        elif "DRY-RUN:" in line or "発注結果:" in line:
            self._stat_ordered += 1
            self._dashboard_view.update_stats(
                self._stat_received, self._stat_ordered, self._stat_skipped
            )
        elif "見送り:" in line:
            self._stat_skipped += 1
            self._dashboard_view.update_stats(
                self._stat_received, self._stat_ordered, self._stat_skipped
            )

        # Detect integration connection
        if "連携接続完了" in line:
            self._discord_connected = True
            self._status_bar.update_discord(True)
            self._dashboard_view.update_discord(True)
        elif "連携切断" in line or "連携エラー:" in line:
            self._discord_connected = False
            self._status_bar.update_discord(False)
            self._dashboard_view.update_discord(False)

        if self._should_hide_log_line(line):
            return

        self._log_view.append_line(line)
        self._dashboard_view.append_activity(line)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        should_close = messagebox.askyesno("終了確認", "本当に閉じますか？")
        if not should_close:
            return
        try:
            self._stop_service(sync=True)
        except Exception:
            logger.exception("stop on close failed")
        self.destroy()
