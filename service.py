from __future__ import annotations

import json
import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

from bet_rules import (
    apply_entry_rules,
    apply_raffine_distribution,
    apply_target_payout_distribution,
    sum_ticket_yen,
)
from config import (
    DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME,
    DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME,
    AppSettings,
    load_internal_selectors,
)
from discord_client import DiscordClientError, DiscordGatewayClient
from ipat_playwright import IpatEntryError, IpatPlaywrightExecutor, ThreadBoundIpatPlaywrightExecutor
from payload_parser import extract_payloads_from_text
from product_profile import (
    clamp_enabled_bet_types,
    clamp_enabled_dayparts,
    infer_tool_slot_from_payload,
    line_cap_axis,
    active_line_channel_id,
    normalize_bet_type,
    normalize_daypart_label,
    tool_slot_hour,
    tool_slot_label,
)
import secrets_local
from strategy_modes import normalize_strategy_code

logger = logging.getLogger(__name__)

KYOUTEI_VENUE_NAMES = frozenset(
    {
        "桐生",
        "戸田",
        "江戸川",
        "平和島",
        "多摩川",
        "浜名湖",
        "蒲郡",
        "常滑",
        "津",
        "三国",
        "びわこ",
        "住之江",
        "尼崎",
        "鳴門",
        "丸亀",
        "児島",
        "宮島",
        "徳山",
        "下関",
        "若松",
        "芦屋",
        "福岡",
        "唐津",
        "大村",
    }
)
KEIRIN_VENUE_NAMES = frozenset(
    {
        "函館",
        "青森",
        "いわき平",
        "弥彦",
        "前橋",
        "取手",
        "宇都宮",
        "大宮",
        "西武園",
        "京王閣",
        "立川",
        "松戸",
        "千葉",
        "川崎",
        "平塚",
        "小田原",
        "伊東",
        "静岡",
        "名古屋",
        "岐阜",
        "大垣",
        "豊橋",
        "富山",
        "松阪",
        "四日市",
        "福井",
        "奈良",
        "向日町",
        "和歌山",
        "岸和田",
        "玉野",
        "広島",
        "防府",
        "高松",
        "小松島",
        "高知",
        "松山",
        "小倉",
        "久留米",
        "武雄",
        "佐世保",
        "別府",
        "熊本",
    }
)
KYOUTEI_MARKET_NAMES = frozenset(
    {
        "2連単",
        "２連単",
        "二連単",
        "2連複",
        "２連複",
        "二連複",
        "拡連複",
        "3連単",
        "３連単",
        "三連単",
        "3連複",
        "３連複",
        "三連複",
    }
)
KEIRIN_MARKET_NAMES = frozenset(
    {
        "2車単",
        "２車単",
        "二車単",
        "2車複",
        "２車複",
        "二車複",
        "3連単",
        "３連単",
        "三連単",
        "3連複",
        "３連複",
        "三連複",
    }
)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_id_set(values: Any) -> set[str]:
    out: set[str] = set()
    if values is None:
        return out
    if isinstance(values, (str, bytes)):
        text = str(values or "").strip()
        if text:
            out.add(text)
        return out
    try:
        iterator = iter(values)
    except TypeError:
        text = str(values or "").strip()
        if text:
            out.add(text)
        return out
    for raw in iterator:
        text = str(raw or "").strip()
        if text:
            out.add(text)
    return out


