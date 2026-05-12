import os
import threading
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import AppSettings
from ipat_playwright import (
    IpatEntryError,
    IpatPlaywrightExecutor,
    IpatRaceCancelledError,
    IpatRaceUnavailableError,
    ThreadBoundIpatPlaywrightExecutor,
    _normalize_ticket,
)


class _DummyPage:
    def wait_for_timeout(self, _ms: int) -> None:
        return


class _DummyLocator:
    def __init__(self, items):
        self._items = list(items or [])

    def count(self):
        return len(self._items)

    def nth(self, index: int):
        return self._items[index]


class _DummyVoteButton:
    def __init__(self, visible: bool = True, disabled: bool = False):
        self._visible = bool(visible)
        self._disabled = bool(disabled)
        self.clicked = 0

    def is_visible(self):
        return bool(self._visible)

    def is_disabled(self):
        return bool(self._disabled)

    def click(self):
        self.clicked += 1


class _DummyVoteRow:
    def __init__(self, text: str, buttons):
        self._text = str(text)
        self._buttons = list(buttons or [])
        self.last_locator_selector = ""

    def inner_text(self):
        return self._text

    def locator(self, _selector: str):
        self.last_locator_selector = str(_selector or "")
        return _DummyLocator(self._buttons)


class _DummyVotePage:
    def __init__(self, rows):
        self._rows = list(rows or [])
        self.last_selector = ""

    def locator(self, _selector: str):
        self.last_selector = str(_selector or "")
        return _DummyLocator(self._rows)

    def wait_for_timeout(self, _ms: int) -> None:
        return


class _DummyInputNode:
    def __init__(
        self,
        *,
        visible: bool = True,
        enabled: bool = True,
        fail_fill: bool = False,
        fail_press: bool = False,
        fail_type: bool = False,
        fail_evaluate: bool = False,
    ):
        self._visible = bool(visible)
        self._enabled = bool(enabled)
        self._fail_fill = bool(fail_fill)
        self._fail_press = bool(fail_press)
        self._fail_type = bool(fail_type)
        self._fail_evaluate = bool(fail_evaluate)
        self.value = ""
        self.click_calls = 0
        self.press_calls = []
        self.type_calls = []
        self.evaluate_calls = []

    def is_visible(self):
        return bool(self._visible)

    def is_enabled(self):
        return bool(self._enabled)

    def click(self):
        self.click_calls += 1

    def fill(self, value):
        if self._fail_fill:
            raise RuntimeError("fill failed")
        self.value = str(value)

    def press(self, key):
        self.press_calls.append(str(key))
        if self._fail_press:
            raise RuntimeError("press failed")

    def type(self, value):
        self.type_calls.append(str(value))
        if self._fail_type:
            raise RuntimeError("type failed")
        self.value = str(value)

    def input_value(self):
        return str(self.value)

    def evaluate(self, _script, arg=None):
        self.evaluate_calls.append(arg)
        if self._fail_evaluate:
            raise RuntimeError("evaluate failed")
        self.value = str(arg or "")
        return self.value


class _DummySelectorPage:
    def __init__(self, mapping=None, js_mapping=None, query_mapping=None):
        self._mapping = dict(mapping or {})
        self._js_mapping = dict(js_mapping or {})
        self._query_mapping = dict(query_mapping or {})
        self.evaluate_calls = []

    def locator(self, selector: str):
        return _DummyLocator(self._mapping.get(str(selector or ""), []))

    def query_selector(self, selector: str):
        return self._query_mapping.get(str(selector or ""), None)

    def evaluate(self, _script, arg=None):
        self.evaluate_calls.append(arg)
        if isinstance(arg, dict):
            payload = dict(arg or {})
            selector = str(payload.get("selector", "") or "")
            target = self._js_mapping.get(selector)
            if target is None:
                return {"found": False, "value": ""}
            if isinstance(target, BaseException):
                raise target
            next_value = str(payload.get("nextValue", "") or "")
            if hasattr(target, "value"):
                target.value = next_value
                return {"found": True, "value": next_value}
            if isinstance(target, dict):
                found = bool(target.get("found", True))
                value = str(target.get("value", next_value if found else "") or "")
                return {"found": found, "value": value}
            return {"found": False, "value": ""}
        if isinstance(arg, str):
            selector = str(arg or "")
            target = self._js_mapping.get(selector) or self._query_mapping.get(selector)
            if target is None:
                return {"found": False}
            return {
                "found": True,
                "tag": "INPUT",
                "id": selector.lstrip("#"),
                "name": "",
                "type": "password",
                "className": "",
                "valueLength": len(str(getattr(target, "value", "") or "")),
                "disabled": False,
                "readOnly": False,
                "outerHTML": f"<input id=\"{selector.lstrip('#')}\">",
                "rect": {"x": 0, "y": 0, "width": 100, "height": 30},
            }
        return {
            "url": "https://example.invalid",
            "readyState": "complete",
            "activeElement": None,
            "betconfFormHtml": "",
            "confirmationHtml": "",
        }


class _DummyCheckbox:
    def __init__(self, checked: bool = False, class_name: str = "", checked_attr: str = ""):
        self._checked = bool(checked)
        self._class_name = str(class_name)
        self._checked_attr = str(checked_attr)

    def is_checked(self) -> bool:
        return bool(self._checked)

    def get_attribute(self, name: str):
        if name == "class":
            return self._class_name
        if name == "checked":
            return self._checked_attr
        return None


class _DummySelect:
    def __init__(self, raise_on_select: bool = False, eval_result: str = "dispatch_change"):
        self.raise_on_select = bool(raise_on_select)
        self.eval_result = str(eval_result)
        self.select_calls = []
        self.eval_calls = 0

    def select_option(self, value=None, label=None):
        self.select_calls.append({"value": value, "label": label})
        if self.raise_on_select:
            raise RuntimeError("select failed")

    def evaluate(self, _script, _arg=None):
        self.eval_calls += 1
        return self.eval_result


class _DummyClickableLink:
    def __init__(self):
        self.click_calls = 0

    def click(self):
        self.click_calls += 1

    def evaluate(self, _script):
        self.click_calls += 1


class _FakeChromiumLauncher:
    def __init__(self, results):
        self._results = list(results or [])
        self.calls = []

    def launch(self, **kwargs):
        self.calls.append(dict(kwargs))
        if not self._results:
            raise RuntimeError("launch result missing")
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class _FakePlaywright:
    def __init__(self, chromium):
        self.chromium = chromium


class _FakeGotoPage:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.goto_calls = []
        self.default_timeout = None
        self.url = "about:blank"

    def goto(self, url, wait_until="domcontentloaded"):
        self.goto_calls.append({"url": url, "wait_until": wait_until})
        self.url = url
        if not self._results:
            return None
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def set_default_timeout(self, timeout_ms):
        self.default_timeout = timeout_ms


