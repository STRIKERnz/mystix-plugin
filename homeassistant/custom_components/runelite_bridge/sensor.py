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

SKILLS = (
    "attack", "strength", "defence", "hitpoints", "ranged", "prayer", "magic",
    "cooking", "woodcutting", "fletching", "fishing", "firemaking", "crafting",
    "smithing", "mining", "herblore", "agility", "thieving", "slayer", "farming",
    "runecraft", "hunter", "construction", "sailing",
)

ENDPOINT_PICTURES = {
    "quests": "/local/runelite/ui/quests.png",
    "achievement-diaries": "/local/runelite/ui/achievement_diaries.png",
    "combat-achievements": "/local/runelite/ui/activities.png",
    "bank": "/local/runelite/ui/bank.png",
    "slayer": "/local/runelite/ui/slayer.png",
    "slayer/catalog": "/local/runelite/ui/slayer.png",
    "slayer/rewards": "/local/runelite/ui/slayer.png",
    "kill-counts": "/local/runelite/ui/kill_counts.png",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one live sensor for each supported RuneLite sync category."""
    runtime = hass.data[DOMAIN]
    entities: list[SensorEntity] = [
        RuneLitePayloadSensor(entry, runtime, endpoint) for endpoint in SYNC_ENDPOINTS
    ]
    entities.extend(_fixed_detail_entities(entry, runtime))
    async_add_entities(entities)

    dynamic_ids: set[str] = set()

    @callback
    def discover(endpoint: str) -> None:
        additions = _dynamic_detail_entities(entry, runtime, endpoint, dynamic_ids)
        if additions:
            async_add_entities(additions)

    runtime["listeners"].append(discover)
    entry.async_on_unload(lambda: runtime["listeners"].remove(discover))
    for endpoint in ("bank", "kill-counts"):
        discover(endpoint)


class RuneLitePayloadSensor(SensorEntity):
    """Represent the latest payload received for a sync category."""

    _attr_has_entity_name = False
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
    def entity_picture(self) -> str | None:
        return ENDPOINT_PICTURES.get(self._endpoint)

    @property
    def _payload(self) -> dict[str, Any] | None:
        payload = self._runtime["payloads"].get(self._endpoint)
        return payload if isinstance(payload, dict) else None


class RuneLiteDetailSensor(SensorEntity):
    """Expose one useful value from a larger RuneLite payload."""

    _attr_has_entity_name = False

    def __init__(
        self,
        entry: ConfigEntry,
        runtime: dict[str, Any],
        endpoint: str,
        key: str,
        name: str,
        value: Callable[[dict[str, Any]], Any],
        attributes: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        icon: str = "mdi:sword-cross",
        entity_picture: str | Callable[[dict[str, Any]], str | None] | None = None,
    ) -> None:
        self._runtime = runtime
        self._endpoint = endpoint
        self._value = value
        self._attributes = attributes
        self._attr_unique_id = f"{entry.entry_id}_detail_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._entity_picture = entity_picture
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="RuneLite Bridge",
            manufacturer="Mystix",
            model="Local bridge",
        )

    async def async_added_to_hass(self) -> None:
        listeners: list[Callable[[str], None]] = self._runtime["listeners"]
        listeners.append(self._payload_updated)
        self.async_on_remove(lambda: listeners.remove(self._payload_updated))

    @callback
    def _payload_updated(self, endpoint: str) -> None:
        if endpoint == self._endpoint:
            self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        payload = self._runtime["payloads"].get(self._endpoint)
        return self._value(payload) if isinstance(payload, dict) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        payload = self._runtime["payloads"].get(self._endpoint)
        if self._attributes is None or not isinstance(payload, dict):
            return None
        return self._attributes(payload)

    @property
    def entity_picture(self) -> str | None:
        if isinstance(self._entity_picture, str) or self._entity_picture is None:
            return self._entity_picture
        payload = self._runtime["payloads"].get(self._endpoint)
        return self._entity_picture(payload) if isinstance(payload, dict) else None


def _fixed_detail_entities(
    entry: ConfigEntry, runtime: dict[str, Any]
) -> list[RuneLiteDetailSensor]:
    entities: list[RuneLiteDetailSensor] = []
    for skill in SKILLS:
        entities.append(RuneLiteDetailSensor(
            entry, runtime, "skills", f"skill_{skill}", f"{skill.title()} level",
            lambda payload, skill=skill: _skill(payload, skill).get("level"),
            lambda payload, skill=skill: {"xp": _skill(payload, skill).get("current_xp")},
            "mdi:star-four-points",
            f"/local/runelite/skills/{skill}.png",
        ))

    for status, label in ((2, "Completed"), (1, "In progress"), (0, "Not started")):
        entities.append(RuneLiteDetailSensor(
            entry, runtime, "quests", f"quests_{status}", f"Quests {label.lower()}",
            lambda payload, status=status: _count_value(payload.get("quests"), status),
            icon="mdi:book-open-page-variant", entity_picture="/local/runelite/ui/quests.png",
        ))

    slayer_fields = (
        ("amount_remaining", "Slayer remaining", "mdi:counter"),
        ("amount_original", "Slayer task size", "mdi:counter"),
        ("points", "Slayer points", "mdi:seal"),
        ("streak", "Slayer streak", "mdi:fire"),
        ("wilderness_streak", "Wilderness Slayer streak", "mdi:fire"),
        ("slayer_level", "Slayer level", "mdi:sword-cross"),
        ("slayer_xp", "Slayer XP", "mdi:chart-line"),
    )
    for field, label, icon in slayer_fields:
        entities.append(RuneLiteDetailSensor(
            entry, runtime, "slayer", f"slayer_{field}", label,
            lambda payload, field=field: _nested(payload, "state", field), icon=icon,
            entity_picture="/local/runelite/ui/slayer.png",
        ))

    entities.extend((
        RuneLiteDetailSensor(
            entry, runtime, "timers", "timers_ready", "Timers ready",
            lambda payload: sum(
                timer.get("crop_state") in ("harvestable", "empty")
                for timer in payload.get("timers", []) if isinstance(timer, dict)
            ), icon="mdi:timer-check",
        ),
        RuneLiteDetailSensor(
            entry, runtime, "loot/drop", "latest_drop_item_count", "Latest drop items",
            lambda payload: _length(_latest_drop(payload).get("items")),
            lambda payload: {
                "npc": _latest_drop(payload).get("npc_name"),
                "kill_count": _latest_drop(payload).get("kill_count"),
                "dropped_at": _latest_drop(payload).get("dropped_at"),
                "items": _latest_drop(payload).get("items", []),
            }, "mdi:treasure-chest", lambda payload: _first_item_picture(_latest_drop(payload)),
        ),
    ))
    return entities


def _dynamic_detail_entities(
    entry: ConfigEntry,
    runtime: dict[str, Any],
    endpoint: str,
    known: set[str],
) -> list[RuneLiteDetailSensor]:
    payload = runtime["payloads"].get(endpoint)
    if not isinstance(payload, dict):
        return []
    entities: list[RuneLiteDetailSensor] = []
    if endpoint == "kill-counts":
        values = payload.get("kill_counts", {})
        if isinstance(values, dict):
            for boss in values:
                key = f"kc_{_slug(boss)}"
                if key not in known:
                    known.add(key)
                    entities.append(RuneLiteDetailSensor(
                        entry, runtime, endpoint, key, f"KC {str(boss).title()}",
                        lambda data, boss=boss: data.get("kill_counts", {}).get(boss),
                        icon="mdi:skull-crossbones",
                        entity_picture=f"/local/runelite/hiscores/{_slug(boss)}.png",
                    ))
    elif endpoint == "bank":
        values = payload.get("items", {})
        if isinstance(values, dict):
            for source in values:
                key = f"bank_{_slug(source)}"
                if key not in known:
                    known.add(key)
                    entities.append(RuneLiteDetailSensor(
                        entry, runtime, endpoint, key, f"{str(source).replace('_', ' ').title()} slots",
                        lambda data, source=source: _length(data.get("items", {}).get(source)),
                        lambda data, source=source: {
                            "total_quantity": sum(
                                item.get("quantity", 0)
                                for item in data.get("items", {}).get(source, [])
                                if isinstance(item, dict) and isinstance(item.get("quantity"), int)
                            ),
                            "items": [
                                {**item, "icon": f"/local/runelite/items/{item.get('item_id')}.png"}
                                for item in data.get("items", {}).get(source, [])[:28]
                                if isinstance(item, dict) and isinstance(item.get("item_id"), int)
                            ],
                        }, "mdi:bank",
                    ))
    return entities


def _skill(payload: dict[str, Any], skill: str) -> dict[str, Any]:
    skills = payload.get("skills", {})
    value = next(
        (item for name, item in skills.items() if str(name).lower() == skill.lower()), {}
    ) if isinstance(skills, dict) else {}
    return value if isinstance(value, dict) else {}


def _nested(payload: dict[str, Any], parent: str, key: str) -> Any:
    value = payload.get(parent, {})
    return value.get(key) if isinstance(value, dict) else None


def _latest_drop(payload: dict[str, Any]) -> dict[str, Any]:
    drops = payload.get("drops", [])
    return drops[-1] if isinstance(drops, list) and drops and isinstance(drops[-1], dict) else {}


def _first_item_picture(payload: dict[str, Any]) -> str | None:
    items = payload.get("items", [])
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None
    item_id = items[0].get("item_id")
    return f"/local/runelite/items/{item_id}.png" if isinstance(item_id, int) else None


def _slug(value: Any) -> str:
    return "".join(character if character.isalnum() else "_" for character in str(value).lower()).strip("_")


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
        return str(_latest_drop(payload).get("npc_name") or "Drop received")
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
