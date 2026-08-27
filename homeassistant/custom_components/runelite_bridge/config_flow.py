"""Config flow for RuneLite Bridge."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_APP_KEY, DOMAIN


class RuneLiteBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a local RuneLite Bridge."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create the single bridge configuration."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="RuneLite Bridge",
                data={CONF_APP_KEY: user_input[CONF_APP_KEY].strip()},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_APP_KEY): str}),
        )
