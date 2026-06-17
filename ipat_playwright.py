from __future__ import annotations

import json
import logging
import os
import queue
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from config import AppSettings, load_internal_selectors

logger = logging.getLogger(__name__)


SINGLE_MARKETS = {"単勝", "複勝"}
PAIR_MARKETS_ORDERED = {"馬単"}
PAIR_MARKETS_UNORDERED = {"枠連", "馬連", "ワイド"}
TRIO_MARKETS_ORDERED = {"3連単", "三連単", "３連単"}
TRIO_MARKETS_UNORDERED = {"3連複", "三連複", "３連複"}
# 競輪券種（競馬券種と共存させ、入力互換を維持する）
KEIRIN_PAIR_MARKETS_ORDERED = {"2車単", "２車単", "二車単"}
KEIRIN_PAIR_MARKETS_UNORDERED = {"2車複", "２車複", "二車複"}
KEIRIN_TRIO_MARKETS_ORDERED = {"3連単", "三連単", "３連単"}
KEIRIN_TRIO_MARKETS_UNORDERED = {"3連複", "三連複", "３連複"}
KYOUTEI_PAIR_MARKETS_ORDERED = {"2連単", "２連単", "二連単"}
KYOUTEI_PAIR_MARKETS_UNORDERED = {"2連複", "２連複", "二連複", "拡連複"}
KYOUTEI_TRIO_MARKETS_ORDERED = {"3連単", "三連単", "３連単"}
KYOUTEI_TRIO_MARKETS_UNORDERED = {"3連複", "三連複", "３連複"}
ALL_PAIR_MARKETS_ORDERED = PAIR_MARKETS_ORDERED | KEIRIN_PAIR_MARKETS_ORDERED | KYOUTEI_PAIR_MARKETS_ORDERED
ALL_PAIR_MARKETS_UNORDERED = PAIR_MARKETS_UNORDERED | KEIRIN_PAIR_MARKETS_UNORDERED | KYOUTEI_PAIR_MARKETS_UNORDERED
ALL_TRIO_MARKETS_ORDERED = TRIO_MARKETS_ORDERED | KEIRIN_TRIO_MARKETS_ORDERED | KYOUTEI_TRIO_MARKETS_ORDERED
ALL_TRIO_MARKETS_UNORDERED = TRIO_MARKETS_UNORDERED | KEIRIN_TRIO_MARKETS_UNORDERED | KYOUTEI_TRIO_MARKETS_UNORDERED
UNORDERED_MARKETS = ALL_PAIR_MARKETS_UNORDERED | ALL_TRIO_MARKETS_UNORDERED
LOCAL_SUPPORTED_MARKETS = {"馬連", "ワイド"}
KNOWN_MARKETS = sorted(
    SINGLE_MARKETS
    | ALL_PAIR_MARKETS_ORDERED
    | ALL_PAIR_MARKETS_UNORDERED
    | ALL_TRIO_MARKETS_ORDERED
    | ALL_TRIO_MARKETS_UNORDERED,
    key=len,
    reverse=True,
)

KYOUTEI_VENUE_CODE_MAP = {
    "桐生": "01",
    "戸田": "02",
    "江戸川": "03",
    "平和島": "04",
    "多摩川": "05",
    "浜名湖": "06",
    "蒲郡": "07",
    "常滑": "08",
    "津": "09",
    "三国": "10",
    "びわこ": "11",
    "住之江": "12",
    "尼崎": "13",
    "鳴門": "14",
    "丸亀": "15",
    "児島": "16",
    "宮島": "17",
    "徳山": "18",
    "下関": "19",
    "若松": "20",
    "芦屋": "21",
    "福岡": "22",
    "唐津": "23",
    "大村": "24",
}

KYOUTEI_KACHISHIKI_MAP = {
    "単勝": "1",
    "複勝": "2",
    "2連単": "3",
    "2連複": "4",
    "拡連複": "5",
    "3連単": "6",
    "3連複": "7",
}


class IpatEntryError(RuntimeError):
    pass


class IpatRaceCancelledError(IpatEntryError):
    pass


class IpatRaceUnavailableError(IpatEntryError):
    pass


def _normalize_target(value: str) -> str:
    text = str(value or "central").strip().lower()
    if text in {"local", "chihou", "chiho"}:
        return "local"
    return "central"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _parse_combo_numbers(combo: str) -> List[int]:
    text = str(combo or "").strip()
    if not text:
        return []
    tokenized = text.replace(">", "-").replace("/", "-")
    parts = [p for p in tokenized.split("-") if str(p).strip()]
    out: List[int] = []
    for p in parts:
        try:
            n = int(p)
        except (TypeError, ValueError):
            return []
        if n <= 0:
            return []
        out.append(n)
    return out


def _canonical_market_name(market: str) -> str:
    text = str(market or "").strip()
    if text == "馬複":
        return "馬連"
    if text in {"２連単", "二連単"}:
        return "2連単"
    if text in {"２連複", "二連複"}:
        return "2連複"
    if text in {"２車単", "二車単"}:
        return "2車単"
    if text in {"２車複", "二車複"}:
        return "2車複"
    if text == "３連複":
        return "3連複"
    if text == "３連単":
        return "3連単"
    if text == "三連複":
        return "3連複"
    if text == "三連単":
        return "3連単"
    return text


def _normalize_ticket(ticket: Dict[str, Any]) -> Dict[str, Any]:
    market_raw = str(ticket.get("market", "") or "").strip()
    market = _canonical_market_name(market_raw)
    combo = str(ticket.get("combo", "") or "").strip()
    bet_yen = int(ticket.get("bet_yen", 0) or 0)
    nums = _parse_combo_numbers(combo)

    if market in SINGLE_MARKETS and len(nums) != 1:
        raise IpatEntryError(f"invalid combo for {market}: {combo}")
    if market in ALL_PAIR_MARKETS_ORDERED and len(nums) != 2:
        raise IpatEntryError(f"invalid combo for {market}: {combo}")
    if market in ALL_PAIR_MARKETS_UNORDERED and len(nums) != 2:
        raise IpatEntryError(f"invalid combo for {market}: {combo}")
    if market in ALL_TRIO_MARKETS_ORDERED and len(nums) != 3:
        raise IpatEntryError(f"invalid combo for {market}: {combo}")
    if market in ALL_TRIO_MARKETS_UNORDERED and len(nums) != 3:
        raise IpatEntryError(f"invalid combo for {market}: {combo}")

    if market in UNORDERED_MARKETS:
        nums = sorted(nums)

    return {
        "market": market,
        "combo": combo,
        "numbers": nums,
        "bet_yen": max(0, int(bet_yen)),
    }


def _combo_key(market: str, numbers: List[int]) -> Tuple[int, ...]:
    if _canonical_market_name(market) in UNORDERED_MARKETS:
        return tuple(sorted(int(n) for n in numbers))
    return tuple(int(n) for n in numbers)


def _race_day_hint(date8: str) -> str:
    text = str(date8 or "").strip()
    if not (len(text) == 8 and text.isdigit()):
        return ""
    try:
        wd = datetime.strptime(text, "%Y%m%d").weekday()
    except ValueError:
        return ""
    if wd == 5:
        return "土"
    if wd == 6:
        return "日"
    return ""


def _contains_race_label(text: str, race_no: int) -> bool:
    normalized = str(text or "").replace(" ", "").replace("　", "")
    return re.search(rf"(?<!\d){int(race_no)}R(?!\d)", normalized) is not None