class _FakeBrowserContext:
    def __init__(self, page):
        self._page = page
        self.closed = False

    def new_page(self):
        return self._page

    def close(self):
        self.closed = True


class _FakeContextBrowser:
    def __init__(self, pages):
        self._pages = list(pages or [])
        self.context_kwargs = []
        self.contexts = []

    def new_context(self, **kwargs):
        self.context_kwargs.append(dict(kwargs))
        if not self._pages:
            raise RuntimeError("context page missing")
        context = _FakeBrowserContext(self._pages.pop(0))
        self.contexts.append(context)
        return context


class IpatPlaywrightBrowserLaunchTests(unittest.TestCase):
    def _new_executor(self, logs=None) -> IpatPlaywrightExecutor:
        settings = AppSettings()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        settings.ipat.selectors_file = str(Path(tmp.name) / "ipat_selectors.json")
        return IpatPlaywrightExecutor(settings, event_logger=(logs.append if logs is not None else None))

    def test_launch_browser_falls_back_to_playwright_chromium_when_channel_launch_fails(self):
        logs = []
        executor = self._new_executor(logs=logs)
        executor.settings.ipat.browser_channel = "chrome"
        fallback_browser = object()
        launcher = _FakeChromiumLauncher([RuntimeError("chrome missing"), fallback_browser])
        executor._playwright = _FakePlaywright(launcher)

        browser = executor._launch_browser()

        self.assertIs(browser, fallback_browser)
        self.assertEqual(launcher.calls[0].get("channel"), "chrome")
        self.assertNotIn("channel", launcher.calls[1])
        self.assertTrue(any("Playwright Chromiumへフォールバックしました" in line for line in logs))

    def test_launch_browser_raises_combined_error_when_channel_and_chromium_both_fail(self):
        executor = self._new_executor()
        executor.settings.ipat.browser_channel = "chrome"
        launcher = _FakeChromiumLauncher([RuntimeError("chrome missing"), RuntimeError("chromium missing")])
        executor._playwright = _FakePlaywright(launcher)

        with self.assertRaises(IpatEntryError) as ctx:
            executor._launch_browser()

        self.assertIn("channel=chrome", str(ctx.exception))
        self.assertIn("Playwright Chromiumでの起動も失敗しました", str(ctx.exception))

    def test_launch_browser_auto_uses_installed_chrome_when_browser_channel_is_empty(self):
        logs = []
        executor = self._new_executor(logs=logs)
        browser_obj = object()
        launcher = _FakeChromiumLauncher([browser_obj])
        executor._playwright = _FakePlaywright(launcher)

        browser = executor._launch_browser()

        self.assertIs(browser, browser_obj)
        self.assertEqual(launcher.calls[0].get("channel"), "chrome")
        self.assertTrue(any("自動使用しました" in line and "chrome" in line for line in logs))

    def test_launch_browser_auto_falls_back_to_edge_when_chrome_is_unavailable(self):
        logs = []
        executor = self._new_executor(logs=logs)
        browser_obj = object()
        launcher = _FakeChromiumLauncher([RuntimeError("chrome missing"), browser_obj])
        executor._playwright = _FakePlaywright(launcher)

        browser = executor._launch_browser()

        self.assertIs(browser, browser_obj)
        self.assertEqual(launcher.calls[0].get("channel"), "chrome")
        self.assertEqual(launcher.calls[1].get("channel"), "msedge")
        self.assertTrue(any("自動使用しました" in line and "msedge" in line for line in logs))

    def test_goto_retries_with_ignored_https_errors_on_cert_authority_error(self):
        logs = []
        executor = self._new_executor(logs=logs)
        first_page = _FakeGotoPage([RuntimeError("Page.goto: net::ERR_CERT_AUTHORITY_INVALID")])
        retry_page = _FakeGotoPage([None])
        old_context = _FakeBrowserContext(first_page)
        browser = _FakeContextBrowser([retry_page])
        executor._browser = browser
        executor._context = old_context
        executor._page = first_page

        page = executor._goto(first_page, "https://keirin.jp/pc/top", wait_until="domcontentloaded")

        self.assertIs(page, retry_page)
        self.assertTrue(old_context.closed)
        self.assertTrue(executor._ignore_https_errors)
        self.assertEqual(browser.context_kwargs, [{"ignore_https_errors": True}])
        self.assertEqual(first_page.goto_calls[0]["url"], "https://keirin.jp/pc/top")
        self.assertEqual(retry_page.goto_calls[0]["url"], "https://keirin.jp/pc/top")
        self.assertTrue(any("HTTPS証明書エラー" in line for line in logs))


