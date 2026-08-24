"""HTTP endpoints matching the Mystix RuneLite API contract."""

from __future__ import annotations

import hmac
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import EVENT_SYNC, HEADER_API_KEY, SYNC_ENDPOINTS
from .store import RuneLiteStore


class RuneLiteApiView(HomeAssistantView):
    """Receive RuneLite requests using the plugin's existing routes."""

    url = "/api/runelite/{tail:.*}"
    name = "api:runelite"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, api_key: str, store: RuneLiteStore) -> None:
        self._hass = hass
        self._api_key = api_key
        self._store = store

    async def get(self, request: web.Request, tail: str) -> web.Response:
        if not self._authorized(request):
            return _error("Unauthorized", 401)

        route = tail.strip("/")
        if route == "slayer/catalog/status":
            payload_hash = request.query.get("hash", "")
            return web.json_response({"needed": await self._store.async_catalog_needed(payload_hash)})

        if route == "roadmaps":
            player = request.query.get("player", "")
            roadmaps = self._store.roadmaps_for(player)
            summaries = [
                {
                    "collection_id": roadmap.get("collection_id"),
                    "title": roadmap.get("title"),
                    "goal_count": len(roadmap.get("goals", [])),
                }
                for roadmap in roadmaps
            ]
            return web.json_response(
                {"player": player, "runelite_connected": bool(player), "roadmaps": summaries}
            )

        parts = route.split("/")
        if len(parts) == 2 and parts[0] == "roadmaps" and parts[1].isdigit():
            player = request.query.get("player", "")
            roadmap = self._store.roadmap(player, int(parts[1]))
            return web.json_response(roadmap) if roadmap else _error("Roadmap not found", 404)

        return _error("Not found", 404)

    async def post(self, request: web.Request, tail: str) -> web.Response:
        if not self._authorized(request):
            return _error("Unauthorized", 401)
        try:
            payload = await request.json()
        except (ValueError, TypeError):
            return _error("Expected a JSON object", 400)
        if not isinstance(payload, dict):
            return _error("Expected a JSON object", 400)

        route = tail.strip("/")
        if route == "slayer/catalog":
            await self._store.async_save_catalog(payload)
            self._fire_event(route, payload.get("player_username"), payload)
            return web.json_response({"success": True})

        if route == "loot/drop":
            player = _player(payload)
            if not player:
                return _error("Missing player_username", 400)
            await self._store.async_append_loot_drops(player, payload)
            self._fire_event(route, player, payload)
            return web.json_response({"success": True})

        if route == "timers":
            players = await self._store.async_save_timers(payload)
            for player in players:
                self._fire_event(route, player, payload)
            return web.json_response({"success": True})

        if route in SYNC_ENDPOINTS:
            player = _player(payload)
            if not player:
                return _error("Missing player username", 400)
            await self._store.async_save_sync(player, route, payload)
            self._fire_event(route, player, payload)
            return web.json_response({"success": True})

        roadmap_response = await self._handle_roadmap(route, payload)
        if roadmap_response is not None:
            return roadmap_response
        return _error("Not found", 404)

    async def _handle_roadmap(
        self, route: str, payload: dict[str, Any]
    ) -> web.Response | None:
        parts = route.split("/")
        if len(parts) < 3 or parts[0] != "roadmaps" or not parts[1].isdigit():
            return None
        player = str(payload.get("player", ""))
        collection_id = int(parts[1])
        operation = parts[2]
        goal_id = None
        if len(parts) == 5 and parts[2] == "goals" and parts[3].isdigit():
            goal_id = int(parts[3])
            operation = parts[4]
        if operation not in {"recompute", "complete", "delete"}:
            return None
        roadmap = await self._store.async_update_roadmap(
            player, collection_id, operation, goal_id
        )
        return web.json_response(roadmap) if roadmap else _error("Roadmap not found", 404)

    def _authorized(self, request: web.Request) -> bool:
        supplied = request.headers.get(HEADER_API_KEY, "")
        return bool(supplied) and hmac.compare_digest(
            supplied.encode("utf-8"), self._api_key.encode("utf-8")
        )

    def _fire_event(self, sync_type: str, player: Any, payload: dict[str, Any]) -> None:
        self._hass.bus.async_fire(
            EVENT_SYNC,
            {"sync_type": sync_type, "player": player, "payload": payload},
        )


def _player(payload: dict[str, Any]) -> str:
    return str(payload.get("player_username") or payload.get("player") or "")


def _error(message: str, status: int) -> web.Response:
    return web.json_response({"error": message}, status=status)
