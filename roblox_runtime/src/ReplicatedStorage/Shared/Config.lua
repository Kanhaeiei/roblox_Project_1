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

-- Server-authoritative upgrades allowlist
Config.Upgrades = {
	attack_power = {
		name = "Attack Power",
		maxLevel = 50,
		costFormula = function(level: number): number
			return math.floor(100 * (1.5 ^ level))
		end,
		bonusFormula = function(level: number): number
			return level * 15
		end,
	},
	mana_efficiency = {
		name = "Mana Efficiency",
		maxLevel = 25,
		costFormula = function(level: number): number
			return math.floor(250 * (1.8 ^ level))
		end,
		bonusFormula = function(level: number): number
			return level * 0.05
		end,
	},
}

-- Combat tuning & bounds
Config.Combat = {
	maxAttackRange = 50, -- studs
	attackCooldown = 0.125, -- seconds (8 attacks/sec)
	ritualSocketMaxDistance = 30, -- studs
	defaultAltarPosition = Vector3.new(0, 5, 75),
}

-- World 1 enemy archetypes (per-player progression)
Config.Enemies = {
	forest_goblin = {
		id = "forest_goblin",
		name = "Forest Goblin",
		maxHealth = 100,
		rewardMana = 25,
		isBoss = false,
		isMiniBoss = false,
		spawnPosition = Vector3.new(0, 5, 20),
	},
	wolf_alpha_miniboss = {
		id = "wolf_alpha_miniboss",
		name = "Alpha Shadow Wolf",
		maxHealth = 1000,
		rewardMana = 500,
		isBoss = false,
		isMiniBoss = true,
		spawnPosition = Vector3.new(0, 5, 50),
	},
	shadow_monarch_boss = {
		id = "shadow_monarch_boss",
		name = "Shadow Monarch",
		maxHealth = 5000,
		rewardMana = 2500,
		isBoss = true,
		isMiniBoss = false,
		spawnPosition = Vector3.new(0, 5, 75),
	},
}

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

-- Developer Products boundary: Disabled until live production product IDs are registered
Config.DeveloperProductsEnabled = false
Config.DeveloperProducts = {} :: { [number]: { name: string, currency: string, amount: number } }

return Config
