# Home Assistant RuneLite Bridge

This repository includes a Home Assistant custom integration that receives the
RuneLite plugin's `/api/runelite/...` sync payloads locally.

## Install

1. Copy `homeassistant/custom_components/runelite_bridge` into the
   `custom_components` directory in your Home Assistant configuration.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration** and select
   **RuneLite Bridge**.
4. Enter a long random app key, for example one generated with:

   ```bash
   openssl rand -hex 32
   ```

5. Enter the same value in RuneLite under **Mystix App Key**.
6. Set **Home Assistant URL** in the plugin to the address reachable from the
   RuneLite computer, such as `http://homeassistant.local:8123`.

## Docker development environment

Start the included Home Assistant environment with:

```bash
docker compose up -d
```

Open `http://localhost:8123`. The Compose configuration mounts the bridge,
dashboard configuration, and RuneLite dashboard into the container.

## Entities, events, and assets

The integration persists the latest payload for every sync category and creates
dashboard entities for account progress, skills, quests, Slayer, loot, timers,
bank sources, and kill counts.

Every accepted sync fires a `runelite_bridge_sync` event containing:

```yaml
sync_type: skills
payload: {}
```

RuneLite cache images uploaded by the plugin are stored below
`/config/www/runelite` and served by Home Assistant under `/local/runelite`.
Uploads are authenticated, deduplicated, and rate limited by the plugin.

The included YAML dashboard is available as **RuneLite** in the Home Assistant
sidebar when using the provided Compose configuration.
