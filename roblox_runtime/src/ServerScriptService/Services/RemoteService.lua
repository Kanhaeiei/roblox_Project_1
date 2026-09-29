--!strict
-- RemoteService: Server-authoritative endpoint dispatcher with rate limiting and schema/argument validation
-- Connects client remotes to backend services with zero client trust

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local MarketplaceService = game:GetService("MarketplaceService")

local RunService = game:GetService("RunService")

local Config = require(ReplicatedStorage.Shared.Config)
local Remotes = require(ReplicatedStorage.Shared.Remotes)
local PlayerDataService = require(script.Parent.PlayerDataService)
local CombatService = require(script.Parent.CombatService)
local ShadowArmyService = require(script.Parent.ShadowArmyService)

local RemoteService = {}
RemoteService.handlers = {} :: { [string]: (player: Player, ...any) -> any }

-- Rate limiters per remote endpoint
local limiters = {
	request_target = Remotes.createRateLimiter(Config.RemoteRules.request_target.ratePerSecond),
	request_upgrade = Remotes.createRateLimiter(Config.RemoteRules.request_upgrade.ratePerSecond),
	request_arise = Remotes.createRateLimiter(Config.RemoteRules.request_arise.ratePerSecond),
	request_summon = Remotes.createRateLimiter(Config.RemoteRules.request_summon.ratePerSecond),
	request_rebirth = Remotes.createRateLimiter(Config.RemoteRules.request_rebirth.ratePerSecond),
	request_snapshot = Remotes.createRateLimiter(Config.RemoteRules.request_snapshot.ratePerSecond),
}

-- Named local handler: Target attack
local function handleTarget(player: Player, enemyId: any): any
	local allowed, limitErr = limiters.request_target.consume(player)
	if not allowed then
		return { success = false, error = limitErr }
	end

	if type(enemyId) ~= "string" or enemyId == "" then
		return { success = false, error = "Invalid enemyId argument" }
	end

	local success, err, result = CombatService.handleTargetRequest(player, enemyId)
	if not success then
		return { success = false, error = err }
	end

	local profile = PlayerDataService.getProfile(player)
	if result and profile then
		result.totalMana = profile.Currencies.Mana or 0
	end

	return { success = true, data = result }
end

-- Named local handler: Upgrade purchase
local function handleUpgrade(player: Player, upgradeType: any): any
	local allowed, limitErr = limiters.request_upgrade.consume(player)
	if not allowed then
		return { success = false, error = limitErr }
	end

	if PlayerDataService.isReadOnly(player) then
		return { success = false, error = "Session is read-only" }
	end

	if type(upgradeType) ~= "string" or upgradeType == "" then
		return { success = false, error = "Invalid upgradeType argument" }
	end

	-- Validate against server-authoritative upgrades allowlist
	local upgradeDef = Config.Upgrades[upgradeType]
	if not upgradeDef then
		return { success = false, error = "Unknown or unapproved upgrade key: " .. tostring(upgradeType) }
	end

	local profile = PlayerDataService.getProfile(player)
	if not profile then
		return { success = false, error = "No active session" }
	end

	local currentLevel = profile.Progression.WorldUpgrades[upgradeType] or 0
	if currentLevel >= upgradeDef.maxLevel then
		return { success = false, error = string.format("Upgrade '%s' has reached maximum level (%d)", upgradeType, upgradeDef.maxLevel) }
	end

	local cost = upgradeDef.costFormula(currentLevel)
	local currentMana = profile.Currencies.Mana or 0

	if currentMana < cost then
		return { success = false, error = string.format("Insufficient mana (have %d, need %d)", currentMana, cost) }
	end

	local deducted, err = PlayerDataService.deductCurrency(player, "Mana", cost)
	if not deducted then
		return { success = false, error = err or "Deduction failed" }
	end

	profile.Progression.WorldUpgrades[upgradeType] = currentLevel + 1
	PlayerDataService.markDirty(player)

	return {
		success = true,
		data = {
			upgradeType = upgradeType,
			newLevel = currentLevel + 1,
			costPaid = cost,
			totalMana = profile.Currencies.Mana or 0,
		},
	}
end

-- Named local handler: ARISE extraction
local function handleArise(player: Player): any
	local allowed, limitErr = limiters.request_arise.consume(player)
	if not allowed then
		return { success = false, error = limitErr }
	end

	local success, err, shadow = ShadowArmyService.handleAriseRequest(player)
	if not success then
		return { success = false, error = err }
	end
	return { success = true, data = shadow }
end

-- Named local handler: Gacha summon
local function handleSummon(player: Player): any
	local allowed, limitErr = limiters.request_summon.consume(player)
	if not allowed then
		return { success = false, error = limitErr }
	end

	local success, err, result = ShadowArmyService.handleSummonRequest(player)
	if not success then
		return { success = false, error = err }
	end
	return { success = true, data = result }
