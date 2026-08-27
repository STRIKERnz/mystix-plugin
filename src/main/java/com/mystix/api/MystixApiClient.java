package com.mystix.api;

import com.google.gson.Gson;
import com.google.gson.JsonSyntaxException;
import com.mystix.MystixConfig;
import com.mystix.SyncGuard;
import com.mystix.model.AchievementDiariesSyncPayload;
import com.mystix.model.BankSyncPayload;
import com.mystix.model.CollectionLogSyncPayload;
import com.mystix.model.CombatAchievementsSyncPayload;
import com.mystix.model.KillCountsSyncPayload;
import com.mystix.model.LoadoutSyncPayload;
import com.mystix.model.LootDropPayload;
import com.mystix.model.LootSyncPayload;
import com.mystix.model.SlayerCatalogPayload;
import com.mystix.model.SlayerRewardsPayload;
import com.mystix.model.SlayerSyncPayload;
import com.mystix.model.PlayerSkillsSyncPayload;
import com.mystix.model.QuestsSyncPayload;
import com.mystix.model.Roadmap;
import com.mystix.model.RoadmapList;
import com.mystix.model.TimerSyncItem;
import com.mystix.model.TimersSyncPayload;
import java.io.IOException;
import java.io.ByteArrayOutputStream;
import java.awt.image.BufferedImage;
import java.io.UnsupportedEncodingException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.TimeUnit;
import javax.inject.Inject;
import javax.inject.Singleton;
import javax.imageio.ImageIO;
import lombok.extern.slf4j.Slf4j;
import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import net.runelite.api.Skill;
import net.runelite.client.game.ItemManager;
import net.runelite.client.game.SkillIconManager;
import net.runelite.client.game.SpriteManager;
import net.runelite.client.hiscore.HiscoreSkill;
import net.runelite.api.gameval.SpriteID;

@Slf4j
@Singleton
public class MystixApiClient
{
	private static final long REQUEST_TIMEOUT_SECONDS = 10;
	private static final long LARGE_REQUEST_TIMEOUT_SECONDS = 60;
	private static final MediaType JSON_MEDIA_TYPE = MediaType.parse("application/json");
	private static final MediaType PNG_MEDIA_TYPE = MediaType.parse("image/png");
	private static final String TIMERS_ENDPOINT = "/api/runelite/timers/";
	private static final String SKILLS_ENDPOINT = "/api/runelite/skills/";
	private static final String BANK_ENDPOINT = "/api/runelite/bank/";
	private static final String COLLECTION_LOG_ENDPOINT = "/api/runelite/collection-log/";
	private static final String QUESTS_ENDPOINT = "/api/runelite/quests/";
	private static final String ACHIEVEMENT_DIARIES_ENDPOINT = "/api/runelite/achievement-diaries/";
	private static final String COMBAT_ACHIEVEMENTS_ENDPOINT = "/api/runelite/combat-achievements/";
	private static final String KILL_COUNTS_ENDPOINT = "/api/runelite/kill-counts/";
	private static final String LOADOUT_ENDPOINT = "/api/runelite/loadouts/";
	private static final String LOOT_ENDPOINT = "/api/runelite/loot/";
	private static final String LOOT_DROP_ENDPOINT = "/api/runelite/loot/drop/";
	private static final String ROADMAPS_ENDPOINT = "/api/runelite/roadmaps/";
	private static final String SLAYER_ENDPOINT = "/api/runelite/slayer/";
	private static final String SLAYER_CATALOG_ENDPOINT = "/api/runelite/slayer/catalog/";
	private static final String SLAYER_CATALOG_STATUS_ENDPOINT = "/api/runelite/slayer/catalog/status/";
	private static final String SLAYER_REWARDS_ENDPOINT = "/api/runelite/slayer/rewards/";
	private static final String ITEM_ASSET_ENDPOINT = "/api/runelite/assets/items/";
	private static final String SKILL_ASSET_ENDPOINT = "/api/runelite/assets/skills/";
	private static final String HISCORE_ASSET_ENDPOINT = "/api/runelite/assets/hiscores/";
	private static final String UI_ASSET_ENDPOINT = "/api/runelite/assets/ui/";
	private static final String ITEM_METADATA_ENDPOINT = "/api/runelite/assets/item-metadata/";

