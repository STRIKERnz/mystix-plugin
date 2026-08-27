"""RuneLite Bridge custom integration."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.const import Platform
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

PLATFORMS = (Platform.SENSOR,)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the bridge and its Mystix-compatible HTTP endpoints."""
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    payloads = await store.async_load() or {}

    runtime = {
        "app_key": entry.data[CONF_APP_KEY],
        "payloads": payloads,
        "store": store,
        "listeners": [],
    }
    hass.data[DOMAIN] = runtime

    for endpoint in SYNC_ENDPOINTS:
        hass.http.register_view(RuneLiteSyncView(endpoint))
    hass.http.register_view(RuneLiteAssetView("items", "{asset_id:\\d+}"))
    hass.http.register_view(RuneLiteAssetView("skills", "{asset_id:[a-z_]+}"))
    hass.http.register_view(RuneLiteAssetView("hiscores", "{asset_id:[a-z0-9_]+}"))
    hass.http.register_view(RuneLiteAssetView("ui", "{asset_id:[a-z_]+}"))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload bridge state."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
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
        for listener in runtime["listeners"]:
            listener(self.endpoint)
        hass.bus.async_fire(
            f"{DOMAIN}_sync",
            {"sync_type": self.endpoint, "payload": payload},
        )

        return web.json_response({"success": True})


class RuneLiteAssetView(HomeAssistantView):
    """Receive a small sprite extracted from RuneLite's local cache."""

    requires_auth = False

    def __init__(self, asset_kind: str, route_parameter: str) -> None:
        self.asset_kind = asset_kind
        self.url = f"/api/runelite/assets/{asset_kind}/{route_parameter}/"
        self.name = f"api:runelite_bridge:{asset_kind}_asset"

    async def post(self, request: web.Request, asset_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        runtime = hass.data.get(DOMAIN)
        if runtime is None:
            return web.json_response({"error": "not_configured"}, status=503)
        supplied_key = request.headers.get("X-RuneLite-Key", "")
        if not supplied_key or not secrets.compare_digest(supplied_key, runtime["app_key"]):
            return web.json_response({"error": "unauthorized"}, status=401)
        if request.content_type != "image/png":
            return web.json_response({"error": "png_required"}, status=415)

        body = await request.read()
        if not body.startswith(b"\x89PNG\r\n\x1a\n") or len(body) > 256 * 1024:
            return web.json_response({"error": "invalid_png"}, status=400)

        directory = Path(hass.config.path("www", "runelite", self.asset_kind))
        destination = directory / f"{asset_id}.png"

        def write_icon() -> None:
            directory.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or destination.read_bytes() != body:
                destination.write_bytes(body)

        await hass.async_add_executor_job(write_icon)
        return web.json_response(
            {"success": True, "url": f"/local/runelite/{self.asset_kind}/{asset_id}.png"}
        )