class IpatPlaywrightFillTests(unittest.TestCase):
    def _new_executor(self, logs=None) -> IpatPlaywrightExecutor:
        settings = AppSettings()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        settings.ipat.selectors_file = str(Path(tmp.name) / "ipat_selectors.json")
        return IpatPlaywrightExecutor(settings, event_logger=(logs.append if logs is not None else None))

    def test_fill_any_falls_back_to_type_when_fill_fails(self):
        executor = self._new_executor()
        node = _DummyInputNode(fail_fill=True)
        page = _DummySelectorPage({"#pass": [node]})

        executor._fill_any(page, "kyoutei_confirm_pass_input", "1234", "#pass")

        self.assertEqual(node.value, "1234")
        self.assertEqual(node.type_calls, ["1234"])
        self.assertIn("ControlOrMeta+A", node.press_calls)

    def test_fill_any_logged_tries_next_selector_after_failure(self):
        logs = []
        executor = self._new_executor(logs=logs)
        failing = _DummyInputNode(fail_fill=True, fail_press=True, fail_type=True, fail_evaluate=True)
        working = _DummyInputNode()
        page = _DummySelectorPage({"#fail": [failing], "#pass": [working]})

        executor._fill_any_logged(page, "unknown_key", "5678", "#fail", "#pass")

        self.assertEqual(working.value, "5678")
        self.assertTrue(any("入力失敗: key=unknown_key selector=#fail" in line for line in logs))

    def test_fill_any_distinguishes_input_not_fillable_from_selector_missing(self):
        executor = self._new_executor()
        page = _DummySelectorPage({"#pass": [_DummyInputNode(fail_fill=True, fail_press=True, fail_type=True, fail_evaluate=True)]})

        with self.assertRaises(IpatEntryError) as ctx:
            executor._fill_any(page, "kyoutei_confirm_pass_input", "9999", "#pass")

        self.assertIn("input not fillable", str(ctx.exception))
        self.assertIn("#pass", str(ctx.exception))

    def test_fill_any_reports_selector_missing_when_no_input_is_found(self):
        executor = self._new_executor()
        page = _DummySelectorPage({})

        with self.assertRaises(IpatEntryError) as ctx:
            executor._fill_any(page, "kyoutei_confirm_pass_input", "9999", "#pass")

        self.assertEqual(str(ctx.exception), "selector missing: kyoutei_confirm_pass_input")

    def test_fill_any_uses_attached_input_when_not_visible(self):
        executor = self._new_executor()
        hidden = _DummyInputNode(visible=False)
        page = _DummySelectorPage({"#pass": [hidden]})

        executor._fill_any(page, "kyoutei_confirm_pass_input", "2468", "#pass")

        self.assertEqual(hidden.value, "2468")

    def test_fill_any_uses_query_selector_handle_when_locator_finds_nothing(self):
        executor = self._new_executor()
        handle = _DummyInputNode()
        page = _DummySelectorPage({}, query_mapping={"#pass": handle})

        executor._fill_any(page, "kyoutei_confirm_pass_input", "8642", "#pass")

        self.assertEqual(handle.value, "8642")

    def test_fill_any_uses_query_selector_fallback_when_locator_finds_nothing(self):
        executor = self._new_executor()
        hidden = _DummyInputNode()
        page = _DummySelectorPage({}, js_mapping={"#pass": hidden})

        executor._fill_any(page, "kyoutei_confirm_pass_input", "1357", "#pass")

        self.assertEqual(hidden.value, "1357")

    def test_launch_browser_falls_back_to_bundled_chromium_when_headless_shell_is_missing(self):
        logs = []
        executor = self._new_executor(logs=logs)
        fallback_browser = object()
        launcher = _FakeChromiumLauncher(
            [
                RuntimeError(
                    "BrowserType.launch: Executable doesn't exist at "
                    "C:\\_MEI12345\\playwright\\driver\\package\\.local-browsers\\"
                    "chromium_headless_shell-1208\\chrome-headless-shell-win64\\chrome-headless-shell.exe"
                ),
                fallback_browser,
            ]
        )
        executor._playwright = _FakePlaywright(launcher)
        executor._find_playwright_chromium_executable = lambda: "C:/bundle/chrome.exe"  # type: ignore[method-assign]

        browser = executor._launch_browser()

        self.assertIs(browser, fallback_browser)
        self.assertEqual(launcher.calls[1].get("executable_path"), "C:/bundle/chrome.exe")
        self.assertTrue(any("headless shell" in line for line in logs))

    def test_prepare_playwright_runtime_env_falls_back_from_invalid_temp(self):
        executor = self._new_executor()
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_app = Path(tmp_dir) / "LocalAppData"
            invalid_temp_file = Path(tmp_dir) / "invalid-temp.txt"
            invalid_temp_file.write_text("ng", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {
                    "TMP": str(invalid_temp_file),
                    "TEMP": str(invalid_temp_file),
                    "TMPDIR": str(invalid_temp_file),
                    "LOCALAPPDATA": str(local_app),
                },
                clear=False,
            ):
                resolved = executor._prepare_playwright_runtime_env()
                self.assertTrue(Path(resolved).exists())
                self.assertEqual(Path(os.environ["TMP"]).resolve(), Path(resolved).resolve())
                self.assertEqual(Path(os.environ["TEMP"]).resolve(), Path(resolved).resolve())
                self.assertEqual(Path(os.environ["TMPDIR"]).resolve(), Path(resolved).resolve())

    def test_thread_bound_executor_uses_single_owner_thread(self):
        settings = AppSettings()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        settings.ipat.selectors_file = str(Path(tmp.name) / "ipat_selectors.json")
        seen_thread_ids = []

        def _fake_prepare(_self):
            thread_id = threading.get_ident()
            seen_thread_ids.append(thread_id)
            return {"ok": True, "thread_id": thread_id}

        with mock.patch.object(IpatPlaywrightExecutor, "prepare_vote_menu", _fake_prepare):
            wrapper = ThreadBoundIpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
            try:
                first = wrapper.prepare_vote_menu()
                second = wrapper.prepare_vote_menu()
            finally:
                wrapper.close()

        self.assertNotEqual(first["thread_id"], threading.get_ident())
        self.assertEqual(first["thread_id"], second["thread_id"])
        self.assertEqual(seen_thread_ids[0], seen_thread_ids[1])