	private static final int HTTP_OK_MIN = 200;
	private static final int HTTP_OK_MAX = 300;

	private final MystixConfig config;
	private final Gson gson;
	private final OkHttpClient okHttpClient;
	private final OkHttpClient largeRequestClient;
	private final ItemManager itemManager;
	private final SkillIconManager skillIconManager;
	private final SpriteManager spriteManager;
	private final ScheduledExecutorService executorService;
	private final java.util.Set<String> queuedAssets = ConcurrentHashMap.newKeySet();
	private final java.util.Set<Integer> queuedItemMetadata = ConcurrentHashMap.newKeySet();
	private final AtomicLong nextAssetSlotMillis = new AtomicLong();

	// Last successfully-sent body per syncType; skips byte-identical idempotent
	// re-syncs. Excludes loot-drops, which are append-style events.
	private final Map<String, String> lastSentBodyByType = new ConcurrentHashMap<>();

	@Inject
	public MystixApiClient(MystixConfig config, Gson gson, OkHttpClient okHttpClient,
		ItemManager itemManager, SkillIconManager skillIconManager, SpriteManager spriteManager,
		ScheduledExecutorService executorService)
	{
		this.config = config;
		this.gson = gson;
		this.okHttpClient = okHttpClient.newBuilder()
			.callTimeout(REQUEST_TIMEOUT_SECONDS, TimeUnit.SECONDS)
			.build();
		this.largeRequestClient = okHttpClient.newBuilder()
			.callTimeout(LARGE_REQUEST_TIMEOUT_SECONDS, TimeUnit.SECONDS)
			.readTimeout(LARGE_REQUEST_TIMEOUT_SECONDS, TimeUnit.SECONDS)
			.build();
		this.itemManager = itemManager;
		this.skillIconManager = skillIconManager;
		this.spriteManager = spriteManager;
		this.executorService = executorService;
	}

	/** Constructor retained for isolated API-client tests. */
	public MystixApiClient(MystixConfig config, Gson gson, OkHttpClient okHttpClient)
	{
		this(config, gson, okHttpClient, null, null, null, null);
	}

	public void sendTimersSync(List<TimerSyncItem> timers)
	{
		String json = TimersSyncPayload.toJson(timers);
		postAsync(TIMERS_ENDPOINT, json, "timers", false, true,
			() -> log.debug("Mystix timers sync successful: {} timers", timers.size()));
	}

	public void sendPlayerSkillsSync(PlayerSkillsSyncPayload payload)
	{
		queueSkillIcons();
		queueUiIcons();
		// Never dedupe skills: the backend skills endpoint also triggers roadmap
		// rechecks and WikiSync, so it must run even when the payload is unchanged.
		postAsync(SKILLS_ENDPOINT, payload.toJson(gson), "skills", false, false,
			() -> log.debug("Mystix player skills sync successful for player: {}", payload.getPlayer()));
	}

	public void sendLoadoutSync(LoadoutSyncPayload payload)
	{
		payload.getLoadoutSets().forEach(set -> {
			set.getEquipmentItems().forEach(item -> queueItemIcon(item.getItemId()));
			set.getInventoryItems().forEach(item -> queueItemIcon(item.getItemId()));
		});
		postAsync(LOADOUT_ENDPOINT, payload.toJson(gson), "loadout", false, true,
			() -> log.debug("Mystix loadout sync successful for player: {}", payload.getPlayerUsername()));
	}

	public void sendBankSync(BankSyncPayload payload)
	{
		payload.getItems().values().forEach(items ->
			items.forEach(item -> queueItemIcon(item.getItemId())));
		queueItemMetadata(payload);
		postAsync(BANK_ENDPOINT, payload.toJson(gson), "bank", false, true,
			() -> log.debug("Mystix bank sync successful: {} items for player: {}",
				payload.getTotalItemCount(), payload.getPlayerUsername()));
	}

