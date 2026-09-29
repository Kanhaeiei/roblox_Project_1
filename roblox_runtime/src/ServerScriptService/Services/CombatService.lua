--!strict
-- CombatService: Server-authoritative targeting, damage calculations, and combat state
-- Enforces server-side character position/health, attack cooldown, per-player enemy progression, and boss-clear eligibility

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)
local PlayerDataService = require(script.Parent.PlayerDataService)

local CombatService = {}

export type EnemyInstance = {
	id: string,
	name: string,
	maxHealth: number,
	health: number,
	position: Vector3,
	rewardMana: number,
	isBoss: boolean,
	isMiniBoss: boolean,
}

export type PlayerCombatState = {
	bossCleared: boolean,
	miniBossCleared: boolean,
	lastAttackTime: number,
	enemies: { [string]: EnemyInstance },
}

local playerCombatStates: { [any]: PlayerCombatState } = {}
local mockCharacters: { [any]: { position: Vector3, isAlive: boolean } } = {}

-- Forward declaration / injection for ShadowArmyService to avoid circular require
local shadowArmyServiceRef: any = nil

function CombatService.setShadowArmyService(service: any)
	shadowArmyServiceRef = service
end

-- Mock character helper for offline unit testing
function CombatService.setMockCharacter(player: any, position: Vector3?, isAlive: boolean?)
	if position == nil and isAlive == nil then
		mockCharacters[player] = nil
	else
		mockCharacters[player] = {
			position = position or Vector3.zero,
			isAlive = if isAlive ~= nil then isAlive else true,
		}
	end
end

-- Initialize per-player enemy progression and combat state
function CombatService.initPlayer(player: any)
	local enemies: { [string]: EnemyInstance } = {}
	for id, template in pairs(Config.Enemies) do
		enemies[id] = {
			id = template.id,
			name = template.name,
			maxHealth = template.maxHealth,
			health = template.maxHealth,
			position = template.spawnPosition,
			rewardMana = template.rewardMana,
			isBoss = template.isBoss,
			isMiniBoss = template.isMiniBoss,
		}
	end

	playerCombatStates[player] = {
		bossCleared = false,
		miniBossCleared = false,
		lastAttackTime = 0,
		enemies = enemies,
	}
end

function CombatService.cleanupPlayer(player: any)
	playerCombatStates[player] = nil
	mockCharacters[player] = nil
end

function CombatService.hasClearedBoss(player: any): boolean
	local state = playerCombatStates[player]
	return state and state.bossCleared or false
end

function CombatService.consumeBossClear(player: any): boolean
	local state = playerCombatStates[player]
	if state and state.bossCleared then
		state.bossCleared = false
		return true
	end
	return false
end

function CombatService.getEnemy(player: any, enemyId: string): EnemyInstance?
	local state = playerCombatStates[player]
	return state and state.enemies[enemyId] or nil
end

function CombatService.calculatePlayerDamage(player: any): number
	local profile = PlayerDataService.getProfile(player)
	local basePower = Config.worldBasePower(1)
	local squadPower = 0
	if shadowArmyServiceRef and shadowArmyServiceRef.getTotalSquadPower then
		squadPower = shadowArmyServiceRef.getTotalSquadPower(player)
	end

	-- Additional power from purchased upgrades
	local upgradeBonus = 0
	if profile and profile.Progression.WorldUpgrades then
		local atkLevel = profile.Progression.WorldUpgrades["attack_power"] or 0
		if Config.Upgrades.attack_power then
			upgradeBonus = Config.Upgrades.attack_power.bonusFormula(atkLevel)
		end
	end

	local rebirthMultiplier = Config.rebirthPowerMultiplier(profile and profile.Progression.RebirthCount or 0)
	local totalDamage = math.floor((basePower + squadPower + upgradeBonus) * rebirthMultiplier)
	return math.max(1, totalDamage)
end

function CombatService.handleTargetRequest(player: any, enemyId: string): (boolean, string?, { [string]: any }?)
	local state = playerCombatStates[player]
	if not state then
		CombatService.initPlayer(player)
		state = playerCombatStates[player]
	end

	-- 1. Server-side attack cooldown check
	local now = os.clock()
	if (now - state.lastAttackTime) < Config.Combat.attackCooldown then
		return false, "Attack cooldown active", nil
	end

	-- 2. Verify target enemy exists in player's per-player instance
	local enemy = state.enemies[enemyId]
	if not enemy then
		return false, "Target enemy does not exist: " .. tostring(enemyId), nil
	end

	if enemy.health <= 0 then
		return false, "Target enemy is already defeated", nil
	end

	-- 3. Server-authoritative player life and position check
	local charPos: Vector3? = nil
	local mock = mockCharacters[player]

	if mock then
		if not mock.isAlive then
			return false, "Player is not alive", nil
		end
		charPos = mock.position
	else
		local character = player.Character
		if not character then
			return false, "Player character not found on server", nil
		end
		local humanoid = character:FindFirstChildOfClass("Humanoid")
		local hrp = character:FindFirstChild("HumanoidRootPart") :: BasePart?
		if not humanoid or humanoid.Health <= 0 or not hrp then
			return false, "Player is not alive", nil
		end
		charPos = hrp.Position
	end

	if not charPos then
		return false, "Player character position unavailable", nil
	end

	-- 4. Server-side distance check
	local distance = (charPos - enemy.position).Magnitude
	if distance > Config.Combat.maxAttackRange then
		return false, string.format("Target out of range (%.1f > %.1f studs)", distance, Config.Combat.maxAttackRange), nil
	end

	-- Record attack time for cooldown
	state.lastAttackTime = now

	-- 5. Calculate damage authoritatively
	local damage = CombatService.calculatePlayerDamage(player)
	enemy.health = math.max(0, enemy.health - damage)

	local defeated = (enemy.health == 0)
	local manaAwarded = 0

	if defeated then
		manaAwarded = enemy.rewardMana
		PlayerDataService.addCurrency(player, "Mana", manaAwarded)

		if enemy.isBoss then
			state.bossCleared = true
		end
		if enemy.isMiniBoss then
			state.miniBossCleared = true
		end

		-- Respawn enemy after delay for ongoing farming
		task.delay(if enemy.isBoss then 5 else 2, function()
			if state and state.enemies[enemyId] then
				state.enemies[enemyId].health = state.enemies[enemyId].maxHealth
			end
		end)
	end

	return true, nil, {
		enemyId = enemy.id,
		damageDealt = damage,
		remainingHealth = enemy.health,
		isDefeated = defeated,
		manaAwarded = manaAwarded,
		bossCleared = state.bossCleared,
	}
end

return CombatService
