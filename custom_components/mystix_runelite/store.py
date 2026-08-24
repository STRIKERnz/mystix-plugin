"""Persistent storage for RuneLite data."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import MAX_LOOT_DROPS, STORAGE_KEY, STORAGE_VERSION


class RuneLiteStore:
    """Own and persist the state received from RuneLite."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {"players": {}, "slayer_catalogs": {}}
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        loaded = await self._store.async_load()
        if isinstance(loaded, dict):
            self._data.update(loaded)
        self._data.setdefault("players", {})
        self._data.setdefault("slayer_catalogs", {})

    async def async_save_sync(self, player: str, sync_type: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            record = self._player(player)
            record["sync"][sync_type] = payload
            record["updated_at"] = _now()
            await self._store.async_save(self._data)

    async def async_save_timers(self, payload: dict[str, Any]) -> list[str]:
        timers_by_player: dict[str, list[dict[str, Any]]] = {}
        for timer in payload.get("timers", []):
            if isinstance(timer, dict) and (player := timer.get("player_username")):
                timers_by_player.setdefault(str(player), []).append(timer)
        async with self._lock:
            for player, timers in timers_by_player.items():
                record = self._player(player)
                record["sync"]["timers"] = {"timers": timers}
                record["updated_at"] = _now()
            await self._store.async_save(self._data)
        return list(timers_by_player)

    async def async_append_loot_drops(self, player: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            record = self._player(player)
            drops = record.setdefault("loot_drops", [])
            source = payload.get("source_client")
            for drop in payload.get("drops", []):
                if isinstance(drop, dict):
                    drops.append({**drop, "source_client": source})
            del drops[:-MAX_LOOT_DROPS]
            record["updated_at"] = _now()
            await self._store.async_save(self._data)

    async def async_catalog_needed(self, payload_hash: str) -> bool:
        return payload_hash not in self._data["slayer_catalogs"]

    async def async_save_catalog(self, payload: dict[str, Any]) -> None:
        payload_hash = str(payload.get("payload_hash", ""))
        async with self._lock:
            self._data["slayer_catalogs"][payload_hash] = payload
            await self._store.async_save(self._data)

    def roadmaps_for(self, player: str) -> list[dict[str, Any]]:
        return deepcopy(self._player(player).get("roadmaps", []))

    async def async_set_roadmaps(self, player: str, roadmaps: list[dict[str, Any]]) -> None:
        async with self._lock:
            self._player(player)["roadmaps"] = roadmaps
            await self._store.async_save(self._data)

    async def async_update_roadmap(
        self, player: str, collection_id: int, operation: str, goal_id: int | None = None
    ) -> dict[str, Any] | None:
        async with self._lock:
            roadmap = self._find_roadmap(player, collection_id)
            if roadmap is None:
                return None
            goals = roadmap.setdefault("goals", [])
            if operation == "complete":
                for goal in goals:
                    if int(goal.get("id", -1)) == goal_id:
                        goal["is_complete"] = True
                        goal["current"] = goal.get("target", goal.get("current", 0))
                        goal["progress_percent"] = 100
                        break
            elif operation == "delete":
                roadmap["goals"] = [g for g in goals if int(g.get("id", -1)) != goal_id]
                roadmap["goal_count"] = len(roadmap["goals"])
            await self._store.async_save(self._data)
            return deepcopy(roadmap)

    def roadmap(self, player: str, collection_id: int) -> dict[str, Any] | None:
        roadmap = self._find_roadmap(player, collection_id)
        return deepcopy(roadmap) if roadmap is not None else None

    def _find_roadmap(self, player: str, collection_id: int) -> dict[str, Any] | None:
        for roadmap in self._player(player).get("roadmaps", []):
            if int(roadmap.get("collection_id", -1)) == collection_id:
                return roadmap
        return None

    def _player(self, player: str) -> dict[str, Any]:
        return self._data["players"].setdefault(
            player, {"sync": {}, "loot_drops": [], "roadmaps": [], "updated_at": None}
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
