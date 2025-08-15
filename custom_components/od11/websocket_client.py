from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Tuple

import aiohttp

from .const import (
    DEFAULT_PROTOCOL_MAJOR,
    DEFAULT_PROTOCOL_MINOR,
    DEFAULT_COLOR_INDEX,
    DEFAULT_NAME,
    DEFAULT_REALTIME,
    DEFAULT_UID,
)

_LOGGER = logging.getLogger(__name__)


def _now_ms() -> int:
    import time
    return int(time.time() * 1000)


class Od11Client:
    """Minimal OD‑11 WebSocket client for Input + Volume only."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        ws_path: str,
        origin: Optional[str] = None,
        cookie: Optional[str] = None,
        name: str = DEFAULT_NAME,
        uid: str = DEFAULT_UID,
        color_index: int = DEFAULT_COLOR_INDEX,
        proto_major: int = DEFAULT_PROTOCOL_MAJOR,
        proto_minor: int = DEFAULT_PROTOCOL_MINOR,
        realtime_data: bool = DEFAULT_REALTIME,
        keepalive: int = 25,
    ) -> None:
        self._session = session
        self._host = host
        self._ws_path = ws_path if ws_path.startswith("/") else f"/{ws_path}"
        self._origin = origin
        self._cookie = cookie
        self._name = name
        self._uid = uid
        self._color_index = color_index
        self._proto_major = proto_major
        self._proto_minor = proto_minor
        self._realtime = realtime_data
        self._keepalive = keepalive

        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._task: Optional[asyncio.Task] = None
        self._pinger: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()

        # Live state (exposed)
        self.sid: Optional[int] = None
        self.volume: Optional[int] = None
        self.source_id: Optional[int] = None
        self.sources: Dict[int, str] = {}

        # Misc
        self.mac: Optional[str] = None
        self.ssid: Optional[str] = None
        self.wifi_quality: Optional[int] = None
        self.revision: Optional[str] = None

        self._last_ping_sent: Optional[int] = None
        self._listeners: list[callable] = []

    def add_listener(self, cb) -> None:
        """Register a callback invoked on any state change."""
        self._listeners.append(cb)

    async def _emit_listeners(self) -> None:
        for cb in self._listeners:
            try:
                maybe_coro = cb()
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
            except Exception:  # pragma: no cover
                _LOGGER.exception("Listener callback failed")

    async def connect(self) -> None:
        url = f"ws://{self._host}{self._ws_path}"
        headers = {}
        if self._origin:
            headers["Origin"] = self._origin.rstrip("/")
        if self._cookie:
            headers["Cookie"] = self._cookie

        _LOGGER.debug("Connecting WS %s", url)
        self.ws = await self._session.ws_connect(url, headers=headers)
        self._task = asyncio.create_task(self._reader_loop())
        if self._keepalive:
            self._pinger = asyncio.create_task(self._ping_loop())

        # Kick off handshake
        await self._send({
            "protocol_major_version": self._proto_major,
            "protocol_minor_version": self._proto_minor,
            "action": "global_join",
        })

    async def close(self) -> None:
        self._stopped.set()
        if self._pinger:
            self._pinger.cancel()
        if self._task:
            self._task.cancel()
        if self.ws and not self.ws.closed:
            await self.ws.close()

    async def _ping_loop(self) -> None:
        try:
            while not self._stopped.is_set():
                await asyncio.sleep(self._keepalive)
                if self.ws is None or self.ws.closed:
                    break
                ts = _now_ms()
                self._last_ping_sent = ts
                await self._send({"action": "speaker_ping", "value": ts}, log=False)
        except asyncio.CancelledError:
            pass

    async def _reader_loop(self) -> None:
        try:
            async for msg in self.ws:  # type: ignore
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    _LOGGER.error("WS error: %s", self.ws.exception())
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            _LOGGER.exception("WS reader crashed")

    async def _handle_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except Exception:
            _LOGGER.debug("Non-JSON message: %s", raw)
            return

        # global_joined -> send group_join
        if data.get("response") == "global_joined":
            # capture some device info if present
            self.mac = data.get("mac")
            self.ssid = data.get("ssid")
            st = data.get("state") or []
            if st and isinstance(st, list):
                for item in st:
                    if item.get("update") == "speaker_added":
                        spk = item.get("speaker") or {}
                        self.revision = spk.get("revision")
                        self.wifi_quality = spk.get("wifi_quality")

            await self._send({
                "color_index": self._color_index,
                "name": self._name,
                "realtime_data": self._realtime,
                "uid": self._uid,
                "action": "group_join",
            })
            return

        # group_joined snapshot
        if data.get("response") == "group_joined":
            self.sid = data.get("sid", self.sid)
            # sources
            self.sources = {int(s["id"]): str(s["name"]) for s in data.get("sources", [])}
            # state list
            for item in data.get("state", []):
                if item.get("update") == "group_volume_changed":
                    self.volume = int(item.get("vol"))
                if item.get("update") == "group_input_source_changed":
                    self.source_id = int(item.get("source"))
            await self._emit_listeners()
            return

        # speaker_pong
        if data.get("response") == "speaker_pong":
            # could compute RTT if value matches _last_ping_sent
            return

        # incremental updates
        upd = data.get("update")
        if upd == "group_volume_changed" and "vol" in data:
            self.volume = int(data["vol"])
            await self._emit_listeners()
        elif upd == "group_input_source_changed" and "source" in data:
            self.source_id = int(data["source"])
            await self._emit_listeners()

    async def _send(self, obj: Dict[str, Any], *, log: bool = True) -> None:
        if self.sid is not None and "sid" not in obj and obj.get("action", "").startswith("group_"):
            obj["sid"] = self.sid
        if log:
            _LOGGER.debug("-> %s", obj)
        assert self.ws is not None
        await self.ws.send_json(obj)

    # ---------- Public control methods ----------

    async def set_input(self, source_id: int) -> None:
        await self._send({"action": "group_set_input_source", "source": int(source_id)})

    async def nudge_volume(self, amount: int) -> None:
        await self._send({"action": "group_change_volume", "amount": int(amount)})

    async def set_volume_absolute(self, target: int) -> None:
        """Compute delta from current volume and send a single nudge."""
        target = max(0, min(100, int(target)))
        if self.volume is None:
            # wait briefly for a volume update after join (cheap)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=0.0)
            except Exception:
                pass
        cur = self.volume if self.volume is not None else 0
        delta = target - cur
        if delta:
            await self.nudge_volume(delta)

