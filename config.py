from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict

from strategy_modes import DEFAULT_STRATEGY_CODE
from product_profile import (
    clamp_enabled_bet_types as _clamp_enabled_bet_types,
    default_enabled_bet_types as _default_enabled_bet_types,
)

CONFIG_FILE = "kyoutei_auto_entry_config.json"
SELECTORS_FILE = "ipat_selectors.json"
DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME = "10:00"
DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME = "21:00"


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        t = value.strip().lower()
        if t in {"1", "true", "yes", "on"}:
            return True
        if t in {"0", "false", "no", "off"}:
            return False
    return bool(default)


DEFAULT_SELECTORS_CENTRAL: Dict[str, Any] = {
    "kyoutei_login_url": "https://ib.mbrace.or.jp/",
    "kyoutei_login_form": "#loginForm",
    "kyoutei_member_no_input": "#memberNo",
    "kyoutei_pin_input": "#pin",
    "kyoutei_auth_password_input": "#authPassword",
    "kyoutei_login_button": "#loginButton",
    "kyoutei_top_ready_selector": "#todayForm, #beforeForm, #jyoInfos, #jyoInfosTab, #raceSelection, #toplogoForm",
    "kyoutei_top_logo_form": "#toplogoForm",
    "kyoutei_venue_list_selector": "#jyoInfos li, #jyoInfosTab li",
    "kyoutei_race_tab_selector": "#raceSelection .raceSelTab, #raceSelection li",
    "kyoutei_bet_page_ready_selector": "#raceSelection, #betlist, #confirmationArea, #voteListAreaInner",
    "kyoutei_betlist_submit_button": "#betlist .btnSubmit, #betlist a.btnSubmit, #betlist .betlistbtn.submit, #betlist a:has-text('投票内容確認')",
    "kyoutei_popup_selector": "#popup",
    "kyoutei_popup_ok_button": "#ok",
    "kyoutei_confirm_ready_selector": "#confirmationArea, #betconfForm, #amount, #pass",
    "kyoutei_confirm_amount_input": "#amount",
    "kyoutei_confirm_pass_input": "#pass",
    "kyoutei_submit_button": "#submitBet",
    "kyoutei_complete_selector": "#sameJyoBet, #modifyJyoBetForm, #voteListAreaInner",
    "inet_id_input": "input[name='inetid']",
    "inet_next_button": "a[title='ログイン']",
    "after_inet_wait_selector": "input[name='i']",
    "login_id_input": "input[name='i']",
    "password_input": "input[name='p']",
    "pars_input": "input[name='r']",
    "login_button": "a[title='ネット投票メニューへ']",
    "post_login_wait_selector": "button[ui-sref='bet.basic']",
    "important_notice_selector": "div.announce:has-text('重要なお知らせ')",
    "important_notice_ok_button": "div.announce button.btn-ok, div.announce button:has-text('OK')",
    "important_notice_skip_checkbox": "#force-info-checkbox",
    "vote_page_url": "",
    "vote_menu_link": "",
    "normal_vote_button": "button[ui-sref='bet.basic']",
    "no_funds_dialog_selector": "div.dialog:has-text('投票の前に')",
    "no_funds_continue_button": "div.dialog button:has-text('このまま進む')",
    "course_select": "#select-course-race-course",
    "race_select": "#select-course-race-race",
    "course_button_selector": "div.places button",
    "race_button_selector": "div.races button",
    "race_ready_selector": "select#bet-basic-type, div.ipat-vote-basic-detail, div.selection-amount input[ng-model='vm.nUnit']",
    "vote_loading_selector": "text=NOW LOADING, .loading, .loading-overlay, .now-loading",
    "market_select": "#bet-basic-type",
    "market_select_mode": "label",
    "market_value_map": {
        "単勝": "単勝",
        "複勝": "複勝",
        "枠連": "枠連",
        "馬連": "馬連",
        "馬複": "馬連",
        "ワイド": "ワイド",
        "馬単": "馬単",
        "2車単": "２車単",
        "２車単": "２車単",
        "二車単": "２車単",
        "2車複": "２車複",
        "２車複": "２車複",
        "二車複": "２車複",
        "3連複": "３連複",
        "3連単": "３連単",
        "３連複": "３連複",
        "３連単": "３連単",
        "三連複": "３連複",
        "三連単": "３連単",
    },
    "method_select": "#bet-basic-method",
    "default_method_label": "通常",
    "horse_checkbox_prefix": "input[id^='no']",
    "ticket_amount_input": "div.selection-amount input[ng-model='vm.nUnit']",
    "expand_set_button": "div.selection-buttons button:has-text('展開セット')",
    "set_button": "div.selection-buttons button:has-text('セット')",
    "input_done_button": "div.selection-buttons button:has-text('入力終了')",
    "purchase_list_ready_selector": "input[ng-model='vm.cAmountTotal'], table.table-ipat",
    "purchase_total_input": "input[ng-model='vm.cAmountTotal']",
    "purchase_button": "button:has-text('購入する')",
    "purchase_confirm_ok_button": "div.dialog button:has-text('OK')",
    "discard_purchase_list_dialog_selector": "div.dialog:has-text('購入予定リストの内容をすべて破棄して投票メニュー画面に戻ります')",
    "discard_purchase_list_ok_button": "div.dialog:has-text('購入予定リストの内容をすべて破棄して投票メニュー画面に戻ります') button.btn-ok, div.dialog:has-text('購入予定リストの内容をすべて破棄して投票メニュー画面に戻ります') button:has-text('OK')",
    "insufficient_funds_dialog_selector": "div.dialog:has-text('購入限度額を超えました')",
    "return_home_button": "div.brand a[ui-sref='home']",
    # Legacy selectors kept for compatibility with older iPAT HTML.
    "horse1_input": "input[name='horse1']",
    "horse2_input": "input[name='horse2']",
    "horse3_input": "input[name='horse3']",
    "amount_input": "input[name='amount']",
    "add_ticket_button": "button:has-text('追加')",
    "submit_button": "button:has-text('投票')",
    "final_confirm_button": "button:has-text('確定')",
    # KEIRIN.JP向けの拡張セレクタ（互換維持のため中央セレクタに同居）
    "keirin_top_login_url": "https://keirin.jp/pc/top",
    "keirin_login_id_input": "#trtxtBallotID",
    "keirin_login_password_input": "#trtxtBallotPW",
    "keirin_login_button": "form[action*='LoginServlet'] input[type='submit'][value='ログイン'], #loginbox1 input[type='submit'][value='ログイン']",
    "keirin_login_success_selector": "#loginbox2, #loginbox2 .now_login",
    "keirin_vote_rows": "li.kyotuHeader, li.kyotuHeader.white_bg_color",
    "keirin_vote_button": "button[id^='hcombtnTouhyou'], input[id^='hcombtnTouhyou'], a[id^='hcombtnTouhyou']",
    "keirin_vote_page_ready_selector": "select[name='cmbKakesiki'], #kai, #bet_right",
    "keirin_market_select": "select[name='cmbKakesiki']",
    "keirin_set_button": "button.btn_set, #UNQ_orbutton_12",
    "keirin_summary_total": ".kimLblTotalGaku",
    "keirin_summary_bet_count": ".kimLblBetCnt",
    "keirin_primary_vote_button": "button.kimBtnVote",
    "keirin_pin_input": "#kimTxtPassWord",
    "keirin_final_vote_button": "#kimBtnVote, button#kimBtnVote",
    "keirin_confirm_ok_button": "#kim_confirm_ok_btn, .kim_confirm_ok_btn",
    "keirin_return_top_selector": "#btnKeirinjp, a#btnKeirinjp",
}

