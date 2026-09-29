--!strict
-- Config: Single authoritative runtime configuration for World 1
-- Matches Golden fixtures/world_01_shadow_forest/07_economy.json

local Config = {}

Config.SchemaVersion = 1
Config.SafeIntegerCeiling = 9000000000000000

Config.Currencies = {
	Mana = {
		scope = "world",
		cap = 1000000000,
	},
	Essence = {
		scope = "account",
		cap = 10000000,
	},
	RebirthSigils = {
		scope = "account",
		cap = 1000000,
	},
	SoulShards = {
		scope = "premium",
		cap = 1000000,
	},
}

Config.Rebirth = {
	baseSquadSlots = 3,
	earnedSlotsPerMilestone = 2,
	firstTargetSeconds = 1200,
}

function Config.worldBasePower(worldIndex: number): number
	return 100 * (1000 ^ (worldIndex - 1))
end

function Config.rebirthCost(rebirthCount: number): number
	local r = math.max(0, math.floor(rebirthCount))
	local baseTerm = 25000 * (6 ^ r)
	local lateGrowth = 1.18 ^ (math.max(0, r - 5) ^ 1.35)
	local cost = math.round(baseTerm * lateGrowth)
	return math.min(cost, Config.SafeIntegerCeiling)
end

function Config.rebirthPowerMultiplier(rebirthCount: number): number
	local r = math.max(0, rebirthCount)
	return 1 + (0.50 * r) + (0.05 * (r ^ 2))
end

Config.GachaPools = {
	pool_shadow_forest = {
		id = "pool_shadow_forest",
		currencyId = "Mana",
		cost = 100,
		paidRandomEligible = false,
		outcomes = {
			{ definitionId = "shadow_imp", rateBasisPoints = 6500, power = 10 },
			{ definitionId = "shadow_hound", rateBasisPoints = 2500, power = 35 },
			{ definitionId = "shadow_mage", rateBasisPoints = 900, power = 120 },
			{ definitionId = "shadow_footman", rateBasisPoints = 100, power = 500 },
		},
		pityCounterKey = "pity_shadow_forest_legendary",
		pityThreshold = 50,
	},
}

Config.ResetManifest = {
	reset = {
		"Currencies.Mana",
		"Progression.WorldUpgrades",
	},
	keep = {
		"Inventory.Shadows",
		"Entitlements",
		"Cosmetics",
		"Pity",
	},
	transform = {
		"Progression.RebirthCount += 1",
		"Currencies.RebirthSigils += reward",
	},
}

Config.RemoteRules = {
	request_target = {
		ratePerSecond = 8,
		validations = { "type", "enemy ownership", "range", "player alive" },
	},
	request_upgrade = {
		ratePerSecond = 2,
		validations = { "type", "server price", "balance", "upgrade state" },
	},
	request_arise = {
		ratePerSecond = 1,
		validations = { "boss clear", "first-clear state", "distance", "not already owned" },
	},
	request_summon = {
		ratePerSecond = 2,
		validations = { "balance", "pity state" },
	},
	request_rebirth = {
		ratePerSecond = 1,
		validations = { "balance", "cost formula" },
	},
}

Config.AnalyticsEvents = {
	ftue_spawned = true,
	ftue_first_kill = true,
	ftue_first_upgrade = true,
	ftue_miniboss_clear = true,
	ftue_first_arise = true,
	ftue_first_rebirth = true,
}

return Config