end

-- Named local handler: Rebirth
local function handleRebirth(player: Player): any
	local allowed, limitErr = limiters.request_rebirth.consume(player)
	if not allowed then
		return { success = false, error = limitErr }
	end

	local success, err, result = ShadowArmyService.handleRebirthRequest(player)
	if not success then
		return { success = false, error = err }
	end
	return { success = true, data = result }
end

-- Named local handler: Initial player snapshot for client HUD
local function handleSnapshot(player: Player): any
	local allowed, limitErr = limiters.request_snapshot.consume(player)
	if not allowed then
		return { success = false, error = limitErr }
	end

	local session = PlayerDataService.getSessionState(player)
	if not session then
		return { success = false, error = "No active session", isReadOnly = true, isConflicted = true }
	end

	local profile = session.data
	local atkLevel = (profile.Progression.WorldUpgrades and profile.Progression.WorldUpgrades["attack_power"]) or 0
	local power = CombatService.calculatePlayerDamage(player)

	return {
		success = true,
		data = {
			mana = profile.Currencies.Mana or 0,
			essence = profile.Currencies.Essence or 0,
			rebirthSigils = profile.Currencies.RebirthSigils or 0,
			rebirthCount = profile.Progression.RebirthCount or 0,
			level = atkLevel,
			power = power,
			worldUpgrades = profile.Progression.WorldUpgrades or {},
			shadowCount = #profile.Inventory.Shadows,
			isReadOnly = session.isReadOnly,
			isConflicted = session.isConflicted,
		},
	}
end

function RemoteService.init()
	-- Wire MarketplaceService idempotent receipt processing
	if RunService:IsServer() and RunService:IsRunning() then
		MarketplaceService.ProcessReceipt = PlayerDataService.processReceipt
	else
		pcall(function()
			MarketplaceService.ProcessReceipt = PlayerDataService.processReceipt
		end)
	end

	-- Ensure remote functions exist
	local rfTarget = Remotes.ensureRemoteFunction("request_target")
	local rfUpgrade = Remotes.ensureRemoteFunction("request_upgrade")
	local rfArise = Remotes.ensureRemoteFunction("request_arise")
	local rfSummon = Remotes.ensureRemoteFunction("request_summon")
	local rfRebirth = Remotes.ensureRemoteFunction("request_rebirth")
	local rfSnapshot = Remotes.ensureRemoteFunction("request_snapshot")

	-- Assign the same named local handlers to OnServerInvoke and RemoteService.handlers table (WITHOUT reading OnServerInvoke)
	if RunService:IsServer() and RunService:IsRunning() then
		rfTarget.OnServerInvoke = handleTarget
		rfUpgrade.OnServerInvoke = handleUpgrade
		rfArise.OnServerInvoke = handleArise
		rfSummon.OnServerInvoke = handleSummon
		rfRebirth.OnServerInvoke = handleRebirth
		rfSnapshot.OnServerInvoke = handleSnapshot
	else
		pcall(function() rfTarget.OnServerInvoke = handleTarget end)
		pcall(function() rfUpgrade.OnServerInvoke = handleUpgrade end)
		pcall(function() rfArise.OnServerInvoke = handleArise end)
		pcall(function() rfSummon.OnServerInvoke = handleSummon end)
		pcall(function() rfRebirth.OnServerInvoke = handleRebirth end)
		pcall(function() rfSnapshot.OnServerInvoke = handleSnapshot end)
	end

	RemoteService.handlers.request_target = handleTarget
	RemoteService.handlers.request_upgrade = handleUpgrade
	RemoteService.handlers.request_arise = handleArise
	RemoteService.handlers.request_summon = handleSummon
	RemoteService.handlers.request_rebirth = handleRebirth
	RemoteService.handlers.request_snapshot = handleSnapshot

	-- Connect lifecycle
	Players.PlayerAdded:Connect(function(player)
		PlayerDataService.loadSession(player)
		CombatService.initPlayer(player)
	end)

	Players.PlayerRemoving:Connect(function(player)
		CombatService.cleanupPlayer(player)
		PlayerDataService.closeSession(player)
		for _, limiter in pairs(limiters) do
			limiter.reset(player)
		end
	end)

	pcall(function()
		game:BindToClose(function()
			PlayerDataService.stopAutosaveLoop()
			for _, player in ipairs(Players:GetPlayers()) do
				PlayerDataService.closeSession(player)
			end
		end)
	end)

	-- Start background autosave loop
	PlayerDataService.startAutosaveLoop()
end

return RemoteService
