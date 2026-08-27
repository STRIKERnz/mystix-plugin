"""Dashboard sensors for the RuneLite Bridge integration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SYNC_ENDPOINTS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one live sensor for each supported RuneLite sync category."""
    runtime = hass.data[DOMAIN]
    async_add_entities(
        RuneLitePayloadSensor(entry, runtime, endpoint) for endpoint in SYNC_ENDPOINTS
    )


class RuneLitePayloadSensor(SensorEntity):
    """Represent the latest payload received for a sync category."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:sword-cross"

    def __init__(self, entry: ConfigEntry, runtime: dict[str, Any], endpoint: str) -> None:
        self._runtime = runtime
        self._endpoint = endpoint
        slug = endpoint.replace("/", "_").replace("-", "_")
        self._attr_unique_id = f"{entry.entry_id}_{slug}"
        self._attr_name = endpoint.replace("/", " ").replace("-", " ").title()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="RuneLite Bridge",
            manufacturer="Mystix",
            model="Local bridge",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to payload updates."""
        listeners: list[Callable[[str], None]] = self._runtime["listeners"]
        listeners.append(self._payload_updated)
        self.async_on_remove(lambda: listeners.remove(self._payload_updated))

    @callback
    def _payload_updated(self, endpoint: str) -> None:
        if endpoint == self._endpoint:
            self.async_write_ha_state()

    @property
    def native_value(self) -> str | int:
        payload = self._payload
        if payload is None:
            return "Waiting"
        return _payload_state(self._endpoint, payload)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        payload = self._payload
        if payload is None:
            return {"sync_type": self._endpoint}
        return {"sync_type": self._endpoint, **_payload_attributes(payload)}

    @property
    def _payload(self) -> dict[str, Any] | None:
        payload = self._runtime["payloads"].get(self._endpoint)
        return payload if isinstance(payload, dict) else None


def _payload_state(endpoint: str, payload: dict[str, Any]) -> str | int:
    """Choose a compact, dashboard-friendly headline for a payload."""
    if endpoint == "skills":
        return _integer(payload.get("total_level"), "Received")
    if endpoint == "bank":
        items = payload.get("items", {})
        return sum(len(value) for value in items.values() if isinstance(value, list)) if isinstance(items, dict) else 0
    if endpoint == "collection-log":
        return _integer(payload.get("collection_log_item_count"), 0)
    if endpoint == "quests":
        return _count_value(payload.get("quests"), 2)
    if endpoint == "achievement-diaries":
        diaries = payload.get("achievement_diaries", {})
        return sum(
            1
            for region in diaries.values()
            if isinstance(region, dict)
            for tier in region.values()
            if isinstance(tier, dict) and tier.get("complete") is True
        ) if isinstance(diaries, dict) else 0
    if endpoint == "combat-achievements":
        return _length(payload.get("combat_achievements"))
    if endpoint == "kill-counts":
        return sum(value for value in payload.get("kill_counts", {}).values() if isinstance(value, int))
    if endpoint == "loadouts":
        return _length(payload.get("loadout_sets"))
    if endpoint == "loot":
        return _length(payload.get("loot_records"))
    if endpoint == "loot/drop":
        return str(payload.get("npc_name") or "Drop received")
    if endpoint == "slayer":
        state = payload.get("state", {})
        return str(state.get("task_name") or "No task") if isinstance(state, dict) else "Received"
    if endpoint == "timers":
        return _length(payload.get("timers"))
    for key in ("items", "rewards", "catalog", "entries", "tasks"):
        if key in payload:
            return _length(payload[key])
    return "Received"


def _payload_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    """Expose useful data while keeping very large nested payloads out of Recorder."""
    attributes: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            attributes[key] = value
        elif isinstance(value, list):
            attributes[f"{key}_count"] = len(value)
            if len(value) <= 25:
                attributes[key] = value
        elif isinstance(value, dict):
            attributes[f"{key}_count"] = len(value)
            if len(value) <= 30 and all(
                child is None or isinstance(child, (str, int, float, bool))
                for child in value.values()
            ):
                attributes[key] = value
    return attributes


def _length(value: Any) -> int:
    return len(value) if isinstance(value, (list, dict)) else 0


def _count_value(value: Any, expected: Any) -> int:
    return sum(item == expected for item in value.values()) if isinstance(value, dict) else 0


def _integer(value: Any, default: Any) -> Any:
    return value if isinstance(value, int) and not isinstance(value, bool) else default
