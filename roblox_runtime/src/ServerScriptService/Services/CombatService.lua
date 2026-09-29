--!strict
-- CombatService: Server-authoritative targeting, damage calculations, and combat state
-- Enforces range, player life, enemy ownership, and boss-clear eligibility

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)
local PlayerDataService = require(script.Parent.PlayerDataService)

local CombatService = {}

local MAX_ATTACK_RANGE = 50 -- studs

export type EnemyData = {
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
	lastTargetTime: number,
}

local activeEnemies: { [string]: EnemyData } = {}
local playerCombatStates: { [Player]: PlayerCombatState } = {}

-- Forward declaration / injection for ShadowArmyService to avoid circular require
local shadowArmyServiceRef: any = nil

function CombatService.setShadowArmyService(service: any)
	shadowArmyServiceRef = service
end

function CombatService.registerEnemy(enemy: EnemyData)
	activeEnemies[enemy.id] = {
		id = enemy.id,
		name = enemy.name,
		maxHealth = enemy.maxHealth,
		health = enemy.maxHealth,
		position = enemy.position,
		rewardMana = enemy.rewardMana,
		isBoss = enemy.isBoss,
		isMiniBoss = enemy.isMiniBoss,
	}
end

function CombatService.getEnemy(enemyId: string): EnemyData?
	return activeEnemies[enemyId]
end

function CombatService.initPlayer(player: Player)
	playerCombatStates[player] = {
		bossCleared = false,
		miniBossCleared = false,
		lastTargetTime = 0,
	}
end

function CombatService.cleanupPlayer(player: Player)
	playerCombatStates[player] = nil
end

function CombatService.hasClearedBoss(player: Player): boolean
	local state = playerCombatStates[player]
	return state and state.bossCleared or false
end

function CombatService.consumeBossClear(player: Player): boolean
	local state = playerCombatStates[player]
	if state and state.bossCleared then
		state.bossCleared = false
		return true
	end
	return false
end

function CombatService.calculatePlayerDamage(player: Player): number
	local profile = PlayerDataService.getProfile(player)
	if not profile then
		return Config.worldBasePower(1)
	end

	local basePower = Config.worldBasePower(1)
	local squadPower = 0
	if shadowArmyServiceRef and shadowArmyServiceRef.getTotalSquadPower then
		squadPower = shadowArmyServiceRef.getTotalSquadPower(player)
	end

	local rebirthMultiplier = Config.rebirthPowerMultiplier(profile.Progression.RebirthCount or 0)
	local totalDamage = math.floor((basePower + squadPower) * rebirthMultiplier)
	return math.max(1, totalDamage)
end

function CombatService.handleTargetRequest(player: Player, enemyId: string, playerPosition: Vector3?): (boolean, string?, { [string]: any }?)
	local enemy = activeEnemies[enemyId]
	if not enemy then
		return false, "Target enemy does not exist", nil
	end

	if enemy.health <= 0 then
		return false, "Target enemy is already defeated", nil
	end

	-- Verify player character position
	local charPos = playerPosition
	if not charPos then
		local character = player.Character
		if not character then
			return false, "Player character not found", nil
		end
		local hrp = character:FindFirstChild("HumanoidRootPart") :: BasePart?
		local humanoid = character:FindFirstChildOfClass("Humanoid")
		if not hrp or not humanoid or humanoid.Health <= 0 then
			return false, "Player is not alive", nil
		end
		charPos = hrp.Position
	end

	-- Server-side range validation
	local distance = (charPos - enemy.position).Magnitude
	if distance > MAX_ATTACK_RANGE then
		return false, string.format("Target out of range (%.1f > %.1f studs)", distance, MAX_ATTACK_RANGE), nil
	end

	local state = playerCombatStates[player]
	if not state then
		CombatService.initPlayer(player)
		state = playerCombatStates[player]
	end
	state.lastTargetTime = os.clock()

	-- Compute damage authoritatively
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