# 地方競馬（SPAT4）向けの内蔵セレクタ定義。
DEFAULT_SELECTORS_LOCAL: Dict[str, Any] = {
    "__configured__": True,
    "login_member_number_input": "#MEMBERNUMR",
    "login_member_id_input": "#MEMBERIDR",
    "login_button": "a.loginbtn, a[onclick*='loginCheck']",
    "local_kaisai_section": "div.section03",
    "local_kaisai_current": "div.section03 li.current",
    "local_kaisai_links": "div.section03 li a",
    "local_race_table": "table.tbl_01",
    "local_race_rows": "table.tbl_01 tr",
    "local_odds_vote_button": "a:has-text('オッズ投票'), a:has-text('オッズ')",
    "local_shiki_select": "select[name='SHIKILINK']",
    "market_select": "select[name='SHIKILINK']",
    "market_select_mode": "value",
    "market_value_map": {
        "馬連": "5",
        "馬複": "5",
        "ワイド": "7",
    },
    "local_bet_table": "#BET_TBL",
    "local_bet_rows": "#BET_TBL tr:has(input.TEXTMONEY)",
    "local_bet_money_inputs": "#BET_TBL input.TEXTMONEY",
    "local_refresh_button": "span.btn_update a:has-text('情報更新'), a:has-text('情報更新'), input[type='button'][value='情報更新']",
    "local_popup_selector": "div#popupscreen.popup-screen, div.popup-screen",
    "local_popup_close_button": "div#popupscreen input.close-btn[value='閉じる'], div#popupscreen input[type='button'][value='閉じる'], div.popup-screen input.close-btn[value='閉じる'], div.popup-screen input[type='button'][value='閉じる']",
    "local_mail_notice_selector": "div.mailAuth:has-text('メールアドレスの認証システムを導入しました')",
    "local_mail_notice_vote_button": "input#goKaisai[value='投票へすすむ'], div.mailAuth input[type='button'][value='投票へすすむ']",
    "local_confirm_button": "input[type='submit'][value='投票内容確認へ'], input[value='投票内容確認へ']",
    "local_member_pass_input": "#MEMBERPASSR",
    "local_total_money_input": "#TOTALMONEYR",
    "local_vote_button": "input[name='KYOUSEI'][value='投票する'], input[value='投票する']",
    "local_return_kaisai_button": "input[value='開催要領']",
}

