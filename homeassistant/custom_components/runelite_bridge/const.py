"""Constants for the RuneLite Bridge integration."""

DOMAIN = "runelite_bridge"
CONF_APP_KEY = "app_key"
STORAGE_KEY = f"{DOMAIN}.payloads"
STORAGE_VERSION = 1

SYNC_ENDPOINTS = (
    "timers",
    "skills",
    "bank",
    "collection-log",
    "quests",
    "achievement-diaries",
    "combat-achievements",
    "kill-counts",
    "loadouts",
    "loot",
    "loot/drop",
    "slayer",
    "slayer/catalog",
    "slayer/rewards",
)