	private void queueItemMetadata(BankSyncPayload payload)
	{
		if (itemManager == null)
		{
			return;
		}
		Map<String, String> names = new LinkedHashMap<>();
		payload.getItems().values().forEach(items -> items.forEach(item ->
		{
			int itemId = item.getItemId();
			if (queuedItemMetadata.add(itemId))
			{
				String name = itemManager.getItemComposition(itemId).getName();
				if (name != null && !name.isBlank())
				{
					names.put(Integer.toString(itemId), name);
				}
			}
		}));
		if (!names.isEmpty())
		{
			Map<String, Object> body = new LinkedHashMap<>();
			body.put("items", names);
			postAsync(ITEM_METADATA_ENDPOINT, gson.toJson(body), "item-metadata", false, false,
				() -> log.debug("Mystix item metadata sync successful: {} names", names.size()));
		}
	}

	public void sendCollectionLogSync(CollectionLogSyncPayload payload)
	{
		payload.getCollectionLog().forEach(this::queueItemIcon);
		postAsync(COLLECTION_LOG_ENDPOINT, payload.toJson(gson), "collection-log", false, true,
			() -> log.debug("Mystix collection log sync successful: {} items for player: {}",
				payload.getItemCount(), payload.getPlayerUsername()));
	}

	public void sendQuestsSync(QuestsSyncPayload payload)
	{
		postAsync(QUESTS_ENDPOINT, payload.toJson(gson), "quests", false, true,
			() -> log.debug("Mystix quests sync successful: {} quests for player: {}",
				payload.getQuests().size(), payload.getPlayerUsername()));
	}

	public void sendAchievementDiariesSync(AchievementDiariesSyncPayload payload)
	{
		postAsync(ACHIEVEMENT_DIARIES_ENDPOINT, payload.toJson(gson), "achievement-diaries", false, true,
			() -> log.debug("Mystix achievement diaries sync successful: {} regions for player: {}",
				payload.getAchievementDiaries().size(), payload.getPlayerUsername()));
	}

	public void sendCombatAchievementsSync(CombatAchievementsSyncPayload payload)
	{
		postAsync(COMBAT_ACHIEVEMENTS_ENDPOINT, payload.toJson(gson), "combat-achievements", false, true,
			() -> log.debug("Mystix combat achievements sync successful: {} tasks for player: {}",
				payload.getCombatAchievements().size(), payload.getPlayerUsername()));
	}

	public void sendKillCountsSync(KillCountsSyncPayload payload)
	{
		queueKillCountIcons(payload.getKillCounts().keySet());
		postAsync(KILL_COUNTS_ENDPOINT, payload.toJson(gson), "kill-counts", false, true,
			() -> log.debug("Mystix kill counts sync successful: {} bosses for player: {}",
				payload.getKillCounts().size(), payload.getPlayerUsername()));
	}

	/**
	 * Syncs slayer state + task transition events. Dedupe is disabled: the
	 * payload carries pending events whose delivery must not be skipped just
	 * because the state half is unchanged; the backend is idempotent on
	 * event_uuid instead.
	 */
	public void sendSlayerSync(SlayerSyncPayload payload, Runnable onSuccess)
	{
		postAsync(SLAYER_ENDPOINT, payload.toJson(gson), "slayer", false, false,
			() -> {
				log.debug("Mystix slayer sync successful: {} events for player: {}",
					payload.getEvents().size(), payload.getPlayerUsername());
				if (onSuccess != null)
				{
					onSuccess.run();
				}
			});
	}

	/** Asks whether the server already has the slayer catalog with this hash. */
	public void getSlayerCatalogStatus(String payloadHash, RoadmapCallback<SlayerCatalogPayload.Status> callback)
	{
		String url = SLAYER_CATALOG_STATUS_ENDPOINT + "?hash=" + urlEncode(payloadHash);
		getAsync(url, "slayer-catalog-status", SlayerCatalogPayload.Status.class, callback);
	}