# 互換のため名称は残す（内部実装は中央向け固定）。
DEFAULT_SELECTORS: Dict[str, Any] = dict(DEFAULT_SELECTORS_CENTRAL)


@dataclass
class IpatSettings:
    login_url: str = "https://ib.mbrace.or.jp/"
    inet_id: str = ""
    login_id: str = ""
    password: str = ""
    pars_no: str = ""
    browser_channel: str = ""
    browser_executable_path: str = ""
    headless: bool = True
    timeout_sec: int = 2
    submit_enabled: bool = True
    selectors_file: str = SELECTORS_FILE


@dataclass
class LocalIpatSettings:
    login_url: str = "https://www.spat4.jp/keiba/pc"
    member_number: str = ""
    member_id: str = ""
    pin: str = ""
    browser_channel: str = ""
    browser_executable_path: str = ""
    headless: bool = False
    timeout_sec: int = 2
    submit_enabled: bool = False
    selectors_file: str = SELECTORS_FILE


@dataclass
class EntrySettings:
    fixed_ticket_yen: int = 100
    raffine_budget_yen: int = 10000
    entry_abort_total_yen: int = 10000
    entry_abort_mode: str = "yen"
    entry_abort_ratio_pct: float = 100.0
    ratio_pct: float = 100.0
    race_cap_yen: int = 0
    ticket_cap_yen: int = 0
    max_tickets: int = 0
    min_ticket_yen: int = 100
    target_payout_mode: str = "yen"
    target_payout_ratio_pct: float = 1000.0
    target_payout_yen: int = 10000
    dry_run: bool = False
    confirm_each_race: bool = False
    show_ticket_preview_window: bool = False
    allocation_mode: str = "target_payout"
    enable_central: bool = True
    enable_local: bool = False
    central_schedule_enabled: bool = True
    central_schedule_open_time: str = DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME
    central_schedule_close_time: str = DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME
    dispatch_mode: str = DEFAULT_STRATEGY_CODE
    # GOLD/SILVER/BRONZE で選択した券種（2連複/3連複/3連単）。
    # この券種の通知だけをキャッチ・エントリーする。エディション上限で切り詰める。
    enabled_bet_types: list = field(default_factory=_default_enabled_bet_types)


