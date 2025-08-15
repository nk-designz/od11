from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import Od11Coordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coord: Od11Coordinator = data["coordinator"]
    device_info = data["device_info"]
    async_add_entities([Od11VolumeNumber(coord, device_info)], True)

class Od11VolumeNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Volume"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: Od11Coordinator, device_info):
        self.coordinator = coordinator
        self._attr_unique_id = f"{self.coordinator.client._host}_volume"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        return self.coordinator.data.get("volume")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_volume_absolute(int(value))
        await self.coordinator.async_request_refresh()

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()
