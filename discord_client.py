from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Callable, Dict, Iterable, Set
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import discord  # type: ignore
except Exception:
    discord = None


def _normalize_id_set(values: Iterable[str] | None) -> Set[str]:
    out: Set[str] = set()
    if values is None:
        return out
    for raw in values:
        text = str(raw or "").strip()
        if text:
            out.add(text)
    return out


class DiscordClientError(RuntimeError):
    pass


class DiscordGatewayClient:
    def __init__(
        self,
        bot_token: str,
        *,
        allowed_channel_ids: Iterable[str] | None = None,
        allowed_guild_ids: Iterable[str] | None = None,
    ) -> None:
        self.bot_token = str(bot_token or "").strip()
        if not self.bot_token:
            raise DiscordClientError("bot token is empty")
        self.allowed_channel_ids = _normalize_id_set(allowed_channel_ids)
        self.allowed_guild_ids = _normalize_id_set(allowed_guild_ids)
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: Any = None
        self._ready_event = threading.Event()
        self._started_event = threading.Event()
        self._last_error: Exception | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def start(
        self,
        *,
        on_message: Callable[[Dict[str, Any]], None],
        on_error: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        with self._lock:
            if self.running:
                raise DiscordClientError("discord gateway already running")
            self._last_error = None
            self._ready_event.clear()
            self._started_event.clear()
            self._thread = threading.Thread(
                target=self._run_gateway,
                args=(on_message, on_error, on_status),
                name="discord-gateway",
                daemon=True,
            )
            self._thread.start()

        if not self._started_event.wait(timeout=10.0):
            raise DiscordClientError("discord gateway start timeout")
        if self._last_error is not None:
            raise DiscordClientError(str(self._last_error))

    def stop(self, timeout_sec: float = 8.0) -> None:
        thread = self._thread
        loop = self._loop
        client = self._client

        if loop and client:
            try:
                future = asyncio.run_coroutine_threadsafe(client.close(), loop)
                future.result(timeout=max(1.0, float(timeout_sec) / 2.0))
            except Exception:
                pass
        if thread and thread.is_alive():
            thread.join(timeout=max(1.0, float(timeout_sec)))

    def fetch_recent_messages(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        timeout_sec: float = 10.0,
    ) -> list[Dict[str, Any]]:
        """Discord REST API からチャンネル履歴を取得する（起動時補完用）。"""
        cid = str(channel_id or "").strip()
        if not cid:
            return []
        lim = max(1, min(100, int(limit)))
        params = urlencode({"limit": lim})
        url = f"https://discord.com/api/v10/channels/{cid}/messages?{params}"
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "User-Agent": "KEIRIN-AI-ZERO/1.0",
        }
        req = Request(url=url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=max(1.0, float(timeout_sec))) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError):
            return []
        except Exception:
            return []

        try:
            arr = json.loads(body)
        except Exception:
            return []
        if not isinstance(arr, list):
            return []

        out: list[Dict[str, Any]] = []
        for msg in arr:
            if not isinstance(msg, dict):
                continue
            author = msg.get("author") if isinstance(msg.get("author"), dict) else {}
            out.append({
                "id": str(msg.get("id", "") or ""),
                "content": str(msg.get("content", "") or ""),
                "author": str(author.get("username", "") or ""),
                "author_id": str(author.get("id", "") or ""),
                "author_is_bot": bool(author.get("bot", False)),
                "channel_id": cid,
                "parent_channel_id": "",
                "guild_id": str(msg.get("guild_id", "") or ""),
                "webhook_id": str(msg.get("webhook_id", "") or ""),
                "timestamp": str(msg.get("timestamp", "") or ""),
            })
        return out

    def _run_gateway(
        self,
        on_message_cb: Callable[[Dict[str, Any]], None],
        on_error: Callable[[str], None] | None,
        on_status: Callable[[str], None] | None,
    ) -> None:
        try:
            if discord is None:
                raise DiscordClientError(
                    "discord.py が必要です。`pip install discord.py` を実行してください。"
                )

            intents = discord.Intents.none()
            intents.guilds = True
            intents.messages = True
            intents.message_content = True

            client = discord.Client(intents=intents)
            self._client = client
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            raw_message_counter = {"count": 0}

            @client.event
            async def on_ready() -> None:
                self._ready_event.set()
                guild_ids = ",".join(str(getattr(g, "id", "")) for g in list(getattr(client, "guilds", []))[:5]) or "-"
                visible_channels = []
                for g in list(getattr(client, "guilds", [])):
                    for c in list(getattr(g, "text_channels", [])):
                        visible_channels.append(str(getattr(c, "id", "") or ""))
                channels_sample = ",".join(visible_channels[:8]) if visible_channels else "-"
                if on_status:
                    on_status(
                        f"Gateway接続完了: user={client.user} "
                        f"guilds={len(getattr(client, 'guilds', []))} "
                        f"guild_ids={guild_ids} "
                        f"visible_text_channels={len(visible_channels)} "
                        f"channels_sample={channels_sample} "
                        f"channels_filter={len(self.allowed_channel_ids)} "
                        f"guilds_filter={len(self.allowed_guild_ids)}"
                    )

            @client.event
            async def on_disconnect() -> None:
                if on_status:
                    on_status("Gateway切断")

            @client.event
            async def on_resumed() -> None:
                if on_status:
                    on_status("Gateway再接続完了")

            @client.event
            async def on_socket_response(payload: Dict[str, Any]) -> None:
                if raw_message_counter["count"] >= 20:
                    return
                if not isinstance(payload, dict):
                    return
                if str(payload.get("t", "") or "") != "MESSAGE_CREATE":
                    return
                body = payload.get("d")
                if not isinstance(body, dict):
                    return
                author = body.get("author") if isinstance(body.get("author"), dict) else {}
                raw_message_counter["count"] += 1
                if on_status:
                    on_status(
                        "raw_message: "
                        f"channel={str(body.get('channel_id', '') or '') or '-'} "
                        f"guild={str(body.get('guild_id', '') or '') or '-'} "
                        f"author={str(author.get('username', '') or '') or '-'} "
                        f"author_id={str(author.get('id', '') or '') or '-'} "
                        f"author_bot={int(bool(author.get('bot', False)))} "
                        f"webhook={str(body.get('webhook_id', '') or '') or '-'} "
                        f"content_len={len(str(body.get('content', '') or ''))}"
                    )

            @client.event
            async def on_message(message) -> None:
                webhook_id = str(getattr(message, "webhook_id", "") or "")
                author = getattr(message, "author", None)
                author_id = str(getattr(author, "id", "") or "")
                author_is_bot = bool(author and getattr(author, "bot", False))

                channel_id = str(getattr(message.channel, "id", "") or "")
                parent_channel_id = str(getattr(message.channel, "parent_id", "") or "")
                guild = getattr(message, "guild", None)
                guild_id = str(getattr(guild, "id", "") or "")

                if self.allowed_channel_ids and channel_id not in self.allowed_channel_ids and parent_channel_id not in self.allowed_channel_ids:
                    if on_status:
                        on_status(
                            f"drop(channel_filter): channel={channel_id or '-'} "
                            f"parent={parent_channel_id or '-'} guild={guild_id or '-'} "
                            f"webhook={webhook_id or '-'}"
                        )
                    return
                if self.allowed_guild_ids and guild_id not in self.allowed_guild_ids:
                    if on_status:
                        on_status(
                            f"drop(guild_filter): channel={channel_id or '-'} "
                            f"guild={guild_id or '-'} webhook={webhook_id or '-'}"
                        )
                    return

                author_name = str(getattr(message.author, "name", "") or "")
                payload = {
                    "id": str(getattr(message, "id", "") or ""),
                    "content": str(getattr(message, "content", "") or ""),
                    "author": author_name,
                    "author_id": author_id,
                    "author_is_bot": author_is_bot,
                    "channel_id": channel_id,
                    "parent_channel_id": parent_channel_id,
                    "guild_id": guild_id,
                    "webhook_id": webhook_id,
                }
                try:
                    on_message_cb(payload)
                except Exception as exc:
                    if on_error:
                        on_error(f"message callback error: {exc}")

            self._started_event.set()
            if on_status:
                on_status("Gateway接続中")

            try:
                self._loop.run_until_complete(client.start(self.bot_token))
            finally:
                self._ready_event.clear()
        except Exception as exc:
            self._last_error = exc
            self._started_event.set()
            if on_error:
                on_error(str(exc))
        finally:
            if not self._started_event.is_set():
                self._started_event.set()
            try:
                if self._client is not None and not self._client.is_closed():
                    if self._loop:
                        self._loop.run_until_complete(self._client.close())
            except Exception:
                pass

            if self._loop:
                try:
                    self._loop.stop()
                except Exception:
                    pass
                try:
                    self._loop.close()
                except Exception:
                    pass

            self._client = None
            self._loop = None
