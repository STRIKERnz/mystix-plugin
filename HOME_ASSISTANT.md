# Home Assistant receiver

This repository includes a Home Assistant custom integration that implements the
RuneLite plugin's `/api/runelite/...` API locally.

## Install

1. Copy `custom_components/mystix_runelite` into the `custom_components` folder
   inside your Home Assistant configuration directory.
2. Add this to `configuration.yaml`, using a long random secret:

   ```yaml
   mystix_runelite:
     api_key: "replace-with-a-long-random-secret"
   ```

3. Restart Home Assistant.
4. Put the same secret in RuneLite under **Mystix App Key**.

The RuneLite plugin sends to `http://homeassistant.local:8123`. If that hostname
does not resolve from the computer running RuneLite, replace the plugin's base
URL with the Home Assistant machine's LAN IP.

## Data and automations

The integration persists the latest payload for each player and sync type in
Home Assistant's `.storage/mystix_runelite.data` store. Do not edit that file
while Home Assistant is running.

Every accepted sync fires a `mystix_runelite_sync` event containing:

```yaml
sync_type: skills
player: Your RS Name
payload: {}
```

Use that event as an automation trigger. Real-time loot drops are retained as a
bounded history of the latest 500 drops per player.

## Roadmaps

Roadmaps can be loaded through the `mystix_runelite.import_roadmaps` action. The
`roadmaps_json` field accepts the same roadmap list/detail shape expected by the
RuneLite plugin. The integration supports listing, viewing, completing, and
deleting goals. `recompute` currently returns the stored roadmap unchanged;
automatic goal evaluation is not yet implemented.
