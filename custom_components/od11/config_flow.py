from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, DEFAULT_WS_PATH

STEP_USER = vol.Schema({
    vol.Required("host"): str,          # e.g. 10.13.12.212
    vol.Optional("ws_path", default=DEFAULT_WS_PATH): str,  # usually /ws
    vol.Optional("origin"): str,        # defaults to http://<host>
    vol.Optional("cookie"): str,        # optional orthoplay=...
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER)
        # Basic uniqueness by host
        await self.async_set_unique_id(f"{DOMAIN}_{user_input['host']}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=f"OD-11 ({user_input['host']})", data=user_input)
