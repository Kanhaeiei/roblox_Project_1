--!strict
-- ShadowArmyService: Squad management, gacha summon with pity, guaranteed boss ARISE, and rebirth reset execution
-- Enforces server-authoritative inventory, pity invariants, and reset manifest boundaries

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)
local PlayerDataService = require(script.Parent.PlayerDataService)
local CombatService = require(script.Parent.CombatService)

local ShadowArmyService = {}

-- Link CombatService back to ShadowArmyService for squad power calculation
CombatService.setShadowArmyService(ShadowArmyService)

local BOSS_ALTAR_POSITION = Vector3.new(0, 0, 75) -- Match socket_boss_ritual position
local MAX_RITUAL_DISTANCE = 30 -- studs

export type ShadowEntity = {
	id: string,
	name: string,
	power: number,
	rarity: string,
}

local SHADOW_DEFINITIONS: { [string]: ShadowEntity } = {
	shadow_imp = { id = "shadow_imp", name = "Shadow Imp", power = 10, rarity = "common" },
	shadow_hound = { id = "shadow_hound", name = "Shadow Hound", power = 35, rarity = "uncommon" },
	shadow_mage = { id = "shadow_mage", name = "Shadow Mage", power = 120, rarity = "rare" },
	shadow_footman = { id = "shadow_footman", name = "Shadow Footman", power = 500, rarity = "legendary" },
	shadow_boss_monarch = { id = "shadow_boss_monarch", name = "Shadow Monarch", power = 1500, rarity = "boss" },
}

function ShadowArmyService.getMaxSquadSlots(player: Player): number
	local profile = PlayerDataService.getProfile(player)
	local rebirthCount = profile and profile.Progression.RebirthCount or 0
	return Config.Rebirth.baseSquadSlots + (Config.Rebirth.earnedSlotsPerMilestone * rebirthCount)
end

