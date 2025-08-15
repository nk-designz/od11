from __future__ import annotations

import voluptuous as vol
from functools import partial

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .websocket_client import Od11Client
from .coordinator import Od11Coordinator

PLATFORMS = ["number", "select"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """YAML setup not used; just return True."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OD-11 from a config entry."""
    host: str = entry.data["host"]
    ws_path: str = entry.data.get("ws_path", "/ws")
    origin: str = entry.data.get("origin") or f"http://{host}"
    cookie: str | None = entry.data.get("cookie")

    session = aiohttp_client.async_get_clientsession(hass)
    client = Od11Client(
        session,
        host=host,
        ws_path=ws_path,
        origin=origin,
        cookie=cookie,
    )
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

    # -------- Services (explicit) --------

    async def svc_volume_set(call: ServiceCall) -> None:
        target = int(call.data["volume"])
        await client.set_volume_absolute(target)
        await coord.async_request_refresh()

    async def svc_volume_nudge(call: ServiceCall) -> None:
        amt = int(call.data["amount"])
        await client.nudge_volume(amt)
        await coord.async_request_refresh()

    # Resolve string/id/alias to a source id using the select helper
    from .select import resolve_source_to_id

    async def svc_set_input(call: ServiceCall) -> None:
        src = str(call.data["source"]).strip().lower()
        src_id = resolve_source_to_id(coord, src)
        await client.set_input(src_id)
        await coord.async_request_refresh()

    # Convenience wrappers per input (use partial to avoid late-binding issues)
    async def _svc_set_input_key(call: ServiceCall, key: str) -> None:
        src_id = resolve_source_to_id(coord, key)
        await client.set_input(src_id)
        await coord.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "volume_set",
        svc_volume_set,
        schema=vol.Schema({vol.Required("volume"): vol.All(int, vol.Range(min=0, max=100))}),
    )
    hass.services.async_register(
        DOMAIN,
        "volume_nudge",
        svc_volume_nudge,
        schema=vol.Schema({vol.Required("amount"): int}),
    )
    hass.services.async_register(
        DOMAIN,
        "set_input",
        svc_set_input,
        schema=vol.Schema({vol.Required("source"): str}),
    )

    for key in ("airplay", "spotify", "playlist", "linein", "optical", "bluetooth"):
        hass.services.async_register(
            DOMAIN,
            f"set_input_{key}",
            partial(_svc_set_input_key, key=key),
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if data:
        client: Od11Client = data["client"]
        await client.close()  # WS only; aiohttp session is HA-managed

    return unload_ok

