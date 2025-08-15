from __future__ import annotations

import aiohttp
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, DEFAULT_WS_PATH
from .websocket_client import Od11Client
from .coordinator import Od11Coordinator

PLATFORMS = ["number", "select"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    host = entry.data["host"]
    ws_path = entry.data.get("ws_path", DEFAULT_WS_PATH)
    origin = entry.data.get("origin") or f"http://{host}"
    cookie = entry.data.get("cookie")

    session = aiohttp.ClientSession()
    client = Od11Client(session, host=host, ws_path=ws_path, origin=origin, cookie=cookie)
    await client.connect()

    coord = Od11Coordinator(hass, client)
    await coord.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coord,
        "device_info": DeviceInfo(
            identifiers={(DOMAIN, host)},
            manufacturer="Teenage Engineering",
            name=f"OD-11 {host}",
            model="OD-11",
            entry_type=DeviceEntryType.SERVICE,
        ),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    async def _vol_set(call):
        target = int(call.data["volume"])
        await client.set_volume_absolute(target)

    async def _vol_nudge(call):
        amt = int(call.data["amount"])
        await client.nudge_volume(amt)

    async def _set_input(call):
        src = str(call.data["source"]).strip().lower()
        # map name/alias/id using the Select entity helper (exposes map via coordinator)
        from .select import resolve_source_to_id  # lazy import
        src_id = resolve_source_to_id(coord, src)
        await client.set_input(src_id)

    for srv, schema in (
        ("volume_set", {"volume": int}),
        ("volume_nudge", {"amount": int}),
        ("set_input", {"source": str}),
    ):
        hass.services.async_register(DOMAIN, srv, locals()[f"_{srv.replace('od11.','')}"])

    # Convenience services
    async def _mk_setter(source_key: str):
        from .select import resolve_source_to_id
        src_id = resolve_source_to_id(coord, source_key)
        await client.set_input(src_id)

    for key in ("airplay", "spotify", "playlist", "linein", "optical", "bluetooth"):
        hass.services.async_register(DOMAIN, f"set_input_{key}", lambda call, k=key: _mk_setter(k))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["number", "select"])
    if data:
        client: Od11Client = data["client"]
        await client.close()
        await client._session.close()
    return unload_ok