	public void sendSlayerCatalog(SlayerCatalogPayload payload)
	{
		postAsync(SLAYER_CATALOG_ENDPOINT, payload.toJson(gson), "slayer-catalog", true, true,
			() -> log.debug("Mystix slayer catalog upload successful: hash {}",
				payload.getPayloadHash()));
	}

	public void sendSlayerRewards(SlayerRewardsPayload payload)
	{
		// Dedupe off: identical scrapes are still distinct per-player facts,
		// and the monitor already skips byte-identical repeats in-session.
		postAsync(SLAYER_REWARDS_ENDPOINT, payload.toJson(gson), "slayer-rewards", false, false,
			() -> log.debug("Mystix slayer rewards sync successful: {} rows for player: {}",
				payload.getRows().size(), payload.getPlayerUsername()));
	}

	public void sendLootSync(LootSyncPayload payload)
	{
		payload.getLootRecords().forEach(record ->
			record.getItems().forEach(item -> queueItemIcon(item.getItemId())));
		postAsync(LOOT_ENDPOINT, payload.toJson(gson), "loot", true, true,
			() -> log.debug("Mystix loot sync successful: {} records for player: {}",
				payload.getLootRecords().size(), payload.getPlayerUsername()));
	}

	public void sendLootDrops(List<LootDropPayload> drops)
	{
		if (drops.isEmpty())
		{
			return;
		}

		// Build batch payload: { player_username, source_client, drops: [{npc_id, npc_name, kill_count, items}, ...] }
		String playerUsername = drops.get(0).getPlayerUsername();
		String sourceClient = drops.get(0).getSourceClient();
		List<Map<String, Object>> dropList = new ArrayList<>();
		for (LootDropPayload drop : drops)
		{
			Map<String, Object> dropMap = new LinkedHashMap<>();
			dropMap.put("npc_id", drop.getNpcId());
			dropMap.put("npc_name", drop.getNpcName());
			dropMap.put("kill_count", drop.getKillCount());
			dropMap.put("dropped_at", drop.getDroppedAt());
			dropMap.put("items", drop.getItems());
			dropList.add(dropMap);
		}
		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("player_username", playerUsername);
		payload.put("source_client", sourceClient);
		payload.put("drops", dropList);

		String json = gson.toJson(payload);
		// Append-style events: each batch is distinct (fresh dropped_at per drop), so never dedupe.
		postAsync(LOOT_DROP_ENDPOINT, json, "loot-drops", true, false,
			() -> log.debug("Mystix loot drops batch recorded: {} drops for player: {}",
				drops.size(), playerUsername));
	}

	/** Upload a small item sprite read from RuneLite's local cache. */
	private void sendAsset(String endpoint, String assetId, byte[] png)
	{
		if (!SyncGuard.hasAppKey(config) || png == null || png.length == 0 || png.length > 256 * 1024)
		{
			return;
		}
		Request request = new Request.Builder()
			.url(apiBaseUrl() + endpoint + assetId + "/")
			.header("X-RuneLite-Key", config.mystixAppKey().trim())
			.post(RequestBody.create(PNG_MEDIA_TYPE, png))
			.build();
		okHttpClient.newCall(request).enqueue(new Callback()
		{
			@Override
			public void onFailure(Call call, IOException e)
			{
				log.debug("Failed to upload asset {}: {}", assetId, e.getMessage());
			}

			@Override
			public void onResponse(Call call, Response response)
			{
				try
				{
					if (response.code() < HTTP_OK_MIN || response.code() >= HTTP_OK_MAX)
					{
						log.debug("Asset {} upload returned {}", assetId, response.code());
					}
				}
				finally
				{
					response.close();
				}
			}
		});
	}

	public void queueItemIcon(int itemId)
	{
		if (itemManager == null || executorService == null || itemId <= 0 || !queuedAssets.add("item:" + itemId))
		{
			return;
		}
		queueImage(ITEM_ASSET_ENDPOINT, Integer.toString(itemId), itemManager.getImage(itemId));
	}

