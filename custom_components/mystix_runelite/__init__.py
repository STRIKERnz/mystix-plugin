"""Mystix RuneLite receiver integration."""

from __future__ import annotations

import json

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_API_KEY, DOMAIN
from .http import RuneLiteApiView
from .store import RuneLiteStore

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {vol.Required(CONF_API_KEY): vol.All(cv.string, vol.Length(min=16))}
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_IMPORT_ROADMAPS = "import_roadmaps"
SERVICE_CLEAR_ROADMAPS = "clear_roadmaps"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the YAML-configured local API receiver."""
    integration_config = config.get(DOMAIN)
    if integration_config is None:
        return True

    store = RuneLiteStore(hass)
    await store.async_load()
    hass.data[DOMAIN] = store
    hass.http.register_view(RuneLiteApiView(hass, integration_config[CONF_API_KEY], store))

    async def async_import_roadmaps(call: ServiceCall) -> None:
        roadmaps = json.loads(call.data["roadmaps_json"])
        if not isinstance(roadmaps, list):
            raise vol.Invalid("roadmaps_json must contain a JSON list")
        await store.async_set_roadmaps(call.data["player"], roadmaps)

    async def async_clear_roadmaps(call: ServiceCall) -> None:
        await store.async_set_roadmaps(call.data["player"], [])

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_ROADMAPS,
        async_import_roadmaps,
        schema=vol.Schema(
            {vol.Required("player"): cv.string, vol.Required("roadmaps_json"): cv.string}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_ROADMAPS,
        async_clear_roadmaps,
        schema=vol.Schema({vol.Required("player"): cv.string}),
    )
    return True
