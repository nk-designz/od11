from __future__ import annotations

from typing import Dict

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CANONICAL_SOURCES, SOURCE_ALIASES
from .coordinator import Od11Coordinator

def _simplify(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())

def resolve_source_to_id(coord: Od11Coordinator, query: str) -> int:
    """Map a string (name/alias/id) to a source id."""
    data = coord.data or {}
    sources: Dict[int, str] = data.get("sources") or {}
    simp = _simplify(query)

    # numeric?
    if simp.isdigit():
        return int(simp)

    # alias → canonical
    canon = SOURCE_ALIASES.get(simp, simp)

    # snapshot exact
    for i, nm in sources.items():
        if _simplify(nm) == canon:
            return int(i)

    # snapshot friendly startswith/contains
    for i, nm in sources.items():
        s = _simplify(nm)
        if s.startswith(canon) or canon in s:
            return int(i)

    # fallback canonical map
    if canon in CANONICAL_SOURCES:
        return CANONICAL_SOURCES[canon]

    raise ValueError(f"Unknown source {query!r}")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coord: Od11Coordinator = data["coordinator"]
    device_info = data["device_info"]
    async_add_entities([Od11InputSelect(coord, device_info)], True)

class Od11InputSelect(SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Input"

    def __init__(self, coordinator: Od11Coordinator, device_info):
        self.coordinator = coordinator
        self._attr_unique_id = f"{self.coordinator.client._host}_input"
        self._attr_device_info = device_info

    @property
    def options(self):
        # Present friendly names in a stable order by id
        srcs = self.coordinator.data.get("sources") or {}
        return [srcs[i] for i in sorted(srcs.keys())] if srcs else []

    @property
    def current_option(self):
        src_id = self.coordinator.data.get("source_id")
        srcs = self.coordinator.data.get("sources") or {}
        return srcs.get(src_id)

    async def async_select_option(self, option: str) -> None:
        # Resolve by name
        srcs = self.coordinator.data.get("sources") or {}
        inv = {v: k for k, v in srcs.items()}
        src_id = inv.get(option)
        if src_id is None:
            # attempt relaxed resolve
            src_id = resolve_source_to_id(self.coordinator, option)
        await self.coordinator.client.set_input(int(src_id))
        await self.coordinator.async_request_refresh()

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()