function ShadowArmyService.getTotalSquadPower(player: Player): number
	local profile = PlayerDataService.getProfile(player)
	if not profile then return 0 end

	local maxSlots = ShadowArmyService.getMaxSquadSlots(player)
	local shadows = profile.Inventory.Shadows
	local totalPower = 0

	for i = 1, math.min(#shadows, maxSlots) do
		totalPower += (shadows[i].power or 0)
	end

	return totalPower
end

function ShadowArmyService.ownsShadow(player: Player, shadowId: string): boolean
	local profile = PlayerDataService.getProfile(player)
	if not profile then return false end
	for _, shadow in ipairs(profile.Inventory.Shadows) do
		if shadow.id == shadowId then
			return true
		end
	end
	return false
end

-- Guaranteed first ARISE on boss clear
function ShadowArmyService.handleAriseRequest(player: Player, playerPosition: Vector3?): (boolean, string?, ShadowEntity?)
	local profile = PlayerDataService.getProfile(player)
	if not profile then
		return false, "No active session", nil
	end

	-- Distance validation to ritual socket / boss arena
	local charPos = playerPosition
	if not charPos then
		local character = player.Character
		if character and character.PrimaryPart then
			charPos = character.PrimaryPart.Position
		end
	end

	if charPos then
		local dist = (charPos - BOSS_ALTAR_POSITION).Magnitude
		if dist > MAX_RITUAL_DISTANCE then
			return false, string.format("Too far from ritual socket (%.1f > %.1f studs)", dist, MAX_RITUAL_DISTANCE), nil
		end
	end

	-- Verify boss clear state
	if not CombatService.hasClearedBoss(player) then
		return false, "Boss has not been cleared", nil
	end

	-- Verify not already owned
	if ShadowArmyService.ownsShadow(player, "shadow_boss_monarch") then
		return false, "Shadow Monarch is already extracted and owned", nil
	end

	-- Consume boss clear
	CombatService.consumeBossClear(player)

	-- Guaranteed extraction
	local bossShadow = table.clone(SHADOW_DEFINITIONS["shadow_boss_monarch"])
	table.insert(profile.Inventory.Shadows, bossShadow)

	return true, nil, bossShadow
end

-- Gacha summon with 10,000 basis point rate table and 50-roll pity counter
function ShadowArmyService.handleSummonRequest(player: Player, forcedRoll: number?): (boolean, string?, { shadow: ShadowEntity, isDuplicate: boolean, isPity: boolean }?)
	local profile = PlayerDataService.getProfile(player)
	if not profile then
		return false, "No active session", nil
	end

	local pool = Config.GachaPools.pool_shadow_forest
	if not pool then
		return false, "Unknown summon pool", nil
	end

	-- Deduct mana
	local deducted, err = PlayerDataService.deductCurrency(player, pool.currencyId, pool.cost)
	if not deducted then
		return false, err or "Failed to deduct currency", nil
	end

	-- Advance pity counter
	local pityKey = pool.pityCounterKey or "pool_shadow_forest"
	local currentPity = (profile.Pity[pityKey] or 0) + 1
	profile.Pity[pityKey] = currentPity

	local outcomeDefinitionId = ""
	local isPity = false

	if currentPity >= pool.pityThreshold then
		-- Pity guarantee: awards legendary outcome (shadow_footman)
		outcomeDefinitionId = "shadow_footman"
		isPity = true
		profile.Pity[pityKey] = 0
	else
		-- Roll from 10,000 basis points
		local roll = forcedRoll or math.random(1, 10000)
		local accumulated = 0
		for _, outcome in ipairs(pool.outcomes) do
			accumulated += outcome.rateBasisPoints
			if roll <= accumulated then
				outcomeDefinitionId = outcome.definitionId
				break
			end
		end
		if outcomeDefinitionId == "shadow_footman" then
			profile.Pity[pityKey] = 0 -- Reset pity on natural legendary
		end
	end

	local def = SHADOW_DEFINITIONS[outcomeDefinitionId]
	if not def then
		return false, "Invalid outcome definition", nil
	end

	local isDuplicate = ShadowArmyService.ownsShadow(player, outcomeDefinitionId)
	if isDuplicate then
		-- Duplicate protection: awards 5 Essence instead of duplicate clutter
		PlayerDataService.addCurrency(player, "Essence", 5)
	else
		table.insert(profile.Inventory.Shadows, table.clone(def))
	end

	return true, nil, {
		shadow = def,
		isDuplicate = isDuplicate,
		isPity = isPity,
	}
end

-- Rebirth execution according to ResetManifest
function ShadowArmyService.handleRebirthRequest(player: Player): (boolean, string?, { newRebirthCount: number, sigilsAwarded: number }?)
	local profile = PlayerDataService.getProfile(player)
	if not profile then
		return false, "No active session", nil
	end

	local currentRebirth = profile.Progression.RebirthCount or 0
	local cost = Config.rebirthCost(currentRebirth)
	local currentMana = profile.Currencies.Mana or 0

	if currentMana < cost then
		return false, string.format("Insufficient mana for rebirth (have %d, need %d)", currentMana, cost), nil
	end

	-- Execute ResetManifest:
	-- Resets:
	profile.Currencies.Mana = 0
	profile.Progression.WorldUpgrades = {}

	-- Kept:
	-- profile.Inventory.Shadows (preserved!)
	-- profile.Pity (preserved!)
	-- profile.Entitlements (preserved!)
	-- profile.Settings (preserved!)

	-- Transforms:
	profile.Progression.RebirthCount = currentRebirth + 1
	local sigilsReward = 1 + math.floor(currentRebirth * 0.5)
	PlayerDataService.addCurrency(player, "RebirthSigils", sigilsReward)

	return true, nil, {
		newRebirthCount = profile.Progression.RebirthCount,
		sigilsAwarded = sigilsReward,
	}
end

return ShadowArmyService