	private void queueSkillIcons()
	{
		if (skillIconManager == null || executorService == null)
		{
			return;
		}
		for (Skill skill : Skill.values())
		{
			String name = skill.getName().toLowerCase().replace(' ', '_');
			if (queuedAssets.add("skill:" + name))
			{
				queueImage(SKILL_ASSET_ENDPOINT, name, skillIconManager.getSkillImage(skill));
			}
		}
	}

	private void queueKillCountIcons(java.util.Set<String> names)
	{
		if (spriteManager == null || executorService == null)
		{
			return;
		}
		Map<String, HiscoreSkill> hiscores = new LinkedHashMap<>();
		for (HiscoreSkill skill : HiscoreSkill.values())
		{
			String slug = assetSlug(skill.getName());
			hiscores.put(slug, skill);
			if (slug.startsWith("the_"))
			{
				hiscores.put(slug.substring(4), skill);
			}
		}
		hiscores.put("guardians_of_the_rift", HiscoreSkill.RIFTS_CLOSED);
		hiscores.put("lunar_chest", HiscoreSkill.LUNAR_CHESTS);
		hiscores.put("theatre_of_blood_entry_mode", HiscoreSkill.THEATRE_OF_BLOOD);
		hiscores.put("tombs_of_amascut_entry_mode", HiscoreSkill.TOMBS_OF_AMASCUT);
		for (String name : names)
		{
			String slug = assetSlug(name);
			if (!queuedAssets.add("hiscore:" + slug))
			{
				continue;
			}
			HiscoreSkill skill = hiscores.get(slug);
			int spriteId;
			if (skill != null)
			{
				spriteId = skill.getSpriteId();
			}
			else if (slug.contains("agility") || slug.endsWith("_rooftop"))
			{
				spriteId = HiscoreSkill.AGILITY.getSpriteId();
			}
			else if (slug.equals("herbiboar") || slug.equals("hunter_rumours"))
			{
				spriteId = HiscoreSkill.HUNTER.getSpriteId();
			}
			else if (slug.equals("brimstone_chest"))
			{
				spriteId = SpriteID.CHEST;
			}
			else
			{
				spriteId = SpriteID.HEADICONS_PK;
			}
			spriteManager.getSpriteAsync(spriteId, 0,
				image -> queueImage(HISCORE_ASSET_ENDPOINT, slug, image));
		}
	}

	private void queueUiIcons()
	{
		if (spriteManager == null || executorService == null)
		{
			return;
		}
		Map<String, Integer> icons = new LinkedHashMap<>();
		icons.put("quests", SpriteID.AchievementDiaryIcons.BLUE_QUESTS);
		icons.put("achievement_diaries", SpriteID.AchievementDiaryIcons.GREEN_ACHIEVEMENT_DIARIES);
		icons.put("activities", SpriteID.AchievementDiaryIcons.RED_MINIGAMES);
		icons.put("bank", SpriteID.Mapfunction._5);
		icons.put("slayer", SpriteID.Mapfunction._51);
		icons.put("kill_counts", SpriteID.HEADICONS_PK);
		for (Map.Entry<String, Integer> icon : icons.entrySet())
		{
			if (queuedAssets.add("ui:" + icon.getKey()))
			{
				spriteManager.getSpriteAsync(icon.getValue(), 0,
					image -> queueImage(UI_ASSET_ENDPOINT, icon.getKey(), image));
			}
		}
	}

	private static String assetSlug(String value)
	{
		return value.toLowerCase().replaceAll("[^a-z0-9]+", "_").replaceAll("^_+|_+$", "");
	}

	private void queueImage(String endpoint, String assetId, BufferedImage image)
	{
		long now = System.currentTimeMillis();
		long slot = nextAssetSlotMillis.updateAndGet(previous -> Math.max(previous, now) + 100L);
		executorService.schedule(() ->
		{
			try (ByteArrayOutputStream output = new ByteArrayOutputStream())
			{
				if (image != null && ImageIO.write(image, "png", output))
				{
					sendAsset(endpoint, assetId, output.toByteArray());
				}
			}
			catch (IOException e)
			{
				log.debug("Could not encode asset {}", assetId, e);
			}
		}, Math.max(0L, slot - now), TimeUnit.MILLISECONDS);
	}

