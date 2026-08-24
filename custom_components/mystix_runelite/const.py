"""Constants for the Mystix RuneLite receiver."""

DOMAIN = "mystix_runelite"
CONF_API_KEY = "api_key"
HEADER_API_KEY = "X-RuneLite-Key"
EVENT_SYNC = "mystix_runelite_sync"
STORAGE_KEY = f"{DOMAIN}.data"
STORAGE_VERSION = 1
MAX_LOOT_DROPS = 500

SYNC_ENDPOINTS = {
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
    "slayer",
    "slayer/rewards",
}