@dataclass
class AuthSettings:
    user_id: str = ""
    auto_login: bool = True


@dataclass
class AppSettings:
    ipat: IpatSettings = field(default_factory=IpatSettings)
    local_ipat: LocalIpatSettings = field(default_factory=LocalIpatSettings)
    entry: EntrySettings = field(default_factory=EntrySettings)
    auth: AuthSettings = field(default_factory=AuthSettings)
    theme_mode: str = "system"


def _normalize_browser_channel(value: Any) -> str:
    channel_raw = str(value or "").strip().lower()
    if channel_raw in {"default", "bundled", "builtin", "playwright", "chromium"}:
        return ""
    if channel_raw in {"msedge", "edge"}:
        return "msedge"
    if channel_raw in {"google-chrome", "googlechrome"}:
        return "chrome"
    return channel_raw


def _coerce_ipat(raw: Dict[str, Any]) -> IpatSettings:
    return IpatSettings(
        login_url=str(raw.get("login_url", "https://ib.mbrace.or.jp/") or "https://ib.mbrace.or.jp/"),
        inet_id=str(raw.get("inet_id", "") or ""),
        login_id=str(raw.get("login_id", "") or ""),
        password=str(raw.get("password", "") or ""),
        pars_no=str(raw.get("pars_no", "") or ""),
        browser_channel=_normalize_browser_channel(raw.get("browser_channel")),
        browser_executable_path=str(raw.get("browser_executable_path", "") or "").strip(),
        headless=_safe_bool(raw.get("headless"), True),
        # 投票中フリーズ時の待機が長すぎる事象を避けるため、待機秒数は 1〜2 秒に制限する。
        timeout_sec=max(1, min(2, _safe_int(raw.get("timeout_sec"), 2))),
        # UI簡素化に合わせて、競輪側の最終確定は常時ONで扱う。
        submit_enabled=True,
        selectors_file=str(raw.get("selectors_file", SELECTORS_FILE) or SELECTORS_FILE),
    )


def _coerce_local_ipat(raw: Dict[str, Any]) -> LocalIpatSettings:
    return LocalIpatSettings(
        login_url=str(raw.get("login_url", "https://www.spat4.jp/keiba/pc") or "https://www.spat4.jp/keiba/pc").strip(),
        # 旧設定互換: member_number <- login_id
        member_number=str(raw.get("member_number", raw.get("login_id", "")) or ""),
        # 旧設定互換: member_id <- inet_id
        member_id=str(raw.get("member_id", raw.get("inet_id", "")) or ""),
        # 旧設定互換: pin <- password
        pin=str(raw.get("pin", raw.get("password", "")) or ""),
        browser_channel=_normalize_browser_channel(raw.get("browser_channel")),
        browser_executable_path=str(raw.get("browser_executable_path", "") or "").strip(),
        headless=_safe_bool(raw.get("headless"), False),
        timeout_sec=max(1, min(2, _safe_int(raw.get("timeout_sec"), 2))),
        submit_enabled=_safe_bool(raw.get("submit_enabled"), False),
        selectors_file=str(raw.get("selectors_file", SELECTORS_FILE) or SELECTORS_FILE),
    )


