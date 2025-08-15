from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .websocket_client import Od11Client

_LOGGER = logging.getLogger(__name__)


class Od11Coordinator(DataUpdateCoordinator):
    """Keeps latest state from the OD-11 client and surfaces it to entities."""

    def __init__(self, hass: HomeAssistant, client: Od11Client) -> None:
        super().__init__(hass, _LOGGER, name="od11", update_interval=timedelta(seconds=15))
        self.client = client
        self._event = asyncio.Event()

        # When client state changes, poke the coordinator
        self.client.add_listener(lambda: self._notify())

    async def _notify(self):
        self._event.set()

    async def _async_update_data(self):
        # We mostly get push updates; this just throttles re-renders.
        # Wait briefly for a push or timeout.
        try:
            self._event.clear()
            await asyncio.wait_for(self._event.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        # Return a snapshot dict
        return {
            "sid": self.client.sid,
            "volume": self.client.volume,
            "source_id": self.client.source_id,
            "sources": self.client.sources,
            "mac": self.client.mac,
            "ssid": self.client.ssid,
            "wifi_quality": self.client.wifi_quality,
            "revision": self.client.revision,
        }