class IpatPlaywrightRaceCancelledTests(unittest.TestCase):
    def _new_executor(self) -> IpatPlaywrightExecutor:
        settings = AppSettings()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        settings.ipat.selectors_file = str(Path(tmp.name) / "ipat_selectors.json")
        return IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)

    def test_set_checkbox_checked_raises_race_cancelled_when_checkbox_missing(self):
        executor = self._new_executor()
        page = _DummyPage()

        executor._wait_until_not_loading = lambda _p, timeout_ms=0, phase="": None  # type: ignore[method-assign]
        executor._find_horse_checkbox = lambda _p, _n: None  # type: ignore[method-assign]

        with self.assertRaises(IpatRaceCancelledError):
            executor._set_checkbox_checked(page, 7)

    def test_horse_select_timeout_has_guard_band(self):
        executor = self._new_executor()
        executor.settings.ipat.timeout_sec = 1
        self.assertEqual(executor._horse_select_timeout_ms(), 4000)

    def test_wait_horses_selected_propagates_race_cancelled(self):
        executor = self._new_executor()
        page = _DummyPage()

        executor._wait_until_not_loading = lambda _p, timeout_ms=0, phase="": None  # type: ignore[method-assign]
        executor._is_horse_checked = lambda _p, _n: False  # type: ignore[method-assign]

        def _raise_cancelled(_p, _n):
            raise IpatRaceCancelledError("馬番を選択できませんでした")

        executor._set_checkbox_checked = _raise_cancelled  # type: ignore[method-assign]

        with self.assertRaises(IpatRaceCancelledError):
            executor._wait_horses_selected(page, [7], timeout_ms=300)

    def test_execute_returns_cancelled_race_and_goes_back_to_menu(self):
        executor = self._new_executor()
        payload = {"race": {"race_id": "東京_02R"}}
        tickets = [{"market": "単勝", "combo": "7", "bet_yen": 300}]
        events = []
        page = object()

        executor._validate_ipat_settings = lambda: "https://example.invalid"  # type: ignore[method-assign]
        executor._ensure_page = lambda: page  # type: ignore[method-assign]
        executor._ensure_logged_in = lambda _p, _u: events.append("logged_in")  # type: ignore[method-assign]
        executor._move_vote_page = lambda _p: events.append("move_vote")  # type: ignore[method-assign]
        executor._select_course_and_race = lambda _p, _payload: events.append("select_race")  # type: ignore[method-assign]

        def _raise_on_input(_p, _row):
            raise IpatRaceCancelledError("馬番を選択できませんでした（競走中止の可能性）: 7")

        executor._input_ticket = _raise_on_input  # type: ignore[method-assign]
        executor._finish_input = lambda _p: True  # type: ignore[method-assign]
        executor._submit = lambda _p, _t, _y: events.append("submit")  # type: ignore[method-assign]
        executor._return_to_main_menu = lambda _p, timeout_ms=0: events.append("return_menu") or True  # type: ignore[method-assign]

        result = executor.execute(payload, tickets)

        self.assertEqual(result.get("status"), "cancelled_race")
        self.assertIn("馬番を選択できませんでした", str(result.get("reason", "")))
        self.assertIn("return_menu", events)
        self.assertNotIn("submit", events)

    def test_return_to_main_menu_clicks_discard_dialog_ok_when_present(self):
        executor = self._new_executor()
        page = _DummyPage()
        wait_calls = {"count": 0}
        dismiss_calls = {"count": 0}
        click_keys = []

        executor._selector_list = lambda _key, *_fallbacks: ["button[ui-sref='bet.basic']"]  # type: ignore[method-assign]

        def _fake_wait(_p, _selectors, timeout_ms=0, poll_ms=0):
            wait_calls["count"] += 1
            return wait_calls["count"] >= 3

        def _fake_click(_p, key, *fallbacks, required=True):
            click_keys.append(key)
            return key == "return_home_button"

        def _fake_dismiss(_p):
            dismiss_calls["count"] += 1
            return dismiss_calls["count"] == 1

        executor._wait_for_any_visible = _fake_wait  # type: ignore[method-assign]
        executor._click_any = _fake_click  # type: ignore[method-assign]
        executor._dismiss_discard_purchase_list_dialog = _fake_dismiss  # type: ignore[method-assign]

        ok = executor._return_to_main_menu(page, timeout_ms=1200)

        self.assertTrue(ok)
        self.assertIn("return_home_button", click_keys)
        self.assertGreaterEqual(dismiss_calls["count"], 1)

    def test_is_horse_checked_uses_ng_not_empty_class(self):
        executor = self._new_executor()
        page = _DummyPage()
        box = _DummyCheckbox(checked=False, class_name="ng-valid ng-not-empty")

        executor._find_horse_checkbox = lambda _p, _n: box  # type: ignore[method-assign]
        executor._find_horse_checkbox_any = lambda _p, _n: box  # type: ignore[method-assign]

        self.assertTrue(executor._is_horse_checked(page, 1))

    def test_is_horse_checked_falls_back_to_non_visible_box_state(self):
        executor = self._new_executor()
        page = _DummyPage()
        box = _DummyCheckbox(checked=False, class_name="ng-valid ng-not-empty")

        executor._find_horse_checkbox = lambda _p, _n: None  # type: ignore[method-assign]
        executor._find_horse_checkbox_any = lambda _p, _n: box  # type: ignore[method-assign]

        self.assertTrue(executor._is_horse_checked(page, 9))

    def test_local_target_requires_member_credentials(self):
        settings = AppSettings()
        settings.local_ipat.member_number = ""
        settings.local_ipat.member_id = ""
        settings.local_ipat.pin = ""
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")

        with self.assertRaises(IpatEntryError):
            executor.execute(
                {"race": {"race_id": "地方_01R"}},
                [{"market": "馬連", "combo": "1-2", "bet_yen": 100}],
            )

    def test_local_market_alias_uses_umaren_shiki(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        self.assertEqual(executor._local_market_shiki("馬連"), "5")
        self.assertEqual(executor._local_market_shiki("馬複"), "5")
        self.assertEqual(executor._local_market_shiki("ワイド"), "7")

    def test_local_select_market_selects_by_value(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()
        select = _DummySelect(raise_on_select=False)
        values = ["1", "5"]

        executor._dismiss_local_interrupts_if_present = lambda _p: False  # type: ignore[method-assign]
        executor._first_visible = lambda _p, _s: select  # type: ignore[method-assign]
        executor._local_read_shiki_value = lambda _p, _sel, _cur=None: values.pop(0) if values else "5"  # type: ignore[method-assign]

        shiki = executor._local_select_market(page, "馬連")

        self.assertEqual(shiki, "5")
        self.assertTrue(any(call.get("value") == "5" for call in select.select_calls))

    def test_local_select_market_uses_js_fallback_when_select_option_fails(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()
        select = _DummySelect(raise_on_select=True, eval_result="dispatch_change")
        values = ["1", "1", "5"]

        executor._dismiss_local_interrupts_if_present = lambda _p: False  # type: ignore[method-assign]
        executor._first_visible = lambda _p, _s: select  # type: ignore[method-assign]
        executor._local_read_shiki_value = lambda _p, _sel, _cur=None: values.pop(0) if values else "5"  # type: ignore[method-assign]

        shiki = executor._local_select_market(page, "馬連")

        self.assertEqual(shiki, "5")

    def test_local_click_odds_link_waits_until_target_link_appears(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()
        link = _DummyClickableLink()
        calls = {"collect": 0}

        def _fake_collect(_p):
            calls["collect"] += 1
            if calls["collect"] < 3:
                return []
            return [
                {
                    "race": 9,
                    "shiki": "5",
                    "code": "000100070000",
                    "visible": True,
                    "link": link,
                }
            ]

        executor._dismiss_local_interrupts_if_present = lambda _p: False  # type: ignore[method-assign]
        executor._local_collect_click_odds_links = _fake_collect  # type: ignore[method-assign]

        executor._local_click_odds_link(page, 9, "5", "000100070000", timeout_ms=400)

        self.assertGreaterEqual(calls["collect"], 3)
        self.assertEqual(link.click_calls, 1)

    def test_local_click_odds_link_error_contains_market_debug(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()

        executor._dismiss_local_interrupts_if_present = lambda _p: False  # type: ignore[method-assign]
        executor._local_collect_click_odds_links = lambda _p: [  # type: ignore[method-assign]
            {"race": 1, "shiki": "1", "code": "000100020000", "visible": True, "link": _DummyClickableLink()}
        ]
        executor._local_read_shiki_value = lambda _p, _sel, _cur=None: "1"  # type: ignore[method-assign]

        with self.assertRaises(IpatEntryError) as ctx:
            executor._local_click_odds_link(page, 1, "5", "000100020000", timeout_ms=220)

        text = str(ctx.exception)
        self.assertIn("current_shiki=1", text)
        self.assertIn("seen_shiki=1", text)

    def test_execute_local_prepared_when_submit_disabled(self):
        settings = AppSettings()
        settings.local_ipat.submit_enabled = False
        settings.local_ipat.member_number = "1001"
        settings.local_ipat.member_id = "ABCD"
        settings.local_ipat.pin = "1234"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()
        events = []

        executor._local_select_venue = lambda _p, _v: events.append("venue")  # type: ignore[method-assign]
        executor._local_open_odds_vote = lambda _p, _r: events.append("odds")  # type: ignore[method-assign]
        executor._local_input_ticket = lambda _p, _r, _t: events.append("ticket")  # type: ignore[method-assign]
        executor._local_fill_ticket_amounts = lambda _p, _ts: events.append("amounts")  # type: ignore[method-assign]
        executor._local_move_to_confirm = lambda _p: events.append("confirm")  # type: ignore[method-assign]
        executor._local_fill_pin_and_total = lambda _p, _y: events.append("pin_total")  # type: ignore[method-assign]
        executor._local_submit_and_return = lambda _p: events.append("submit")  # type: ignore[method-assign]

        result = executor._execute_local(
            page,
            {"race": {"venue_name": "高知", "race_num": 3}},
            [{"market": "馬連", "combo": "1-2", "numbers": [1, 2], "bet_yen": 100}],
            total_yen=100,
        )

        self.assertEqual(result.get("status"), "prepared")
        self.assertNotIn("submit", events)

    def test_execute_local_submitted_when_submit_enabled(self):
        settings = AppSettings()
        settings.local_ipat.submit_enabled = True
        settings.local_ipat.member_number = "1001"
        settings.local_ipat.member_id = "ABCD"
        settings.local_ipat.pin = "1234"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()
        events = []

        executor._local_select_venue = lambda _p, _v: events.append("venue")  # type: ignore[method-assign]
        executor._local_open_odds_vote = lambda _p, _r: events.append("odds")  # type: ignore[method-assign]
        executor._local_input_ticket = lambda _p, _r, _t: events.append("ticket")  # type: ignore[method-assign]
        executor._local_fill_ticket_amounts = lambda _p, _ts: events.append("amounts")  # type: ignore[method-assign]
        executor._local_move_to_confirm = lambda _p: events.append("confirm")  # type: ignore[method-assign]
        executor._local_fill_pin_and_total = lambda _p, _y: events.append("pin_total")  # type: ignore[method-assign]
        executor._local_submit_and_return = lambda _p: events.append("submit")  # type: ignore[method-assign]

        result = executor._execute_local(
            page,
            {"race": {"venue_name": "高知", "race_num": 3}},
            [{"market": "ワイド", "combo": "1-2", "numbers": [1, 2], "bet_yen": 100}],
            total_yen=100,
        )

        self.assertEqual(result.get("status"), "submitted")
        self.assertIn("submit", events)

    def test_execute_local_skips_when_market_is_unsupported(self):
        settings = AppSettings()
        settings.local_ipat.member_number = "1001"
        settings.local_ipat.member_id = "ABCD"
        settings.local_ipat.pin = "1234"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()

        result = executor._execute_local(
            page,
            {"race": {"venue_name": "高知", "race_num": 3}},
            [{"market": "単勝", "combo": "1", "numbers": [1], "bet_yen": 100}],
            total_yen=100,
        )

        self.assertEqual(result.get("status"), "skipped_unsupported_market")

    def test_wait_local_post_login_ready_handles_mail_notice(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()
        calls = {"dismiss": 0}

        def _fake_dismiss(_p):
            calls["dismiss"] += 1
            return calls["dismiss"] == 1

        def _fake_home_ready(_p):
            return calls["dismiss"] >= 2

        executor._dismiss_local_mail_notice_if_present = _fake_dismiss  # type: ignore[method-assign]
        executor._is_local_home_ready = _fake_home_ready  # type: ignore[method-assign]

        executor._wait_local_post_login_ready(page, timeout_ms=1200)
        self.assertGreaterEqual(calls["dismiss"], 1)

    def test_dismiss_local_interrupts_checks_popup_and_mail_notice(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()
        calls = {"popup": 0, "mail": 0}

        def _fake_popup(_p):
            calls["popup"] += 1
            return calls["popup"] == 1

        def _fake_mail(_p):
            calls["mail"] += 1
            return calls["mail"] == 1

        executor._dismiss_local_popup_if_present = _fake_popup  # type: ignore[method-assign]
        executor._dismiss_local_mail_notice_if_present = _fake_mail  # type: ignore[method-assign]

        self.assertTrue(executor._dismiss_local_interrupts_if_present(page))
        self.assertGreaterEqual(calls["popup"], 1)
        self.assertGreaterEqual(calls["mail"], 1)

    def test_local_move_to_confirm_retries_with_interrupt_check(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()
        calls = {"dismiss": 0, "click": 0, "wait": 0}

        def _fake_dismiss(_p):
            calls["dismiss"] += 1
            return False

        def _fake_click(_p, _key, *_fallbacks, required=True):
            calls["click"] += 1
            return True

        def _fake_wait(_p, _selectors, timeout_ms=0, poll_ms=0):
            calls["wait"] += 1
            return calls["wait"] >= 2

        executor._dismiss_local_interrupts_if_present = _fake_dismiss  # type: ignore[method-assign]
        executor._click_first_visible = _fake_click  # type: ignore[method-assign]
        executor._local_wait_for_any_visible = _fake_wait  # type: ignore[method-assign]

        executor._local_move_to_confirm(page)

        self.assertEqual(calls["click"], 2)
        self.assertEqual(calls["wait"], 2)
        self.assertGreaterEqual(calls["dismiss"], 3)

    def test_local_submit_and_return_retries_with_interrupt_check(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()
        calls = {"dismiss": 0, "vote_click": 0, "return_click": 0, "wait": 0}

        def _fake_dismiss(_p):
            calls["dismiss"] += 1
            return False

        def _fake_click(_p, key, *_fallbacks, required=True):
            if key == "local_vote_button":
                calls["vote_click"] += 1
            if key == "local_return_kaisai_button":
                calls["return_click"] += 1
            return True

        def _fake_wait(_p, _selectors, timeout_ms=0, poll_ms=0):
            calls["wait"] += 1
            return calls["wait"] >= 2

        executor._dismiss_local_interrupts_if_present = _fake_dismiss  # type: ignore[method-assign]
        executor._click_first_visible = _fake_click  # type: ignore[method-assign]
        executor._local_wait_for_any_visible = _fake_wait  # type: ignore[method-assign]

        executor._local_submit_and_return(page)

        self.assertEqual(calls["vote_click"], 2)
        self.assertEqual(calls["wait"], 2)
        self.assertEqual(calls["return_click"], 1)
        self.assertGreaterEqual(calls["dismiss"], 4)

    def test_refresh_local_info_runs_update_when_button_available(self):
        settings = AppSettings()
        settings.local_ipat.member_number = "1001"
        settings.local_ipat.member_id = "ABCD"
        settings.local_ipat.pin = "1234"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        page = _DummyPage()
        calls = {"login": 0, "refresh": 0}

        executor._validate_ipat_settings = lambda: "https://www.spat4.jp/keiba/pc"  # type: ignore[method-assign]
        executor._ensure_page = lambda: page  # type: ignore[method-assign]
        executor._ensure_logged_in_local = lambda _p, _u: calls.__setitem__("login", calls["login"] + 1)  # type: ignore[method-assign]
        executor._local_refresh_info = lambda _p: calls.__setitem__("refresh", calls["refresh"] + 1) or True  # type: ignore[method-assign]

        result = executor.refresh_local_info()

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("status"), "refreshed")
        self.assertEqual(calls["login"], 1)
        self.assertEqual(calls["refresh"], 1)

    def test_refresh_local_info_skips_for_non_local_target(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="central")
        result = executor.refresh_local_info()
        self.assertFalse(bool(result.get("ok")))
        self.assertEqual(result.get("status"), "skip_not_local")

    def test_refresh_central_info_runs_update_when_keirin_mode(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        settings.ipat.inet_id = "ABC123"
        settings.ipat.password = "PASS1234"
        settings.ipat.pars_no = "1234"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="central")
        calls = {"login": 0}

        class _Page:
            def __init__(self):
                self.url = "https://keirin.jp/pc/top"
                self.goto_calls = 0

            def goto(self, url: str, wait_until: str = "domcontentloaded"):
                _ = wait_until
                self.goto_calls += 1
                self.url = str(url)

            def wait_for_timeout(self, _ms: int) -> None:
                return

        page = _Page()
        executor._validate_ipat_settings = lambda: "https://keirin.jp/pc/top"  # type: ignore[method-assign]
        executor._ensure_page = lambda: page  # type: ignore[method-assign]
        executor._ensure_logged_in_keirin = lambda _p, _u: calls.__setitem__("login", calls["login"] + 1)  # type: ignore[method-assign]
        executor._is_keirin_logged_in = lambda _p: True  # type: ignore[method-assign]

        result = executor.refresh_central_info()

        self.assertTrue(bool(result.get("ok")))
        self.assertEqual(result.get("status"), "refreshed")
        self.assertEqual(page.goto_calls, 1)
        self.assertGreaterEqual(calls["login"], 1)

    def test_refresh_central_info_skips_for_local_target(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="local")
        result = executor.refresh_central_info()
        self.assertFalse(bool(result.get("ok")))
        self.assertEqual(result.get("status"), "skip_not_central")

    def test_refresh_central_info_runs_update_when_kyoutei_mode(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://ib.mbrace.or.jp/"
        settings.ipat.inet_id = "12345678"
        settings.ipat.pars_no = "1234"
        settings.ipat.password = "AUTHPASS"
        settings.ipat.login_id = "VOTEPASS"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None, target="central")
        calls = {"login": 0, "wait": 0}

        class _Page:
            def __init__(self):
                self.url = "https://ib.mbrace.or.jp/tohyo-ap-pctohyo-web/"
                self.reload_calls = 0

            def reload(self, wait_until: str = "domcontentloaded"):
                _ = wait_until
                self.reload_calls += 1

            def wait_for_timeout(self, _ms: int) -> None:
                return

        page = _Page()
        executor._validate_ipat_settings = lambda: "https://ib.mbrace.or.jp/"  # type: ignore[method-assign]
        executor._ensure_page = lambda: page  # type: ignore[method-assign]
        executor._ensure_logged_in_kyoutei = lambda _p, _u: calls.__setitem__("login", calls["login"] + 1) or page  # type: ignore[method-assign]
        executor._kyoutei_wait_top_page_ready = lambda _p: calls.__setitem__("wait", calls["wait"] + 1)  # type: ignore[method-assign]

        result = executor.refresh_central_info()

        self.assertTrue(bool(result.get("ok")))
        self.assertEqual(result.get("status"), "refreshed")
        self.assertEqual(page.reload_calls, 1)
        self.assertEqual(calls["login"], 1)
        self.assertEqual(calls["wait"], 1)


class IpatPlaywrightKeirinTests(unittest.TestCase):
    def test_validate_keirin_requires_credentials(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        settings.ipat.inet_id = ""
        settings.ipat.password = ""
        settings.ipat.pars_no = ""
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)

        with self.assertRaises(IpatEntryError):
            executor._validate_ipat_settings()

    def test_validate_keirin_accepts_credentials(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        settings.ipat.inet_id = "ABC123"
        settings.ipat.password = "PASS1234"
        settings.ipat.pars_no = "1234"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)

        resolved = executor._validate_ipat_settings()
        self.assertEqual(resolved, "https://keirin.jp/pc/top")

    def test_validate_kyoutei_requires_credentials(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://ib.mbrace.or.jp/"
        settings.ipat.inet_id = ""
        settings.ipat.pars_no = ""
        settings.ipat.password = ""
        settings.ipat.login_id = ""
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)

        with self.assertRaises(IpatEntryError):
            executor._validate_ipat_settings()

    def test_validate_kyoutei_accepts_credentials(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://ib.mbrace.or.jp/"
        settings.ipat.inet_id = "12345678"
        settings.ipat.pars_no = "1234"
        settings.ipat.password = "AUTHPASS"
        settings.ipat.login_id = "VOTEPASS"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)

        resolved = executor._validate_ipat_settings()
        self.assertEqual(resolved, "https://ib.mbrace.or.jp/")

    def test_kyoutei_sanrenpuku_maps_to_boatrace_kachishiki(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        row = _normalize_ticket({"market": "三連複", "combo": "3-1-2", "bet_yen": 500})
        calls = []

        class _Page:
            def evaluate(self, _script, payload=None):
                calls.append(dict(payload or {}))
                return {"ok": True, "isErrorDisp": False}

        executor._kyoutei_add_ticket(_Page(), row)

        self.assertEqual(row["market"], "3連複")
        self.assertEqual(row["numbers"], [1, 2, 3])
        self.assertEqual(calls[0]["numberOfSheets"], 5)
        self.assertEqual(calls[0]["kachishiki"], "7")
        self.assertEqual(calls[0]["selectList"], ["1", "2", "3"])

    def test_keirin_required_positions(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)

        self.assertEqual(executor._keirin_required_positions("2車単", [1, 2]), 2)
        self.assertEqual(executor._keirin_required_positions("2車複", [1, 2]), 2)
        self.assertEqual(executor._keirin_required_positions("3連単", [1, 2, 3]), 3)

    def test_keirin_insufficient_funds_message_detect(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        self.assertTrue(executor._keirin_is_insufficient_funds_message("成立予定合計金額が購入限度額を超えています。ご確認ください。"))
        self.assertFalse(executor._keirin_is_insufficient_funds_message("投票成立予定 受付番号数 1"))

    def test_keirin_is_top_page_detects_top_url(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)

        class _Page:
            def __init__(self):
                self.url = "https://keirin.jp/pc/top"

        page = _Page()
        executor._is_visible = lambda _p, _sel: False  # type: ignore[method-assign]

        self.assertTrue(executor._keirin_is_top_page(page))

    def test_keirin_is_top_page_returns_false_on_racevote_url(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)

        class _Page:
            def __init__(self):
                self.url = "https://keirin.jp/pc/racevote"

        page = _Page()
        executor._is_visible = lambda _p, _sel: True  # type: ignore[method-assign]

        self.assertFalse(executor._keirin_is_top_page(page))

    def test_keirin_is_top_page_returns_false_when_racevote_ui_is_visible(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)

        class _Page:
            def __init__(self):
                self.url = "https://keirin.jp/pc/unknown"

        page = _Page()

        def _is_visible(_p, sel):
            return "cmbKakesiki" in str(sel)

        executor._is_visible = _is_visible  # type: ignore[method-assign]
        self.assertFalse(executor._keirin_is_top_page(page))

    def test_keirin_return_top_dismisses_confirm_after_top_click(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        page = _DummyPage()
        calls = {"click_top": 0, "dismiss": 0, "is_top": 0}
        state = {"top": False}

        executor._keirin_is_top_page = lambda _p: calls.__setitem__("is_top", calls["is_top"] + 1) or state["top"]  # type: ignore[method-assign]
        executor._click_first_visible = (  # type: ignore[method-assign]
            lambda _p, _key, *_fallbacks, required=False: calls.__setitem__("click_top", calls["click_top"] + 1) or True
        )

        def _dismiss(_p):
            calls["dismiss"] += 1
            if calls["dismiss"] == 1:
                state["top"] = True
                return True
            return False

        executor._keirin_dismiss_confirm_dialog = _dismiss  # type: ignore[method-assign]

        ok = executor._keirin_return_top(page)
        self.assertTrue(ok)
        self.assertGreaterEqual(calls["click_top"], 1)
        self.assertGreaterEqual(calls["dismiss"], 1)

    def test_keirin_return_top_falls_back_to_login_url_when_button_missing(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)

        class _Page:
            def __init__(self):
                self.url = "https://keirin.jp/pc/vote"
                self.goto_calls = 0

            def goto(self, url: str, wait_until: str = "domcontentloaded"):
                _ = wait_until
                self.goto_calls += 1
                self.url = str(url)

            def wait_for_timeout(self, _ms: int) -> None:
                return

        page = _Page()
        executor._click_first_visible = lambda _p, _key, *_fallbacks, required=False: False  # type: ignore[method-assign]
        executor._keirin_dismiss_confirm_dialog = lambda _p: False  # type: ignore[method-assign]

        ok = executor._keirin_return_top(page)
        self.assertTrue(ok)
        self.assertEqual(page.goto_calls, 1)

    def test_keirin_return_top_handles_delayed_confirm_after_top_detected(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        page = _DummyPage()
        state = {"on_top": False}
        calls = {"dismiss": 0}

        executor._keirin_is_top_page = lambda _p: state["on_top"]  # type: ignore[method-assign]
        executor._click_first_visible = (  # type: ignore[method-assign]
            lambda _p, _key, *_fallbacks, required=False: state.__setitem__("on_top", True) or True
        )

        def _dismiss(_p):
            calls["dismiss"] += 1
            # トップ判定後に遅れて確認ダイアログが出るケースを再現
            return calls["dismiss"] == 2

        executor._keirin_dismiss_confirm_dialog = _dismiss  # type: ignore[method-assign]

        ok = executor._keirin_return_top(page)
        self.assertTrue(ok)
        self.assertGreaterEqual(calls["dismiss"], 3)

    def test_keirin_click_number_raises_funds_error_when_warning_present(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        page = _DummyPage()

        executor._keirin_collect_warning_text = (  # type: ignore[method-assign]
            lambda _p: "成立予定合計金額が購入限度額を超えています。ご確認ください。"
        )
        executor._first_enabled_button = lambda _p, _s, contains_text="", exact_text="": None  # type: ignore[method-assign]
        executor._first_visible = lambda _p, _s: None  # type: ignore[method-assign]

        with self.assertRaises(IpatEntryError) as ctx:
            executor._keirin_click_number(page, 1, 1)
        self.assertIn("購入限度額を超えました", str(ctx.exception))

    def test_keirin_find_group_for_ticket_skips_used_selector(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        page = _DummyPage()
        groups = [
            {"id": "divKIM0", "idx": 1, "combo": "3-2", "market": "２車単 フォーメーション", "sub_total": "100", "unit": "1"},
            {"id": "divKIM1", "idx": 2, "combo": "3-2", "market": "２車単 フォーメーション", "sub_total": "100", "unit": "1"},
        ]
        executor._keirin_collect_groups = lambda _p: list(groups)  # type: ignore[method-assign]

        selector = executor._keirin_find_group_for_ticket(page, "2車単", [3, 2], {"#divKIM0"})
        self.assertEqual(selector, "#divKIM1")

    def test_keirin_find_group_for_ticket_combo_only_fallback(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        page = _DummyPage()
        groups = [
            {"id": "divKIM2", "idx": 1, "combo": "2-3", "market": "", "sub_total": "100", "unit": "1"},
        ]
        executor._keirin_collect_groups = lambda _p: list(groups)  # type: ignore[method-assign]

        selector = executor._keirin_find_group_for_ticket(page, "2車複", [2, 3], set())
        self.assertEqual(selector, "#divKIM2")

    def test_keirin_combo_match_accepts_duplicated_pattern(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        self.assertTrue(executor._keirin_combo_match("7-1-7-1", [7, 1]))
        self.assertTrue(executor._keirin_combo_match("1-2-3-1-2-3", [1, 2, 3]))
        self.assertFalse(executor._keirin_combo_match("7-1-7-2", [7, 1]))

    def test_keirin_find_group_for_ticket_accepts_duplicated_combo_text(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        page = _DummyPage()
        groups = [
            {
                "id": "divKIM0",
                "idx": 1,
                "combo": "7-1-7-1",
                "market": "２車単 フォーメーション",
                "sub_total": "100",
                "unit": "1",
            },
        ]
        executor._keirin_collect_groups = lambda _p: list(groups)  # type: ignore[method-assign]

        selector = executor._keirin_find_group_for_ticket(page, "2車単", [7, 1], set())
        self.assertEqual(selector, "#divKIM0")

    def test_execute_keirin_prepared_moves_to_pin_screen(self):
        settings = AppSettings()
        settings.ipat.submit_enabled = False
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        page = _DummyPage()
        calls = {"open": 0, "set": 0, "move": 0}

        executor._keirin_open_target_race = lambda _p, _payload: calls.__setitem__("open", calls["open"] + 1)  # type: ignore[method-assign]
        executor._keirin_set_ticket = lambda _p, _ticket, _used: calls.__setitem__("set", calls["set"] + 1)  # type: ignore[method-assign]
        executor._keirin_read_summary_total = lambda _p: 900  # type: ignore[method-assign]
        executor._keirin_move_to_pin_screen = lambda _p, total_yen: calls.__setitem__("move", calls["move"] + int(total_yen))  # type: ignore[method-assign]

        result = executor._execute_keirin(
            page,
            {"race": {"venue_name": "高知", "race_num": 8}},
            [
                {"market": "2車単", "combo": "2-1", "numbers": [2, 1], "bet_yen": 300},
                {"market": "2車複", "combo": "1-2", "numbers": [1, 2], "bet_yen": 600},
            ],
            total_yen=900,
        )

        self.assertEqual(result.get("status"), "prepared")
        self.assertEqual(calls["open"], 1)
        self.assertEqual(calls["set"], 2)
        self.assertEqual(calls["move"], 900)

    def test_execute_kyoutei_prepared_moves_to_confirm_screen(self):
        settings = AppSettings()
        settings.ipat.submit_enabled = False
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        page = _DummyPage()
        calls = {"open": 0, "set": 0, "move": 0}

        executor._kyoutei_open_target_race = lambda _p, _payload: calls.__setitem__("open", calls["open"] + 1)  # type: ignore[method-assign]
        executor._kyoutei_add_ticket = lambda _p, _ticket: calls.__setitem__("set", calls["set"] + 1)  # type: ignore[method-assign]
        executor._kyoutei_move_to_confirm = lambda _p: calls.__setitem__("move", calls["move"] + 1)  # type: ignore[method-assign]

        result = executor._execute_kyoutei(
            page,
            {"race": {"venue_name": "大村", "race_num": 1}},
            [
                {"market": "2連複", "combo": "1-2", "numbers": [1, 2], "bet_yen": 4200},
            ],
            total_yen=4200,
        )

        self.assertEqual(result.get("status"), "prepared")
        self.assertEqual(calls["open"], 1)
        self.assertEqual(calls["set"], 1)
        self.assertEqual(calls["move"], 1)

    def test_execute_keirin_returns_top_on_insufficient_funds_error(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        page = _DummyPage()
        calls = {"return_top": 0}

        executor._validate_ipat_settings = lambda: "https://keirin.jp/pc/top"  # type: ignore[method-assign]
        executor._ensure_page = lambda: page  # type: ignore[method-assign]
        executor._ensure_logged_in_keirin = lambda _p, _u: None  # type: ignore[method-assign]
        executor._execute_keirin = (  # type: ignore[method-assign]
            lambda _p, _payload, _tickets, _total: (_ for _ in ()).throw(
                IpatEntryError("購入限度額を超えました。入金後に再実行してください。")
            )
        )
        executor._save_debug_artifacts = lambda _p, _r: "runtime_logs/debug/mock"  # type: ignore[method-assign]
        executor._keirin_return_top = lambda _p: calls.__setitem__("return_top", calls["return_top"] + 1) or True  # type: ignore[method-assign]

        with self.assertRaises(IpatEntryError) as ctx:
            executor.execute(
                {"race": {"race_id": "高知_09R"}},
                [{"market": "2車単", "combo": "1-3", "bet_yen": 100}],
            )
        self.assertIn("debug: runtime_logs/debug/mock", str(ctx.exception))
        self.assertEqual(calls["return_top"], 1)

    def test_execute_keirin_unavailable_race_returns_status(self):
        settings = AppSettings()
        settings.ipat.login_url = "https://keirin.jp/pc/top"
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        page = _DummyPage()
        calls = {"return_top": 0}

        executor._validate_ipat_settings = lambda: "https://keirin.jp/pc/top"  # type: ignore[method-assign]
        executor._ensure_page = lambda: page  # type: ignore[method-assign]
        executor._ensure_logged_in_keirin = lambda _p, _u: None  # type: ignore[method-assign]
        executor._execute_keirin = (  # type: ignore[method-assign]
            lambda _p, _payload, _tickets, _total: (_ for _ in ()).throw(
                IpatRaceUnavailableError("対象会場は見つかりましたが指定Rは未発売です")
            )
        )
        executor._keirin_return_top = lambda _p: calls.__setitem__("return_top", calls["return_top"] + 1) or True  # type: ignore[method-assign]

        result = executor.execute(
            {"race": {"race_id": "小松島_06R"}},
            [{"market": "2車複", "combo": "1-6", "bet_yen": 100}],
        )

        self.assertEqual(result.get("status"), "unavailable_race")
        self.assertEqual(calls["return_top"], 1)

    def test_keirin_open_target_race_fallback_clicks_same_venue_even_if_race_text_differs(self):
        settings = AppSettings()
        events = []
        executor = IpatPlaywrightExecutor(settings, event_logger=events.append)
        btn = _DummyVoteButton(visible=True, disabled=False)
        page = _DummyVotePage(
            [
                _DummyVoteRow("小松島 3R 発売締切 09:28 LIVE 投票", [btn]),
                _DummyVoteRow("高知 1R 発売締切 20:37 LIVE 投票", [_DummyVoteButton()]),
            ]
        )

        executor._keirin_wait_vote_page_ready = lambda _p: None  # type: ignore[method-assign]

        executor._keirin_open_target_race(
            page,
            {"race": {"venue_name": "小松島", "race_num": 6}},
        )

        self.assertEqual(btn.clicked, 1)
        self.assertTrue(any("投票ボタン押下(会場優先)" in str(line) for line in events))

    def test_keirin_open_target_race_uses_broad_default_selectors(self):
        settings = AppSettings()
        executor = IpatPlaywrightExecutor(settings, event_logger=lambda _line: None)
        btn = _DummyVoteButton(visible=True, disabled=False)
        row = _DummyVoteRow("大垣 1R 発売締切 11:25 LIVE 投票", [btn])
        page = _DummyVotePage([row])

        # 空文字を設定してフォールバックセレクタを強制適用する。
        executor.selectors["keirin_vote_rows"] = ""
        executor.selectors["keirin_vote_button"] = ""
        executor._keirin_wait_vote_page_ready = lambda _p: None  # type: ignore[method-assign]

        executor._keirin_open_target_race(
            page,
            {"race": {"venue_name": "大垣", "race_num": 1}},
        )

        self.assertIn("li.kyotuHeader", page.last_selector)
        self.assertIn("input[id^='hcombtnTouhyou']", row.last_locator_selector)
        self.assertEqual(btn.clicked, 1)


if __name__ == "__main__":
    unittest.main()