def _coerce_entry(raw: Dict[str, Any]) -> EntrySettings:
    fixed_ticket_raw = raw.get("fixed_ticket_yen", None)
    if fixed_ticket_raw is None:
        # 旧設定互換: ratio_pct を固定投票金額として読み替える。
        fixed_ticket_raw = raw.get("ratio_pct", 100)

    def _normalize_hhmm(value: Any, default: str) -> str:
        text = str(value or "").strip().replace("：", ":")
        if not text:
            text = str(default or "").strip()
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
        if not m:
            return str(default)
        hour = _safe_int(m.group(1), -1)
        minute = _safe_int(m.group(2), -1)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return str(default)
        return f"{int(hour):02d}:{int(minute):02d}"

    return EntrySettings(
        fixed_ticket_yen=max(100, _safe_int(fixed_ticket_raw, 100)),
        raffine_budget_yen=max(100, _safe_int(raw.get("raffine_budget_yen"), 10000)),
        entry_abort_total_yen=max(0, _safe_int(raw.get("entry_abort_total_yen"), 10000)),
        # 中止金額は円基準のみを露出する。
        entry_abort_mode="yen",
        entry_abort_ratio_pct=max(0.0, _safe_float(raw.get("entry_abort_ratio_pct"), 100.0)),
        ratio_pct=max(0.0, _safe_float(raw.get("ratio_pct"), 100.0)),
        race_cap_yen=0,
        ticket_cap_yen=0,
        max_tickets=0,
        min_ticket_yen=100,
        target_payout_mode="yen",
        target_payout_ratio_pct=max(1.0, _safe_float(raw.get("target_payout_ratio_pct"), 1000.0)),
        target_payout_yen=max(100, _safe_int(raw.get("target_payout_yen"), 10000)),
        dry_run=False,
        confirm_each_race=False,
        show_ticket_preview_window=False,
        allocation_mode="target_payout",
        enable_central=True,
        enable_local=False,
        central_schedule_enabled=True,
        central_schedule_open_time=_normalize_hhmm(
            DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME,
            DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME,
        ),
        central_schedule_close_time=_normalize_hhmm(
            DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME,
            DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME,
        ),
        # Hidden compatibility field. GUI and service no longer switch behavior by strategy.
        dispatch_mode=DEFAULT_STRATEGY_CODE,
        enabled_bet_types=_coerce_enabled_bet_types(raw.get("enabled_bet_types")),
    )


def _coerce_enabled_bet_types(raw: Any) -> list:
    # 未設定(None=初回)はエディション既定。明示的な空リストはユーザーの「選択なし」を尊重。
    if raw is None:
        return _default_enabled_bet_types()
    return _clamp_enabled_bet_types(raw)


def _coerce_auth(raw: Dict[str, Any]) -> AuthSettings:
    return AuthSettings(
        user_id=str(raw.get("user_id", "") or "").strip(),
        auto_login=_safe_bool(raw.get("auto_login"), True),
    )


def _coerce_theme_mode(raw: Any) -> str:
    mode = str(raw or "system").strip().lower()
    if mode not in {"light", "dark", "system"}:
        mode = "system"
    return mode


def load_settings(path: str | Path = CONFIG_FILE) -> AppSettings:
    p = Path(path)
    if not p.exists():
        return AppSettings()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return AppSettings()
    if not isinstance(raw, dict):
        return AppSettings()
    return AppSettings(
        ipat=_coerce_ipat(raw.get("ipat") or {}),
        local_ipat=_coerce_local_ipat(raw.get("local_ipat") or {}),
        entry=_coerce_entry(raw.get("entry") or {}),
        auth=_coerce_auth(raw.get("auth") or {}),
        theme_mode=_coerce_theme_mode(raw.get("theme_mode", "system")),
    )



def save_settings(settings: AppSettings, path: str | Path = CONFIG_FILE) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    return p



def ensure_selectors_file(path: str | Path) -> Path:
    # 互換関数。セレクタは完全内蔵化したためファイルは生成しない。
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _normalize_selector_target(value: str) -> str:
    text = str(value or "central").strip().lower()
    if text in {"local", "chihou", "chiho"}:
        return "local"
    return "central"


def load_internal_selectors(target: str = "central") -> Dict[str, Any]:
    target_kind = _normalize_selector_target(target)
    if target_kind == "local":
        return dict(DEFAULT_SELECTORS_LOCAL)
    return dict(DEFAULT_SELECTORS_CENTRAL)



def load_selectors(path: str | Path, target: str = "central") -> Dict[str, Any]:
    del path
    # 互換関数。外部JSONは参照せず、内蔵セレクタのみ返す。
    return load_internal_selectors(target=target)