class IpatPlaywrightExecutor:
    def __init__(
        self,
        app_settings: AppSettings,
        event_logger: Optional[Callable[[str], None]] = None,
        target: str = "central",
    ):
        self.settings = app_settings
        self.target = _normalize_target(target)
        self._ipat_settings = app_settings.local_ipat if self.target == "local" else app_settings.ipat
        self.selectors = load_internal_selectors(target=self.target)
        self._selectors_configured = bool(self.selectors.get("__configured__", True))
        self._event_logger = event_logger
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._local_dialog_handler_attached = False
        self._playwright_temp_dir = ""
        self._ignore_https_errors = False
        self._last_debug_context: Dict[str, Any] = {}

    def _target_label(self) -> str:
        if self.target == "local":
            return "地方競馬"
        return "競艇"

    def _is_keirin_mode(self, login_url: str = "") -> bool:
        if self.target == "local":
            return False
        url = str(login_url or getattr(self._ipat_settings, "login_url", "") or "").strip().lower()
        return "keirin.jp" in url

    def _is_kyoutei_mode(self, login_url: str = "") -> bool:
        if self.target == "local":
            return False
        url = str(login_url or getattr(self._ipat_settings, "login_url", "") or "").strip().lower()
        return ("ib.mbrace.or.jp" in url) or ("boatrace" in url)

    def _ensure_selectors_configured(self) -> None:
        if self._selectors_configured:
            return
        raise IpatEntryError(f"{self._target_label()}のセレクタが未設定です")

    def _selector(self, key: str, default: str = "") -> str:
        return str(self.selectors.get(key, default) or default).strip()

    def _selector_list(self, key: str, *fallbacks: str) -> List[str]:
        raw = self._selector(key)
        out: List[str] = []
        if raw:
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            out.extend(parts if parts else [raw])
        for fb in fallbacks:
            f = str(fb or "").strip()
            if not f:
                continue
            for part in [p.strip() for p in f.split(",") if p.strip()]:
                if part and part not in out:
                    out.append(part)
        return out

    def _emit(self, text: str) -> None:
        logger.info(text)
        if self._event_logger is not None:
            try:
                self._event_logger(f"{self._target_label()}: {text}")
            except Exception:
                logger.exception("event_logger failed")

    def _selector_candidates(self, key: str, *fallbacks: str) -> List[str]:
        out: List[str] = []
        base = self._selector(key)
        if base:
            out.append(base)
        for fallback in fallbacks:
            f = str(fallback or "").strip()
            if f and f not in out:
                out.append(f)
        return out

    def _market_select_value(self, market: str) -> str:
        mapping = self.selectors.get("market_value_map")
        if not isinstance(mapping, dict):
            mapping = {}
        canonical = _canonical_market_name(market)
        return str(mapping.get(canonical, canonical))

    def _first_visible(self, page, selector: str):
        sel = str(selector or "").strip()
        if not sel:
            return None
        try:
            loc = page.locator(sel)
            count = loc.count()
        except Exception:
            return None
        for i in range(count):
            item = loc.nth(i)
            try:
                if item.is_visible():
                    return item
            except Exception:
                continue
        return None

    def _first_attached(self, page, selector: str):
        sel = str(selector or "").strip()
        if not sel:
            return None
        try:
            loc = page.locator(sel)
            count = loc.count()
        except Exception:
            return None
        for i in range(count):
            try:
                return loc.nth(i)
            except Exception:
                continue
        return None

    def _first_enabled_button(self, page, selector: str, contains_text: str = "", exact_text: str = ""):
        sel = str(selector or "").strip()
        if not sel:
            return None
        try:
            loc = page.locator(sel)
            count = loc.count()
        except Exception:
            return None
        for i in range(count):
            item = loc.nth(i)
            try:
                if not item.is_visible() or not item.is_enabled():
                    continue
                text = str(item.inner_text(timeout=1000) or "").strip()
                if exact_text and text != exact_text:
                    continue
                if contains_text and contains_text not in text:
                    continue
                return item
            except Exception:
                continue
        return None

    def _set_node_value(self, node, value: str) -> bool:
        text = str(value)
        try:
            node.click()
        except Exception:
            pass
        try:
            node.fill(text)
            return True
        except Exception:
            pass
        try:
            node.press("ControlOrMeta+A")
            node.press("Backspace")
            node.type(text)
            try:
                if str(node.input_value()) == text:
                    return True
            except Exception:
                return True
        except Exception:
            pass
        try:
            applied = node.evaluate(
                """
                (el, nextValue) => {
                  el.focus();
                  el.value = String(nextValue ?? '');
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                  el.dispatchEvent(new Event('change', { bubbles: true }));
                  return el.value;
                }
                """,
                text,
            )
            return str(applied or "") == text
        except Exception:
            return False

    def _set_value_by_selector_js(self, page, selector: str, value: str) -> Tuple[bool, bool]:
        sel = str(selector or "").strip()
        text = str(value)
        if not sel:
            return False, False
        try:
            result = page.evaluate(
                """
                ({ selector, nextValue }) => {
                  const el = document.querySelector(selector);
                  if (!el) {
                    return { found: false, value: '' };
                  }
                  try { el.focus(); } catch (e) {}
                  try { el.click(); } catch (e) {}
                  el.value = String(nextValue ?? '');
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                  el.dispatchEvent(new Event('change', { bubbles: true }));
                  return {
                    found: true,
                    value: String(el.value ?? ''),
                  };
                }
                """,
                {"selector": sel, "nextValue": text},
            )
        except Exception:
            return False, False
        if not isinstance(result, dict):
            return False, False
        found = bool(result.get("found"))
        applied = found and str(result.get("value", "") or "") == text
        return found, applied

    def _query_selector_handle(self, page, selector: str):
        sel = str(selector or "").strip()
        if not sel:
            return None
        try:
            return page.query_selector(sel)
        except Exception:
            return None

    def _collect_selector_probe(self, page, selector: str) -> Dict[str, Any]:
        sel = str(selector or "").strip()
        info: Dict[str, Any] = {"selector": sel}
        if not sel:
            return info
        try:
            loc = page.locator(sel)
            count = int(loc.count())
            info["locator_count"] = count
            visible = 0
            for i in range(min(count, 3)):
                try:
                    if loc.nth(i).is_visible():
                        visible += 1
                except Exception:
                    continue
            info["visible_count_preview"] = visible
        except Exception as exc:
            info["locator_error"] = str(exc)
        try:
            handle = page.query_selector(sel)
            info["query_selector_found"] = handle is not None
        except Exception as exc:
            info["query_selector_error"] = str(exc)
        try:
            dom_info = page.evaluate(
                """
                (selector) => {
                  const el = document.querySelector(selector);
                  if (!el) {
                    return { found: false };
                  }
                  const rect = typeof el.getBoundingClientRect === 'function' ? el.getBoundingClientRect() : null;
                  return {
                    found: true,
                    tag: String(el.tagName || ''),
                    id: String(el.id || ''),
                    name: String(el.getAttribute('name') || ''),
                    type: String(el.getAttribute('type') || ''),
                    className: String(el.className || ''),
                    valueLength: typeof el.value === 'string' ? el.value.length : null,
                    disabled: !!el.disabled,
                    readOnly: !!el.readOnly,
                    outerHTML: String(el.outerHTML || '').slice(0, 600),
                    rect: rect ? {
                      x: Math.round(rect.x),
                      y: Math.round(rect.y),
                      width: Math.round(rect.width),
                      height: Math.round(rect.height),
                    } : null,
                  };
                }
                """,
                sel,
            )
            if isinstance(dom_info, dict):
                info["dom"] = dom_info
        except Exception as exc:
            info["dom_error"] = str(exc)
        return info

    def _remember_input_debug_context(self, page, key: str, selectors: List[str], *, reason: str) -> None:
        cleaned = [str(sel or "").strip() for sel in selectors if str(sel or "").strip()]
        probes = [self._collect_selector_probe(page, sel) for sel in cleaned]
        context: Dict[str, Any] = {
            "kind": "input_probe",
            "key": str(key or ""),
            "reason": str(reason or ""),
            "selectors": cleaned,
            "probes": probes,
        }
        try:
            summary = page.evaluate(
                """
                () => {
                  const form = document.querySelector('#betconfForm');
                  const confirmation = document.querySelector('#confirmationArea');
                  const active = document.activeElement;
                  return {
                    url: String(location.href || ''),
                    readyState: String(document.readyState || ''),
                    activeElement: active ? {
                      tag: String(active.tagName || ''),
                      id: String(active.id || ''),
                      name: String(active.getAttribute('name') || ''),
                    } : null,
                    betconfFormHtml: form ? String(form.outerHTML || '').slice(0, 2000) : '',
                    confirmationHtml: confirmation ? String(confirmation.outerHTML || '').slice(0, 2000) : '',
                  };
                }
                """
            )
            if isinstance(summary, dict):
                context["page"] = summary
        except Exception as exc:
            context["page_error"] = str(exc)
        self._last_debug_context = context

    def _fill_any(self, page, key: str, value: str, *fallbacks: str) -> None:
        selector_candidates = self._selector_candidates(key, *fallbacks)
        matched_selectors: List[str] = []
        for sel in selector_candidates:
            node = self._first_visible(page, sel)
            if node is None:
                node = self._first_attached(page, sel)
            if node is None:
                node = self._query_selector_handle(page, sel)
            if node is None:
                found, applied = self._set_value_by_selector_js(page, sel, str(value))
                if found:
                    matched_selectors.append(sel)
                if applied:
                    return
                continue
            matched_selectors.append(sel)
            try:
                if self._set_node_value(node, str(value)):
                    return
            except Exception:
                continue
        if matched_selectors:
            joined = ", ".join(matched_selectors)
            self._remember_input_debug_context(page, key, selector_candidates, reason="input_not_fillable")
            raise IpatEntryError(f"input not fillable: {key} selectors={joined}")
        self._remember_input_debug_context(page, key, selector_candidates, reason="selector_missing")
        raise IpatEntryError(f"selector missing: {key}")

    def _fill_any_logged(self, page, key: str, value: str, *fallbacks: str) -> None:
        selector_candidates = self._selector_candidates(key, *fallbacks)
        matched_selectors: List[str] = []
        for sel in selector_candidates:
            node = self._first_visible(page, sel)
            if node is None:
                node = self._first_attached(page, sel)
            if node is None:
                node = self._query_selector_handle(page, sel)
            if node is None:
                found, applied = self._set_value_by_selector_js(page, sel, str(value))
                if found:
                    matched_selectors.append(sel)
                if applied:
                    return
                if found:
                    self._emit(f"入力失敗: key={key} selector={sel} method=querySelector")
                continue
            matched_selectors.append(sel)
            try:
                if self._set_node_value(node, str(value)):
                    return
                self._emit(f"入力失敗: key={key} selector={sel}")
                continue
            except Exception:
                continue
        if matched_selectors:
            joined = ", ".join(matched_selectors)
            self._remember_input_debug_context(page, key, selector_candidates, reason="input_not_fillable")
            raise IpatEntryError(f"input not fillable: {key} selectors={joined}")
        self._remember_input_debug_context(page, key, selector_candidates, reason="selector_missing")
        raise IpatEntryError(f"selector missing: {key}")

    def _click_any(self, page, key: str, *fallbacks: str, required: bool = True) -> bool:
        for sel in self._selector_candidates(key, *fallbacks):
            node = self._first_enabled_button(page, sel)
            if node is None:
                continue
            try:
                node.click()
                return True
            except Exception:
                continue
        if required:
            raise IpatEntryError(f"selector missing or not clickable: {key}")
        return False

    def _click_first_visible(self, page, key: str, *fallbacks: str, required: bool = True) -> bool:
        for sel in self._selector_candidates(key, *fallbacks):
            node = self._first_visible(page, sel)
            if node is None:
                continue
            try:
                node.click()
                return True
            except Exception:
                continue
        if required:
            raise IpatEntryError(f"selector missing or not clickable: {key}")
        return False

    def _is_visible(self, page, selector: str) -> bool:
        node = self._first_visible(page, selector)
        return node is not None

    def _wait_for_any_visible(self, page, selectors: List[str], timeout_ms: int = 2000, poll_ms: int = 200) -> bool:
        end = datetime.now().timestamp() + (max(200, int(timeout_ms)) / 1000.0)
        checked = [str(s or "").strip() for s in selectors if str(s or "").strip()]
        if not checked:
            return False
        while datetime.now().timestamp() < end:
            for sel in checked:
                if self._is_visible(page, sel):
                    return True
            page.wait_for_timeout(int(poll_ms))
        return False

    def _wait_for_selector_attached(self, page, selector: str, timeout_ms: int = 1500) -> bool:
        sel = str(selector or "").strip()
        if not sel:
            return False
        try:
            page.wait_for_selector(sel, state="attached", timeout=max(200, int(timeout_ms)))
            return True
        except Exception:
            return False

    def _wait_until_not_loading(self, page, timeout_ms: int = 2000, phase: str = "") -> None:
        selectors = self._selector_list("vote_loading_selector", "text=NOW LOADING")
        if not selectors:
            return
        end = datetime.now().timestamp() + (max(200, int(timeout_ms)) / 1000.0)
        while datetime.now().timestamp() < end:
            any_visible = False
            for sel in selectors:
                if self._is_visible(page, sel):
                    any_visible = True
                    break
            if not any_visible:
                return
            page.wait_for_timeout(200)
        tag = f" ({phase})" if phase else ""
        raise IpatEntryError(f"ロード完了待機がタイムアウトしました{tag} (url={getattr(page, 'url', '-')})")

    def _save_debug_artifacts(self, page, reason: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path("runtime_logs") / "debug" / stamp
        out_dir.mkdir(parents=True, exist_ok=True)
        png_path = out_dir / "ipat_error.png"
        html_path = out_dir / "ipat_error.html"
        txt_path = out_dir / "ipat_error.txt"
        ctx_path = out_dir / "ipat_error_context.json"
        try:
            page.screenshot(path=str(png_path), full_page=True)
        except Exception:
            pass
        try:
            html_path.write_text(page.content(), encoding="utf-8")
        except Exception:
            pass
        try:
            txt_path.write_text(
                f"url={getattr(page, 'url', '')}\nreason={reason}\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        try:
            if self._last_debug_context:
                ctx_path.write_text(
                    json.dumps(self._last_debug_context, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass
        return str(out_dir)

    def _validate_ipat_settings(self) -> str:
        ipat = self._ipat_settings
        target_label = self._target_label()
        login_url = str(ipat.login_url or "").strip()
        if not login_url:
            raise IpatEntryError(f"{target_label}ログインURLが未設定です")

        if self.target == "local":
            if not str(getattr(ipat, "member_number", "") or "").strip():
                raise IpatEntryError(f"{target_label}の認証情報（加入者番号）が未設定です")
            if not str(getattr(ipat, "member_id", "") or "").strip():
                raise IpatEntryError(f"{target_label}の認証情報（利用者ID）が未設定です")
            if not str(getattr(ipat, "pin", "") or "").strip():
                raise IpatEntryError(f"{target_label}の認証情報（暗証番号）が未設定です")
        elif self._is_kyoutei_mode(login_url):
            if not str(getattr(ipat, "inet_id", "") or "").strip():
                raise IpatEntryError(f"{target_label}の認証情報（加入者番号）が未設定です")
            if not str(getattr(ipat, "pars_no", "") or "").strip():
                raise IpatEntryError(f"{target_label}の認証情報（暗証番号）が未設定です")
            if not str(getattr(ipat, "password", "") or "").strip():
                raise IpatEntryError(f"{target_label}の認証情報（認証用パスワード）が未設定です")
            if not str(getattr(ipat, "login_id", "") or "").strip():
                raise IpatEntryError(f"{target_label}の認証情報（投票用パスワード）が未設定です")
        elif self._is_keirin_mode(login_url):
            if not str(getattr(ipat, "inet_id", "") or "").strip():
                raise IpatEntryError(f"{target_label}の認証情報（インターネット投票認証ID）が未設定です")
            if not str(getattr(ipat, "password", "") or "").strip():
                raise IpatEntryError(f"{target_label}の認証情報（インターネット投票パスワード）が未設定です")
            if not str(getattr(ipat, "pars_no", "") or "").strip():
                raise IpatEntryError(f"{target_label}の認証情報（暗証番号）が未設定です")
        else:
            if not ipat.inet_id:
                raise IpatEntryError(f"{target_label}の認証情報（INET-ID）が未設定です")
            if not ipat.login_id or not ipat.password or not ipat.pars_no:
                raise IpatEntryError(f"{target_label}の認証情報（加入者番号/パスワード/P-ARS番号）が未設定です")
        return login_url

    def _op_timeout_sec(self) -> int:
        raw = _safe_int(getattr(self._ipat_settings, "timeout_sec", 2), 2)
        return max(1, min(2, raw))

    def _op_timeout_ms(self, minimum_ms: int = 2000, scale: int = 1000) -> int:
        return max(int(minimum_ms), int(self._op_timeout_sec() * int(scale)))

    def _navigation_timeout_ms(self) -> int:
        return max(15000, self._op_timeout_ms(minimum_ms=15000, scale=10000))

    def _configure_page_timeouts(self, page) -> None:
        page.set_default_timeout(self._op_timeout_ms(minimum_ms=1000))
        set_navigation_timeout = getattr(page, "set_default_navigation_timeout", None)
        if callable(set_navigation_timeout):
            set_navigation_timeout(self._navigation_timeout_ms())

    def _horse_select_timeout_ms(self) -> int:
        # 馬番選択は画面反映が遅れることがあるため、全体待機より少し長めに許容する。
        return max(4000, self._op_timeout_ms())

    def _default_playwright_browser_cache_dir(self) -> Path:
        if os.name == "nt":
            local = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
            if local:
                return Path(local) / "ms-playwright"
        elif sys.platform == "darwin":
            return Path.home() / "Library" / "Caches" / "ms-playwright"
        xdg = str(os.environ.get("XDG_CACHE_HOME", "") or "").strip()
        if xdg:
            return Path(xdg) / "ms-playwright"
        return Path.home() / ".cache" / "ms-playwright"

    def _candidate_playwright_browser_roots(self) -> List[Path]:
        out: List[Path] = []

        def _append(path: Path) -> None:
            if path not in out:
                out.append(path)

        try:
            import playwright

            _append(Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers")
        except Exception:
            pass

        env_root = str(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "") or "").strip()
        if env_root and env_root != "0":
            _append(Path(env_root))
        _append(self._default_playwright_browser_cache_dir())
        return out

    def _find_playwright_chromium_executable(self) -> str:
        if os.name == "nt":
            rel_paths = ("chrome-win64/chrome.exe", "chrome-win/chrome.exe")
        elif sys.platform == "darwin":
            rel_paths = ("chrome-mac/Chromium.app/Contents/MacOS/Chromium",)
        else:
            rel_paths = ("chrome-linux/chrome",)

        for root in self._candidate_playwright_browser_roots():
            if not root.exists() or not root.is_dir():
                continue
            try:
                candidates = sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("chromium-"))
            except Exception:
                continue
            for browser_dir in candidates:
                for rel_path in rel_paths:
                    executable = browser_dir / rel_path
                    if executable.exists() and executable.is_file():
                        return str(executable)
        return ""

    def _is_missing_headless_shell_error(self, exc: BaseException) -> bool:
        text = str(exc or "")
        return "Executable doesn't exist" in text and "chromium_headless_shell" in text

    def _launch_playwright_chromium_with_fallback(self, launch_kwargs: Dict[str, Any]):
        try:
            return self._playwright.chromium.launch(**launch_kwargs)
        except Exception as exc:
            if not self._is_missing_headless_shell_error(exc):
                raise
            chromium_path = self._find_playwright_chromium_executable()
            if not chromium_path:
                raise
            retry_kwargs = dict(launch_kwargs)
            retry_kwargs.pop("channel", None)
            retry_kwargs["executable_path"] = chromium_path
            browser = self._playwright.chromium.launch(**retry_kwargs)
            self._emit(
                "Playwright headless shell が見つからないため、Chromium 実行ファイルへフォールバックしました "
                f"(executable_path={chromium_path})"
            )
            return browser

    def _auto_browser_channels(self) -> List[str]:
        return ["chrome", "msedge"]

    def _launch_browser(self):
        ipat = self._ipat_settings
        base_launch_kwargs: Dict[str, Any] = {
            "headless": bool(ipat.headless),
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        browser_channel = str(getattr(ipat, "browser_channel", "") or "").strip()
        browser_executable_path = str(getattr(ipat, "browser_executable_path", "") or "").strip()
        launch_kwargs = dict(base_launch_kwargs)
        if browser_executable_path:
            launch_kwargs["executable_path"] = browser_executable_path
        elif browser_channel:
            launch_kwargs["channel"] = browser_channel
        else:
            for auto_channel in self._auto_browser_channels():
                try:
                    browser = self._launch_playwright_chromium_with_fallback(
                        dict(base_launch_kwargs, channel=auto_channel)
                    )
                    self._emit(
                        "browser_channel 未設定のため、インストール済みブラウザを自動使用しました "
                        f"(channel={auto_channel})"
                    )
                    return browser
                except Exception:
                    continue
        try:
            return self._launch_playwright_chromium_with_fallback(launch_kwargs)
        except Exception as primary_exc:
            if browser_executable_path or browser_channel:
                try:
                    browser = self._launch_playwright_chromium_with_fallback(base_launch_kwargs)
                    if browser_executable_path:
                        self._emit(
                            f"指定ブラウザの起動に失敗したため、Playwright Chromiumへフォールバックしました "
                            f"(executable_path={browser_executable_path})"
                        )
                    else:
                        self._emit(
                            f"指定ブラウザの起動に失敗したため、Playwright Chromiumへフォールバックしました "
                            f"(channel={browser_channel})"
                        )
                    return browser
                except Exception as fallback_exc:
                    if browser_executable_path:
                        raise IpatEntryError(
                            f"ブラウザ起動に失敗しました (executable_path={browser_executable_path}): {primary_exc}. "
                            f"Playwright Chromiumでの起動も失敗しました: {fallback_exc}. "
                            "browser_executable_path を見直すか、`python -m playwright install chromium` または Chromium 同梱を確認してください。"
                        ) from fallback_exc
                    raise IpatEntryError(
                        f"ブラウザ起動に失敗しました (channel={browser_channel}): {primary_exc}. "
                        f"Playwright Chromiumでの起動も失敗しました: {fallback_exc}. "
                        "browser_channel を空欄のまま使うか、`python -m playwright install chromium` または Chromium 同梱を確認してください。"
                    ) from fallback_exc
            raise IpatEntryError(
                f"ブラウザ起動に失敗しました: {primary_exc}. "
                "必要に応じて `python -m playwright install chromium` を実行してください。"
            ) from primary_exc

    def _candidate_playwright_temp_dirs(self) -> List[Path]:
        out: List[Path] = []

        def _append(path_text: str) -> None:
            text = str(path_text or "").strip()
            if not text:
                return
            path = Path(text)
            if path not in out:
                out.append(path)

        for key in ("TMP", "TEMP", "TMPDIR"):
            _append(os.environ.get(key, ""))

        if os.name == "nt":
            local_app_data = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
            if local_app_data:
                _append(str(Path(local_app_data) / "kyoutei_auto_entry" / "playwright_tmp"))
            user_profile = str(os.environ.get("USERPROFILE", "") or "").strip()
            if user_profile:
                _append(str(Path(user_profile) / "AppData" / "Local" / "kyoutei_auto_entry" / "playwright_tmp"))

        _append(str(Path.cwd() / "runtime_logs" / "playwright_tmp"))
        _append(str(Path.home() / ".cache" / "kyoutei_auto_entry" / "playwright_tmp"))
        return out

    def _ensure_writable_dir(self, path: Path) -> Path | None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path.resolve()
        except Exception:
            return None

    def _prepare_playwright_runtime_env(self) -> Path:
        for candidate in self._candidate_playwright_temp_dirs():
            resolved = self._ensure_writable_dir(candidate)
            if resolved is None:
                continue
            chosen = str(resolved)
            os.environ["TMP"] = chosen
            os.environ["TEMP"] = chosen
            os.environ["TMPDIR"] = chosen
            self._playwright_temp_dir = chosen
            return resolved
        raise IpatEntryError("Playwright の一時フォルダを準備できませんでした。書き込み可能な Temp 領域を確認してください。")

    def _ensure_page(self):
        if self._page is not None:
            try:
                _ = self._page.url
                return self._page
            except Exception:
                self.close()

        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover
            raise IpatEntryError(
                "playwright が見つかりません。`pip install playwright` と `python -m playwright install chromium` を実行してください。"
            ) from exc

        self._prepare_playwright_runtime_env()
        self._playwright = sync_playwright().start()
        self._browser = self._launch_browser()
        self._context = self._new_browser_context()
        self._page = self._context.new_page()
        if self.target == "local":
            self._attach_local_dialog_handler()
        self._configure_page_timeouts(self._page)
        return self._page

    def _new_browser_context(self):
        if self._ignore_https_errors:
            return self._browser.new_context(ignore_https_errors=True)
        return self._browser.new_context()

    def _is_certificate_authority_error(self, exc: BaseException) -> bool:
        return "ERR_CERT_AUTHORITY_INVALID" in str(exc or "")

    def _recreate_page_ignoring_https_errors(self):
        if self._browser is None:
            raise IpatEntryError("ブラウザが未起動のため、証明書エラー再試行を実行できません。")
        if not self._ignore_https_errors:
            self._ignore_https_errors = True
            self._emit("HTTPS証明書エラーを検知したため、証明書エラーを許可して再接続します")
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
        self._page = None
        self._context = None
        self._local_dialog_handler_attached = False
        self._context = self._new_browser_context()
        self._page = self._context.new_page()
        if self.target == "local":
            self._attach_local_dialog_handler()
        self._configure_page_timeouts(self._page)
        return self._page

    def _goto_once(self, page, url: str, wait_until: str):
        timeout_ms = self._navigation_timeout_ms()
        try:
            return page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        except TypeError as exc:
            if "timeout" not in str(exc):
                raise
            return page.goto(url, wait_until=wait_until)

    def _goto(self, page, url: str, wait_until: str = "domcontentloaded"):
        try:
            self._goto_once(page, url, wait_until)
            return page
        except Exception as exc:
            if (not self._is_certificate_authority_error(exc)) or self._ignore_https_errors:
                raise
            retry_page = self._recreate_page_ignoring_https_errors()
            self._goto_once(retry_page, url, wait_until)
            return retry_page

    def _attach_local_dialog_handler(self) -> None:
        if self._context is None or self._local_dialog_handler_attached:
            return

        def _on_dialog(dialog) -> None:
            try:
                self._emit(f"SPAT4確認ダイアログを自動OK: {str(dialog.message or '').strip()}")
                dialog.accept()
            except Exception:
                logger.exception("failed to accept local dialog")

        try:
            self._context.on("dialog", _on_dialog)
            self._local_dialog_handler_attached = True
        except Exception:
            logger.exception("failed to attach local dialog handler")

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._local_dialog_handler_attached = False
        self._ignore_https_errors = False

    def _is_login_form_visible(self, page) -> bool:
        login_id = self._selector("login_id_input", "input[name='i']")
        password = self._selector("password_input", "input[name='p']")
        return self._is_visible(page, login_id) and self._is_visible(page, password)

    def _is_menu_ready(self, page) -> bool:
        return self._wait_for_any_visible(
            page,
            self._selector_list(
                "normal_vote_button",
                self._selector("vote_menu_link"),
                self._selector("market_select"),
                self._selector("course_select"),
            ),
            timeout_ms=1000,
            poll_ms=100,
        )

    def _is_important_notice_visible(self, page) -> bool:
        selectors = self._selector_list(
            "important_notice_selector",
            "div.announce:has-text('重要なお知らせ')",
            "h1.page-header:has-text('重要なお知らせ')",
            "text=重要なお知らせ",
        )
        for sel in selectors:
            if self._is_visible(page, sel):
                return True
        try:
            heading = page.get_by_role("heading", name="重要なお知らせ")
            if heading.count() > 0 and heading.first.is_visible():
                return True
        except Exception:
            pass
        return False

    def _click_important_notice_ok(self, page) -> bool:
        try:
            btn = page.get_by_role("button", name="OK")
            if btn.count() > 0 and btn.first.is_visible() and btn.first.is_enabled():
                btn.first.click()
                return True
        except Exception:
            pass
        return self._click_any(
            page,
            "important_notice_ok_button",
            "div.announce button.btn-ok",
            "div.announce button:has-text('OK')",
            "button:has-text('OK')",
            required=False,
        )

    def _dismiss_important_notice_if_present(self, page) -> bool:
        if not self._is_important_notice_visible(page):
            return False

        self._emit("重要なお知らせを検知。OKを押して続行します")

        checkbox_sel = self._selector(
            "important_notice_skip_checkbox",
            "#force-info-checkbox",
        )
        if checkbox_sel:
            checkbox = self._first_visible(page, checkbox_sel)
            if checkbox is not None:
                try:
                    if not checkbox.is_checked():
                        checkbox.check(force=True)
                except Exception:
                    try:
                        checkbox.click(force=True)
                    except Exception:
                        pass

        # 表示直後はAngularのイベントバインド準備中でクリックが落ちることがあるため、短くリトライする。
        clicked = False
        for _ in range(8):
            clicked = self._click_important_notice_ok(page)
            if clicked:
                break
            page.wait_for_timeout(120)
        if not clicked:
            raise IpatEntryError("重要なお知らせ画面のOKボタンを押せませんでした")

        # 通知画面が閉じるまで待機。
        for _ in range(20):
            if not self._is_important_notice_visible(page):
                break
            page.wait_for_timeout(100)
        if self._is_important_notice_visible(page):
            raise IpatEntryError("重要なお知らせ画面が閉じませんでした")
        return True

    def _wait_post_login_ready(self, page) -> None:
        timeout_ms = self._op_timeout_ms()
        end = datetime.now().timestamp() + (timeout_ms / 1000.0)
        while datetime.now().timestamp() < end:
            if self._dismiss_important_notice_if_present(page):
                page.wait_for_timeout(150)
                continue
            if self._is_menu_ready(page):
                return
            page.wait_for_timeout(150)
        raise IpatEntryError(f"ログイン後の画面遷移待機に失敗しました (url={getattr(page, 'url', '-')})")

    def _stabilize_post_login_view(self, page) -> None:
        # ログイン直後に遅れて通知画面が差し込まれるケースを吸収する。
        # 「通知なし + メニュー可視」が一定期間続くまで待機する。
        end = datetime.now().timestamp() + 2.0
        stable_count = 0
        stable_required = 8  # 約1秒（120ms * 8）
        while datetime.now().timestamp() < end:
            if self._dismiss_important_notice_if_present(page):
                stable_count = 0
                page.wait_for_timeout(150)
                continue
            if self._is_menu_ready(page):
                stable_count += 1
                if stable_count >= stable_required:
                    return
            else:
                stable_count = 0
            page.wait_for_timeout(120)

    def _ensure_logged_in(self, page, login_url: str) -> None:
        if self._is_menu_ready(page):
            self._stabilize_post_login_view(page)
            self._dismiss_important_notice_if_present(page)
            return page

        self._dismiss_important_notice_if_present(page)

        if self._click_any(
            page,
            "return_home_button",
            "div.brand a[ui-sref='home']",
            required=False,
        ):
            if self._wait_for_any_visible(
                page,
                self._selector_list("normal_vote_button", self._selector("vote_menu_link")),
                timeout_ms=self._op_timeout_ms(),
                poll_ms=150,
            ):
                return page

        if not self._is_login_form_visible(page):
            page = self._goto(page, login_url, wait_until="domcontentloaded")
        page = self._login(page, login_url)
        self._stabilize_post_login_view(page)
        if not self._is_menu_ready(page):
            raise IpatEntryError(f"ログイン後の投票メニュー表示に失敗しました (url={getattr(page, 'url', '-')})")
        return page

    def _is_local_login_form_visible(self, page) -> bool:
        member_number = self._selector("login_member_number_input", "#MEMBERNUMR")
        member_id = self._selector("login_member_id_input", "#MEMBERIDR")
        return self._is_visible(page, member_number) and self._is_visible(page, member_id)

    def _is_local_home_ready(self, page) -> bool:
        return self._wait_for_any_visible(
            page,
            self._selector_list(
                "local_kaisai_section",
                self._selector("local_race_table"),
            ),
            timeout_ms=1500,
            poll_ms=120,
        )

    def _is_local_popup_visible(self, page) -> bool:
        popup_selectors = self._selector_list(
            "local_popup_selector",
            "div#popupscreen.popup-screen",
            "div.popup-screen",
        )
        for sel in popup_selectors:
            if self._is_visible(page, sel):
                return True
        close_selectors = self._selector_list(
            "local_popup_close_button",
            "div#popupscreen input.close-btn[value='閉じる']",
            "div#popupscreen input[type='button'][value='閉じる']",
            "div.popup-screen input.close-btn",
            "div.popup-screen input[type='button'][value='閉じる']",
        )
        for sel in close_selectors:
            if self._is_visible(page, sel):
                return True
        try:
            return bool(
                page.evaluate(
                    """
                    () => {
                      const popups = Array.from(document.querySelectorAll('#popupscreen, .popup-screen'));
                      for (const el of popups) {
                        if (!el) continue;
                        const style = window.getComputedStyle(el);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                          return true;
                        }
                      }
                      return false;
                    }
                    """
                )
            )
        except Exception:
            return False

    def _dismiss_local_popup_if_present(self, page) -> bool:
        if not self._is_local_popup_visible(page):
            return False
        self._emit("SPAT4ポップアップを検知。『閉じる』を押して続行します")

        if self._click_first_visible(
            page,
            "local_popup_close_button",
            "div#popupscreen input.close-btn[value='閉じる']",
            "div#popupscreen input[type='button'][value='閉じる']",
            "div.popup-screen input.close-btn[value='閉じる']",
            "div.popup-screen input[type='button'][value='閉じる']",
            "input.close-btn[value='閉じる']",
            "input[type='button'][value='閉じる']",
            required=False,
        ):
            page.wait_for_timeout(220)
            return True

        try:
            action = page.evaluate(
                """
                () => {
                  try {
                    if (window.WPKaisai && typeof window.WPKaisai.NoticePopupClose === 'function') {
                      window.WPKaisai.NoticePopupClose();
                      return 'WPKaisai.NoticePopupClose';
                    }
                  } catch (e) {}
                  try {
                    const popups = Array.from(document.querySelectorAll('#popupscreen, .popup-screen'));
                    for (const popup of popups) {
                      if (!popup) continue;
                      const style = window.getComputedStyle(popup);
                      if (style.display === 'none' || style.visibility === 'hidden') continue;
                      const btns = Array.from(popup.querySelectorAll("input[type='button'], input.close-btn, button"));
                      for (const btn of btns) {
                        const value = String(btn.value || btn.textContent || '').trim();
                        if (value.includes('閉じる') || value.toLowerCase().includes('close')) {
                          btn.click();
                          return 'button.click';
                        }
                      }
                    }
                  } catch (e) {}
                  return 'none';
                }
                """
            )
            self._emit(f"SPAT4ポップアップフォールバック実行: {action}")
            page.wait_for_timeout(240)
            return str(action or "none") != "none"
        except Exception:
            return False

    def _is_local_mail_notice_visible(self, page) -> bool:
        return self._is_visible(
            page,
            self._selector(
                "local_mail_notice_selector",
                "div.mailAuth:has-text('メールアドレスの認証システムを導入しました')",
            ),
        ) or self._is_visible(
            page,
            self._selector(
                "local_mail_notice_vote_button",
                "input#goKaisai[value='投票へすすむ']",
            ),
        )

    def _dismiss_local_mail_notice_if_present(self, page) -> bool:
        if not self._is_local_mail_notice_visible(page):
            return False
        self._emit("SPAT4お知らせ画面を検知。『投票へすすむ』を押して続行します")

        if self._click_first_visible(
            page,
            "local_mail_notice_vote_button",
            "input#goKaisai[value='投票へすすむ']",
            "div.mailAuth input[type='button'][value='投票へすすむ']",
            required=False,
        ):
            page.wait_for_timeout(240)
            return True

        try:
            action = page.evaluate(
                """
                () => {
                  try {
                    const btn = document.getElementById('goKaisai');
                    if (btn) {
                      btn.click();
                      return 'goKaisai.click';
                    }
                  } catch (e) {}
                  try {
                    if (typeof clickGoKaisai === 'function') {
                      clickGoKaisai();
                      return 'clickGoKaisai';
                    }
                  } catch (e) {}
                  try {
                    const btn = Array.from(document.querySelectorAll("input[type='button']")).find((el) => String(el.value || '').trim() === '投票へすすむ');
                    if (btn) {
                      btn.click();
                      return 'button.click';
                    }
                  } catch (e) {}
                  return 'none';
                }
                """
            )
            self._emit(f"SPAT4お知らせ画面フォールバック実行: {action}")
            page.wait_for_timeout(260)
            return str(action or "none") != "none"
        except Exception:
            return False

    def _collect_local_notice_debug(self, page) -> Dict[str, Any]:
        popup_visible = bool(self._is_local_popup_visible(page))
        mail_notice_visible = bool(self._is_local_mail_notice_visible(page))
        refresh_btn = self._first_visible(
            page,
            self._selector(
                "local_refresh_button",
                "span.btn_update a:has-text('情報更新'), a:has-text('情報更新'), input[type='button'][value='情報更新']",
            ),
        )
        refresh_button_visible = refresh_btn is not None
        popup_title = ""
        try:
            popup_title = str(
                page.evaluate(
                    """
                    () => {
                      const node = document.querySelector('#popupscreen .poptitle, .popup-screen .poptitle');
                      return String((node && node.textContent) || '').trim();
                    }
                    """
                )
                or ""
            ).strip()
        except Exception:
            popup_title = ""
        return {
            "url": str(getattr(page, "url", "") or ""),
            "popup_visible": popup_visible,
            "mail_notice_visible": mail_notice_visible,
            "refresh_button_visible": refresh_button_visible,
            "popup_title": popup_title,
        }

    def _emit_local_notice_debug(self, page, phase: str) -> Dict[str, Any]:
        info = self._collect_local_notice_debug(page)
        title = str(info.get("popup_title", "") or "").strip()
        title_suffix = f" popup_title={title}" if title else ""
        self._emit(
            "SPAT4通知デバッグ"
            f"[{phase}]"
            f" url={info.get('url', '-')}"
            f" popup={bool(info.get('popup_visible'))}"
            f" mail_notice={bool(info.get('mail_notice_visible'))}"
            f" refresh_button={bool(info.get('refresh_button_visible'))}"
            f"{title_suffix}"
        )
        return info

    def _dismiss_local_interrupts_if_present(self, page) -> bool:
        dismissed_any = False
        for _ in range(4):
            changed = False
            if self._dismiss_local_popup_if_present(page):
                changed = True
                dismissed_any = True
            if self._dismiss_local_mail_notice_if_present(page):
                changed = True
                dismissed_any = True
            if not changed:
                break
        return dismissed_any

    def _wait_local_post_login_ready(self, page, timeout_ms: int) -> None:
        end = datetime.now().timestamp() + (max(4000, int(timeout_ms)) / 1000.0)
        while datetime.now().timestamp() < end:
            if self._dismiss_local_interrupts_if_present(page):
                continue
            if self._is_local_home_ready(page):
                return
            page.wait_for_timeout(120)
        raise IpatEntryError(f"SPAT4ログイン後の開催画面表示に失敗しました (url={getattr(page, 'url', '-')})")

    def _login_local(self, page, login_url: str):
        self._emit(f"ログインURLへアクセス: {login_url}")
        page = self._goto(page, login_url, wait_until="domcontentloaded")

        self._fill_any(
            page,
            "login_member_number_input",
            str(getattr(self._ipat_settings, "member_number", "") or ""),
            "#MEMBERNUMR",
        )
        self._fill_any(
            page,
            "login_member_id_input",
            str(getattr(self._ipat_settings, "member_id", "") or ""),
            "#MEMBERIDR",
        )

        self._emit("SPAT4ログインボタン押下")
        self._trigger_local_login(page)
        self._wait_local_post_login_ready(
            page,
            timeout_ms=max(10000, self._op_timeout_ms(scale=4000)),
        )
        self._emit("SPAT4ログイン完了")
        return page

    def _trigger_local_login(self, page) -> None:
        selectors = self._selector_candidates(
            "login_button",
            "a.loginbtn",
            "a[onclick*='loginCheck']",
        )

        # 1) 通常クリック
        if self._click_first_visible(
            page,
            "login_button",
            "a.loginbtn",
            "a[onclick*='loginCheck']",
            required=False,
        ):
            page.wait_for_timeout(220)
            if self._is_local_home_ready(page) or self._is_local_mail_notice_visible(page) or self._is_local_popup_visible(page):
                return

        # 2) force クリック
        for sel in selectors:
            node = self._first_visible(page, sel)
            if node is None:
                continue
            try:
                node.click(force=True)
                page.wait_for_timeout(240)
                if self._is_local_home_ready(page) or self._is_local_mail_notice_visible(page) or self._is_local_popup_visible(page):
                    return
            except Exception:
                continue

        # 3) ページ内JS: loginCheck() / form.submit()
        try:
            action = page.evaluate(
                """
                () => {
                  try {
                    if (typeof loginCheck === 'function') {
                      const ret = loginCheck();
                      return `loginCheck:${String(ret)}`;
                    }
                  } catch (e) {}
                  try {
                    const form = document.forms['LOGIN'] || document.querySelector("form[name='LOGIN']");
                    if (form) {
                      form.submit();
                      return 'form.submit';
                    }
                  } catch (e) {}
                  try {
                    const a = document.querySelector("a.loginbtn");
                    if (a) {
                      a.click();
                      return 'anchor.click';
                    }
                  } catch (e) {}
                  return 'none';
                }
                """
            )
            self._emit(f"SPAT4ログイン押下フォールバック実行: {action}")
        except Exception:
            pass

    def _ensure_logged_in_local(self, page, login_url: str):
        if self._dismiss_local_interrupts_if_present(page):
            self._wait_local_post_login_ready(
                page,
                timeout_ms=max(6000, self._op_timeout_ms(scale=2500)),
            )
            return page
        if self._is_local_home_ready(page):
            return page
        if not self._is_local_login_form_visible(page):
            page = self._goto(page, login_url, wait_until="domcontentloaded")
            if self._dismiss_local_interrupts_if_present(page):
                self._wait_local_post_login_ready(
                    page,
                    timeout_ms=max(6000, self._op_timeout_ms(scale=2500)),
                )
                return page
        return self._login_local(page, login_url)

    def _local_refresh_info(self, page) -> bool:
        self._dismiss_local_interrupts_if_present(page)
        clicked = self._click_first_visible(
            page,
            "local_refresh_button",
            "span.btn_update a:has-text('情報更新')",
            "a:has-text('情報更新')",
            "input[type='button'][value='情報更新']",
            required=False,
        )
        if not clicked:
            try:
                action = page.evaluate(
                    """
                    () => {
                      try {
                        const candidates = Array.from(document.querySelectorAll("span.btn_update a, a, input[type='button']"));
                        for (const el of candidates) {
                          const text = String(el.value || el.textContent || '').trim();
                          if (text !== '情報更新') continue;
                          if (typeof el.click === 'function') {
                            el.click();
                            return 'click';
                          }
                        }
                      } catch (e) {}
                      return 'none';
                    }
                    """
                )
                if str(action or "none") != "none":
                    self._emit(f"SPAT4待機維持: 情報更新フォールバック実行: {action}")
                    clicked = True
            except Exception:
                clicked = False
        if not clicked:
            self._emit("SPAT4待機維持: 情報更新ボタンを押せませんでした")
            return False
        page.wait_for_timeout(250)
        self._dismiss_local_interrupts_if_present(page)
        self._wait_local_post_login_ready(
            page,
            timeout_ms=max(6000, self._op_timeout_ms(scale=2500)),
        )
        return True

    def refresh_local_info(self) -> Dict[str, Any]:
        if self.target != "local":
            return {"ok": False, "status": "skip_not_local"}

        self._ensure_selectors_configured()
        login_url = self._validate_ipat_settings()
        page = self._ensure_page()
        page = self._ensure_logged_in_local(page, login_url) or page
        debug_before = self._emit_local_notice_debug(page, "before_refresh")
        refreshed = self._local_refresh_info(page)
        if refreshed:
            self._emit("SPAT4待機維持: 情報更新を実行しました")
            debug_after = self._emit_local_notice_debug(page, "after_refresh")
            return {
                "ok": True,
                "status": "refreshed",
                "debug_before": debug_before,
                "debug_after": debug_after,
            }
        self._emit_local_notice_debug(page, "refresh_button_not_found")
        return {
            "ok": True,
            "status": "ready_no_refresh_button",
            "debug_before": debug_before,
        }

    def refresh_central_info(self) -> Dict[str, Any]:
        if self.target == "local":
            return {"ok": False, "status": "skip_not_central"}

        self._ensure_selectors_configured()
        login_url = self._validate_ipat_settings()
        page = self._ensure_page()

        if self._is_kyoutei_mode(login_url):
            page = self._ensure_logged_in_kyoutei(page, login_url)
            try:
                page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
            self._kyoutei_wait_top_page_ready(page)
            self._page = page
            self._emit("BOAT RACE待機維持: TOPを更新しました")
            return {
                "ok": True,
                "status": "refreshed",
                "url": str(getattr(page, "url", "") or ""),
            }

        if not self._is_keirin_mode(login_url):
            return {
                "ok": True,
                "status": "skip_non_central_mode",
                "url": str(getattr(page, "url", "") or ""),
            }

        top_url = str(login_url or "").strip() or "https://keirin.jp/pc/top"
        page = self._ensure_logged_in_keirin(page, top_url) or page
        page = self._goto(page, top_url, wait_until="domcontentloaded")
        if not self._is_keirin_logged_in(page):
            page = self._ensure_logged_in_keirin(page, top_url) or page
        self._emit("KEIRIN.JP待機維持: TOPを更新しました")
        return {
            "ok": True,
            "status": "refreshed",
            "url": str(getattr(page, "url", "") or ""),
        }

    def prepare_vote_menu(self) -> Dict[str, Any]:
        self._ensure_selectors_configured()
        login_url = self._validate_ipat_settings()
        page = self._ensure_page()
        self._last_debug_context = {}
        try:
            if self.target == "local":
                self._emit("事前準備: SPAT4へログイン")
                page = self._ensure_logged_in_local(page, login_url) or page
                self._emit("事前準備完了: SPAT4開催画面で待機中")
            elif self._is_kyoutei_mode(login_url):
                self._emit("事前準備: BOAT RACEへログイン")
                page = self._ensure_logged_in_kyoutei(page, login_url)
                self._page = page
                self._emit("事前準備完了: 競艇TOP画面で待機中")
            elif self._is_keirin_mode(login_url):
                self._emit("事前準備: KEIRIN.JPへログイン")
                page = self._ensure_logged_in_keirin(page, login_url) or page
                self._emit("事前準備完了: 競輪TOP画面で待機中")
            else:
                self._emit("事前準備: 投票メニューまで遷移")
                page = self._ensure_logged_in(page, login_url) or page
                self._emit("事前準備完了: 通常投票開始前で待機中")
            return {
                "ok": True,
                "status": "ready",
                "url": str(getattr(page, "url", "") or ""),
            }
        except IpatEntryError as exc:
            debug_dir = self._save_debug_artifacts(page, str(exc))
            raise IpatEntryError(f"{exc} (debug: {debug_dir})") from exc
        except Exception as exc:
            debug_dir = self._save_debug_artifacts(page, repr(exc))
            raise IpatEntryError(f"予期しない例外: {exc} (debug: {debug_dir})") from exc


    def execute(self, payload: Dict[str, Any], tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not tickets:
            return {"status": "skip", "reason": "no_tickets"}

        self._ensure_selectors_configured()
        login_url = self._validate_ipat_settings()

        normalized = [_normalize_ticket(t) for t in tickets]
        total_yen = int(sum(int(r["bet_yen"]) for r in normalized))

        self._emit(
            "発注開始 "
            f"race={(payload.get('race') or {}).get('race_id', '-')}"
            f" tickets={len(normalized)} total={total_yen:,}円"
        )
        page = self._ensure_page()
        self._last_debug_context = {}
        try:
            if self.target == "local":
                page = self._ensure_logged_in_local(page, login_url) or page
                result = self._execute_local(page, payload, normalized, total_yen)
                self._emit(f"発注処理完了 status={result.get('status')}")
                return result
            if self._is_kyoutei_mode(login_url):
                page = self._ensure_logged_in_kyoutei(page, login_url)
                self._page = page
                result = self._execute_kyoutei(page, payload, normalized, total_yen)
                self._emit(f"発注処理完了 status={result.get('status')}")
                return result
            if self._is_keirin_mode(login_url):
                page = self._ensure_logged_in_keirin(page, login_url) or page
                result = self._execute_keirin(page, payload, normalized, total_yen)
                self._emit(f"発注処理完了 status={result.get('status')}")
                return result

            page = self._ensure_logged_in(page, login_url) or page
            self._emit("通常投票ページへ遷移")
            page = self._move_vote_page(page) or page
            self._emit("場名・レース選択")
            self._select_course_and_race(page, payload)
            for row in normalized:
                self._emit(f"買い目入力: {row.get('market')} {row.get('combo')} {int(row.get('bet_yen', 0)):,}円")
                self._input_ticket(page, row)
            moved_to_purchase = self._finish_input(page)
            if bool(self._ipat_settings.submit_enabled):
                if not moved_to_purchase:
                    raise IpatEntryError("購入予定リストへ遷移できませんでした")
                self._emit("購入確定処理を実行")
                self._submit(page, normalized, total_yen)
                status = "submitted"
            else:
                status = "prepared"
            self._emit(f"発注処理完了 status={status}")
            return {
                "status": status,
                "ticket_count": len(normalized),
                "total_yen": total_yen,
            }
        except IpatRaceCancelledError as exc:
            if self.target == "local":
                raise IpatEntryError(str(exc)) from exc
            back_ok = self._return_to_main_menu(
                page,
                timeout_ms=self._op_timeout_ms(),
            )
            if back_ok:
                self._emit("馬番選択不可を競走中止扱いとして購入を中断し、メインメニューへ戻りました")
            else:
                self._emit("馬番選択不可を競走中止扱いとして購入を中断しました（メインメニュー復帰確認は未完了）")
            return {
                "status": "cancelled_race",
                "reason": str(exc),
                "ticket_count": len(normalized),
                "total_yen": total_yen,
            }
        except IpatRaceUnavailableError as exc:
            if self._is_kyoutei_mode(login_url):
                if self._kyoutei_return_top(page):
                    self._emit("競艇: 対象レース未発売/締切のためトップへ戻りました")
                else:
                    self._emit("競艇: 対象レース未発売/締切を検知しましたがトップ復帰に失敗しました")
            elif self._is_keirin_mode(login_url):
                if self._keirin_return_top(page):
                    self._emit("競輪: 対象レース未発売/締切のためトップへ戻りました")
                else:
                    self._emit("競輪: 対象レース未発売/締切を検知しましたがトップ復帰に失敗しました")
            self._emit(f"{self._target_label()}: 対象レース未発売/締切のため見送りました")
            return {
                "status": "unavailable_race",
                "reason": str(exc),
                "ticket_count": len(normalized),
                "total_yen": total_yen,
            }
        except IpatEntryError as exc:
            debug_dir = self._save_debug_artifacts(page, str(exc))
            if self._is_kyoutei_mode(login_url):
                self._kyoutei_dismiss_popup(page)
            elif self._is_keirin_mode(login_url):
                if self._keirin_is_insufficient_funds_message(str(exc)) or self._keirin_has_insufficient_funds_state(page):
                    if self._keirin_return_top(page):
                        self._emit("競輪: 資金不足/限度額超過のためトップへ戻りました")
                    else:
                        self._emit("競輪: 資金不足/限度額超過を検知しましたがトップ復帰に失敗しました")
                else:
                    self._keirin_dismiss_confirm_dialog(page)
            raise IpatEntryError(f"{exc} (debug: {debug_dir})") from exc
        except Exception as exc:
            debug_dir = self._save_debug_artifacts(page, repr(exc))
            raise IpatEntryError(f"予期しない例外: {exc} (debug: {debug_dir})") from exc

    def _parse_number_text(self, value: Any, default: int = 0) -> int:
        text = str(value or "")
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return int(default)
        return _safe_int(digits, default)

    def _kyoutei_pages(self, page) -> List[Any]:
        pages: List[Any] = []
        if page is not None:
            pages.append(page)
        try:
            context_pages = list(getattr(self._context, "pages", []) or [])
        except Exception:
            context_pages = []
        for item in context_pages:
            if item is not None and item not in pages:
                pages.append(item)
        return pages

    def _kyoutei_top_ready_selectors(self) -> List[str]:
        return self._selector_list(
            "kyoutei_top_ready_selector",
            "#todayForm",
            "#beforeForm",
            "#jyoInfos",
            "#jyoInfosTab",
            "#raceSelection",
            "#toplogoForm",
        )

    def _kyoutei_confirm_ready_selectors(self) -> List[str]:
        return self._selector_list(
            "kyoutei_confirm_ready_selector",
            "#confirmationArea",
            "#betconfForm",
            "#amount",
            "#pass",
        )

    def _kyoutei_complete_selectors(self) -> List[str]:
        return self._selector_list(
            "kyoutei_complete_selector",
            "#sameJyoBet",
            "#modifyJyoBetForm",
            "#voteListAreaInner",
        )

    def _kyoutei_current_url(self, page) -> str:
        try:
            return str(getattr(page, "url", "") or "").strip().lower()
        except Exception:
            return ""

    def _kyoutei_is_top_url(self, page) -> bool:
        current_url = self._kyoutei_current_url(page)
        return "ib.mbrace.or.jp" in current_url and "/service/bet/top/" in current_url

    def _kyoutei_is_logged_in(self, page) -> bool:
        if self._kyoutei_is_top_url(page):
            return True
        if self._wait_for_any_visible(
            page,
            self._kyoutei_top_ready_selectors(),
            timeout_ms=500,
            poll_ms=80,
        ):
            return True
        return self._wait_for_any_visible(
            page,
            self._selector_list(
                "kyoutei_logout_selector",
                "a:has-text('ログアウト')",
                "button:has-text('ログアウト')",
                "text=ログアウト",
            ),
            timeout_ms=300,
            poll_ms=80,
        )

    def _kyoutei_is_top_page(self, page) -> bool:
        if self._kyoutei_is_top_url(page):
            return True
        return self._wait_for_any_visible(
            page,
            self._selector_list("kyoutei_venue_list_selector", "#jyoInfos li", "#jyoInfosTab li", "#todayForm", "#beforeForm"),
            timeout_ms=500,
            poll_ms=80,
        )

    def _kyoutei_wait_top_page_ready(self, page) -> None:
        if self._kyoutei_is_top_page(page):
            return
        if not self._wait_for_any_visible(
            page,
            self._kyoutei_top_ready_selectors(),
            timeout_ms=max(5000, self._op_timeout_ms(scale=3000)),
            poll_ms=120,
        ):
            raise IpatEntryError(f"競艇TOP画面の初期化待機に失敗しました (url={getattr(page, 'url', '-')})")

    def _kyoutei_dismiss_popup(self, page) -> bool:
        if not self._wait_for_any_visible(
            page,
            self._selector_list("kyoutei_popup_selector", "#popup"),
            timeout_ms=600,
            poll_ms=80,
        ):
            return False
        if self._click_any(page, "kyoutei_popup_ok_button", "#ok", "#close", required=False):
            page.wait_for_timeout(240)
            return True
        return False

    def _kyoutei_find_active_page(self, page):
        for candidate in self._kyoutei_pages(page):
            try:
                if self._kyoutei_is_logged_in(candidate):
                    return candidate
            except Exception:
                continue
        return None

    def _ensure_logged_in_kyoutei(self, page, login_url: str):
        active = self._kyoutei_find_active_page(page)
        if active is not None:
            self._page = active
            return active

        page = self._goto(page, login_url, wait_until="domcontentloaded")
        active = self._kyoutei_find_active_page(page)
        if active is not None:
            self._page = active
            return active

        if not self._wait_for_any_visible(
            page,
            self._selector_list(
                "kyoutei_member_no_input",
                "#memberNo",
                "#pin",
                "#authPassword",
                "#loginButton",
            ),
            timeout_ms=max(4000, self._op_timeout_ms(scale=2500)),
            poll_ms=100,
        ):
            raise IpatEntryError(f"競艇ログインフォームを検出できませんでした (url={getattr(page, 'url', '-')})")

        self._fill_any(page, "kyoutei_member_no_input", str(getattr(self._ipat_settings, "inet_id", "") or ""), "#memberNo")
        self._fill_any(page, "kyoutei_pin_input", str(getattr(self._ipat_settings, "pars_no", "") or ""), "#pin")
        self._fill_any(
            page,
            "kyoutei_auth_password_input",
            str(getattr(self._ipat_settings, "password", "") or ""),
            "#authPassword",
        )

        popup_page = None
        try:
            with page.expect_popup(timeout=max(4000, self._op_timeout_ms(scale=2500))) as popup_info:
                self._click_any(page, "kyoutei_login_button", "#loginButton")
            popup_page = popup_info.value
        except Exception:
            self._click_any(page, "kyoutei_login_button", "#loginButton")
            page.wait_for_timeout(800)

        if popup_page is not None:
            try:
                popup_page.wait_for_load_state("domcontentloaded")
            except Exception:
                pass

        active = popup_page or self._kyoutei_find_active_page(page) or page
        self._kyoutei_wait_top_page_ready(active)
        self._page = active
        return active

    def _kyoutei_return_top(self, page) -> bool:
        if self._kyoutei_is_top_page(page):
            return True
        try:
            moved = page.evaluate(
                """
                () => {
                  const form = document.querySelector('#toplogoForm');
                  if (form) {
                    form.submit();
                    return true;
                  }
                  return false;
                }
                """
            )
            if moved:
                self._kyoutei_wait_top_page_ready(page)
                return self._kyoutei_is_top_page(page)
        except Exception:
            pass
        return False

    def _kyoutei_venue_code(self, venue_name: str) -> str:
        text = str(venue_name or "").strip()
        aliases = {
            "琵琶湖": "びわこ",
        }
        text = aliases.get(text, text)
        return str(KYOUTEI_VENUE_CODE_MAP.get(text, "") or "")

    def _kyoutei_open_target_race(self, page, payload: Dict[str, Any]) -> None:
        race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
        venue_name = str(race.get("venue_name", "") or "").strip()
        race_num = _safe_int(race.get("race_num"), 0)
        if not venue_name or race_num <= 0:
            raise IpatEntryError("競艇レース情報が不正です（venue_name/race_num）")
        jyo_code = self._kyoutei_venue_code(venue_name)
        if not jyo_code:
            raise IpatEntryError(f"競艇場コードを解決できませんでした: {venue_name}")

        if not self._kyoutei_is_top_page(page) and (not self._kyoutei_return_top(page)):
            raise IpatEntryError("競艇TOP画面へ戻れませんでした")

        try:
            moved = page.evaluate(
                """
                (payload) => {
                  const form = document.querySelector('#todayForm') || document.querySelector('#beforeForm');
                  if (!form) return false;
                  const jyoCode = form.querySelector("input[name='jyoCode']");
                  const operationKbn = form.querySelector("input[name='operationKbn']");
                  if (!jyoCode || !operationKbn) return false;
                  jyoCode.value = payload.jyoCode;
                  operationKbn.value = '2';
                  form.submit();
                  return true;
                }
                """,
                {"jyoCode": jyo_code},
            )
        except Exception as exc:
            raise IpatEntryError(f"競艇場選択フォーム送信に失敗しました: {venue_name}") from exc
        if not moved:
            raise IpatEntryError(f"競艇場選択フォームが見つかりませんでした: {venue_name}")

        if not self._wait_for_any_visible(
            page,
            self._selector_list("kyoutei_race_tab_selector", "#raceSelection .raceSelTab", "#raceSelection li"),
            timeout_ms=max(5000, self._op_timeout_ms(scale=3000)),
            poll_ms=120,
        ):
            raise IpatEntryError(f"競艇レース選択タブが見つかりませんでした: {venue_name}")

        try:
            clicked = page.evaluate(
                """
                (payload) => {
                  const targetId = 'selRaceNo' + String(payload.raceNum).padStart(2, '0');
                  const targetText = String(payload.raceNum) + 'R';
                  const nodes = Array.from(document.querySelectorAll('#raceSelection .raceSelTab, #raceSelection li'));
                  const exact = document.getElementById(targetId);
                  if (exact) {
                    exact.click();
                    return true;
                  }
                  for (const node of nodes) {
                    const text = String(node.textContent || '').replace(/\\s+/g, '');
                    if (text.includes(targetText)) {
                      node.click();
                      return true;
                    }
                  }
                  return false;
                }
                """,
                {"raceNum": int(race_num)},
            )
        except Exception as exc:
            raise IpatEntryError(f"競艇レース選択に失敗しました: {venue_name} {race_num}R") from exc
        if not clicked:
            raise IpatRaceUnavailableError(f"対象レースの選択タブが見つかりませんでした: {venue_name} {race_num}R")

        if not self._wait_for_any_visible(
            page,
            self._selector_list("kyoutei_bet_page_ready_selector", "#betlist", "#raceSelection"),
            timeout_ms=max(5000, self._op_timeout_ms(scale=3000)),
            poll_ms=120,
        ):
            raise IpatEntryError(f"競艇投票画面の初期化待機に失敗しました: {venue_name} {race_num}R")

        try:
            page.evaluate(
                """
                () => {
                  try {
                    if (window.BOAT && BOAT.betlist_service && typeof BOAT.betlist_service.deleteBetAll === 'function') {
                      BOAT.betlist_service.deleteBetAll();
                    }
                    if (window.BOAT && BOAT.betlist_controller && typeof BOAT.betlist_controller.draw === 'function') {
                      BOAT.betlist_controller.draw(true);
                    }
                  } catch (e) {}
                }
                """
            )
        except Exception:
            pass

    def _kyoutei_kachishiki(self, market: str) -> str:
        canonical = _canonical_market_name(market)
        return str(KYOUTEI_KACHISHIKI_MAP.get(canonical, "") or "")

    def _kyoutei_add_ticket(self, page, ticket: Dict[str, Any]) -> None:
        market = _canonical_market_name(str(ticket.get("market", "") or ""))
        numbers = [str(int(n)) for n in ticket.get("numbers", [])]
        bet_yen = int(ticket.get("bet_yen", 0) or 0)
        kachishiki = self._kyoutei_kachishiki(market)
        if not kachishiki:
            raise IpatEntryError(f"競艇未対応券種を検出しました: {market}")
        if bet_yen <= 0 or (bet_yen % 100) != 0:
            raise IpatEntryError(f"競艇買い目金額は100円単位が必要です: {bet_yen}")

        result = page.evaluate(
            """
            (payload) => {
              try {
                if (!(window.BOAT && BOAT.reg_service && typeof BOAT.reg_service.addBet === 'function')) {
                  return { ok: false, error: 'BOAT.reg_service.addBet unavailable' };
                }
                const res = BOAT.reg_service.addBet(payload.numberOfSheets, payload.kachishiki, '1', payload.selectList, false) || {};
                try {
                  if (BOAT.betlist_controller && typeof BOAT.betlist_controller.draw === 'function') {
                    BOAT.betlist_controller.draw(true);
                  }
                } catch (e) {}
                return {
                  ok: !res.isErrorDisp,
                  isAlertDisp: !!res.isAlertDisp,
                  alertCode: String(res.alertCode || ''),
                  isErrorDisp: !!res.isErrorDisp,
                  errorCode: String(res.errorCode || ''),
                  errorReplaceString: String(res.errorReplaceString || ''),
                };
              } catch (e) {
                return { ok: false, error: String(e) };
              }
            }
            """,
            {
                "numberOfSheets": bet_yen // 100,
                "kachishiki": kachishiki,
                "selectList": numbers,
            },
        )
        if not isinstance(result, dict):
            raise IpatEntryError(f"競艇買い目追加に失敗しました: {market} {'-'.join(numbers)}")
        if str(result.get("error", "") or "").strip():
            raise IpatEntryError(f"競艇買い目追加に失敗しました: {result.get('error')}")
        if bool(result.get("isErrorDisp")):
            raise IpatEntryError(
                f"競艇買い目追加エラー code={str(result.get('errorCode', '') or '-')}"
                f" detail={str(result.get('errorReplaceString', '') or '-')}"
            )

    def _kyoutei_move_to_confirm(self, page) -> None:
        moved = False
        if self._click_any(
            page,
            "kyoutei_betlist_submit_button",
            "#betlist .btnSubmit",
            "#betlist .betlistbtn.submit",
            required=False,
        ):
            moved = True
        if not moved:
            try:
                moved = bool(
                    page.evaluate(
                        """
                        () => {
                          try {
                            if (window.BOAT && BOAT.betlist_controller && typeof BOAT.betlist_controller.betlistSubmit === 'function') {
                              BOAT.betlist_controller.betlistSubmit();
                              return true;
                            }
                          } catch (e) {}
                          return false;
                        }
                        """
                    )
                )
            except Exception:
                moved = False
        if not moved:
            raise IpatEntryError("競艇の投票内容確認導線を押せませんでした")
        if not self._wait_for_any_visible(
            page,
            self._kyoutei_confirm_ready_selectors(),
            timeout_ms=max(5000, self._op_timeout_ms(scale=3000)),
            poll_ms=120,
        ):
            raise IpatEntryError("競艇の投票内容確認画面に遷移できませんでした")

    def _kyoutei_submit(self, page, total_yen: int) -> None:
        self._kyoutei_move_to_confirm(page)
        self._wait_for_selector_attached(page, "#betconfForm", timeout_ms=2000)
        self._wait_for_selector_attached(page, "#amount", timeout_ms=1200)
        self._wait_for_selector_attached(page, "#pass", timeout_ms=1200)
        self._fill_any_logged(
            page,
            "kyoutei_confirm_amount_input",
            str(int(total_yen)),
            "#amount",
            "#betconfForm input[name='betAmount']",
            "#betconfForm input.inputAmount",
        )
        self._fill_any_logged(
            page,
            "kyoutei_confirm_pass_input",
            str(getattr(self._ipat_settings, "login_id", "") or ""),
            "#pass",
            "#betconfForm input[name='betPassword']",
            "#betconfForm input.inputPass",
        )
        if not self._click_first_visible(page, "kyoutei_submit_button", "#submitBet a", "#submitBet", required=False):
            try:
                page.evaluate(
                    """
                    () => {
                      const btn = document.querySelector('#submitBet a') || document.querySelector('#submitBet');
                      if (btn) btn.click();
                    }
                    """
                )
            except Exception as exc:
                raise IpatEntryError("競艇の投票実行ボタン押下に失敗しました") from exc
        self._kyoutei_dismiss_popup(page)
        if not self._wait_for_any_visible(
            page,
            self._kyoutei_complete_selectors(),
            timeout_ms=max(5000, self._op_timeout_ms(scale=3000)),
            poll_ms=120,
        ):
            raise IpatEntryError("競艇の投票完了画面を確認できませんでした")

    def _execute_kyoutei(
        self,
        page,
        payload: Dict[str, Any],
        tickets: List[Dict[str, Any]],
        total_yen: int,
    ) -> Dict[str, Any]:
        self._kyoutei_open_target_race(page, payload)
        for row in tickets:
            self._emit(
                f"競艇買い目入力: {row.get('market')} {row.get('combo')} {int(row.get('bet_yen', 0)):,}円"
            )
            self._kyoutei_add_ticket(page, row)
        if not bool(self._ipat_settings.submit_enabled):
            self._kyoutei_move_to_confirm(page)
            self._emit("競艇: 投票内容確認画面で待機します")
            return {
                "status": "prepared",
                "ticket_count": len(tickets),
                "total_yen": total_yen,
            }
        self._kyoutei_submit(page, total_yen=total_yen)
        return {
            "status": "submitted",
            "ticket_count": len(tickets),
            "total_yen": total_yen,
        }

    def _is_keirin_logged_in(self, page) -> bool:
        if self._wait_for_any_visible(
            page,
            self._selector_list("keirin_login_success_selector", "#loginbox2"),
            timeout_ms=800,
            poll_ms=80,
        ):
            return True
        return False

    def _ensure_logged_in_keirin(self, page, login_url: str):
        if self._is_keirin_logged_in(page):
            self._emit("KEIRIN.JPログイン状態を確認済み")
            return page

        self._emit(f"競輪ログインページへアクセス: {login_url}")
        page = self._goto(page, login_url, wait_until="domcontentloaded")

        if self._is_keirin_logged_in(page):
            self._emit("競輪ログイン状態を確認済み")
            return page

        login_id_sel = self._selector("keirin_login_id_input", "#trtxtBallotID")
        password_sel = self._selector("keirin_login_password_input", "#trtxtBallotPW")
        if not self._wait_for_any_visible(page, [login_id_sel, password_sel], timeout_ms=self._op_timeout_ms(scale=2000)):
            raise IpatEntryError(
                "競輪ログインフォームを検出できませんでした "
                f"(url={getattr(page, 'url', '-')})"
            )

        self._fill_any(page, "keirin_login_id_input", str(getattr(self._ipat_settings, "inet_id", "") or ""), "#trtxtBallotID")
        self._fill_any(
            page,
            "keirin_login_password_input",
            str(getattr(self._ipat_settings, "password", "") or ""),
            "#trtxtBallotPW",
        )
        self._emit("競輪ログイン情報入力完了")
        self._click_any(
            page,
            "keirin_login_button",
            "form[action*='LoginServlet'] input[type='submit'][value='ログイン']",
            "#loginbox1 input[type='submit'][value='ログイン']",
        )
        self._emit("競輪ログインボタン押下")

        if not self._wait_for_any_visible(
            page,
            self._selector_list("keirin_login_success_selector", "#loginbox2"),
            timeout_ms=max(4000, self._op_timeout_ms(scale=2500)),
            poll_ms=120,
        ):
            raise IpatEntryError(
                "競輪ログイン後の状態確認に失敗しました "
                f"(url={getattr(page, 'url', '-')})"
            )
        self._emit("競輪ログイン成功")
        return page

    def _keirin_wait_vote_page_ready(self, page) -> None:
        selectors = self._selector_list(
            "keirin_vote_page_ready_selector",
            "select[name='cmbKakesiki']",
            "#kai",
            "#bet_right",
        )
        if not self._wait_for_any_visible(
            page,
            selectors,
            timeout_ms=max(5000, self._op_timeout_ms(scale=3000)),
            poll_ms=120,
        ):
            raise IpatEntryError(f"競輪投票画面の初期化待機に失敗しました (url={getattr(page, 'url', '-')})")

    def _keirin_open_target_race(self, page, payload: Dict[str, Any]) -> None:
        race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
        venue = str(race.get("venue_name", "") or "").strip()
        race_no = _safe_int(race.get("race_num"), 0)
        if not venue or race_no <= 0:
            raise IpatEntryError("競輪レース情報が不正です（venue_name/race_num）")

        rows_sel = self._selector("keirin_vote_rows", "li.kyotuHeader, li.kyotuHeader.white_bg_color")
        vote_btn_sel = self._selector(
            "keirin_vote_button",
            "button[id^='hcombtnTouhyou'], input[id^='hcombtnTouhyou'], a[id^='hcombtnTouhyou']",
        )
        rows = page.locator(rows_sel)
        try:
            row_count = rows.count()
        except Exception:
            row_count = 0
        if row_count <= 0:
            raise IpatEntryError(f"競輪開催一覧の取得に失敗しました (selector={rows_sel})")

        candidates: List[str] = []
        venue_candidates: List[str] = []
        found_disabled = False
        for i in range(row_count):
            row = rows.nth(i)
            try:
                row_text = str(row.inner_text() or "").replace("\n", " ").strip()
            except Exception:
                continue
            compact = row_text.replace(" ", "").replace("　", "")
            candidates.append(compact[:80])
            if venue in row_text:
                venue_candidates.append(compact[:80])
            if (venue not in row_text) or (not _contains_race_label(compact, race_no)):
                continue
            try:
                buttons = row.locator(vote_btn_sel)
                btn_count = buttons.count()
            except Exception:
                btn_count = 0
                buttons = None
            if buttons is None or btn_count <= 0:
                continue
            for j in range(btn_count):
                btn = buttons.nth(j)
                try:
                    if not btn.is_visible():
                        continue
                    if btn.is_disabled():
                        found_disabled = True
                        continue
                    btn.click()
                    self._emit(f"投票ボタン押下: venue={venue} race={race_no}R row={i + 1}")
                    self._keirin_wait_vote_page_ready(page)
                    return
                except Exception:
                    continue
            found_disabled = True

        # フォールバック: 会場が一致していれば、表示Rが異なっていても投票導線へ進む。
        # TOP一覧の表示更新が遅れているケースで、投票画面側に進むと対象Rへ遷移できる場合があるため。
        venue_disabled = False
        for i in range(row_count):
            row = rows.nth(i)
            try:
                row_text = str(row.inner_text() or "").replace("\n", " ").strip()
            except Exception:
                continue
            if venue not in row_text:
                continue
            try:
                buttons = row.locator(vote_btn_sel)
                btn_count = buttons.count()
            except Exception:
                btn_count = 0
                buttons = None
            if buttons is None or btn_count <= 0:
                continue
            for j in range(btn_count):
                btn = buttons.nth(j)
                try:
                    if not btn.is_visible():
                        continue
                    if btn.is_disabled():
                        venue_disabled = True
                        continue
                    btn.click()
                    self._emit(
                        f"投票ボタン押下(会場優先): venue={venue} requested_race={race_no}R row={i + 1}"
                    )
                    self._keirin_wait_vote_page_ready(page)
                    return
                except Exception:
                    continue
            venue_disabled = True

        if venue_disabled:
            raise IpatRaceUnavailableError(
                f"対象会場の投票ボタンが無効です（発売締切の可能性）: venue={venue} race={race_no}R"
            )
        if found_disabled:
            raise IpatRaceUnavailableError(
                f"対象レースの投票ボタンが無効です（発売締切の可能性）: venue={venue} race={race_no}R"
            )
        if venue_candidates:
            preview_venue = ", ".join(venue_candidates[:4])
            raise IpatRaceUnavailableError(
                f"対象会場は見つかりましたが指定Rの投票導線が未発売または締切です: "
                f"venue={venue} race={race_no}R seen_venue={preview_venue}"
            )
        preview = ", ".join(candidates[:6]) if candidates else "-"
        raise IpatEntryError(
            f"対象レースの投票導線を検出できませんでした: venue={venue} race={race_no}R seen={preview}"
        )

    def _keirin_required_positions(self, market: str, numbers: List[int]) -> int:
        canonical = _canonical_market_name(market)
        if canonical in ALL_PAIR_MARKETS_ORDERED or canonical in ALL_PAIR_MARKETS_UNORDERED:
            return 2
        if canonical in ALL_TRIO_MARKETS_ORDERED or canonical in ALL_TRIO_MARKETS_UNORDERED:
            return 3
        return len(numbers)

    def _keirin_select_market(self, page, market: str) -> None:
        market_sel = self._selector("keirin_market_select", "select[name='cmbKakesiki']")
        node = self._first_visible(page, market_sel)
        if node is None:
            raise IpatEntryError("競輪券種プルダウンが見つかりません")
        market_label = self._market_select_value(market)
        try:
            node.select_option(label=market_label)
            self._emit(f"競輪券種選択: {market_label}")
            return
        except Exception:
            pass
        try:
            node.select_option(value=market_label)
            self._emit(f"競輪券種選択(value): {market_label}")
            return
        except Exception as exc:
            raise IpatEntryError(f"競輪券種の選択に失敗しました: market={market_label}") from exc

    def _keirin_clear_combo(self, page, positions: int) -> None:
        for pos in range(1, int(positions) + 1):
            sel = f"input[name='clear{pos}']"
            btn = self._first_enabled_button(page, sel)
            if btn is None:
                continue
            try:
                btn.click()
                page.wait_for_timeout(60)
            except Exception:
                continue

    def _keirin_collect_warning_text(self, page) -> str:
        selectors = [
            ".kimLblYoteiMsg",
            "#bet_right .warning_msg_fsz",
            "#kim_conf_dialog",
            "div.ui-dialog-content",
        ]
        texts: List[str] = []
        for sel in selectors:
            node = self._first_visible(page, sel)
            if node is None:
                continue
            try:
                text = str(node.inner_text() or "").strip()
            except Exception:
                text = ""
            if text:
                texts.append(text.replace("\n", " "))
        return " / ".join(texts)

    def _keirin_is_insufficient_funds_message(self, text: str) -> bool:
        t = str(text or "")
        if not t:
            return False
        if ("購入限度額" in t and "超" in t) or ("成立予定合計金額" in t and "超" in t):
            return True
        if ("残高" in t and "不足" in t) or ("入金" in t and "必要" in t):
            return True
        return False

    def _keirin_has_insufficient_funds_state(self, page) -> bool:
        return self._keirin_is_insufficient_funds_message(self._keirin_collect_warning_text(page))

    def _keirin_raise_if_insufficient_funds(self, page) -> None:
        warning = self._keirin_collect_warning_text(page)
        if self._keirin_is_insufficient_funds_message(warning):
            self._emit(f"競輪: 資金不足/限度額超過を検知 warning={warning}")
            raise IpatEntryError(
                f"購入限度額を超えました。入金後に再実行してください。"
                f"{' warning=' + warning if warning else ''}"
            )

    def _keirin_dismiss_confirm_dialog(self, page) -> bool:
        """「編集中の買い目は破棄されますがよろしいですか」ダイアログのOKを押す。"""
        if self._wait_for_any_visible(
            page,
            self._selector_list("keirin_confirm_ok_button", "#kim_confirm_ok_btn"),
            timeout_ms=600,
            poll_ms=80,
        ):
            self._click_any(page, "keirin_confirm_ok_button", "#kim_confirm_ok_btn", required=False)
            self._emit("確認ダイアログでOK押下（買い目破棄）")
            page.wait_for_timeout(300)
            return True
        return False

    def _keirin_is_top_page(self, page) -> bool:
        try:
            current_url = str(getattr(page, "url", "") or "").strip().lower()
        except Exception:
            current_url = ""
        if "/pc/racevote" in current_url:
            return False
        if "/pc/top" in current_url:
            return True
        racevote_ready_sel = self._selector("keirin_vote_page_ready_selector", "select[name='cmbKakesiki'], #kai, #bet_right")
        if racevote_ready_sel and self._is_visible(page, racevote_ready_sel):
            return False
        vote_rows_sel = self._selector("keirin_vote_rows", "li.kyotuHeader, li.kyotuHeader.white_bg_color")
        if vote_rows_sel and self._is_visible(page, vote_rows_sel):
            return True
        return False

    def _keirin_finalize_top_return(self, page) -> bool:
        """トップ復帰直後に遅延表示される確認ダイアログを処理する。"""
        if not self._keirin_is_top_page(page):
            return False
        self._keirin_dismiss_confirm_dialog(page)
        page.wait_for_timeout(220)
        self._keirin_dismiss_confirm_dialog(page)
        return bool(self._keirin_is_top_page(page))

    def _keirin_return_top(self, page) -> bool:
        if self._keirin_is_top_page(page):
            return self._keirin_finalize_top_return(page)

        for attempt in range(1, 5):
            clicked_top = self._click_first_visible(
                page,
                "keirin_return_top_selector",
                "#btnKeirinjp",
                "a#btnKeirinjp",
                required=False,
            )
            end = datetime.now().timestamp() + 1.8
            while datetime.now().timestamp() < end:
                dismissed = self._keirin_dismiss_confirm_dialog(page)
                if self._keirin_is_top_page(page):
                    return self._keirin_finalize_top_return(page)
                if (not clicked_top) and (not dismissed):
                    break
                page.wait_for_timeout(120)
        login_url = str(getattr(self._ipat_settings, "login_url", "") or "").strip() or "https://keirin.jp/pc/top"
        try:
            page = self._goto(page, login_url, wait_until="domcontentloaded")
            if self._keirin_is_top_page(page):
                return self._keirin_finalize_top_return(page)
            moved = self._wait_for_any_visible(
                page,
                self._selector_list(
                    "keirin_vote_rows",
                    "li.kyotuHeader, li.kyotuHeader.white_bg_color",
                    self._selector("keirin_login_success_selector", "#loginbox2"),
                ),
                timeout_ms=max(2500, self._op_timeout_ms(scale=1600)),
                poll_ms=120,
            )
            if moved and self._keirin_is_top_page(page):
                return self._keirin_finalize_top_return(page)
            return bool(moved)
        except Exception as exc:
            self._emit(f"トップ復帰フォールバック遷移に失敗 error={exc}")
            return False

    def _keirin_click_number(self, page, position: int, number: int) -> None:
        self._keirin_raise_if_insufficient_funds(page)
        sel = f"#syabanWakuban{int(position)}{int(number)}"
        btn = self._first_enabled_button(page, sel)
        if btn is None:
            btn = self._first_visible(page, sel)
        if btn is None:
            self._keirin_raise_if_insufficient_funds(page)
            raise IpatEntryError(
                f"競輪買い目ボタンが見つかりません: pos={int(position)} number={int(number)} selector={sel}"
            )
        try:
            btn.click()
        except Exception as exc:
            self._keirin_raise_if_insufficient_funds(page)
            raise IpatEntryError(f"競輪買い目ボタン押下に失敗しました: pos={position} number={number}") from exc

    def _keirin_read_summary_total(self, page) -> int:
        node = self._first_visible(page, self._selector("keirin_summary_total", ".kimLblTotalGaku"))
        if node is None:
            return 0
        try:
            text = str(node.inner_text() or "").strip()
        except Exception:
            text = ""
        return self._parse_number_text(text, 0)

    def _keirin_read_summary_bet_count(self, page) -> int:
        node = self._first_visible(page, self._selector("keirin_summary_bet_count", ".kimLblBetCnt"))
        if node is None:
            return -1
        try:
            text = str(node.inner_text() or "").strip()
        except Exception:
            text = ""
        return self._parse_number_text(text, -1)

    def _keirin_click_set_button(self, page) -> None:
        set_btn = self._first_enabled_button(
            page,
            self._selector("keirin_set_button", "button.btn_set, #UNQ_orbutton_12"),
            contains_text="セット",
        )
        if set_btn is None:
            raise IpatEntryError("競輪セットボタンが有効状態になりませんでした")
        try:
            set_btn.click()
        except Exception as exc:
            raise IpatEntryError("競輪セットボタン押下に失敗しました") from exc

    def _keirin_collect_groups(self, page) -> List[Dict[str, Any]]:
        try:
            rows = page.evaluate(
                """
                () => {
                  const root = document.querySelector('#kaimeGroupList');
                  if (!root) return [];
                  const groups = Array.from(root.querySelectorAll(':scope > div'));
                  return groups.map((g, idx) => {
                    const summaryTable = g.querySelector(':scope > table:first-of-type') || g;
                    const combo = Array.from(summaryTable.querySelectorAll('span.sd1, span.sd2, span.sd3'))
                      .map((el) => String(el.textContent || '').trim())
                      .filter(Boolean)
                      .join('-');
                    let market = '';
                    const pTags = Array.from(g.querySelectorAll('table p'));
                    for (const p of pTags) {
                      const t = String(p.textContent || '').trim();
                      if (!t) continue;
                      if (t.includes('車') || t.includes('連') || t.includes('単') || t.includes('ワイド')) {
                        market = t;
                        break;
                      }
                    }
                    const subtotal = String((g.querySelector('.subTotal')?.textContent || '')).trim();
                    const amountInput = g.querySelector('input.input_money');
                    const unit = amountInput ? String(amountInput.value || '').trim() : '';
                    return {
                      idx: idx + 1,
                      id: String(g.id || '').trim(),
                      groupid: String(g.getAttribute('groupid') || '').trim(),
                      combo,
                      market,
                      sub_total: subtotal,
                      unit,
                    };
                  });
                }
                """
            )
        except Exception:
            return []
        if not isinstance(rows, list):
            return []
        return [dict(r) for r in rows if isinstance(r, dict)]

    def _keirin_group_selector(self, row: Dict[str, Any]) -> str:
        gid = str(row.get("id", "") or "").strip()
        if gid:
            return f"#{gid}"
        groupid = str(row.get("groupid", "") or "").strip()
        if groupid:
            return f"#kaimeGroupList > div[groupid='{groupid}']"
        idx = _safe_int(row.get("idx"), 0)
        if idx > 0:
            return f"#kaimeGroupList > div:nth-child({idx})"
        return ""

    def _keirin_combo_match(self, combo_text: str, numbers: List[int]) -> bool:
        target = [int(n) for n in numbers]
        digits = [int(v) for v in re.findall(r"\d+", str(combo_text or ""))]
        if not digits:
            return False
        if digits == target:
            return True
        target_len = len(target)
        if target_len <= 0:
            return False
        if len(digits) == (target_len * 2):
            if digits[:target_len] == target and digits[target_len:] == target:
                return True
        if len(digits) > target_len and (len(digits) % target_len == 0):
            chunk = digits[:target_len]
            repeats = len(digits) // target_len
            if chunk == target and all(digits[i * target_len : (i + 1) * target_len] == chunk for i in range(repeats)):
                return True
        return False

    def _keirin_find_group_for_ticket(
        self,
        page,
        market: str,
        numbers: List[int],
        used_group_selectors: set[str],
    ) -> str:
        target_combo = "-".join(str(int(n)) for n in numbers)
        market_label = str(self._market_select_value(market) or "").replace(" ", "").replace("　", "")
        end = datetime.now().timestamp() + 1.2
        last_groups: List[Dict[str, Any]] = []

        while datetime.now().timestamp() < end:
            groups = self._keirin_collect_groups(page)
            last_groups = groups

            def _pick(matches: List[Tuple[Dict[str, Any], str]]) -> str:
                # 追加直後の既定値(100円/1口)を優先し、同点なら表示順を優先する。
                matches.sort(
                    key=lambda item: (
                        0
                        if (
                            self._parse_number_text(item[0].get("sub_total"), -1) == 100
                            or self._parse_number_text(item[0].get("unit"), -1) == 1
                        )
                        else 1,
                        _safe_int(item[0].get("idx"), 999),
                    )
                )
                return matches[0][1]

            strict_matches: List[Tuple[Dict[str, Any], str]] = []
            combo_only_matches: List[Tuple[Dict[str, Any], str]] = []
            for row in groups:
                selector = self._keirin_group_selector(row)
                if (not selector) or (selector in used_group_selectors):
                    continue
                combo = str(row.get("combo", "") or "").strip()
                if not self._keirin_combo_match(combo, numbers):
                    continue
                combo_only_matches.append((row, selector))
                market_text = str(row.get("market", "") or "").replace(" ", "").replace("　", "")
                if (not market_label) or (market_label in market_text):
                    strict_matches.append((row, selector))

            if strict_matches:
                return _pick(strict_matches)
            if combo_only_matches:
                return _pick(combo_only_matches)

            page.wait_for_timeout(40)

        seen = ", ".join(
            f"{self._keirin_group_selector(row)}:{row.get('market', '-')}/{row.get('combo', '-')}/{row.get('sub_total', '-')}"
            for row in last_groups[:8]
        ) or "-"
        raise IpatEntryError(
            f"金額修正対象の買い目グループ特定に失敗しました: market={market} combo={target_combo} seen={seen}"
        )

    def _keirin_read_group_subtotal(self, page, group_selector: str) -> int:
        node = self._first_visible(page, f"{group_selector} .subTotal")
        if node is None:
            return 0
        try:
            text = str(node.inner_text() or "").strip()
        except Exception:
            text = ""
        return self._parse_number_text(text, 0)

    def _keirin_update_group_amount(self, page, group_selector: str, bet_yen: int) -> None:
        if int(bet_yen) <= 0 or int(bet_yen) % 100 != 0:
            raise IpatEntryError(f"競輪買い目金額は100円単位が必要です: {int(bet_yen)}")
        unit = int(bet_yen) // 100

        modify_sel = f"{group_selector} .kimBtnModify"
        complete_sel = f"{group_selector} .kimBtnModifyComplete"
        input_sel = f"{group_selector} input.input_money"

        modify_btn = self._first_enabled_button(page, modify_sel, contains_text="修正")
        if modify_btn is None:
            modify_btn = self._first_visible(page, modify_sel)
        if modify_btn is None:
            raise IpatEntryError(f"修正ボタンが見つかりません: selector={group_selector}")
        modify_btn.click()
        self._emit(f"買い目修正モード開始: selector={group_selector}")

        amount_input = None
        complete_visible = False
        end = datetime.now().timestamp() + 1.4
        while datetime.now().timestamp() < end:
            amount_input = self._first_visible(page, input_sel)
            complete_btn_probe = self._first_visible(page, complete_sel)
            complete_visible = complete_btn_probe is not None
            input_enabled = False
            if amount_input is not None:
                try:
                    input_enabled = not bool(amount_input.is_disabled())
                except Exception:
                    input_enabled = True
            if complete_visible and input_enabled:
                break
            page.wait_for_timeout(40)
        else:
            raise IpatEntryError(f"修正モードへの遷移待機に失敗しました: selector={group_selector}")

        if amount_input is None:
            raise IpatEntryError(f"金額入力欄が見つかりません: selector={group_selector}")

        edited = False
        try:
            amount_input.click()
            amount_input.press("ControlOrMeta+A")
            amount_input.press("Backspace")
            amount_input.fill(str(unit))
            edited = True
        except Exception:
            edited = False

        if not edited:
            try:
                edited = bool(
                    page.evaluate(
                        """
                        (args) => {
                          const el = document.querySelector(args.selector);
                          if (!el) return false;
                          el.focus();
                          el.value = '';
                          el.dispatchEvent(new Event('input', { bubbles: true }));
                          el.value = String(args.value);
                          el.dispatchEvent(new Event('input', { bubbles: true }));
                          el.dispatchEvent(new Event('change', { bubbles: true }));
                          el.blur();
                          return true;
                        }
                        """,
                        {"selector": input_sel, "value": str(unit)},
                    )
                )
            except Exception:
                edited = False

        if not edited:
            raise IpatEntryError(f"金額入力に失敗しました: selector={group_selector} unit={unit}")

        try:
            amount_input.press("Tab")
        except Exception:
            pass

        complete_btn = self._first_enabled_button(page, complete_sel, contains_text="修正完了")
        if complete_btn is None:
            complete_btn = self._first_visible(page, complete_sel)
        if complete_btn is None:
            raise IpatEntryError(f"修正完了ボタンが見つかりません: selector={group_selector}")
        complete_btn.click()
        self._emit(f"買い目修正完了押下: selector={group_selector} amount={int(bet_yen):,}円")

        end = datetime.now().timestamp() + 1.6
        last_total = -1
        while datetime.now().timestamp() < end:
            subtotal = self._keirin_read_group_subtotal(page, group_selector)
            last_total = int(subtotal)
            if int(subtotal) == int(bet_yen):
                return
            page.wait_for_timeout(40)
        raise IpatEntryError(
            f"修正後金額の反映確認に失敗しました: selector={group_selector} expected={int(bet_yen)} actual={last_total}"
        )

    def _keirin_set_ticket(self, page, ticket: Dict[str, Any], used_group_selectors: set[str]) -> None:
        market = str(ticket.get("market", "") or "").strip()
        numbers = [int(n) for n in list(ticket.get("numbers") or [])]
        bet_yen = int(ticket.get("bet_yen", 0) or 0)
        positions = self._keirin_required_positions(market, numbers)
        if positions <= 1:
            raise IpatEntryError(f"競輪未対応券種を検出しました: {market}")
        if len(numbers) != positions:
            raise IpatEntryError(f"買い目桁数が不正です: market={market} combo={ticket.get('combo')}")

        self._keirin_select_market(page, market)
        self._keirin_clear_combo(page, positions)
        for idx, number in enumerate(numbers, start=1):
            self._keirin_click_number(page, idx, int(number))
        before_count = self._keirin_read_summary_bet_count(page)
        self._keirin_click_set_button(page)
        self._emit(f"買い目セット: market={market} combo={ticket.get('combo')} amount={bet_yen:,}円")
        if before_count >= 0:
            page.wait_for_timeout(80)

        target_group = self._keirin_find_group_for_ticket(
            page,
            market=market,
            numbers=numbers,
            used_group_selectors=used_group_selectors,
        )
        self._keirin_update_group_amount(page, target_group, bet_yen=bet_yen)
        used_group_selectors.add(target_group)

    def _keirin_wait_pin_input(self, page) -> None:
        if not self._wait_for_any_visible(
            page,
            self._selector_list(
                "keirin_pin_input",
                "#kimTxtPassWord",
                self._selector("keirin_final_vote_button", "#kimBtnVote"),
            ),
            timeout_ms=max(5000, self._op_timeout_ms(scale=3000)),
            poll_ms=120,
        ):
            raise IpatEntryError("暗証番号入力画面への遷移に失敗しました")

    def _keirin_move_to_pin_screen(self, page, total_yen: int) -> None:
        self._keirin_raise_if_insufficient_funds(page)
        vote_btn = self._first_enabled_button(
            page,
            self._selector("keirin_primary_vote_button", "button.kimBtnVote"),
            contains_text="投",
        )
        if vote_btn is None:
            self._keirin_raise_if_insufficient_funds(page)
            raise IpatEntryError("投票ボタンが有効化されていません")
        vote_btn.click()
        self._emit("投票ボタン押下（暗証番号入力画面へ）")

        self._keirin_wait_pin_input(page)
        confirm_total = self._keirin_read_summary_total(page)
        if confirm_total > 0 and int(confirm_total) != int(total_yen):
            raise IpatEntryError(
                f"投票確認画面の合計金額が一致しません: expected={int(total_yen)} actual={int(confirm_total)}"
            )

    def _keirin_submit(self, page, total_yen: int) -> None:
        self._keirin_move_to_pin_screen(page, total_yen=total_yen)
        pin_value = str(getattr(self._ipat_settings, "pars_no", "") or "").strip()
        self._fill_any(page, "keirin_pin_input", pin_value, "#kimTxtPassWord")
        self._emit("暗証番号入力完了")

        self._click_any(page, "keirin_final_vote_button", "#kimBtnVote", required=True)
        self._emit("最終投票ボタン押下")
        if self._wait_for_any_visible(
            page,
            self._selector_list("keirin_confirm_ok_button", "#kim_confirm_ok_btn"),
            timeout_ms=max(3000, self._op_timeout_ms(scale=2000)),
            poll_ms=100,
        ):
            self._click_any(page, "keirin_confirm_ok_button", "#kim_confirm_ok_btn", required=False)
            self._emit("最終確認ダイアログでOK押下")

        self._wait_for_any_visible(
            page,
            self._selector_list(
                "keirin_return_top_selector",
                "#btnKeirinjp",
                self._selector("keirin_vote_rows", "li.kyotuHeader, li.kyotuHeader.white_bg_color"),
            ),
            timeout_ms=max(5000, self._op_timeout_ms(scale=3000)),
            poll_ms=120,
        )

    def _execute_keirin(
        self,
        page,
        payload: Dict[str, Any],
        tickets: List[Dict[str, Any]],
        total_yen: int,
    ) -> Dict[str, Any]:
        self._emit("対象会場の投票導線を検索")
        self._keirin_open_target_race(page, payload)

        used_group_selectors: set[str] = set()
        for row in tickets:
            self._keirin_raise_if_insufficient_funds(page)
            self._keirin_set_ticket(page, row, used_group_selectors)
            self._keirin_raise_if_insufficient_funds(page)

        planned_total = self._keirin_read_summary_total(page)
        self._emit(f"投票成立予定金額チェック: expected={int(total_yen)} actual={int(planned_total)}")
        if int(planned_total) != int(total_yen):
            raise IpatEntryError(
                f"投票成立予定の合計金額が一致しません: expected={int(total_yen)} actual={int(planned_total)}"
            )

        if not bool(self._ipat_settings.submit_enabled):
            self._keirin_move_to_pin_screen(page, total_yen=total_yen)
            self._emit("競輪: 投票ボタン押下済み。暗証番号入力画面で待機します")
            return {
                "status": "prepared",
                "ticket_count": len(tickets),
                "total_yen": total_yen,
            }

        self._keirin_submit(page, total_yen=total_yen)
        return {
            "status": "submitted",
            "ticket_count": len(tickets),
            "total_yen": total_yen,
        }

    def _local_contexts(self, page) -> List[Any]:
        contexts: List[Any] = [page]
        frames = []
        try:
            frames = list(getattr(page, "frames", []) or [])
        except Exception:
            frames = []
        for frame in frames:
            if frame is None or frame in contexts:
                continue
            contexts.append(frame)
        return contexts

    def _local_first_visible_anywhere(self, page, selector: str) -> Tuple[Optional[Any], Optional[Any]]:
        sel = str(selector or "").strip()
        if not sel:
            return None, None
        for ctx in self._local_contexts(page):
            node = self._first_visible(ctx, sel)
            if node is not None:
                return ctx, node
        return None, None

    def _local_wait_for_any_visible(
        self,
        page,
        selectors: List[str],
        timeout_ms: int = 2000,
        poll_ms: int = 200,
    ) -> bool:
        end = datetime.now().timestamp() + (max(200, int(timeout_ms)) / 1000.0)
        checked = [str(s or "").strip() for s in selectors if str(s or "").strip()]
        if not checked:
            return False
        while datetime.now().timestamp() < end:
            for ctx in self._local_contexts(page):
                for sel in checked:
                    if self._first_visible(ctx, sel) is not None:
                        return True
            page.wait_for_timeout(int(poll_ms))
        return False

    def _local_context_urls(self, page) -> List[str]:
        urls: List[str] = []
        for ctx in self._local_contexts(page):
            try:
                u = str(getattr(ctx, "url", "") or "").strip()
            except Exception:
                u = ""
            if u and u not in urls:
                urls.append(u)
        return urls

    def _local_click_first_visible_anywhere(self, page, key: str, *fallbacks: str, required: bool = True) -> bool:
        for ctx in self._local_contexts(page):
            if self._click_first_visible(ctx, key, *fallbacks, required=False):
                return True
        if required:
            raise IpatEntryError(f"selector missing or not clickable: {key}")
        return False

    def _local_fill_anywhere(self, page, key: str, value: str, *fallbacks: str) -> None:
        for ctx in self._local_contexts(page):
            try:
                self._fill_any(ctx, key, value, *fallbacks)
                return
            except Exception:
                continue
        raise IpatEntryError(f"selector missing or not fillable: {key}")

    def _local_select_venue(self, page, venue: str) -> None:
        self._dismiss_local_interrupts_if_present(page)

        wanted = str(venue or "").strip()
        if not wanted:
            raise IpatEntryError("地方開催場名が空です")

        current_sel = self._selector("local_kaisai_current", "div.section03 li.current")
        current = self._first_visible(page, current_sel)
        if current is not None:
            try:
                if wanted in str(current.inner_text() or "").strip():
                    return
            except Exception:
                pass

        links_sel = self._selector("local_kaisai_links", "div.section03 li a")
        try:
            links = page.locator(links_sel)
            count = links.count()
        except Exception:
            count = 0
            links = None

        clicked = False
        if links is not None:
            for i in range(count):
                item = links.nth(i)
                try:
                    text = str(item.inner_text() or "").strip()
                    if wanted not in text:
                        continue
                    item.click()
                    clicked = True
                    break
                except Exception:
                    continue
        if not clicked:
            raise IpatEntryError(f"地方開催場を選択できませんでした: {wanted}")

        end = datetime.now().timestamp() + (max(4000, self._op_timeout_ms(scale=2000)) / 1000.0)
        while datetime.now().timestamp() < end:
            self._dismiss_local_interrupts_if_present(page)
            cur = self._first_visible(page, current_sel)
            if cur is not None:
                try:
                    if wanted in str(cur.inner_text() or "").strip():
                        return
                except Exception:
                    pass
            page.wait_for_timeout(120)
        raise IpatEntryError(f"地方開催場の切替反映待機に失敗しました: {wanted}")

    def _local_find_race_row(self, page, race_no: int):
        rows_sel = self._selector("local_race_rows", "table.tbl_01 tr")
        try:
            rows = page.locator(rows_sel)
            count = rows.count()
        except Exception:
            return None
        for i in range(count):
            row = rows.nth(i)
            try:
                text = str(row.inner_text() or "")
            except Exception:
                continue
            if _contains_race_label(text, int(race_no)):
                return row
        return None

    def _local_open_odds_vote(self, page, race_no: int) -> None:
        self._dismiss_local_interrupts_if_present(page)

        row = None
        end = datetime.now().timestamp() + (max(4000, self._op_timeout_ms(scale=2000)) / 1000.0)
        while datetime.now().timestamp() < end:
            self._dismiss_local_interrupts_if_present(page)
            row = self._local_find_race_row(page, race_no)
            if row is not None:
                break
            page.wait_for_timeout(120)
        if row is None:
            raise IpatEntryError(f"地方レース行を見つけられませんでした: {race_no}R")

        btn_sel = self._selector("local_odds_vote_button", "a:has-text('オッズ投票'), a:has-text('オッズ')")
        button = None
        try:
            btns = row.locator(btn_sel)
            count = btns.count()
            for i in range(count):
                item = btns.nth(i)
                if item.is_visible():
                    button = item
                    text = str(item.inner_text() or "").strip()
                    if "オッズ投票" in text:
                        break
        except Exception:
            button = None
        if button is None:
            raise IpatEntryError(f"地方レースのオッズ投票導線が見つかりませんでした: {race_no}R")
        try:
            button.click()
        except Exception:
            pass

        wait_selectors = self._selector_list(
            "local_shiki_select",
            self._selector("local_bet_table"),
            "a[onclick*='clickOddsBet']",
        )
        wait_timeout = max(4000, self._op_timeout_ms(scale=2000))
        if self._local_wait_for_any_visible(
            page,
            wait_selectors,
            timeout_ms=wait_timeout,
            poll_ms=120,
        ):
            return

        # クリックで遷移しない環境向け: href/onclick から遷移先URLを抽出して直接遷移する。
        target_url = ""
        base_url = str(getattr(page, "url", "") or "")
        try:
            href = str(button.get_attribute("href") or "").strip()
            if href and (href != "#") and (not href.lower().startswith("javascript:")):
                target_url = urljoin(base_url, href)
        except Exception:
            target_url = ""
        if not target_url:
            try:
                onclick = str(button.get_attribute("onclick") or "")
                m = re.search(r"['\"](/keiba/pc\\?[^'\"]+)['\"]", onclick)
                if m is not None:
                    target_url = urljoin(base_url, str(m.group(1) or "").strip())
            except Exception:
                target_url = ""
        if target_url:
            self._emit(f"地方オッズ投票遷移フォールバック: direct_goto={target_url}")
            try:
                page = self._goto(page, target_url, wait_until="domcontentloaded")
            except Exception:
                pass
            if self._local_wait_for_any_visible(
                page,
                wait_selectors,
                timeout_ms=max(5000, self._op_timeout_ms(scale=2500)),
                poll_ms=120,
            ):
                return

        context_urls = self._local_context_urls(page)
        context_urls_text = ",".join(context_urls[:5]) if context_urls else "-"
        raise IpatEntryError(
            f"地方オッズ投票画面への遷移に失敗しました: {race_no}R "
            f"(url={str(getattr(page, 'url', '') or '-')}, contexts={context_urls_text})"
        )

    def _local_market_shiki(self, market: str) -> str:
        canonical = _canonical_market_name(market)
        shiki = str(self._market_select_value(canonical) or "").strip()
        if not shiki:
            if canonical == "馬連":
                shiki = "5"
            elif canonical == "ワイド":
                shiki = "7"
        return shiki

    def _local_read_shiki_value(self, page, select_selector: str, current_select=None) -> str:
        candidates = []
        if current_select is not None:
            candidates.append(current_select)
        fallback = self._first_visible(page, select_selector)
        if fallback is not None:
            candidates.append(fallback)

        for node in candidates:
            try:
                value = str(node.evaluate("el => String((el && el.value) || '')") or "").strip()
                if value:
                    return value
            except Exception:
                continue

        try:
            value = str(
                page.evaluate(
                    """
                    (sel) => {
                      try {
                        const el = document.querySelector(sel);
                        return String((el && el.value) || '').trim();
                      } catch (e) {
                        return '';
                      }
                    }
                    """,
                    select_selector,
                )
                or ""
            ).strip()
            return value
        except Exception:
            return ""

    def _local_select_market(self, page, market: str) -> str:
        self._dismiss_local_interrupts_if_present(page)

        canonical = _canonical_market_name(market)
        if canonical not in LOCAL_SUPPORTED_MARKETS:
            raise IpatEntryError(f"地方未対応券種です: {canonical}")
        shiki = self._local_market_shiki(canonical)
        if not shiki:
            raise IpatEntryError(f"地方券種コードが未設定です: {canonical}")
        select_selector = self._selector("local_shiki_select", "select[name='SHIKILINK']")
        select_ctx, select = self._local_first_visible_anywhere(page, select_selector)
        if select is None:
            context_urls = self._local_context_urls(page)
            raise IpatEntryError(
                "地方式別セレクタが見つかりません "
                f"(contexts={','.join(context_urls[:5]) if context_urls else '-'})"
            )

        select_page = select_ctx or page
        before_value = self._local_read_shiki_value(select_page, select_selector, select)
        self._emit(f"地方式別選択開始: market={canonical} target={shiki} current={before_value or '-'}")

        if before_value == shiki:
            self._emit(f"地方式別選択完了: market={canonical} value={shiki} (already selected)")
            return shiki

        # 1) 通常の value 指定選択
        try:
            select.select_option(value=shiki)
        except Exception:
            pass
        page.wait_for_timeout(180)
        current_value = self._local_read_shiki_value(select_page, select_selector, select)
        if current_value == shiki:
            self._dismiss_local_interrupts_if_present(page)
            self._emit(f"地方式別選択完了: market={canonical} value={shiki}")
            return shiki

        # 2) ラベル選択（馬連は馬複表記も許容）
        label_hints = ["馬複", "馬連"] if canonical == "馬連" else [canonical]
        for label in label_hints:
            try:
                select.select_option(label=label)
            except Exception:
                continue
            page.wait_for_timeout(180)
            current_value = self._local_read_shiki_value(select_page, select_selector, select)
            if current_value == shiki:
                self._dismiss_local_interrupts_if_present(page)
                self._emit(f"地方式別選択完了: market={canonical} value={shiki} label={label}")
                return shiki

        # 3) ページ内JSフォールバック
        try:
            action = self._local_retrigger_market_change(page, shiki, context=select_page, label_hints=label_hints)
            self._emit(f"地方式別選択フォールバック実行: market={canonical} action={action}")
        except Exception:
            pass

        page.wait_for_timeout(220)
        current_value = self._local_read_shiki_value(select_page, select_selector, select)
        if current_value == shiki:
            self._dismiss_local_interrupts_if_present(page)
            self._emit(f"地方式別選択完了: market={canonical} value={shiki} fallback")
            return shiki

        raise IpatEntryError(
            f"地方式別を選択できませんでした: market={canonical} target={shiki} current={current_value or '-'}"
        )

    def _local_encode_umakumistr(self, numbers: List[int]) -> str:
        if len(numbers) != 2:
            raise IpatEntryError(f"地方の組番形式が不正です: {numbers}")
        n1, n2 = sorted(int(n) for n in numbers)
        if n1 <= 0 or n2 <= 0:
            raise IpatEntryError(f"地方の組番形式が不正です: {numbers}")
        return f"{n1:04X}{n2:04X}0000"

    def _local_collect_click_odds_links(self, page) -> List[Dict[str, Any]]:
        pattern = re.compile(
            r'clickOddsBet\(\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*(\d+)\s*,\s*"(\d+)"\s*,\s*"[^"]*"\s*,\s*"([0-9A-Fa-f]+)"\s*\)'
        )
        out: List[Dict[str, Any]] = []
        for ctx in self._local_contexts(page):
            links = ctx.locator("a[onclick*='clickOddsBet']")
            try:
                count = links.count()
            except Exception:
                count = 0
            for i in range(count):
                link = links.nth(i)
                try:
                    onclick = str(link.get_attribute("onclick") or "")
                    m = pattern.search(onclick)
                    if m is None:
                        continue
                    race_attr = _safe_int(m.group(1), 0)
                    if race_attr <= 0:
                        continue
                    shiki_attr = str(m.group(2) or "").strip()
                    code_attr = str(m.group(3) or "").strip().upper()
                    visible = False
                    try:
                        visible = bool(link.is_visible())
                    except Exception:
                        visible = False
                    context_url = ""
                    try:
                        context_url = str(getattr(ctx, "url", "") or "").strip()
                    except Exception:
                        context_url = ""
                    out.append(
                        {
                            "race": int(race_attr),
                            "shiki": shiki_attr,
                            "code": code_attr,
                            "visible": visible,
                            "link": link,
                            "context": ctx,
                            "context_url": context_url,
                        }
                    )
                except Exception:
                    continue
        return out

    def _local_retrigger_market_change(
        self,
        page,
        shiki: str,
        context=None,
        label_hints: Optional[List[str]] = None,
    ) -> str:
        select_selector = self._selector("local_shiki_select", "select[name='SHIKILINK']")
        eval_ctx = context
        if eval_ctx is None:
            eval_ctx, _ = self._local_first_visible_anywhere(page, select_selector)
        if eval_ctx is None:
            eval_ctx = page
        try:
            action = eval_ctx.evaluate(
                """
                (args) => {
                  try {
                    const selector = String((args && args.selector) || "select[name='SHIKILINK']");
                    const target = String((args && args.value) || '');
                    const labels = Array.isArray(args && args.labels) ? args.labels.map((s) => String(s || '')) : [];
                    const el = document.querySelector(selector);
                    if (!el) return 'missing_select';
                    let selected = false;
                    for (const opt of Array.from(el.options || [])) {
                      const text = String(opt.textContent || '').trim();
                      const value = String(opt.value || '').trim();
                      if (value === target || labels.some((lb) => lb && text.includes(lb))) {
                        el.value = value;
                        selected = true;
                        break;
                      }
                    }
                    if (!selected) {
                      el.value = target;
                    }
                    try {
                      el.dispatchEvent(new Event('change', { bubbles: true }));
                    } catch (e) {}
                    try {
                      const f = el.form;
                      if (f && typeof selectOddsLink3 === 'function') {
                        selectOddsLink3(f, f.RACEDAYR, f.PLACEIDR, f.RACER, f.KINDINFOR, f.PLACE, f.RACE, f.SHIKILINK, el);
                        return 'selectOddsLink3';
                      }
                    } catch (e) {}
                    return 'dispatch_change';
                  } catch (e) {
                    return `error:${String(e)}`;
                  }
                }
                """,
                {"selector": select_selector, "value": str(shiki), "labels": list(label_hints or [])},
            )
            return str(action or "")
        except Exception:
            return "eval_error"

    def _local_click_odds_link(
        self,
        page,
        race_no: int,
        shiki: str,
        umakumistr: str,
        timeout_ms: Optional[int] = None,
    ) -> None:
        self._dismiss_local_interrupts_if_present(page)

        target_race = int(race_no)
        target_shiki = str(shiki or "").strip()
        target_code = str(umakumistr or "").strip().upper()
        wait_timeout_ms = _safe_int(timeout_ms, 0)
        if wait_timeout_ms <= 0:
            wait_timeout_ms = max(5000, self._op_timeout_ms(scale=2500))
        end = datetime.now().timestamp() + (wait_timeout_ms / 1000.0)
        attempts = 0
        last_entries: List[Dict[str, Any]] = []

        while datetime.now().timestamp() < end:
            self._dismiss_local_interrupts_if_present(page)
            entries = self._local_collect_click_odds_links(page)
            last_entries = entries
            for row in entries:
                if int(row.get("race", 0) or 0) != target_race:
                    continue
                if str(row.get("shiki", "") or "").strip() != target_shiki:
                    continue
                if str(row.get("code", "") or "").strip().upper() != target_code:
                    continue
                if not bool(row.get("visible", False)):
                    continue
                link = row.get("link")
                if link is None:
                    continue
                try:
                    link.click()
                    return
                except Exception:
                    try:
                        link.evaluate("el => el.click()")
                        return
                    except Exception:
                        continue

            attempts += 1
            if attempts in {4, 12}:
                select_ctx, _ = self._local_first_visible_anywhere(
                    page,
                    self._selector("local_shiki_select", "select[name='SHIKILINK']"),
                )
                action = self._local_retrigger_market_change(page, target_shiki, context=select_ctx)
                self._emit(f"地方式別再同期フォールバック: shiki={target_shiki} action={action}")
            page.wait_for_timeout(120)

        select_selector = self._selector("local_shiki_select", "select[name='SHIKILINK']")
        select_ctx, _ = self._local_first_visible_anywhere(page, select_selector)
        current_shiki = self._local_read_shiki_value(select_ctx or page, select_selector)
        race_entries = [row for row in last_entries if int(row.get("race", 0) or 0) == target_race]
        seen_shiki = sorted({str(row.get("shiki", "") or "").strip() for row in race_entries if row.get("shiki")})
        seen_codes = sorted(
            {
                str(row.get("code", "") or "").strip().upper()
                for row in race_entries
                if str(row.get("shiki", "") or "").strip() == target_shiki and row.get("code")
            }
        )
        seen_contexts = sorted(
            {
                str(row.get("context_url", "") or "").strip()
                for row in race_entries
                if str(row.get("context_url", "") or "").strip()
            }
        )
        raise IpatEntryError(
            "地方オッズリンクが見つかりません: "
            f"race={target_race} shiki={target_shiki} umakumistr={target_code} "
            f"current_shiki={current_shiki or '-'} "
            f"seen_shiki={','.join(seen_shiki) if seen_shiki else '-'} "
            f"seen_codes={','.join(seen_codes[:8]) if seen_codes else '-'} "
            f"seen_contexts={','.join(seen_contexts[:3]) if seen_contexts else '-'} "
            f"url={str(getattr(page, 'url', '') or '-')}"
        )

    def _local_bet_row_count(self, page) -> int:
        rows_sel = self._selector("local_bet_rows", "#BET_TBL tr:has(input.TEXTMONEY)")
        best = 0
        for ctx in self._local_contexts(page):
            try:
                count = int(ctx.locator(rows_sel).count())
            except Exception:
                count = 0
            if count > best:
                best = count
        return int(best)

    def _local_wait_bet_row_increment(self, page, before_count: int) -> None:
        end = datetime.now().timestamp() + (max(4000, self._op_timeout_ms(scale=2000)) / 1000.0)
        while datetime.now().timestamp() < end:
            self._dismiss_local_interrupts_if_present(page)
            now_count = self._local_bet_row_count(page)
            if now_count > int(before_count):
                return
            page.wait_for_timeout(120)
        raise IpatEntryError("地方購入予定リストへの追加反映待機に失敗しました")

    def _local_input_ticket(self, page, race_no: int, ticket: Dict[str, Any]) -> None:
        market = str(ticket.get("market", "") or "").strip()
        numbers = [int(n) for n in list(ticket.get("numbers") or [])]
        shiki = self._local_select_market(page, market)
        code = self._local_encode_umakumistr(numbers)
        before = self._local_bet_row_count(page)
        self._local_click_odds_link(page, int(race_no), shiki, code)
        self._local_wait_bet_row_increment(page, before)

    def _local_fill_ticket_amounts(self, page, tickets: List[Dict[str, Any]]) -> None:
        self._dismiss_local_interrupts_if_present(page)

        inputs_sel = self._selector("local_bet_money_inputs", "#BET_TBL input.TEXTMONEY")
        best_ctx = None
        best_count = -1
        for ctx in self._local_contexts(page):
            try:
                count = int(ctx.locator(inputs_sel).count())
            except Exception:
                count = 0
            if count > best_count:
                best_ctx = ctx
                best_count = count
            if count >= len(tickets):
                best_ctx = ctx
                best_count = count
                break
        if best_ctx is None:
            best_ctx = page
        inputs = best_ctx.locator(inputs_sel)
        count = int(best_count if best_count >= 0 else 0)
        if count < len(tickets):
            raise IpatEntryError(f"地方投票金額入力欄が不足しています: expected={len(tickets)} actual={count}")
        for idx, row in enumerate(tickets):
            self._dismiss_local_interrupts_if_present(page)
            bet = int(row.get("bet_yen", 0) or 0)
            if bet % 100 != 0:
                raise IpatEntryError(f"地方買い目金額は100円単位である必要があります: {bet}")
            unit = bet // 100
            try:
                inputs.nth(idx).fill(str(unit))
            except Exception as exc:
                raise IpatEntryError(f"地方投票金額入力に失敗しました: row={idx + 1}") from exc

    def _local_move_to_confirm(self, page) -> None:
        for _ in range(3):
            self._dismiss_local_interrupts_if_present(page)
            self._local_click_first_visible_anywhere(
                page,
                "local_confirm_button",
                "input[type='submit'][value='投票内容確認へ']",
                "input[value='投票内容確認へ']",
            )
            if self._local_wait_for_any_visible(
                page,
                self._selector_list(
                    "local_member_pass_input",
                    self._selector("local_total_money_input"),
                ),
                timeout_ms=max(5000, self._op_timeout_ms(scale=2500)),
                poll_ms=120,
            ):
                self._dismiss_local_interrupts_if_present(page)
                return
            self._dismiss_local_interrupts_if_present(page)
            page.wait_for_timeout(160)
        raise IpatEntryError("地方確認画面への遷移に失敗しました")

    def _local_fill_pin_and_total(self, page, total_yen: int) -> None:
        self._local_fill_anywhere(
            page,
            "local_member_pass_input",
            str(getattr(self._ipat_settings, "pin", "") or ""),
            "#MEMBERPASSR",
        )
        self._local_fill_anywhere(
            page,
            "local_total_money_input",
            str(int(total_yen)),
            "#TOTALMONEYR",
        )

    def _local_submit_and_return(self, page) -> None:
        for _ in range(3):
            self._dismiss_local_interrupts_if_present(page)
            self._local_click_first_visible_anywhere(
                page,
                "local_vote_button",
                "input[name='KYOUSEI'][value='投票する']",
                "input[value='投票する']",
            )
            if self._local_wait_for_any_visible(
                page,
                self._selector_list(
                    "local_return_kaisai_button",
                    self._selector("local_kaisai_section"),
                ),
                timeout_ms=max(6000, self._op_timeout_ms(scale=2500)),
                poll_ms=120,
            ):
                break
            self._dismiss_local_interrupts_if_present(page)
            page.wait_for_timeout(180)
        else:
            raise IpatEntryError("地方投票実行後の画面遷移待機に失敗しました")

        self._dismiss_local_interrupts_if_present(page)
        self._local_click_first_visible_anywhere(
            page,
            "local_return_kaisai_button",
            "input[value='開催要領']",
            required=False,
        )

    def _execute_local(
        self,
        page,
        payload: Dict[str, Any],
        tickets: List[Dict[str, Any]],
        total_yen: int,
    ) -> Dict[str, Any]:
        race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
        venue = str(race.get("venue_name", "") or "").strip()
        race_no = _safe_int(race.get("race_num"), 0)
        if not venue or race_no <= 0:
            raise IpatEntryError("地方レース情報が不正です（venue/race_num）")

        unsupported = sorted(
            {
                str(row.get("market", "") or "").strip()
                for row in tickets
                if _canonical_market_name(str(row.get("market", "") or "").strip()) not in LOCAL_SUPPORTED_MARKETS
            }
        )
        if unsupported:
            reason = f"地方未対応券種を含むため見送り: {', '.join(unsupported)}"
            self._emit(reason)
            return {
                "status": "skipped_unsupported_market",
                "reason": reason,
                "ticket_count": len(tickets),
                "total_yen": total_yen,
            }

        self._emit(f"地方開催場選択: {venue}")
        self._local_select_venue(page, venue)
        self._emit(f"地方レース選択: {race_no}R")
        self._local_open_odds_vote(page, race_no)
        for row in tickets:
            self._emit(f"地方買い目入力: {row.get('market')} {row.get('combo')} {int(row.get('bet_yen', 0)):,}円")
            self._local_input_ticket(page, race_no, row)
        self._local_fill_ticket_amounts(page, tickets)
        self._emit("地方: 投票内容確認へ遷移")
        self._local_move_to_confirm(page)
        self._local_fill_pin_and_total(page, total_yen)

        if not bool(self._ipat_settings.submit_enabled):
            self._emit("地方: 暗証番号/投票金額を入力済み。投票する押下前で待機します")
            return {
                "status": "prepared",
                "ticket_count": len(tickets),
                "total_yen": total_yen,
            }

        self._emit("地方: 投票するを押して確定します")
        self._local_submit_and_return(page)
        return {
            "status": "submitted",
            "ticket_count": len(tickets),
            "total_yen": total_yen,
        }

    def _login(self, page, login_url: str):
        self._emit(f"ログインURLへアクセス: {login_url}")
        page = self._goto(page, login_url, wait_until="domcontentloaded")

        inet_id_sel = self._selector("inet_id_input")
        if inet_id_sel:
            try:
                self._fill_any(page, "inet_id_input", self._ipat_settings.inet_id, "input[name='inetid']")
                self._click_any(page, "inet_next_button", "a[title='ログイン']", required=False)
                inet_wait = self._selector("after_inet_wait_selector")
                if inet_wait:
                    page.wait_for_selector(inet_wait)
                self._emit("INET-ID入力完了")
            except Exception as exc:
                raise IpatEntryError(f"INET-ID入力に失敗しました: {exc}") from exc

        self._fill_any(page, "login_id_input", self._ipat_settings.login_id, "input[name='i']", "input[name='loginId']")
        self._fill_any(page, "password_input", self._ipat_settings.password, "input[name='p']", "input[name='password']")
        self._fill_any(page, "pars_input", self._ipat_settings.pars_no, "input[name='r']", "input[name='parsNo']")
        self._click_any(
            page,
            "login_button",
            "a[title='ネット投票メニューへ']",
            "button[type='submit']",
        )
        self._wait_post_login_ready(page)
        self._emit("加入者情報ログイン完了")
        return page

    def _move_vote_page(self, page):
        self._dismiss_important_notice_if_present(page)

        vote_url = self._selector("vote_page_url")
        if vote_url:
            page = self._goto(page, vote_url, wait_until="domcontentloaded")
            self._dismiss_important_notice_if_present(page)
            return page

        ready = self._wait_for_any_visible(
            page,
            [
                self._selector("normal_vote_button"),
                self._selector("vote_menu_link"),
            ],
            timeout_ms=self._op_timeout_ms(),
        )
        if not ready:
            if self._click_any(
                page,
                "return_home_button",
                "div.brand a[ui-sref='home']",
                required=False,
            ):
                self._wait_for_any_visible(
                    page,
                    [
                        self._selector("normal_vote_button"),
                        self._selector("vote_menu_link"),
                    ],
                    timeout_ms=self._op_timeout_ms(scale=700),
                )
        clicked = self._click_any(
            page,
            "normal_vote_button",
            "button[ui-sref='bet.basic']",
            required=False,
        )
        if not clicked:
            clicked = self._click_any(page, "vote_menu_link", required=False)
        if not clicked:
            raise IpatEntryError(f"通常投票画面へ遷移できませんでした (url={getattr(page, 'url', '-')})")
        self._emit("通常投票ボタン押下")
        self._dismiss_important_notice_if_present(page)
        self._pause_if_no_funds_dialog(page)
        return page

    def _pause_if_no_funds_dialog(self, page) -> None:
        dialog_sel = self._selector("no_funds_dialog_selector", "div.dialog:has-text('投票の前に')")
        if not dialog_sel:
            return
        dialog = self._first_visible(page, dialog_sel)
        if dialog is None:
            return
        self._emit("お金が入っていません。入金後に「このまま進む」を押してください。")
        try:
            dialog.wait_for(state="hidden", timeout=0)
        except Exception as exc:
            raise IpatEntryError(f"入金待機中に中断されました: {exc}") from exc
        self._emit("入金待機を解除しました。処理を再開します。")

    def _select_option_by_text(
        self,
        page,
        select_selector: str,
        required_text: str,
        preferred_text: str = "",
        race_no: int = 0,
    ) -> bool:
        select = self._first_visible(page, select_selector)
        if select is None:
            return False
        options = select.locator("option")
        try:
            count = options.count()
        except Exception:
            return False

        best_value = ""
        best_score = -1
        for i in range(count):
            opt = options.nth(i)
            try:
                label = str(opt.get_attribute("label") or opt.inner_text() or "").strip()
                value = str(opt.get_attribute("value") or "").strip()
            except Exception:
                continue
            if not value:
                continue
            score = 1
            if race_no > 0:
                if not _contains_race_label(label, race_no):
                    continue
                score += 3
            elif required_text:
                if required_text not in label:
                    continue
                score += 2
            if preferred_text and preferred_text in label:
                score += 1
            if score > best_score:
                best_score = score
                best_value = value

        if best_score < 0:
            return False
        select.select_option(value=best_value)
        return True

    def _select_course_and_race(self, page, payload: Dict[str, Any]) -> None:
        race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
        venue = str(race.get("venue_name", "") or "").strip()
        race_no = _safe_int(race.get("race_num"), 0)
        date8 = str(race.get("date", "") or "").strip()
        if not venue or race_no <= 0:
            return

        day_hint = _race_day_hint(date8)
        self._emit(f"場名選択開始: venue={venue} day_hint={day_hint or '-'}")

        ready = self._wait_for_any_visible(
            page,
            self._selector_list(
                "course_select",
                self._selector("course_button_selector"),
                self._selector("race_ready_selector"),
            ),
            timeout_ms=self._op_timeout_ms(),
        )
        if not ready:
            raise IpatEntryError(f"投票画面要素が見つかりません (url={getattr(page, 'url', '-')})")

        course_ok = self._select_option_by_text(
            page,
            self._selector("course_select"),
            required_text=venue,
            preferred_text=day_hint,
        )
        if not course_ok:
            course_buttons = self._selector("course_button_selector")
            btn = self._first_enabled_button(page, course_buttons, contains_text=venue)
            if btn is not None:
                btn.click()
                course_ok = True
        if not course_ok:
            raise IpatEntryError(f"場名を選択できませんでした: {venue} (url={getattr(page, 'url', '-')})")
        self._emit(f"場名選択完了: {venue}")

        self._emit(f"レース選択開始: {race_no}R")
        race_ok = self._select_option_by_text(
            page,
            self._selector("race_select"),
            required_text="",
            preferred_text="",
            race_no=race_no,
        )
        if not race_ok:
            race_buttons = self._selector("race_button_selector")
            btn = self._find_race_button(page, race_buttons, race_no)
            if btn is not None:
                btn.click()
                race_ok = True
        if not race_ok:
            raise IpatEntryError(f"レース番号を選択できませんでした: {race_no}R (url={getattr(page, 'url', '-')})")
        self._emit(f"レース選択完了: {race_no}R")

        ready_selectors = self._selector_list(
            "race_ready_selector",
            "select#bet-basic-type",
            "div.ipat-vote-basic-detail",
            "div.selection-amount input[ng-model='vm.nUnit']",
        )
        if ready_selectors and not self._wait_for_any_visible(
            page,
            ready_selectors,
            timeout_ms=self._op_timeout_ms(),
        ):
            raise IpatEntryError(
                "レース選択後の投票入力領域が表示されませんでした "
                f"(url={getattr(page, 'url', '-')})"
            )
        self._wait_until_not_loading(
            page,
            timeout_ms=self._op_timeout_ms(),
            phase="レース選択後",
        )

    def _find_race_button(self, page, selector: str, race_no: int):
        sel = str(selector or "").strip()
        if not sel:
            return None
        try:
            loc = page.locator(sel)
            count = loc.count()
        except Exception:
            return None
        for i in range(count):
            btn = loc.nth(i)
            try:
                if not btn.is_visible() or not btn.is_enabled():
                    continue
                text = str(btn.inner_text(timeout=1000) or "")
                if _contains_race_label(text, race_no):
                    return btn
            except Exception:
                continue
        return None

    def _select_market(self, page, market: str) -> None:
        sel = self._selector("market_select")
        select = self._first_visible(page, sel)
        if select is None:
            raise IpatEntryError("selector missing: market_select")
        mode = str(self.selectors.get("market_select_mode", "label") or "label").strip().lower()
        market_value = self._market_select_value(market)
        if mode == "value":
            select.select_option(value=market_value)
        else:
            select.select_option(label=market_value)

    def _select_default_method_if_visible(self, page) -> None:
        method_sel = self._selector("method_select")
        method = self._first_visible(page, method_sel)
        if method is None:
            return
        method_label = str(self.selectors.get("default_method_label", "通常") or "通常")
        try:
            method.select_option(label=method_label)
        except Exception:
            pass

    def _clear_selected_horses(self, page) -> None:
        base = self._selector("horse_checkbox_prefix", "input[id^='no']")
        if not base:
            return
        checked = page.locator(f"{base}:checked")
        try:
            count = checked.count()
        except Exception:
            return
        for i in range(count):
            box = checked.nth(i)
            try:
                if box.is_visible():
                    box.uncheck(force=True)
            except Exception:
                continue

    def _find_horse_checkbox(self, page, horse_no: int):
        selectors = self._horse_checkbox_selectors(int(horse_no))
        for sel in selectors:
            node = self._first_visible(page, sel)
            if node is not None:
                return node
        return None

    def _horse_checkbox_selectors(self, horse_no: int) -> List[str]:
        n = int(horse_no)
        return [
            f"input#no{n}",
            f"input#no{n:02d}",
            f"input[id^='no{n}_']",
            f"input[id^='no{n}-']",
            f"xpath=//tr[.//span[contains(@class,'ipat-racer-no') and normalize-space(text())='{n}']]//input[@type='checkbox']",
        ]

    def _find_horse_checkbox_any(self, page, horse_no: int):
        for sel in self._horse_checkbox_selectors(int(horse_no)):
            try:
                loc = page.locator(sel)
                count = loc.count()
            except Exception:
                continue
            for i in range(count):
                node = loc.nth(i)
                try:
                    if node.is_visible():
                        return node
                except Exception:
                    pass
                return node
        return None

    def _is_checkbox_selected(self, box) -> bool:
        if box is None:
            return False
        try:
            if bool(box.is_checked()):
                return True
        except Exception:
            pass
        try:
            cls = str(box.get_attribute("class") or "")
            tokens = {t.strip() for t in cls.split() if t.strip()}
            if "ng-not-empty" in tokens:
                return True
            if "ng-empty" in tokens:
                return False
        except Exception:
            pass
        try:
            checked_attr = str(box.get_attribute("checked") or "").strip().lower()
            if checked_attr in {"true", "checked", "1"}:
                return True
        except Exception:
            pass
        return False

    def _is_horse_checked(self, page, horse_no: int) -> bool:
        box = self._find_horse_checkbox(page, int(horse_no))
        if self._is_checkbox_selected(box):
            return True
        alt = self._find_horse_checkbox_any(page, int(horse_no))
        return self._is_checkbox_selected(alt)

    def _set_checkbox_checked(self, page, horse_no: int) -> None:
        for _ in range(4):
            self._wait_until_not_loading(page, timeout_ms=self._horse_select_timeout_ms(), phase=f"馬番{horse_no}選択前")
            box = self._find_horse_checkbox(page, int(horse_no))
            if box is None:
                page.wait_for_timeout(200)
                continue
            try:
                if box.is_disabled():
                    page.wait_for_timeout(250)
                    continue
            except Exception:
                page.wait_for_timeout(250)
                continue

            try:
                if box.is_checked():
                    return
            except Exception:
                pass

            try:
                box.check(force=True)
                page.wait_for_timeout(80)
                if box.is_checked():
                    return
            except Exception:
                pass

            try:
                box.click(force=True)
                page.wait_for_timeout(80)
                if box.is_checked():
                    return
            except Exception:
                pass

            # iPAT画面ではinputクリックが反映されにくい場合があるため、labelクリックも試す。
            label = self._first_visible(
                page,
                ",".join(
                    [
                        f"label[for='no{int(horse_no)}']",
                        f"label[for='no{int(horse_no):02d}']",
                        f"label[for^='no{int(horse_no)}_']",
                        f"label[for^='no{int(horse_no)}-']",
                    ]
                ),
            )
            if label is not None:
                try:
                    label.click(force=True)
                    page.wait_for_timeout(100)
                    if self._is_horse_checked(page, int(horse_no)):
                        return
                except Exception:
                    pass

            page.wait_for_timeout(200)

        raise IpatRaceCancelledError(f"馬番を選択できませんでした（競走中止の可能性）: {horse_no}")

    def _select_horses(self, page, numbers: List[int]) -> None:
        for n in numbers:
            self._set_checkbox_checked(page, int(n))

    def _wait_horses_selected(self, page, numbers: List[int], timeout_ms: int = 4000) -> None:
        required = [int(n) for n in numbers]
        end = datetime.now().timestamp() + (max(200, int(timeout_ms)) / 1000.0)
        next_retry_at = 0.0
        while datetime.now().timestamp() < end:
            try:
                self._wait_until_not_loading(page, timeout_ms=1500, phase="馬番反映待機")
            except Exception:
                pass

            all_selected = True
            missing: List[int] = []
            for n in required:
                if not self._is_horse_checked(page, n):
                    all_selected = False
                    missing.append(n)
            if all_selected:
                return

            now_ts = datetime.now().timestamp()
            if missing and now_ts >= next_retry_at:
                for n in missing:
                    try:
                        self._emit(f"馬番再選択: {n}")
                        self._set_checkbox_checked(page, n)
                    except IpatRaceCancelledError:
                        raise
                    except Exception:
                        continue
                next_retry_at = now_ts + 0.4
            page.wait_for_timeout(120)
        raise IpatRaceCancelledError(f"馬番選択が反映されませんでした（競走中止の可能性）: {required}")

    def _dismiss_discard_purchase_list_dialog(self, page) -> bool:
        dialog_sel = self._selector(
            "discard_purchase_list_dialog_selector",
            "div.dialog:has-text('購入予定リストの内容をすべて破棄して投票メニュー画面に戻ります')",
        )
        if not dialog_sel or (not self._is_visible(page, dialog_sel)):
            return False
        clicked = self._click_any(
            page,
            "discard_purchase_list_ok_button",
            "div.dialog:has-text('購入予定リストの内容をすべて破棄して投票メニュー画面に戻ります') button.btn-ok",
            "div.dialog:has-text('購入予定リストの内容をすべて破棄して投票メニュー画面に戻ります') button:has-text('OK')",
            required=False,
        )
        if clicked:
            self._emit("購入予定リスト破棄確認でOK押下")
        return clicked

    def _return_to_main_menu(self, page, timeout_ms: int = 2000) -> bool:
        menu_selectors = self._selector_list("normal_vote_button", self._selector("vote_menu_link"))
        if menu_selectors and self._wait_for_any_visible(page, menu_selectors, timeout_ms=1200, poll_ms=120):
            return True

        moved = self._click_any(
            page,
            "return_home_button",
            "div.brand a[ui-sref='home']",
            required=False,
        )
        if not moved:
            return False
        if not menu_selectors:
            return True
        end = datetime.now().timestamp() + (max(1200, int(timeout_ms)) / 1000.0)
        while datetime.now().timestamp() < end:
            if self._wait_for_any_visible(page, menu_selectors, timeout_ms=250, poll_ms=80):
                return True
            self._dismiss_discard_purchase_list_dialog(page)
            page.wait_for_timeout(120)
        return False

    def _click_set_button(self, page) -> None:
        timeout_ms = max(4000, self._op_timeout_ms())
        end = datetime.now().timestamp() + (timeout_ms / 1000.0)
        while datetime.now().timestamp() < end:
            try:
                self._wait_until_not_loading(page, timeout_ms=2000, phase="セット押下前")
            except Exception:
                pass

            expand = self._first_enabled_button(
                page,
                self._selector("expand_set_button"),
                contains_text="展開セット",
            )
            if expand is not None:
                expand.click()
                return

            set_btn = self._first_enabled_button(
                page,
                self._selector("set_button"),
                exact_text="セット",
            )
            if set_btn is None:
                set_btn = self._first_enabled_button(
                    page,
                    self._selector("set_button"),
                    contains_text="セット",
                )
            if set_btn is not None:
                set_btn.click()
                return

            page.wait_for_timeout(120)
        raise IpatEntryError("セットボタンを押せませんでした")

    def _is_modern_vote_ui(self, page) -> bool:
        market_sel = self._selector("market_select")
        amount_sel = self._selector("ticket_amount_input")
        horse_sel = self._selector("horse_checkbox_prefix")
        if market_sel and self._is_visible(page, market_sel):
            if amount_sel and self._is_visible(page, amount_sel):
                return True
            if horse_sel and self._is_visible(page, horse_sel):
                return True
        return False

    def _fill_combo_legacy(self, page, numbers: List[int]) -> None:
        self._fill_any(page, "horse1_input", str(numbers[0]))
        horse2 = self._selector("horse2_input")
        horse3 = self._selector("horse3_input")

        if len(numbers) >= 2:
            if not horse2:
                raise IpatEntryError("selector missing: horse2_input")
            page.fill(horse2, str(numbers[1]))
        elif horse2:
            page.fill(horse2, "")

        if len(numbers) >= 3:
            if not horse3:
                raise IpatEntryError("selector missing: horse3_input")
            page.fill(horse3, str(numbers[2]))
        elif horse3:
            page.fill(horse3, "")

    def _input_ticket_legacy(self, page, ticket: Dict[str, Any]) -> None:
        market = str(ticket.get("market", "") or "").strip()
        numbers = list(ticket.get("numbers") or [])
        bet_yen = int(ticket.get("bet_yen", 0) or 0)
        self._select_market(page, market)
        self._fill_combo_legacy(page, numbers)
        self._fill_any(page, "amount_input", str(bet_yen))
        self._click_any(page, "add_ticket_button")
        wait = self._selector("after_add_wait_selector")
        if wait:
            page.wait_for_selector(wait)

    def _input_ticket_modern(self, page, ticket: Dict[str, Any]) -> None:
        market = str(ticket.get("market", "") or "").strip()
        numbers = list(ticket.get("numbers") or [])
        bet_yen = int(ticket.get("bet_yen", 0) or 0)
        if bet_yen % 100 != 0:
            raise IpatEntryError(f"買い目金額は100円単位である必要があります: {bet_yen}")
        unit = bet_yen // 100

        self._wait_until_not_loading(
            page,
            timeout_ms=self._op_timeout_ms(),
            phase="券種選択前",
        )
        self._select_market(page, market)
        self._wait_until_not_loading(
            page,
            timeout_ms=self._op_timeout_ms(),
            phase=f"券種({market})選択後",
        )
        self._select_default_method_if_visible(page)
        horse_ready = self._wait_for_any_visible(
            page,
            self._selector_list("horse_checkbox_prefix", "input[id^='no']"),
            timeout_ms=self._horse_select_timeout_ms(),
        )
        if not horse_ready:
            raise IpatEntryError(f"馬番選択欄が表示されませんでした ({market})")
        self._clear_selected_horses(page)
        self._select_horses(page, numbers)
        self._wait_horses_selected(
            page,
            numbers,
            timeout_ms=self._horse_select_timeout_ms(),
        )
        self._fill_any(
            page,
            "ticket_amount_input",
            str(unit),
            self._selector("amount_input"),
        )
        self._click_set_button(page)

        wait = self._selector("after_add_wait_selector")
        if wait:
            page.wait_for_selector(wait)

    def _input_ticket(self, page, ticket: Dict[str, Any]) -> None:
        if self._is_modern_vote_ui(page):
            self._input_ticket_modern(page, ticket)
            return
        self._input_ticket_legacy(page, ticket)

    def _finish_input(self, page) -> bool:
        if self._is_visible(page, self._selector("purchase_total_input")):
            return True
        done_btn = self._first_enabled_button(
            page,
            self._selector("input_done_button"),
            exact_text="入力終了",
        )
        if done_btn is None:
            done_btn = self._first_enabled_button(
                page,
                self._selector("input_done_button"),
                contains_text="入力終了",
            )
        if done_btn is None:
            return False
        done_btn.click()
        self._emit("入力終了ボタン押下")

        ready = self._selector("purchase_list_ready_selector")
        if ready:
            page.wait_for_selector(ready)
        return self._is_visible(page, self._selector("purchase_total_input"))

    def _extract_market_from_text(self, text: str) -> str:
        body = str(text or "")
        for market in KNOWN_MARKETS:
            if market in body:
                return _canonical_market_name(market)
        return ""

    def _collect_purchase_rows(self, page) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        trs = page.locator("table.table-ipat tbody tr:has(td.vote-content)")
        try:
            count = trs.count()
        except Exception:
            return rows

        for i in range(count):
            row = trs.nth(i)
            try:
                vote_text = str(row.locator("td.vote-content").first.inner_text() or "")
                market = self._extract_market_from_text(vote_text)
                combos = row.locator(".set-heading").all_inner_texts()
                numbers = []
                for combo in combos:
                    digits = "".join(ch for ch in str(combo or "") if ch.isdigit())
                    if digits:
                        numbers.append(int(digits))
                amount_input = row.locator("input[ng-model='item.unit']").first
                amount_unit = _safe_int(amount_input.input_value(), 0)
                amount = int(amount_unit) * 100
                rows.append(
                    {
                        "market": market,
                        "numbers": numbers,
                        "combo_key": _combo_key(market, numbers),
                        "amount": amount,
                    }
                )
            except Exception:
                continue
        return rows

    def _verify_purchase_list(self, page, expected: List[Dict[str, Any]]) -> None:
        actual = self._collect_purchase_rows(page)
        self._emit(f"購入予定リスト照合: expected={len(expected)} actual={len(actual)}")
        used = [False] * len(actual)

        for row in expected:
            market = _canonical_market_name(str(row.get("market", "") or ""))
            numbers = [int(n) for n in list(row.get("numbers") or [])]
            amount = int(row.get("bet_yen", 0) or 0)
            key = _combo_key(market, numbers)

            found = False
            for idx, act in enumerate(actual):
                if used[idx]:
                    continue
                if str(act.get("market", "")) != market:
                    continue
                if tuple(act.get("combo_key") or ()) != tuple(key):
                    continue
                if int(act.get("amount", 0) or 0) != amount:
                    continue
                used[idx] = True
                found = True
                break

            if not found:
                raise IpatEntryError(
                    f"購入予定リスト照合エラー: market={market} combo={numbers} amount={amount}"
                )

    def _click_dialog_ok(self, page) -> None:
        if self._click_any(
            page,
            "purchase_confirm_ok_button",
            "div.dialog button:has-text('OK')",
            required=False,
        ):
            return

    def _submit(self, page, tickets: List[Dict[str, Any]], total_yen: int) -> None:
        self._verify_purchase_list(page, tickets)

        self._fill_any(
            page,
            "purchase_total_input",
            str(int(total_yen)),
            "input[ng-model='vm.cAmountTotal']",
        )
        self._click_any(page, "purchase_button", "button:has-text('購入する')")
        self._emit("購入するボタン押下")

        # 購入確認ダイアログが出た場合はOKを押す。
        page.wait_for_timeout(300)
        self._click_dialog_ok(page)

        # 資金不足ダイアログが出る場合はOKを押して失敗扱いにする。
        insufficient_sel = self._selector(
            "insufficient_funds_dialog_selector",
            "div.dialog:has-text('購入限度額を超えました')",
        )
        for _ in range(8):
            if insufficient_sel and self._is_visible(page, insufficient_sel):
                self._click_dialog_ok(page)
                raise IpatEntryError("購入限度額を超えました。入金後に再実行してください。")
            page.wait_for_timeout(400)

        # 購入完了後は投票メニューへ戻す。
        self._click_any(
            page,
            "return_home_button",
            "div.brand a[ui-sref='home']",
            required=False,
        )


class ThreadBoundIpatPlaywrightExecutor(IpatPlaywrightExecutor):
    def __init__(
        self,
        app_settings: AppSettings,
        event_logger: Optional[Callable[[str], None]] = None,
        target: str = "central",
    ):
        self.settings = app_settings
        self.target = _normalize_target(target)
        self._event_logger = event_logger
        self._requests: "queue.Queue[tuple[str, tuple[Any, ...], dict[str, Any], queue.Queue[tuple[bool, Any]]]]" = (
            queue.Queue()
        )
        self._ready_queue: "queue.Queue[tuple[bool, Any]]" = queue.Queue(maxsize=1)
        self._closed = False
        self._thread = threading.Thread(
            target=self._owner_loop,
            name=f"playwright-owner-{self.target}",
            daemon=True,
        )
        self._thread.start()
        try:
            ready_ok, payload = self._ready_queue.get(timeout=5.0)
        except queue.Empty as exc:
            self._closed = True
            raise IpatEntryError("Playwright 専用スレッドの起動がタイムアウトしました") from exc
        if not ready_ok:
            self._closed = True
            if isinstance(payload, BaseException):
                raise payload
            raise IpatEntryError(str(payload or "Playwright 専用スレッドの初期化に失敗しました"))

    def _owner_loop(self) -> None:
        try:
            executor = IpatPlaywrightExecutor(
                self.settings,
                event_logger=self._event_logger,
                target=self.target,
            )
        except Exception as exc:
            self._ready_queue.put((False, exc))
            return

        self._ready_queue.put((True, None))
        while True:
            method_name, args, kwargs, response_queue = self._requests.get()
            if method_name == "__close__":
                try:
                    executor.close()
                    response_queue.put((True, None))
                except Exception as exc:
                    response_queue.put((False, exc))
                return
            try:
                method = getattr(executor, method_name)
                response_queue.put((True, method(*args, **kwargs)))
            except Exception as exc:
                response_queue.put((False, exc))

    def _submit_to_owner(self, method_name: str, *args: Any, _allow_closed: bool = False, **kwargs: Any) -> Any:
        if self._closed and not _allow_closed:
            raise IpatEntryError("Playwright 実行スレッドはすでに終了しています")
        if (not self._thread.is_alive()) and method_name != "__close__":
            self._closed = True
            raise IpatEntryError("Playwright 実行スレッドが停止しました")
        response_queue: "queue.Queue[tuple[bool, Any]]" = queue.Queue(maxsize=1)
        self._requests.put((method_name, args, kwargs, response_queue))
        ok, payload = response_queue.get()
        if ok:
            return payload
        if isinstance(payload, BaseException):
            raise payload
        raise IpatEntryError(str(payload or f"Playwright 実行に失敗しました: {method_name}"))

    def prepare_vote_menu(self) -> Dict[str, Any]:
        return self._submit_to_owner("prepare_vote_menu")

    def refresh_local_info(self) -> Dict[str, Any]:
        return self._submit_to_owner("refresh_local_info")

    def refresh_central_info(self) -> Dict[str, Any]:
        return self._submit_to_owner("refresh_central_info")

    def execute(self, payload: Dict[str, Any], tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._submit_to_owner("execute", payload, tickets)

    def close(self) -> None:
        if self._closed:
            return
        try:
            if self._thread.is_alive():
                self._submit_to_owner("__close__", _allow_closed=True)
        finally:
            self._closed = True
            if self._thread.is_alive():
                self._thread.join(timeout=5.0)
