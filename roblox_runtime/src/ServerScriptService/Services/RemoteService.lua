--!strict
-- RemoteService: Server-authoritative endpoint dispatcher with rate limiting and schema/argument validation
-- Connects client remotes to backend services with zero client trust

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local MarketplaceService = game:GetService("MarketplaceService")

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
}

function RemoteService.init()
	-- Wire MarketplaceService idempotent receipt processing
	MarketplaceService.ProcessReceipt = PlayerDataService.processReceipt

	-- Ensure remote functions exist
	local rfTarget = Remotes.ensureRemoteFunction("request_target")
	local rfUpgrade = Remotes.ensureRemoteFunction("request_upgrade")
	local rfArise = Remotes.ensureRemoteFunction("request_arise")
	local rfSummon = Remotes.ensureRemoteFunction("request_summon")
	local rfRebirth = Remotes.ensureRemoteFunction("request_rebirth")

	rfTarget.OnServerInvoke = function(player: Player, enemyId: any)
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
		return { success = true, data = result }
	end
	RemoteService.handlers.request_target = rfTarget.OnServerInvoke

	rfUpgrade.OnServerInvoke = function(player: Player, upgradeType: any)
		local allowed, limitErr = limiters.request_upgrade.consume(player)
		if not allowed then
			return { success = false, error = limitErr }
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
			},
		}
	end
	RemoteService.handlers.request_upgrade = rfUpgrade.OnServerInvoke

	rfArise.OnServerInvoke = function(player: Player)
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
	RemoteService.handlers.request_arise = rfArise.OnServerInvoke

	rfSummon.OnServerInvoke = function(player: Player)
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
	RemoteService.handlers.request_summon = rfSummon.OnServerInvoke

	rfRebirth.OnServerInvoke = function(player: Player)
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
	RemoteService.handlers.request_rebirth = rfRebirth.OnServerInvoke

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

	game:BindToClose(function()
		PlayerDataService.stopAutosaveLoop()
		for _, player in ipairs(Players:GetPlayers()) do
			PlayerDataService.closeSession(player)
		end
	end)

	-- Start background autosave loop
	PlayerDataService.startAutosaveLoop()
end

return RemoteService
