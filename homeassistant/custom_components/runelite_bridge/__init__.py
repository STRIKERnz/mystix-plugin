"""RuneLite Bridge custom integration."""

from __future__ import annotations

import secrets
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_APP_KEY,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
    SYNC_ENDPOINTS,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the bridge and its Mystix-compatible HTTP endpoints."""
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    payloads = await store.async_load() or {}

    runtime = {
        "app_key": entry.data[CONF_APP_KEY],
        "payloads": payloads,
        "store": store,
    }
    hass.data[DOMAIN] = runtime

    for endpoint in SYNC_ENDPOINTS:
        hass.http.register_view(RuneLiteSyncView(endpoint))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload bridge state."""
    hass.data.pop(DOMAIN, None)
    return True


class RuneLiteSyncView(HomeAssistantView):
    """Receive one category of RuneLite sync payload."""

    requires_auth = False

    def __init__(self, endpoint: str) -> None:
        """Create a view for an API-compatible endpoint."""
        self.endpoint = endpoint
        self.url = f"/api/runelite/{endpoint}/"
        self.name = f"api:runelite_bridge:{endpoint.replace('/', '_')}"

    async def post(self, request: web.Request) -> web.Response:
        """Authenticate, validate, and persist the latest JSON payload."""
        hass: HomeAssistant = request.app["hass"]
        runtime = hass.data.get(DOMAIN)
        if runtime is None:
            return web.json_response({"error": "not_configured"}, status=503)

        supplied_key = request.headers.get("X-RuneLite-Key", "")
        if not supplied_key or not secrets.compare_digest(
            supplied_key, runtime["app_key"]
        ):
            return web.json_response({"error": "unauthorized"}, status=401)

        try:
            payload = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"error": "invalid_json"}, status=400)

        runtime["payloads"][self.endpoint] = payload
        await runtime["store"].async_save(runtime["payloads"])
        hass.bus.async_fire(
            f"{DOMAIN}_sync",
            {"sync_type": self.endpoint, "payload": payload},
        )

        return web.json_response({"success": True})