def _safe_float(value: Any, default: float = -1.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _sample_ids(values: set[str] | list[str], limit: int = 5) -> str:
    ids = sorted(str(v or "").strip() for v in values if str(v or "").strip())
    if not ids:
        return "-"
    if len(ids) <= int(limit):
        return ",".join(ids)
    remain = len(ids) - int(limit)
    return f"{','.join(ids[: int(limit)])}...(+{remain})"


def _extract_odds_range(ticket: Dict[str, Any]) -> tuple[float, float] | None:
    low = _safe_float(ticket.get("odds"), -1.0)
    high = _safe_float(ticket.get("high_odds"), -1.0)
    if high <= 0:
        high = _safe_float(ticket.get("odds_high"), -1.0)
    if high <= 0:
        high = _safe_float(ticket.get("highOdds"), -1.0)

    if low <= 0 and high <= 0:
        return None
    if low <= 0 < high:
        low = high
    if high <= 0 < low:
        high = low
    if high < low:
        low, high = high, low
    return (low, high)


def _format_odds_value(value: float) -> str:
    text = f"{value:.1f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _format_odds_text(ticket: Dict[str, Any]) -> str:
    odds = _extract_odds_range(ticket)
    if odds is None:
        return "-"
    low, high = odds
    if high > low:
        return f"{_format_odds_value(low)}～{_format_odds_value(high)}"
    return _format_odds_value(low)


def _format_expected_payout_text(ticket: Dict[str, Any]) -> str:
    bet = int(ticket.get("bet_yen", 0) or 0)
    if bet <= 0:
        return "-"

    odds = _extract_odds_range(ticket)
    if odds is None:
        return "-"
    low, high = odds

    low_yen = int(round(float(low) * float(bet)))
    high_yen = int(round(float(high) * float(bet)))
    if high_yen > low_yen:
        return f"{low_yen:,}～{high_yen:,}円"
    return f"{low_yen:,}円"


class AutoEntryService:
    CMD_PAYLOAD = "payload"
    CMD_PREPARE = "prepare"
    CMD_CANDIDATE_CONTROL = "candidate_control"
    TARGET_CENTRAL = "central"
    TARGET_LOCAL = "local"
    CENTRAL_KEEPALIVE_INTERVAL_SEC = 600.0
    LOCAL_KEEPALIVE_INTERVAL_SEC = 600.0
    CENTRAL_SCHEDULE_RETRY_SEC = 60.0
    TARGETS = (TARGET_CENTRAL, TARGET_LOCAL)
    TARGET_LABELS = {
        TARGET_CENTRAL: "中央",
        TARGET_LOCAL: "地方",
    }
    NO_PAYLOAD_DEBUG_LIMIT = 20
    STARTUP_HISTORY_LIMIT = 100

    def __init__(
        self,
        settings: AppSettings,
        log_func: Callable[[str], None],
        review_func: Callable[[Dict[str, Any], List[Dict[str, Any]], int, bool, bool], bool] | None = None,
    ):
        self.settings = settings
        self.log_func = log_func
        self.review_func = review_func
        self._worker_threads: Dict[str, threading.Thread | None] = {k: None for k in self.TARGETS}
        self._discord: DiscordGatewayClient | None = None
        self._executors: Dict[str, IpatPlaywrightExecutor | None] = {k: None for k in self.TARGETS}
        self._ipat_locks: Dict[str, threading.Lock] = {k: threading.Lock() for k in self.TARGETS}
        self._review_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self._queues: Dict[str, "queue.Queue[tuple[str, Any]]"] = {k: queue.Queue() for k in self.TARGETS}
        self._last_discord_start_monotonic = 0.0
        self._next_central_keepalive_monotonic = 0.0
        self._next_local_keepalive_monotonic = 0.0
        self._next_central_schedule_retry_monotonic = 0.0
        self._no_payload_debug_count = 0
        self._legacy_allowed_channel_ids = _normalize_id_set(getattr(secrets_local, "DISCORD_ALLOWED_CHANNEL_IDS", []))
        # 製品ライン（aqua=ch1521 / clearism=ch1490）の配信チャンネルを最優先で採用する。
        # これにより同じ secrets でもEXEのラインごとに読み取りチャンネルが分かれる。
        _line_channel = str(active_line_channel_id() or "").strip()
        if _line_channel:
            self._central_channel_ids = _normalize_id_set([_line_channel])
        else:
            self._central_channel_ids = _normalize_id_set(getattr(secrets_local, "DISCORD_CENTRAL_CHANNEL_IDS", []))
        self._local_channel_ids = _normalize_id_set(getattr(secrets_local, "DISCORD_LOCAL_CHANNEL_IDS", []))
        self._central_candidate_pause_active = False
        self._central_candidate_pause_date = ""
        self._central_candidate_control_actions: Dict[str, str] = {}
        self._startup_history_replay_active = False
        if (not self._central_channel_ids) and (not self._local_channel_ids) and self._legacy_allowed_channel_ids:
            # 互換: 新設定未指定時は従来の許可チャンネルを中央として扱う。
            self._central_channel_ids = set(self._legacy_allowed_channel_ids)
        if self._central_channel_ids or self._local_channel_ids:
            self._discord_allowed_channel_ids = sorted(self._central_channel_ids | self._local_channel_ids)
        else:
            self._discord_allowed_channel_ids = sorted(self._legacy_allowed_channel_ids)
        self._discord_allowed_guild_ids = sorted(_normalize_id_set(getattr(secrets_local, "DISCORD_ALLOWED_GUILD_IDS", [])))

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._running)

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True

        token = str(getattr(secrets_local, "DISCORD_BOT_TOKEN", "") or "").strip()
        if (not token) or ("PASTE_DISCORD_BOT_TOKEN_HERE" in token):
            with self._lock:
                self._running = False
            raise DiscordClientError("`secrets_local.py` の DISCORD_BOT_TOKEN を設定してください")

        self._stop_event.clear()
        self._next_central_keepalive_monotonic = 0.0
        self._next_local_keepalive_monotonic = 0.0
        self._next_central_schedule_retry_monotonic = 0.0
        self._no_payload_debug_count = 0
        self._startup_history_replay_active = True
        for target in self.TARGETS:
            worker = threading.Thread(
                target=self._worker_loop,
                args=(target,),
                name=f"entry-worker-{target}",
                daemon=True,
            )
            self._worker_threads[target] = worker
            worker.start()

        try:
            self._start_discord_gateway()
        except Exception:
            self._stop_event.set()
            self._startup_history_replay_active = False
            for worker in self._worker_threads.values():
                if worker and worker.is_alive():
                    worker.join(timeout=1.0)
            with self._lock:
                self._running = False
            raise

        self._log(
            "連携設定: "
            f"中央ch={_sample_ids(self._central_channel_ids)} "
            f"地方ch={_sample_ids(self._local_channel_ids)} "
            f"許可ch={_sample_ids(self._discord_allowed_channel_ids)}"
        )
        if self._legacy_allowed_channel_ids and (self._central_channel_ids or self._local_channel_ids):
            self._log(
                "連携設定注意: DISCORD_CENTRAL/LOCAL_CHANNEL_IDS が設定されているため、"
                "DISCORD_ALLOWED_CHANNEL_IDS は受信判定に使用しません"
            )

        if self._central_channel_ids and self._local_channel_ids and (self._central_channel_ids & self._local_channel_ids):
            overlap = ",".join(sorted(self._central_channel_ids & self._local_channel_ids))
            self._log(f"注意: 中央/地方チャンネル設定が重複しています: {overlap}")
        try:
            self._replay_pre_race_candidates_from_history()
        finally:
            self._startup_history_replay_active = False
        self._log("監視開始")
        return True

    def stop(self, join_timeout_sec: float = 5.0) -> None:
        self._stop_event.set()

        discord = self._discord
        if discord:
            discord.stop(timeout_sec=max(2.0, float(join_timeout_sec)))
        self._discord = None

        for target in self.TARGETS:
            worker = self._worker_threads.get(target)
            if worker and worker.is_alive():
                worker.join(timeout=max(1.0, float(join_timeout_sec)))
            self._worker_threads[target] = None

        for target in self.TARGETS:
            with self._ipat_locks[target]:
                executor = self._executors.get(target)
                if executor:
                    try:
                        executor.close()
                    except Exception:
                        logger.exception("failed to close iPAT executor (%s)", target)
                    self._executors[target] = None

        with self._lock:
            self._running = False
        self._next_central_keepalive_monotonic = 0.0
        self._next_local_keepalive_monotonic = 0.0
        self._next_central_schedule_retry_monotonic = 0.0
        self._central_candidate_pause_active = False
        self._central_candidate_pause_date = ""
        self._central_candidate_control_actions = {}
        self._startup_history_replay_active = False
        self._log("監視停止")

    def _start_discord_gateway(self) -> None:
        token = str(getattr(secrets_local, "DISCORD_BOT_TOKEN", "") or "").strip()
        if (not token) or ("PASTE_DISCORD_BOT_TOKEN_HERE" in token):
            raise DiscordClientError("`secrets_local.py` の DISCORD_BOT_TOKEN を設定してください")

        self._discord = DiscordGatewayClient(
            bot_token=token,
            allowed_channel_ids=self._discord_allowed_channel_ids,
            allowed_guild_ids=self._discord_allowed_guild_ids,
        )
        self._discord.start(
            on_message=self._on_discord_message,
            on_error=self._on_discord_error,
            on_status=self._on_discord_status,
        )
        self._last_discord_start_monotonic = time.monotonic()

    def _ensure_discord_alive(self) -> None:
        if self._stop_event.is_set():
            return
        discord = self._discord
        if discord is not None and discord.running:
            return

        now_mono = time.monotonic()
        if (now_mono - self._last_discord_start_monotonic) < 5.0:
            return

        self._log("連携再接続を試行します")
        try:
            self._start_discord_gateway()
            self._log("連携再接続を開始しました")
        except Exception:
            self._last_discord_start_monotonic = now_mono
            self._log("連携再接続失敗: しばらく待って再試行します")

    def _log(self, text: str) -> None:
        self.log_func(f"[{_now()}] {text}")

    def _target_label(self, target: str) -> str:
        return self.TARGET_LABELS.get(str(target or "").strip().lower(), "中央")

    def _log_target(self, target: str, text: str) -> None:
        del target
        self._log(text)

    def _exception_detail_text(self, exc: BaseException | str | None) -> str:
        if exc is None:
            return ""
        if isinstance(exc, BaseException):
            text = str(exc or "").strip()
            return text or repr(exc)
        return str(exc or "").strip()

    def _log_failure_detail(self, target: str, prefix: str, exc: BaseException | str | None) -> None:
        detail = self._exception_detail_text(exc)
        if detail:
            self._log_target(target, f"{prefix}: {detail}")

    def _current_date8(self) -> str:
        return datetime.now().strftime("%Y%m%d")

    def _is_target_enabled(self, target: str) -> bool:
        entry = self.settings.entry
        t = str(target or "").strip().lower()
        if t == self.TARGET_LOCAL:
            return bool(getattr(entry, "enable_local", False))
        return bool(getattr(entry, "enable_central", True))

    def _is_target_selectors_configured(self, target: str) -> bool:
        selectors = load_internal_selectors(target=target)
        return bool(selectors.get("__configured__", True))

    def _race_tag(self, payload: Dict[str, Any]) -> str:
        race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
        return f"{race.get('date', '-')}_{race.get('venue_name', '-')}_{int(race.get('race_num', 0) or 0):02d}R"

    def _candidate_tag(self, candidate: Dict[str, Any]) -> str:
        date8 = str(candidate.get("date", "") or "-")
        venue = str(candidate.get("venue_name", "") or "-")
        race_num = int(candidate.get("race_num", 0) or 0)
        return f"{date8}_{venue}_{race_num:02d}R"

    def _resolve_payload_strategy_code(self, payload: Dict[str, Any]) -> str:
        strategy = payload.get("strategy") if isinstance(payload.get("strategy"), dict) else {}
        code = normalize_strategy_code(
            payload.get("strategy_code", "") or strategy.get("code", "") or "",
            default="",
        )
        if code:
            return code
        name = str(payload.get("strategy_name", "") or strategy.get("name", "") or "").strip()
        return normalize_strategy_code(name, default="")

    def _resolve_payload_tool_slot(self, payload: Dict[str, Any]) -> str:
        slot = infer_tool_slot_from_payload(payload)
        if slot:
            return slot
        return ""

    def _accepts_payload_strategy(self, payload: Dict[str, Any]) -> tuple[bool, str]:
        del payload
        return True, ""

    def _expected_central_sport(self) -> str:
        login_url = str(getattr(self.settings.ipat, "login_url", "") or "").strip().lower()
        if ("ib.mbrace.or.jp" in login_url) or ("boatrace" in login_url):
            return "kyoutei"
        if "keirin.jp" in login_url:
            return "keirin"
        return ""

    def _payload_venue_names(self, payload: Dict[str, Any]) -> list[str]:
        venues: list[str] = []
        race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
        race_venue = str(race.get("venue_name", "") or "").strip()
        if race_venue:
            venues.append(race_venue)
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            venue = str(item.get("venue_name", "") or "").strip()
            if venue:
                venues.append(venue)
        return venues

    def _payload_market_names(self, payload: Dict[str, Any]) -> list[str]:
        markets: list[str] = []
        tickets = payload.get("tickets") if isinstance(payload.get("tickets"), list) else []
        for item in tickets:
            if not isinstance(item, dict):
                continue
            market = str(item.get("market", "") or "").strip()
            if market:
                markets.append(market)
        return markets

    def _enabled_bet_types(self) -> list[str]:
        """エディションの上限内で、ユーザーが選択した券種（正規化済み）。"""
        raw = getattr(self.settings.entry, "enabled_bet_types", None)
        return clamp_enabled_bet_types(raw if raw is not None else [])

    def _accepts_payload_bet_types(self, payload: Dict[str, Any]) -> tuple[bool, str]:
        """選択券種のチケットだけを残す。残ればpayloadを書き換えてTrue。

        - 選択0件 → すべて見送り。
        - 券種情報を持たないpayload（候補のみ等）は素通し。
        - 取り扱い対象(2連複/3連複/3連単)のチケットが1つも選択券種に該当しなければ見送り。
        """
        enabled = set(self._enabled_bet_types())
        tickets = payload.get("tickets") if isinstance(payload.get("tickets"), list) else []
        if not tickets:
            return True, ""
        # この商品ラインで扱う券種のチケットだけを対象に判定する。
        managed = [t for t in tickets if isinstance(t, dict) and normalize_bet_type(t.get("market", ""))]
        if not managed:
            return True, ""
        if not enabled:
            return False, "選択券種が0件です"
        kept = [t for t in managed if normalize_bet_type(t.get("market", "")) in enabled]
        if not kept:
            return False, f"選択券種外(有効={'/'.join(sorted(enabled)) or 'なし'})"
        payload["tickets"] = kept
        return True, ""

    def _enabled_dayparts(self) -> list[str]:
        raw = getattr(self.settings.entry, "enabled_dayparts", None)
        return clamp_enabled_dayparts(raw if raw is not None else [])

    def _payload_daypart(self, payload: Dict[str, Any]) -> str:
        """通知の日区分（モーニング/日中/ナイター）。payload明示 → tool_slot推定の順。"""
        direct = normalize_daypart_label(payload.get("daypart"))
        if direct:
            return direct
        race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
        direct = normalize_daypart_label(race.get("daypart"))
        if direct:
            return direct
        slot = str(infer_tool_slot_from_payload(payload) or "")
        # tool_slot は midnight を使うが、clearism ラインの第3枠はナイター。
        return {"morning": "モーニング", "daytime": "日中", "midnight": "ナイター", "night": "ナイター"}.get(slot, "")

    def _accepts_payload_dayparts(self, payload: Dict[str, Any]) -> tuple[bool, str]:
        """clearismライン: 選択した日区分の通知だけ通す。"""
        enabled = set(self._enabled_dayparts())
        if not enabled:
            return False, "選択日区分が0件です"
        dp = self._payload_daypart(payload)
        if not dp:
            # 日区分不明の通知は安全側で通す（従来挙動）。
            return True, ""
        if dp not in enabled:
            return False, f"選択日区分外({dp} / 有効={'/'.join(enabled)})"
        return True, ""

    def _accepts_payload_selection(self, payload: Dict[str, Any]) -> tuple[bool, str]:
        """製品ラインの軸に応じてフィルタする（aqua=券種 / clearism=日区分）。"""
        if line_cap_axis() == "daypart":
            return self._accepts_payload_dayparts(payload)
        return self._accepts_payload_bet_types(payload)

    def _infer_payload_sport(self, payload: Dict[str, Any]) -> str:
        provider = str(payload.get("provider", "") or "").strip().lower()
        source = str(payload.get("source", "") or "").strip().lower()
        joined = f"{provider} {source}"
        if any(token in joined for token in ("kyoutei", "競艇", "boatrace", "mbrace")):
            return "kyoutei"
        if any(token in joined for token in ("keirin", "競輪", "keirinjp", "kdreams")):
            return "keirin"

        venues = self._payload_venue_names(payload)
        if venues and all(venue in KYOUTEI_VENUE_NAMES for venue in venues):
            return "kyoutei"
        if venues and all(venue in KEIRIN_VENUE_NAMES for venue in venues):
            return "keirin"

        markets = self._payload_market_names(payload)
        has_kyoutei_market = any(market in KYOUTEI_MARKET_NAMES for market in markets)
        has_keirin_market = any(market in KEIRIN_MARKET_NAMES for market in markets)
        if has_kyoutei_market and not has_keirin_market:
            return "kyoutei"
        if has_keirin_market and not has_kyoutei_market:
            return "keirin"
        return ""

    def _accepts_payload_sport(self, target: str, payload: Dict[str, Any]) -> tuple[bool, str]:
        if str(target or "").strip().lower() != self.TARGET_CENTRAL:
            return True, ""
        expected = self._expected_central_sport()
        if not expected:
            return True, ""
        actual = self._infer_payload_sport(payload)
        if actual == expected:
            return True, ""
        if actual:
            return False, f"競技不一致: {actual}"
        return False, "競技判定不可"

    def _on_pre_race_candidates(self, target: str, payload: Dict[str, Any]) -> None:
        date8 = str(payload.get("date", "") or "-").strip() or "-"
        odds_provider = str(payload.get("odds_provider", "") or "").strip() or "-"
        advisory = str(payload.get("advisory", "") or "").strip()
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        candidate_count = self._payload_candidate_count(payload)
        slot = self._resolve_payload_tool_slot(payload)
        slot_note = f" [{tool_slot_label(slot)}]" if slot else ""
        self._log_target(
            target,
            f"事前候補受信{slot_note}: date={date8} races={candidate_count} odds={odds_provider}",
        )
        if advisory:
            self._log_target(target, f"候補注記: {advisory}")
        self._request_candidate_browser_control(target, payload, candidate_count=candidate_count)
        if candidate_count <= 0:
            self._log_target(target, "候補なし")
            return
        preview_limit = 50
        for idx, row in enumerate(candidates, start=1):
            if not isinstance(row, dict):
                continue
            if idx > preview_limit:
                break
            venue = str(row.get("venue_name", "") or "-")
            race_num = int(row.get("race_num", 0) or 0)
            start_time = str(row.get("start_time", "") or "").strip()
            if start_time:
                self._log_target(target, f"候補: {venue} {race_num}R {start_time}")
            else:
                self._log_target(target, f"候補: {venue} {race_num}R")
        if len(candidates) > preview_limit:
            self._log_target(target, f"候補: ... 省略 {len(candidates) - preview_limit}件")

    def _replay_pre_race_candidates_from_history(self) -> None:
        """起動時に直近の候補通知（pre_race_candidates）だけ再取得する。"""
        discord = self._discord
        if discord is None:
            return

        channel_ids: list[str]
        if self._central_channel_ids or self._local_channel_ids:
            channel_ids = sorted(self._central_channel_ids | self._local_channel_ids)
        else:
            channel_ids = sorted(self._discord_allowed_channel_ids)
        if not channel_ids:
            return

        today = datetime.now().strftime("%Y%m%d")
        replay_count = 0
        seen_message_ids: set[str] = set()
        for cid in channel_ids:
            messages = discord.fetch_recent_messages(
                cid,
                limit=int(self.STARTUP_HISTORY_LIMIT),
                timeout_sec=10.0,
            )
            # 古い順に処理
            try:
                messages.sort(key=lambda x: int(str(x.get("id", "0") or "0")))
            except Exception:
                pass
            for msg in messages:
                msg_id = str(msg.get("id", "") or "").strip()
                if msg_id and msg_id in seen_message_ids:
                    continue
                if msg_id:
                    seen_message_ids.add(msg_id)

                payloads = extract_payloads_from_text(str(msg.get("content", "") or ""))
                if not payloads:
                    continue
                for payload in payloads:
                    if not isinstance(payload, dict):
                        continue
                    if str(payload.get("message_type", "") or "").strip().lower() != "pre_race_candidates":
                        continue
                    payload_date = str(payload.get("date", "") or "").strip()
                    if payload_date and payload_date != today:
                        continue
                    target, reason = self._resolve_payload_target(msg)
                    if target is None:
                        self._log(f"起動時候補見送り: {reason} ({payload_date or '-'})")
                        continue
                    if not self._is_target_enabled(target):
                        continue
                    accepted_sport, reason_sport = self._accepts_payload_sport(target, payload)
                    if not accepted_sport:
                        self._log_target(target, f"起動時候補見送り: {reason_sport} ({payload_date or '-'})")
                        continue
                    accepted, reason_strategy = self._accepts_payload_strategy(payload)
                    if not accepted:
                        self._log_target(target, f"起動時候補見送り: {reason_strategy} ({payload_date or '-'})")
                        continue
                    self._on_pre_race_candidates(target, payload)
                    replay_count += 1

        if replay_count > 0:
            self._log(f"起動時候補再取得: payload={replay_count}件")

    def _resolve_payload_target(self, message: Dict[str, Any]) -> tuple[str | None, str]:
        channel_id = str(message.get("channel_id", "") or "").strip()
        parent_channel_id = str(message.get("parent_channel_id", "") or "").strip()
        matched: set[str] = set()
        for cid in [channel_id, parent_channel_id]:
            if not cid:
                continue
            if cid in self._central_channel_ids:
                matched.add(self.TARGET_CENTRAL)
            if cid in self._local_channel_ids:
                matched.add(self.TARGET_LOCAL)

        if len(matched) == 1:
            return next(iter(matched)), ""
        if len(matched) >= 2:
            return None, "チャンネルIDが中央/地方の両方に割り当てられています"

        # 新方式の割当がある場合は、未割当チャンネルを見送りにする。
        if self._central_channel_ids or self._local_channel_ids:
            return None, "チャンネルIDが中央/地方の割り当てに存在しません"
        return self.TARGET_CENTRAL, ""

    def _payload_requested_hour(self, payload: Dict[str, Any]) -> int | None:
        text = str(payload.get("requested_at", "") or "").strip()
        if not text:
            return None
        try:
            return int(datetime.fromisoformat(text).hour)
        except Exception:
            return None

    def _payload_candidate_count(self, payload: Dict[str, Any]) -> int:
        raw = payload.get("candidate_count")
        if raw is not None:
            try:
                text = str(raw).strip()
                if text:
                    return max(0, int(text))
            except Exception:
                pass
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        return len(candidates)

    def _is_central_browser_automation_mode(self) -> bool:
        login_url = str(getattr(self.settings.ipat, "login_url", "") or "").strip().lower()
        if "keirin.jp" in login_url:
            return True
        if ("ib.mbrace.or.jp" in login_url) or ("boatrace" in login_url):
            return True
        return False

    def _is_keirin_central_browser_control_enabled(self, target: str) -> bool:
        if target != self.TARGET_CENTRAL:
            return False
        if not self._is_target_enabled(self.TARGET_CENTRAL):
            return False
        if self.settings.entry.dry_run:
            return False
        return self._is_central_browser_automation_mode()

    def _clear_stale_central_candidate_pause(self, *, today: str = "") -> None:
        if not self._central_candidate_pause_active:
            return
        current = str(today or self._current_date8() or "").strip()
        if self._central_candidate_pause_date and self._central_candidate_pause_date != current:
            self._central_candidate_pause_active = False
            self._central_candidate_pause_date = ""

    def _clear_stale_central_candidate_control_actions(self, *, today: str = "") -> None:
        current = str(today or self._current_date8() or "").strip()
        if not current:
            self._central_candidate_control_actions = {}
            return
        self._central_candidate_control_actions = {
            key: action
            for key, action in self._central_candidate_control_actions.items()
            if key.startswith(f"{current}:")
        }

    def _close_executor(self, target: str) -> bool:
        closed = False
        with self._ipat_locks[target]:
            executor = self._executors.get(target)
            if executor is None:
                return False
            try:
                executor.close()
            except Exception:
                logger.exception("failed to close executor (%s)", target)
                raise
            self._executors[target] = None
            closed = True
        if target == self.TARGET_CENTRAL:
            self._next_central_keepalive_monotonic = 0.0
            self._next_central_schedule_retry_monotonic = 0.0
        elif target == self.TARGET_LOCAL:
            self._next_local_keepalive_monotonic = 0.0
        return closed

    def _pause_central_browser_by_candidates(self, *, date8: str, slot: str = "") -> None:
        self._central_candidate_pause_active = True
        self._central_candidate_pause_date = str(date8 or self._current_date8() or "").strip()
        slot_name = tool_slot_label(slot) or slot or "候補"
        slot_hour = tool_slot_hour(slot)
        time_note = f"{int(slot_hour):02d}時" if slot_hour is not None else "候補通知時"
        with self._ipat_locks[self.TARGET_CENTRAL]:
            executor = self._executors.get(self.TARGET_CENTRAL)
        if executor is None:
            self._log_target(self.TARGET_CENTRAL, f"候補連動: {time_note}{slot_name}候補なしのためブラウザ未起動状態を維持します")
        else:
            self._log_target(self.TARGET_CENTRAL, f"候補連動: {time_note}{slot_name}候補なしのためブラウザは保持し、自動起動のみ停止します")

    def _restart_central_browser_by_candidates(self, *, date8: str, slot: str = "") -> None:
        self._central_candidate_pause_active = False
        self._central_candidate_pause_date = str(date8 or self._current_date8() or "").strip()
        slot_name = tool_slot_label(slot) or slot or "候補"
        slot_hour = tool_slot_hour(slot)
        time_note = f"{int(slot_hour):02d}時" if slot_hour is not None else "候補通知時"
        if not self._is_central_schedule_active_now():
            self._log_target(
                self.TARGET_CENTRAL,
                f"候補連動: {time_note}{slot_name}候補ありですが、起動時間外のためブラウザを起動しません",
            )
            return
        had_executor = False
        try:
            had_executor = self._close_executor(self.TARGET_CENTRAL)
        except Exception:
            self._log_target(self.TARGET_CENTRAL, f"候補連動: {slot_name}候補でブラウザ再起動前の停止に失敗しました")
            return

        try:
            with self._ipat_locks[self.TARGET_CENTRAL]:
                executor = self._get_executor(self.TARGET_CENTRAL)
                result = executor.prepare_vote_menu()
            self._next_central_schedule_retry_monotonic = 0.0
            self._next_central_keepalive_due()
        except IpatEntryError as exc:
            self._next_central_schedule_retry_monotonic = time.monotonic() + float(self.CENTRAL_SCHEDULE_RETRY_SEC)
            self._log_target(self.TARGET_CENTRAL, f"候補連動: {time_note}{slot_name}候補ありでブラウザ起動に失敗しました")
            self._log_failure_detail(self.TARGET_CENTRAL, "候補連動詳細", exc)
            return
        except Exception as exc:
            logger.exception("candidate-driven central restart error")
            self._next_central_schedule_retry_monotonic = time.monotonic() + float(self.CENTRAL_SCHEDULE_RETRY_SEC)
            self._log_target(self.TARGET_CENTRAL, f"候補連動: {time_note}{slot_name}候補ありでブラウザ起動中に例外が発生しました")
            self._log_failure_detail(self.TARGET_CENTRAL, "候補連動詳細", exc)
            return

        if bool(result.get("ok")):
            if had_executor:
                self._log_target(self.TARGET_CENTRAL, f"候補連動: {time_note}{slot_name}候補ありのためブラウザを起動し直しました")
            else:
                self._log_target(self.TARGET_CENTRAL, f"候補連動: {time_note}{slot_name}候補ありのためブラウザを起動しました")

    def _candidate_browser_control_action(self, target: str, payload: Dict[str, Any], *, candidate_count: int) -> str | None:
        if not self._is_keirin_central_browser_control_enabled(target):
            return None
        slot = self._resolve_payload_tool_slot(payload)
        if not slot:
            return None
        requested_hour = self._payload_requested_hour(payload)
        slot_hour = tool_slot_hour(slot)
        if requested_hour is None or slot_hour is None or requested_hour != slot_hour:
            return None
        if slot == "morning":
            return "pause" if candidate_count <= 0 else None
        if slot == "daytime":
            return "restart" if candidate_count > 0 else "pause"
        if slot == "midnight":
            return "restart" if candidate_count > 0 else None
        return None

    def _maybe_control_browser_by_candidates(self, target: str, payload: Dict[str, Any], *, candidate_count: int) -> None:
        action = self._candidate_browser_control_action(target, payload, candidate_count=candidate_count)
        if not action:
            return
        date8 = str(payload.get("date", "") or self._current_date8()).strip() or self._current_date8()
        self._clear_stale_central_candidate_pause(today=date8)
        self._clear_stale_central_candidate_control_actions(today=date8)
        slot = self._resolve_payload_tool_slot(payload)
        action_key = f"{date8}:{slot}"
        if self._central_candidate_control_actions.get(action_key) == action:
            return
        if action == "pause":
            self._pause_central_browser_by_candidates(date8=date8, slot=slot)
        elif action == "restart":
            self._restart_central_browser_by_candidates(date8=date8, slot=slot)
        self._central_candidate_control_actions[action_key] = action

    def _request_candidate_browser_control(self, target: str, payload: Dict[str, Any], *, candidate_count: int) -> None:
        if not self._candidate_browser_control_action(target, payload, candidate_count=candidate_count):
            return
        self._queues[target].put(
            (
                self.CMD_CANDIDATE_CONTROL,
                {
                    "payload": payload,
                    "candidate_count": int(candidate_count),
                },
            )
        )

    def _handle_candidate_browser_control(self, target: str, payload: Dict[str, Any], *, candidate_count: int) -> None:
        self._maybe_control_browser_by_candidates(target, payload, candidate_count=int(candidate_count))

    def _write_runtime_file(self, payload: Dict, tickets: List[Dict], result: Dict, target: str) -> Path:
        race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
        date8 = str(race.get("date", "") or datetime.now().strftime("%Y%m%d"))
        race_no = int(race.get("race_num", 0) or 0)
        venue = str(race.get("venue_name", "") or "UNK")
        out_dir = Path("runtime_logs") / date8
        out_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{datetime.now().strftime('%H%M%S')}_{self._target_label(target)}_{venue}_{race_no:02d}.json"
        path = out_dir / file_name
        path.write_text(
            json.dumps(
                {
                    "payload": payload,
                    "entry_tickets": tickets,
                    "entry_result": result,
                    "target": target,
                    "saved_at": _now(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def _build_preview_text(self, payload: Dict, tickets: List[Dict], total_yen: int, race_tag: str) -> str:
        strategy_name = str(payload.get("strategy_name", "") or "").strip()
        strategy_code = self._resolve_payload_strategy_code(payload)
        tool_slot = self._resolve_payload_tool_slot(payload)
        strategy_note = ""
        if strategy_name and strategy_code:
            strategy_note = f" [{strategy_name}/{strategy_code}]"
        elif strategy_name:
            strategy_note = f" [{strategy_name}]"
        elif strategy_code:
            strategy_note = f" [{strategy_code}]"
        elif tool_slot:
            strategy_note = f" [{tool_slot_label(tool_slot) or tool_slot}]"

        lines = [f"プレビュー: {race_tag}{strategy_note} {len(tickets)}点 合計{int(total_yen):,}円", "買い目:"]
        for idx, row in enumerate(tickets, start=1):
            payout_text = _format_expected_payout_text(row)
            lines.append(
                f"{idx:02d}. {str(row.get('market', '') or '')} "
                f"{str(row.get('combo', '') or '')} {int(row.get('bet_yen', 0) or 0):,}円 "
                f"想定払い戻し:{payout_text}"
            )
        return "\n".join(lines)

    def _build_post_entry_text(self, race_tag: str, tickets: List[Dict], total_yen: int, status: str) -> str:
        lines = [
            f"発注後内訳: {race_tag} status={status} {len(tickets)}点 合計想定金額{int(total_yen):,}円",
            "買い目(確定):",
        ]
        for idx, row in enumerate(tickets, start=1):
            odds_text = _format_odds_text(row)
            payout_text = _format_expected_payout_text(row)
            lines.append(
                f"{idx:02d}. {str(row.get('market', '') or '')} "
                f"{str(row.get('combo', '') or '')} {odds_text} {int(row.get('bet_yen', 0) or 0):,}円 "
                f"想定払い戻し:{payout_text}"
            )
        return "\n".join(lines)

    def _on_discord_status(self, text: str) -> None:
        msg = str(text or "")
        lowered = msg.lower()
        if msg.startswith("raw_message:") or msg.startswith("drop("):
            self._log(f"連携デバッグ: {msg}")
            return
        if "gateway接続完了" in lowered or "gateway再接続完了" in lowered or "connected" in lowered:
            self._log("連携接続完了")
            self._log(f"連携デバッグ: {msg}")
        elif "gateway切断" in lowered or "disconnect" in lowered:
            self._log("連携切断")
            self._log(f"連携デバッグ: {msg}")

    def _on_discord_error(self, text: str) -> None:
        del text
        self._log("連携エラー: 接続エラーが発生しました。自動再接続を待機します")

    def _on_discord_message(self, message: Dict[str, Any]) -> None:
        if self._stop_event.is_set():
            return
        content = str(message.get("content", "") or "")
        payloads = extract_payloads_from_text(content)
        if not payloads:
            if self._no_payload_debug_count < int(self.NO_PAYLOAD_DEBUG_LIMIT):
                self._no_payload_debug_count += 1
                self._log(
                    "受信デバッグ: payload抽出0件 "
                    f"channel={str(message.get('channel_id', '') or '') or '-'} "
                    f"parent={str(message.get('parent_channel_id', '') or '') or '-'} "
                    f"len={len(content)}"
                )
            return

        self._log(f"指示受信: payload={len(payloads)}件")
        for payload in payloads:
            payload_obj = payload if isinstance(payload, dict) else {}
            message_type = str(payload_obj.get("message_type", "entry_tickets") or "entry_tickets").strip().lower()
            if message_type == "pre_race_candidates":
                candidates = payload_obj.get("candidates") if isinstance(payload_obj.get("candidates"), list) else []
                race_tag = self._candidate_tag(candidates[0]) if candidates else f"{str(payload_obj.get('date', '') or '-')}_candidates"
            else:
                race_tag = self._race_tag(payload_obj)
            target, reason = self._resolve_payload_target(message)
            if target is None:
                self._log(f"見送り: {reason} ({race_tag})")
                continue
            if not self._is_target_enabled(target):
                self._log_target(target, f"見送り: 対象が無効設定です ({race_tag})")
                continue
            accepted_sport, reason_sport = self._accepts_payload_sport(target, payload_obj)
            if not accepted_sport:
                self._log_target(target, f"見送り: {reason_sport} ({race_tag})")
                continue
            if message_type == "pre_race_candidates":
                accepted, reason_strategy = self._accepts_payload_strategy(payload_obj)
                if not accepted:
                    self._log_target(target, f"見送り: {reason_strategy} ({race_tag})")
                    continue
                self._on_pre_race_candidates(target, payload_obj)
                continue
            accepted, reason_strategy = self._accepts_payload_strategy(payload_obj)
            if not accepted:
                self._log_target(target, f"見送り: {reason_strategy} ({race_tag})")
                continue
            accepted_bt, reason_bt = self._accepts_payload_selection(payload_obj)
            if not accepted_bt:
                self._log_target(target, f"見送り: {reason_bt} ({race_tag})")
                continue
            envelope = {
                "payload": payload_obj,
                "channel_id": str(message.get("channel_id", "") or ""),
                "parent_channel_id": str(message.get("parent_channel_id", "") or ""),
            }
            self._queues[target].put((self.CMD_PAYLOAD, envelope))

    def _get_executor(self, target: str) -> IpatPlaywrightExecutor:
        normalized = self.TARGET_LOCAL if str(target or "").strip().lower() == self.TARGET_LOCAL else self.TARGET_CENTRAL
        if self._executors[normalized] is None:
            self._executors[normalized] = ThreadBoundIpatPlaywrightExecutor(
                self.settings,
                event_logger=lambda text, t=normalized: self._log_target(t, text),
                target=normalized,
            )
        return self._executors[normalized]

    def prepare_ipat(self) -> bool:
        # 旧互換: 呼び出し元は真偽値を期待するため True を返す。
        self.request_prepare_ipat()
        return True

    def request_prepare_ipat(self) -> None:
        if self._stop_event.is_set():
            return
        for target in self.TARGETS:
            if self._is_target_enabled(target):
                self._queues[target].put((self.CMD_PREPARE, None))

    def _handle_prepare_ipat(self, target: str) -> None:
        if self.settings.entry.dry_run:
            return
        if not self._is_target_enabled(target):
            return
        if target == self.TARGET_CENTRAL and not self._is_central_schedule_active_now():
            self._close_executor_by_schedule_if_needed()
            self._log_target(target, "見送り: 起動時間外のため事前準備を実行しません")
            return
        if (target == self.TARGET_LOCAL) and (not self._is_target_selectors_configured(target)):
            self._log_target(target, "見送り: 地方セレクタ未設定のため事前準備を実行しません")
            return
        with self._ipat_locks[target]:
            executor = self._get_executor(target)
            result = executor.prepare_vote_menu()
        if bool(result.get("ok")):
            self._log_target(target, "iPAT事前準備が完了しました")

    def _next_local_keepalive_due(self) -> None:
        self._next_local_keepalive_monotonic = time.monotonic() + float(self.LOCAL_KEEPALIVE_INTERVAL_SEC)

    def _next_central_keepalive_due(self) -> None:
        self._next_central_keepalive_monotonic = time.monotonic() + float(self.CENTRAL_KEEPALIVE_INTERVAL_SEC)

    def _schedule_central_window_minutes(self) -> tuple[bool, int, int]:
        entry = self.settings.entry
        enabled = bool(getattr(entry, "central_schedule_enabled", True))
        open_text = str(
            getattr(entry, "central_schedule_open_time", DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME)
            or DEFAULT_CENTRAL_SCHEDULE_OPEN_TIME
        ).strip().replace("：", ":")
        close_text = str(
            getattr(entry, "central_schedule_close_time", DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME)
            or DEFAULT_CENTRAL_SCHEDULE_CLOSE_TIME
        ).strip().replace("：", ":")
        open_min = self._parse_hhmm_to_minutes(open_text, 10 * 60)
        close_min = self._parse_hhmm_to_minutes(close_text, 21 * 60)
        return enabled, open_min, close_min

    def _parse_hhmm_to_minutes(self, text: str, default: int) -> int:
        value = str(text or "").strip()
        parts = value.split(":")
        if len(parts) != 2:
            return int(default)
        hour = -1
        minute = -1
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except Exception:
            return int(default)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return int(default)
        return int(hour * 60 + minute)

    def _is_in_schedule_window(self, now_minutes: int, open_minutes: int, close_minutes: int) -> bool:
        cur = int(now_minutes)
        open_m = int(open_minutes)
        close_m = int(close_minutes)
        if open_m == close_m:
            return False
        if open_m < close_m:
            return open_m <= cur < close_m
        # 日跨ぎ（例: 23:00-08:00）
        return (cur >= open_m) or (cur < close_m)

    def _central_schedule_now(self) -> datetime:
        return datetime.now()

    def _is_central_schedule_active_now(self) -> bool:
        enabled, open_min, close_min = self._schedule_central_window_minutes()
        if not enabled:
            return True
        now = self._central_schedule_now()
        now_min = int(now.hour * 60 + now.minute)
        return self._is_in_schedule_window(now_min, open_min, close_min)

    def _close_executor_by_schedule_if_needed(self) -> bool:
        with self._ipat_locks[self.TARGET_CENTRAL]:
            executor = self._executors.get(self.TARGET_CENTRAL)
            if executor is None:
                return False
            try:
                executor.close()
            except Exception:
                logger.exception("failed to close central executor by schedule")
            self._executors[self.TARGET_CENTRAL] = None
        self._next_central_keepalive_monotonic = 0.0
        self._next_central_schedule_retry_monotonic = 0.0
        return True

    def _maybe_schedule_central_session(self) -> None:
        if self._stop_event.is_set():
            return
        if not self._is_target_enabled(self.TARGET_CENTRAL):
            return
        if self.settings.entry.dry_run:
            return

        if not self._is_central_browser_automation_mode():
            return

        enabled, open_min, close_min = self._schedule_central_window_minutes()
        if not enabled:
            return
        if self._startup_history_replay_active:
            return

        now = self._central_schedule_now()
        self._clear_stale_central_candidate_pause(today=now.strftime("%Y%m%d"))
        self._clear_stale_central_candidate_control_actions(today=now.strftime("%Y%m%d"))
        now_min = int(now.hour * 60 + now.minute)
        should_run = self._is_in_schedule_window(now_min, open_min, close_min)

        if not should_run:
            if self._close_executor_by_schedule_if_needed():
                self._log_target(self.TARGET_CENTRAL, "待機スケジュール: 起動時間外のためブラウザを停止しました")
            return

        with self._ipat_locks[self.TARGET_CENTRAL]:
            executor = self._executors.get(self.TARGET_CENTRAL)
        if executor is not None:
            return
        if self._central_candidate_pause_active:
            return

        now_mono = time.monotonic()
        if now_mono < float(self._next_central_schedule_retry_monotonic):
            return

        try:
            with self._ipat_locks[self.TARGET_CENTRAL]:
                executor = self._get_executor(self.TARGET_CENTRAL)
                result = executor.prepare_vote_menu()
            if bool(result.get("ok")):
                self._log_target(self.TARGET_CENTRAL, "待機スケジュール: 開始時刻帯のためブラウザを起動しました")
            self._next_central_schedule_retry_monotonic = 0.0
            self._next_central_keepalive_due()
        except IpatEntryError as exc:
            self._next_central_schedule_retry_monotonic = time.monotonic() + float(self.CENTRAL_SCHEDULE_RETRY_SEC)
            self._log_target(self.TARGET_CENTRAL, "待機スケジュール: 自動起動に失敗しました")
            self._log_failure_detail(self.TARGET_CENTRAL, "待機スケジュール詳細", exc)
        except Exception as exc:  # pragma: no cover
            logger.exception("central schedule start error")
            self._next_central_schedule_retry_monotonic = time.monotonic() + float(self.CENTRAL_SCHEDULE_RETRY_SEC)
            self._log_target(self.TARGET_CENTRAL, "待機スケジュール: 自動起動で例外が発生しました")
            self._log_failure_detail(self.TARGET_CENTRAL, "待機スケジュール詳細", exc)

    def _schedule_keepalive_due(self, target: str) -> None:
        if target == self.TARGET_LOCAL:
            self._next_local_keepalive_due()
        elif target == self.TARGET_CENTRAL:
            self._next_central_keepalive_due()

    def _maybe_keepalive_central(self) -> None:
        if self._stop_event.is_set():
            return
        if not self._is_target_enabled(self.TARGET_CENTRAL):
            return
        if self.settings.entry.dry_run:
            return

        now = time.monotonic()
        if self._next_central_keepalive_monotonic <= 0:
            self._next_central_keepalive_due()
            return
        if now < self._next_central_keepalive_monotonic:
            return

        self._next_central_keepalive_due()
        try:
            with self._ipat_locks[self.TARGET_CENTRAL]:
                executor = self._executors.get(self.TARGET_CENTRAL)
                if executor is None:
                    return
                result = executor.refresh_central_info()
            status = str(result.get("status", "") or "")
            if status == "refreshed":
                self._log_target(self.TARGET_CENTRAL, "待機維持: 10分経過のため中央投票サイトを更新しました")
            elif status.startswith("skip_"):
                self._log_target(self.TARGET_CENTRAL, "待機維持: 対応外モードのため更新をスキップしました")
        except IpatEntryError:
            self._log_target(self.TARGET_CENTRAL, "待機維持: 中央投票サイト更新に失敗しました")
        except Exception:  # pragma: no cover
            logger.exception("central keepalive error")
            self._log_target(self.TARGET_CENTRAL, "待機維持: 中央投票サイト更新で例外が発生しました")

    def _maybe_keepalive_local(self) -> None:
        if self._stop_event.is_set():
            return
        if not self._is_target_enabled(self.TARGET_LOCAL):
            return
        if self.settings.entry.dry_run:
            return

        now = time.monotonic()
        if self._next_local_keepalive_monotonic <= 0:
            self._next_local_keepalive_due()
            return
        if now < self._next_local_keepalive_monotonic:
            return

        self._next_local_keepalive_due()
        try:
            with self._ipat_locks[self.TARGET_LOCAL]:
                executor = self._executors.get(self.TARGET_LOCAL)
                if executor is None:
                    self._log_target(self.TARGET_LOCAL, "待機維持デバッグ: 実行インスタンス未初期化のため情報更新をスキップしました")
                    return
                result = executor.refresh_local_info()
            status = str(result.get("status", "") or "")
            if status == "refreshed":
                self._log_target(self.TARGET_LOCAL, "待機維持: 10分経過のため情報更新を実行しました")
            elif status == "ready_no_refresh_button":
                debug_before = result.get("debug_before") if isinstance(result, dict) else None
                if isinstance(debug_before, dict):
                    self._log_target(
                        self.TARGET_LOCAL,
                        "待機維持デバッグ: 情報更新ボタン未検出 "
                        f"(url={debug_before.get('url', '-')}, "
                        f"popup={bool(debug_before.get('popup_visible'))}, "
                        f"mail_notice={bool(debug_before.get('mail_notice_visible'))})",
                    )
                else:
                    self._log_target(self.TARGET_LOCAL, "待機維持デバッグ: 情報更新ボタン未検出")
        except IpatEntryError:
            self._log_target(self.TARGET_LOCAL, "待機維持: 情報更新に失敗しました")
        except Exception:  # pragma: no cover
            logger.exception("local keepalive error")
            self._log_target(self.TARGET_LOCAL, "待機維持: 情報更新で例外が発生しました")

    def _normalize_yen_ratio_mode(self, value: Any, default: str = "yen") -> str:
        mode = str(value or default).strip().lower()
        if mode in {"rate", "pct", "percent", "割合"}:
            mode = "ratio"
        if mode not in {"yen", "ratio"}:
            mode = "yen"
        return mode

    def _resolve_target_payout_yen(self, rows: List[Dict[str, Any]]) -> int:
        entry = self.settings.entry
        target_mode = self._normalize_yen_ratio_mode(getattr(entry, "target_payout_mode", "yen"), default="yen")
        if target_mode == "ratio":
            ratio_pct = _safe_float(getattr(entry, "target_payout_ratio_pct", 1000.0), 1000.0)
            ratio_pct = max(1.0, ratio_pct)
            base_total = sum_ticket_yen(rows)
            return max(100, int(round(float(base_total) * ratio_pct / 100.0)))
        return int(getattr(entry, "target_payout_yen", 10000) or 10000)

    def _resolve_entry_abort_total(self, rows: List[Dict[str, Any]]) -> tuple[int, str]:
        entry = self.settings.entry
        abort_mode = self._normalize_yen_ratio_mode(getattr(entry, "entry_abort_mode", "yen"), default="yen")
        if abort_mode != "ratio":
            abort_total = max(0, int(getattr(entry, "entry_abort_total_yen", 10000) or 0))
            return abort_total, ""

        ratio_pct = _safe_float(getattr(entry, "entry_abort_ratio_pct", 100.0), 100.0)
        ratio_pct = max(0.0, ratio_pct)
        target_payout = self._resolve_target_payout_yen(rows)
        abort_total = max(0, int(round(float(target_payout) * ratio_pct / 100.0)))
        ratio_text = f"{ratio_pct:.2f}".rstrip("0").rstrip(".")
        detail = f"（目標払戻{target_payout:,}円に対して{ratio_text}%）"
        return abort_total, detail

    def _uses_notified_ticket_amounts(self, payload: Dict[str, Any]) -> bool:
        provider = str(payload.get("provider", "") or "").strip().lower()
        source = str(payload.get("source", "") or "").strip().lower()
        message_type = str(payload.get("message_type", "entry_tickets") or "entry_tickets").strip().lower()
        return provider == "kyoutei" and source == "discord_text" and message_type == "entry_tickets"

    def _prepare_tickets(self, payload: Dict) -> List[Dict]:
        entry = self.settings.entry
        payload_tickets = payload.get("tickets") if isinstance(payload.get("tickets"), list) else []
        fixed_ticket = int(getattr(entry, "fixed_ticket_yen", 100) or 100)
        fixed_ticket = max(100, fixed_ticket)
        use_notified_amounts = self._uses_notified_ticket_amounts(payload)
        base_tickets: List[Dict[str, Any]] = []
        for row in payload_tickets:
            if not isinstance(row, dict):
                continue
            copied = dict(row)
            if not use_notified_amounts:
                copied["bet_yen"] = fixed_ticket
            base_tickets.append(copied)

        rows = apply_entry_rules(
            base_tickets,
            ratio_pct=100.0,
            min_ticket_yen=entry.min_ticket_yen,
            ticket_cap_yen=entry.ticket_cap_yen,
            race_cap_yen=entry.race_cap_yen,
            max_tickets=entry.max_tickets,
        )
        if use_notified_amounts:
            return rows

        allocation_mode = str(getattr(entry, "allocation_mode", "target_payout") or "target_payout").strip().lower()
        if allocation_mode in {"current", "ratio"}:
            allocation_mode = "flat"
        if allocation_mode == "raffine":
            raffine_budget = int(getattr(entry, "raffine_budget_yen", 10000) or 10000)
            rows = apply_raffine_distribution(rows, budget_yen=max(100, raffine_budget))
        elif allocation_mode in {"target_payout", "payout_target"}:
            resolved_target = self._resolve_target_payout_yen(rows)
            rows = apply_target_payout_distribution(
                rows,
                target_payout_yen=resolved_target,
                min_ticket_yen=entry.min_ticket_yen,
            )
        return rows

    def _execute_payload(self, target: str, payload: Dict) -> None:
        race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
        race_tag = f"{race.get('date', '-')}_{race.get('venue_name', '-')}_{int(race.get('race_num', 0) or 0):02d}R"
        klog: Callable[[str], None] = lambda text: self._log_target(target, text)
        if (
            target == self.TARGET_CENTRAL
            and not self.settings.entry.dry_run
            and not self._is_central_schedule_active_now()
        ):
            self._close_executor_by_schedule_if_needed()
            klog(f"見送り: 起動時間外のためブラウザを起動しません ({race_tag})")
            return
        if (target == self.TARGET_LOCAL) and (not self._is_target_selectors_configured(target)):
            klog(f"見送り: 地方セレクタ未設定のため実行できません ({race_tag})")
            return

        base_tickets = payload.get("tickets") if isinstance(payload.get("tickets"), list) else []
        tickets = self._prepare_tickets(payload)
        if len(base_tickets) > len(tickets):
            entry = self.settings.entry
            reasons: List[str] = []
            if int(entry.max_tickets or 0) > 0:
                reasons.append(f"最大点数={int(entry.max_tickets)}")
            if (not self._uses_notified_ticket_amounts(payload)) and int(getattr(entry, "fixed_ticket_yen", 100) or 100) > 0:
                reasons.append(f"固定投票金額={int(getattr(entry, 'fixed_ticket_yen', 100) or 100)}円")
            if int(entry.ticket_cap_yen or 0) > 0:
                reasons.append(f"1点上限={int(entry.ticket_cap_yen)}円")
            if int(entry.race_cap_yen or 0) > 0:
                reasons.append(f"1レース上限={int(entry.race_cap_yen)}円")
            reason_text = " / ".join(reasons) if reasons else "投票ルール"
            klog(
                f"投票ルール適用: {len(base_tickets)}件 -> {len(tickets)}件（{reason_text}）"
            )
        if not tickets:
            klog(f"見送り: 条件適用後チケットなし ({race_tag})")
            return
        total_yen = sum_ticket_yen(tickets)
        abort_total, abort_detail = self._resolve_entry_abort_total(tickets)
        if abort_total > 0 and total_yen >= abort_total:
            klog(
                f"見送り: 合計金額{total_yen:,}円がエントリー中止金額{abort_total:,}円以上{abort_detail} ({race_tag})"
            )
            return
        klog(self._build_preview_text(payload, tickets, total_yen, race_tag))

        need_review = bool(self.settings.entry.confirm_each_race or self.settings.entry.show_ticket_preview_window)
        if need_review:
            if not self.review_func:
                klog(f"見送り: レビュー関数未設定 ({race_tag})")
                return
            try:
                with self._review_lock:
                    approved = bool(
                        self.review_func(
                            payload,
                            tickets,
                            total_yen,
                            bool(self.settings.entry.confirm_each_race),
                            bool(self.settings.entry.show_ticket_preview_window),
                        )
                    )
            except Exception:
                logger.exception("review callback error")
                klog(f"見送り: レビュー処理でエラーが発生しました ({race_tag})")
                return
            if not approved:
                klog(f"見送り: レビューでキャンセル ({race_tag})")
                return
            total_yen = sum_ticket_yen(tickets)
            if total_yen <= 0 or (not tickets):
                klog(f"見送り: レビュー後チケットなし ({race_tag})")
                return
            abort_total, abort_detail = self._resolve_entry_abort_total(tickets)
            if abort_total > 0 and total_yen >= abort_total:
                klog(
                    f"見送り: レビュー後の合計金額{total_yen:,}円がエントリー中止金額{abort_total:,}円以上{abort_detail} ({race_tag})"
                )
                return
            klog(self._build_preview_text(payload, tickets, total_yen, race_tag))

        if self.settings.entry.dry_run:
            result = {"status": "dry_run", "ticket_count": len(tickets), "total_yen": total_yen}
            path = self._write_runtime_file(payload, tickets, result, target=target)
            klog(f"DRY-RUN: {race_tag} {len(tickets)}点 {total_yen:,}円 -> {path}")
            klog(self._build_post_entry_text(race_tag, tickets, total_yen, "dry_run"))
            return

        try:
            with self._ipat_locks[target]:
                executor = self._get_executor(target)
                result = executor.execute(payload, tickets)
            path = self._write_runtime_file(payload, tickets, result, target=target)
            klog(
                f"発注結果: {race_tag} status={result.get('status')} "
                f"{int(result.get('ticket_count', 0) or 0)}点 {int(result.get('total_yen', 0) or 0):,}円 -> {path}"
            )
            result_total = int(result.get("total_yen", total_yen) or total_yen)
            result_status = str(result.get("status", "") or "unknown")
            klog(self._build_post_entry_text(race_tag, tickets, result_total, result_status))
        except IpatEntryError as exc:
            klog(f"発注失敗: {race_tag} 入力処理でエラーが発生しました")
            detail = str(exc or "").strip()
            if detail:
                klog(f"発注失敗詳細: {detail}")
        except Exception as exc:  # pragma: no cover
            logger.exception("unexpected entry error")
            klog(f"発注例外: {race_tag} システムエラーが発生しました")
            detail = str(exc or "").strip()
            if detail:
                klog(f"発注例外詳細: {detail}")

    def _worker_loop(self, target: str) -> None:
        task_queue = self._queues[target]
        while not self._stop_event.is_set():
            try:
                command, data = task_queue.get(timeout=0.5)
            except queue.Empty:
                if target == self.TARGET_CENTRAL:
                    self._ensure_discord_alive()
                    self._maybe_schedule_central_session()
                    self._maybe_keepalive_central()
                elif target == self.TARGET_LOCAL:
                    self._maybe_keepalive_local()
                continue

            try:
                if command == self.CMD_PREPARE:
                    self._handle_prepare_ipat(target)
                elif command == self.CMD_CANDIDATE_CONTROL:
                    envelope = data if isinstance(data, dict) else {}
                    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
                    candidate_count = int(envelope.get("candidate_count", 0) or 0)
                    self._handle_candidate_browser_control(target, payload, candidate_count=candidate_count)
                elif command == self.CMD_PAYLOAD:
                    envelope = data if isinstance(data, dict) else {}
                    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
                    self._execute_payload(target, payload)
                else:
                    self._log_target(target, f"不明コマンドを無視しました: {command}")
                self._schedule_keepalive_due(target)
            except DiscordClientError:
                self._log_target(target, "連携処理エラー: 連携設定を確認してください")
            except Exception:  # pragma: no cover
                logger.exception("entry worker error")
                self._log_target(target, "処理例外: 処理中にエラーが発生しました")