	/**
	 * Result callback for roadmap reads. Both methods are invoked on the OkHttp
	 * dispatcher thread (not the client/EDT thread); callers that touch Swing must
	 * marshal back via SwingUtilities.invokeLater.
	 *
	 * @param <T> parsed response type
	 */
	public interface RoadmapCallback<T>
	{
		void onSuccess(T result);

		void onError(String message);
	}

	/**
	 * Fetches the player's roadmaps (id/title/goal_count) for the panel selector.
	 */
	public void getRoadmaps(String playerUsername, RoadmapCallback<RoadmapList> callback)
	{
		String url = ROADMAPS_ENDPOINT + "?player=" + urlEncode(playerUsername);
		getAsync(url, "roadmaps", RoadmapList.class, callback);
	}

	/**
	 * Fetches a single roadmap fully rendered (goals + progress).
	 */
	public void getRoadmap(int collectionId, String playerUsername, RoadmapCallback<Roadmap> callback)
	{
		String url = ROADMAPS_ENDPOINT + collectionId + "/?player=" + urlEncode(playerUsername);
		getAsync(url, "roadmap", Roadmap.class, callback);
	}

	/**
	 * Recomputes a roadmap's goal completion against current synced data and
	 * returns the re-rendered roadmap.
	 */
	public void recomputeRoadmap(int collectionId, String playerUsername, RoadmapCallback<Roadmap> callback)
	{
		String url = ROADMAPS_ENDPOINT + collectionId + "/recompute/";
		Map<String, Object> body = new LinkedHashMap<>();
		body.put("player", playerUsername);
		postForResult(url, gson.toJson(body), "roadmap-recompute", Roadmap.class, callback);
	}

	/**
	 * Manually marks a single goal complete and returns the re-rendered roadmap.
	 */
	public void completeRoadmapGoal(int collectionId, int goalId, String playerUsername,
		RoadmapCallback<Roadmap> callback)
	{
		String url = ROADMAPS_ENDPOINT + collectionId + "/goals/" + goalId + "/complete/";
		Map<String, Object> body = new LinkedHashMap<>();
		body.put("player", playerUsername);
		postForResult(url, gson.toJson(body), "roadmap-goal-complete", Roadmap.class, callback);
	}

	/**
	 * Deletes a single goal from a roadmap and returns the re-rendered roadmap.
	 */
	public void deleteRoadmapGoal(int collectionId, int goalId, String playerUsername,
		RoadmapCallback<Roadmap> callback)
	{
		String url = ROADMAPS_ENDPOINT + collectionId + "/goals/" + goalId + "/delete/";
		Map<String, Object> body = new LinkedHashMap<>();
		body.put("player", playerUsername);
		postForResult(url, gson.toJson(body), "roadmap-goal-delete", Roadmap.class, callback);
	}

	private <T> void getAsync(String endpoint, String label, Class<T> type, RoadmapCallback<T> callback)
	{
		if (!SyncGuard.hasAppKey(config))
		{
			callback.onError("No Mystix App Key configured");
			return;
		}

		Request request = new Request.Builder()
			.url(apiBaseUrl() + endpoint)
			.header("X-RuneLite-Key", config.mystixAppKey().trim())
			.get()
			.build();

		okHttpClient.newCall(request).enqueue(parsingCallback(label, type, callback));
	}

	private <T> void postForResult(String endpoint, String json, String label, Class<T> type,
		RoadmapCallback<T> callback)
	{
		if (!SyncGuard.hasAppKey(config))
		{
			callback.onError("No Mystix App Key configured");
			return;
		}

		Request request = new Request.Builder()
			.url(apiBaseUrl() + endpoint)
			.header("Content-Type", "application/json")
			.header("X-RuneLite-Key", config.mystixAppKey().trim())
			.post(RequestBody.create(JSON_MEDIA_TYPE, json))
			.build();

		largeRequestClient.newCall(request).enqueue(parsingCallback(label, type, callback));
	}

	private <T> Callback parsingCallback(String label, Class<T> type, RoadmapCallback<T> callback)
	{
		return new Callback()
		{
			@Override
			public void onFailure(Call call, IOException e)
			{
				log.warn("Failed {} request to Mystix API: {}", label, e.getMessage());
				callback.onError("Network error");
			}

			@Override
			public void onResponse(Call call, Response response)
			{
				try
				{
					if (response.code() < HTTP_OK_MIN || response.code() >= HTTP_OK_MAX)
					{
						log.warn("Mystix API returned {} for {}", response.code(), label);
						callback.onError("Server returned " + response.code());
						return;
					}
					String responseBody = response.body() != null ? response.body().string() : "";
					T parsed = gson.fromJson(responseBody, type);
					if (parsed == null)
					{
						callback.onError("Empty response");
						return;
					}
					callback.onSuccess(parsed);
				}
				catch (IOException | JsonSyntaxException e)
				{
					log.warn("Failed to parse {} response: {}", label, e.getMessage());
					callback.onError("Could not read response");
				}
				finally
				{
					response.close();
				}
			}
		};
	}

	private static String urlEncode(String value)
	{
		if (value == null)
		{
			return "";
		}
		try
		{
			return URLEncoder.encode(value, StandardCharsets.UTF_8.name());
		}
		catch (UnsupportedEncodingException e)
		{
			return value;
		}
	}

	private void postAsync(String endpoint, String json, String syncType, boolean largeRequest,
		boolean dedupe, Runnable onSuccess)
	{
		if (!SyncGuard.hasAppKey(config))
		{
			log.debug("Skipping {} sync: no Mystix App Key configured", syncType);
			return;
		}

		if (dedupe && isDuplicate(lastSentBodyByType.get(syncType), json))
		{
			log.debug("Skipping {} sync: identical to last sent request", syncType);
			return;
		}

		String appKey = config.mystixAppKey();
		String url = apiBaseUrl() + endpoint;

		Request request = new Request.Builder()
			.url(url)
			.header("Content-Type", "application/json")
			.header("X-RuneLite-Key", appKey.trim())
			.post(RequestBody.create(JSON_MEDIA_TYPE, json))
			.build();

		OkHttpClient client = largeRequest ? largeRequestClient : okHttpClient;
		client.newCall(request).enqueue(new Callback()
		{
			@Override
			public void onFailure(Call call, IOException e)
			{
				log.warn("Failed to send {} sync to Mystix API: {}", syncType, e.getMessage());
			}

			@Override
			public void onResponse(Call call, Response response)
			{
				try
				{
					if (response.code() >= HTTP_OK_MIN && response.code() < HTTP_OK_MAX)
					{
						if (dedupe)
						{
							lastSentBodyByType.put(syncType, json);
						}
						onSuccess.run();
					}
					else
					{
						log.warn("Mystix API returned {} for {} sync", response.code(), syncType);
					}
				}
				finally
				{
					response.close();
				}
			}
		});
	}

	static boolean isDuplicate(String previousBody, String currentJson)
	{
		return previousBody != null && previousBody.equals(currentJson);
	}

	private String apiBaseUrl()
	{
		String configured = config.apiBaseUrl().trim();
		while (configured.endsWith("/"))
		{
			configured = configured.substring(0, configured.length() - 1);
		}
		return configured;
	}

	/**
	 * Forgets the last-sent body for every sync type, so the next send of each
	 * type goes out even if its payload is byte-identical to the previous one.
	 *
	 * <p>The roadmap panel's "Sync &amp; refresh" is an explicit, user-triggered
	 * re-sync: the dedupe guard (which silently skips unchanged idempotent syncs)
	 * must not swallow it, or the button would do nothing when the player's data
	 * hasn't changed since the last automatic sync.
	 */
	public void clearDedupeCache()
	{
		lastSentBodyByType.clear();
	}
}
