--!strict
-- PlayerDataService: Server-authoritative player data persistence, session leasing, and migrations
-- Includes token-based session ownership, bounded retry/backoff, and idempotent developer-product receipt handling

local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)

local PlayerDataService = {}

local DATA_STORE_NAME = "ShadowArmy_PlayerData_v1"
local LEASE_DURATION = 30 -- seconds
local AUTOSAVE_INTERVAL = 15 -- seconds (< LEASE_DURATION)
local MAX_SAVE_RETRIES = 3

export type ShadowEntity = {
	id: string,
	name: string,
	power: number,
	rarity: string,
}

export type PlayerProfile = {
	schemaVersion: number,
	Currencies: {
		Mana: number,
		Essence: number,
		RebirthSigils: number,
		SoulShards: number,
	},
	Progression: {
		RebirthCount: number,
		WorldId: string,
		WorldUpgrades: { [string]: number },
	},
	Inventory: {
		Shadows: { ShadowEntity },
	},
	Pity: { [string]: number },
	Entitlements: { [string]: boolean },
	Settings: {
		ReducedMotion: boolean,
	},
	PurchaseHistory: { [string]: number },
}

export type SessionRecord = {
	sessionToken: string,
	sessionLock: string,
	leaseTimestamp: number,
	data: PlayerProfile,
}

export type SessionState = {
	sessionToken: string,
	data: PlayerProfile,
	isReadOnly: boolean,
	isDirty: boolean,
	isConflicted: boolean,
	lastSaveTime: number,
}

-- Active runtime session cache per player
local activeSessions: { [any]: SessionState } = {}

-- Diagnostic queue for failed saves on shutdown/leave
local failedSavesLog: { [string]: { userId: number, sessionToken: string, error: string, timestamp: number } } = {}

-- DataStore Adapter interface (allows mocking for tests without touching production DataStores)
export type DataStoreAdapter = {
	getAsync: (key: string) -> (boolean, SessionRecord?, string?),
	updateAsync: (key: string, transform: (prevRecord: SessionRecord?) -> SessionRecord?) -> (boolean, SessionRecord?, string?),
}

local defaultAdapter: DataStoreAdapter = {
	getAsync = function(key: string)
		local success, store = pcall(function()
			return DataStoreService:GetDataStore(DATA_STORE_NAME)
		end)
		if not success or not store then
			return false, nil, "Failed to access DataStore"
		end
		local ok, result = pcall(function()
			return store:GetAsync(key)
		end)
		return ok, result, if not ok then tostring(result) else nil
	end,
	updateAsync = function(key: string, transform: (prevRecord: SessionRecord?) -> SessionRecord?)
		local success, store = pcall(function()
			return DataStoreService:GetDataStore(DATA_STORE_NAME)
		end)
		if not success or not store then
			return false, nil, "Failed to access DataStore"
		end
		local ok, result = pcall(function()
			return store:UpdateAsync(key, transform)
		end)
		return ok, result, if not ok then tostring(result) else nil
	end,
}

local currentAdapter: DataStoreAdapter = defaultAdapter

function PlayerDataService.setDataStoreAdapter(adapter: DataStoreAdapter)
	currentAdapter = adapter
end

function PlayerDataService.resetDataStoreAdapter()
	currentAdapter = defaultAdapter
end

-- Generate a unique session token per session
local function generateSessionToken(player: any): string
	local ok, guid = pcall(function()
		return HttpService:GenerateGUID(false)
	end)
	if ok and guid then
		return guid
	end
	return string.format("token_%d_%d_%d", player.UserId or 0, os.time(), math.random(100000, 999999))
end

function PlayerDataService.getDefaultProfile(): PlayerProfile
	return {
		schemaVersion = Config.SchemaVersion,
		Currencies = {
			Mana = 0,
			Essence = 0,
			RebirthSigils = 0,
			SoulShards = 0,
		},
		Progression = {
			RebirthCount = 0,
			WorldId = "world_01_shadow_forest",
			WorldUpgrades = {},
		},
		Inventory = {
			Shadows = {},
		},
		Pity = {
			pool_shadow_forest = 0,
		},
		Entitlements = {},
		Settings = {
			ReducedMotion = false,
		},
		PurchaseHistory = {},
	}
end

-- Ordered migration pipeline
local MIGRATIONS: { [number]: (data: any) -> () } = {}

function PlayerDataService.migrate(raw: any): PlayerProfile
	local profile = raw or PlayerDataService.getDefaultProfile()
	local currentVer = profile.schemaVersion or 1

	while currentVer < Config.SchemaVersion do
		local nextVer = currentVer + 1
		local migrationFn = MIGRATIONS[nextVer]
		if migrationFn then
			migrationFn(profile)
		end
		profile.schemaVersion = nextVer
		currentVer = nextVer
	end

	return profile
end

-- Bounded exponential backoff with jitter
local function executeWithRetry<T>(operation: () -> (boolean, T?, string?), maxAttempts: number?): (boolean, T?, string?)
	local attempts = maxAttempts or MAX_SAVE_RETRIES
	local baseDelay = 0.4
	local maxDelay = 2.5
	local lastErr: string? = nil

	for attempt = 1, attempts do
		local ok, result, err = operation()
		if ok then
			return true, result, nil
		end
		lastErr = err or "Unknown error"
		if attempt < attempts then
			local jitter = math.random() * 0.2
			local delay = math.min(maxDelay, baseDelay * (2 ^ (attempt - 1))) + jitter
			task.wait(delay)
		end
	end
	return false, nil, lastErr
end

-- Mark session dirty through centralized path
function PlayerDataService.markDirty(player: any)
	local session = activeSessions[player]
	if session and not session.isReadOnly then
		session.isDirty = true
	end
end

-- Load player session with session lease acquisition
function PlayerDataService.loadSession(player: any): (PlayerProfile, boolean)
	local key = "Player_" .. tostring(player.UserId)
	local now = os.time()
	local currentJobId = game.JobId ~= "" and game.JobId or "StandaloneJob"
	local newSessionToken = generateSessionToken(player)

	local conflictDetected = false
	local ok, record, err = executeWithRetry(function()
		return currentAdapter.updateAsync(key, function(prevRecord: SessionRecord?)
			if prevRecord and prevRecord.sessionToken and prevRecord.sessionToken ~= "" then
				-- Check if existing lease is unexpired and held by a different session
				if (now - prevRecord.leaseTimestamp) < LEASE_DURATION then
					conflictDetected = true
					return prevRecord
				end
			end

			-- Lease expired or free: acquire lease with our unique token
			local profile = if prevRecord and prevRecord.data then PlayerDataService.migrate(prevRecord.data) else PlayerDataService.getDefaultProfile()
			return {
				sessionToken = newSessionToken,
				sessionLock = currentJobId,
				leaseTimestamp = now,
				data = profile,
			}
		end)
	end)

	if not ok or not record then
		warn("[PlayerDataService] Failed to load DataStore for", player.UserId, "Error:", err, "- fallback to read-only defaults")
		local fallback = PlayerDataService.getDefaultProfile()
		activeSessions[player] = {
			sessionToken = newSessionToken,
			data = fallback,
			isReadOnly = true,
			isDirty = false,
			isConflicted = true,
			lastSaveTime = now,
		}
		return fallback, true
	end

	-- Check whether we acquired the lease or if another session owns it
	local isReadOnly = false
	local isConflicted = false
	if conflictDetected or record.sessionToken ~= newSessionToken then
		isReadOnly = true
		isConflicted = true
		warn("[PlayerDataService] Session conflict for player", player.UserId, "- lease owned by token:", record.sessionToken)
	end

	local profile = record.data or PlayerDataService.getDefaultProfile()
	activeSessions[player] = {
		sessionToken = if isReadOnly then (record.sessionToken or newSessionToken) else newSessionToken,
		data = profile,
		isReadOnly = isReadOnly,
		isDirty = false,
		isConflicted = isConflicted,
		lastSaveTime = now,
	}

	return profile, isReadOnly
end

-- Save session with session token ownership check
function PlayerDataService.saveSession(player: any, releaseLease: boolean): boolean
	local session = activeSessions[player]
	if not session then
		return false
	end
	if session.isReadOnly then
		return false
	end

	local key = "Player_" .. tostring(player.UserId)
	local now = os.time()
	local currentJobId = game.JobId ~= "" and game.JobId or "StandaloneJob"
	local myToken = session.sessionToken
	local conflictDetected = false

	local ok, resultRecord, err = executeWithRetry(function()
		return currentAdapter.updateAsync(key, function(prevRecord: SessionRecord?)
			if prevRecord and prevRecord.sessionToken and prevRecord.sessionToken ~= "" and prevRecord.sessionToken ~= myToken then
				if (now - prevRecord.leaseTimestamp) < LEASE_DURATION then
					-- Ownership lost! Another session acquired the lease.
					-- Abort write by returning nil.
					conflictDetected = true
					return nil
				end
			end

			return {
				sessionToken = if releaseLease then "" else myToken,
				sessionLock = if releaseLease then "" else currentJobId,
				leaseTimestamp = if releaseLease then 0 else now,
				data = session.data,
			}
		end)
	end)

	if conflictDetected then
		session.isReadOnly = true
		session.isConflicted = true
		warn("[PlayerDataService] Ownership lost for player", player.UserId, "- session entered read-only mode")
		return false
	end

	if not ok or not resultRecord then
		warn("[PlayerDataService] Save failed for player", player.UserId, "Error:", err)
		return false
	end

	-- Verify the written record actually matches our token (or empty on release)
	if not releaseLease and resultRecord.sessionToken ~= myToken then
		session.isReadOnly = true
		session.isConflicted = true
		warn("[PlayerDataService] Lease lost during save for player", player.UserId)
		return false
	end

	session.isDirty = false
	session.lastSaveTime = now
	return true
end

function PlayerDataService.getProfile(player: any): PlayerProfile?
	local session = activeSessions[player]
	return session and session.data or nil
end

function PlayerDataService.getSessionState(player: any): SessionState?
	return activeSessions[player]
end

function PlayerDataService.isReadOnly(player: any): boolean
	local session = activeSessions[player]
	return session and session.isReadOnly or false
end

function PlayerDataService.getCurrency(player: any, currencyId: string): number
	local profile = PlayerDataService.getProfile(player)
	if not profile then return 0 end
	return (profile.Currencies :: any)[currencyId] or 0
end

-- Validate currency mutation parameters strictly
local function validateCurrencyMutation(currencyId: string, amount: number): (boolean, string?)
	-- 1. Must be recognized currency
	if type(currencyId) ~= "string" or not (Config.Currencies :: any)[currencyId] then
		return false, "Unknown or invalid currency: " .. tostring(currencyId)
	end

	-- 2. Must be number
	if type(amount) ~= "number" then
		return false, "Amount must be a number"
	end

	-- 3. Reject NaN (amount ~= amount) and Infinity (math.huge)
	if amount ~= amount or amount == math.huge or amount == -math.huge then
		return false, "Amount must be a finite number"
	end

	-- 4. Must be positive integer
	if amount <= 0 or amount ~= math.floor(amount) then
		return false, "Amount must be a positive integer"
	end

	-- 5. Safe integer ceiling
	if amount > Config.SafeIntegerCeiling then
		return false, "Amount exceeds safe integer ceiling"
	end

	return true, nil
end

function PlayerDataService.addCurrency(player: any, currencyId: string, amount: number): (boolean, string?)
	local valid, valErr = validateCurrencyMutation(currencyId, amount)
	if not valid then
		return false, valErr
	end

	local session = activeSessions[player]
	if not session then
		return false, "No active session"
	end
	if session.isReadOnly then
		return false, "Session is read-only"
	end

	local curMap = session.data.Currencies :: any
	local current = curMap[currencyId] or 0
	local meta = (Config.Currencies :: any)[currencyId]
	local cap = meta and meta.cap or Config.SafeIntegerCeiling

	local newAmount = math.min(current + amount, cap)
	newAmount = math.min(newAmount, Config.SafeIntegerCeiling)
	curMap[currencyId] = newAmount
	session.isDirty = true
	return true, nil
end

function PlayerDataService.deductCurrency(player: any, currencyId: string, amount: number): (boolean, string?)
	local valid, valErr = validateCurrencyMutation(currencyId, amount)
	if not valid then
		return false, valErr
	end

	local session = activeSessions[player]
	if not session then
		return false, "No active session"
	end
	if session.isReadOnly then
		return false, "Session is read-only"
	end

	local curMap = session.data.Currencies :: any
	local current = curMap[currencyId] or 0
	if current < amount then
		return false, "Insufficient balance"
	end

	curMap[currencyId] = current - amount
	session.isDirty = true
	return true, nil
end

function PlayerDataService.addShadow(player: any, shadow: ShadowEntity): (boolean, string?)
	local session = activeSessions[player]
	if not session then
		return false, "No active session"
	end
	if session.isReadOnly then
		return false, "Session is read-only"
	end

	table.insert(session.data.Inventory.Shadows, shadow)
	session.isDirty = true
	return true, nil
end

-- Developer Product receipt handling
-- Hardened against currency cap, save failure, ambiguous outcome, and duplicate receipts
function PlayerDataService.processReceipt(receiptInfo: {
	PurchaseId: string,
	PlayerId: number,
	ProductId: number,
	CurrencySpent: number?,
}): Enum.ProductPurchaseDecision
	-- 1. Check if developer products are enabled
	if not Config.DeveloperProductsEnabled then
		warn("[PlayerDataService] Developer product processing disabled. ProductId:", receiptInfo.ProductId)
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	-- 2. Validate product definition exists
	local productDef = Config.DeveloperProducts[receiptInfo.ProductId]
	if not productDef then
		warn("[PlayerDataService] Unknown product ID:", receiptInfo.ProductId, "- returning NotProcessedYet")
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	-- 3. Lookup player & active session
	local player = Players:GetPlayerByUserId(receiptInfo.PlayerId)
	local session = player and activeSessions[player]
	if not session then
		for p, s in pairs(activeSessions) do
			if p.UserId == receiptInfo.PlayerId then
				player = p
				session = s
				break
			end
		end
	end
	if not session or session.isReadOnly then
		-- Player not present or in read-only mode; do not grant or mark processed
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	-- 4. Idempotency check in local memory
	if session.data.PurchaseHistory and session.data.PurchaseHistory[receiptInfo.PurchaseId] then
		return Enum.ProductPurchaseDecision.PurchaseGranted
	end

	-- 5. Currency Cap check BEFORE touching memory
	local targetCurrency = productDef.currency
	local grantAmount = productDef.amount
	local meta = (Config.Currencies :: any)[targetCurrency]
	local cap = meta and meta.cap or Config.SafeIntegerCeiling
	local currentBalance = session.data.Currencies[targetCurrency] or 0

	if currentBalance + grantAmount > cap then
		warn("[PlayerDataService] Product grant would exceed currency cap for player", receiptInfo.PlayerId, "PurchaseId:", receiptInfo.PurchaseId)
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	-- 6. Atomic grant and save commit via UpdateAsync
	-- Commit directly into DataStore so memory is never modified ahead of durable storage
	local purchaseId = receiptInfo.PurchaseId
	local key = "Player_" .. tostring(receiptInfo.PlayerId)
	local now = os.time()
	local myToken = session.sessionToken

	local purchaseAlreadyGranted = false
	local capExceededInDataStore = false
	local conflictInStore = false

	local ok, updatedRecord, err = executeWithRetry(function()
		return currentAdapter.updateAsync(key, function(prevRecord: SessionRecord?)
			if not prevRecord or not prevRecord.data then
				return nil
			end

			-- Check session ownership
			if prevRecord.sessionToken and prevRecord.sessionToken ~= "" and prevRecord.sessionToken ~= myToken then
				if (now - prevRecord.leaseTimestamp) < LEASE_DURATION then
					conflictInStore = true
					return nil
				end
			end

			local data = prevRecord.data
			if not data.PurchaseHistory then
				data.PurchaseHistory = {}
			end

			-- Duplicate receipt check in storage
			if data.PurchaseHistory[purchaseId] then
				purchaseAlreadyGranted = true
				return prevRecord
			end

			-- Currency cap check in storage
			local storeBalance = data.Currencies[targetCurrency] or 0
			if storeBalance + grantAmount > cap then
				capExceededInDataStore = true
				return nil
			end

			data.Currencies[targetCurrency] = storeBalance + grantAmount
			data.PurchaseHistory[purchaseId] = now

			return {
				sessionToken = myToken,
				sessionLock = prevRecord.sessionLock,
				leaseTimestamp = now,
				data = data,
			}
		end)
	end)

	if conflictInStore then
		session.isReadOnly = true
		session.isConflicted = true
		warn("[PlayerDataService] Session conflict detected during processReceipt for player", receiptInfo.PlayerId)
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	if purchaseAlreadyGranted then
		-- Receipt already exists in DataStore; sync memory and acknowledge
		session.data.PurchaseHistory[purchaseId] = session.data.PurchaseHistory[purchaseId] or now
		return Enum.ProductPurchaseDecision.PurchaseGranted
	end

	if capExceededInDataStore then
		warn("[PlayerDataService] Currency cap reached in DataStore during processReceipt for player", receiptInfo.PlayerId)
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	if not ok or not updatedRecord then
		-- Save failed or ambiguous network outcome:
		-- In-memory balance was NEVER modified, so existing balance is 100% safe.
		-- Return NotProcessedYet so Roblox can retry.
		warn("[PlayerDataService] Failed to commit product purchase to DataStore for player", receiptInfo.PlayerId, "Error:", err)
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	-- Save succeeded! Sync in-memory session with the authoritative record from storage
	if updatedRecord.data then
		for k, v in pairs(updatedRecord.data) do
			(session.data :: any)[k] = v
		end
	end
	session.isDirty = false
	session.lastSaveTime = now

	return Enum.ProductPurchaseDecision.PurchaseGranted
end

-- Close session on player removing
function PlayerDataService.closeSession(player: any)
	local session = activeSessions[player]
	if not session then return end

	if not session.isReadOnly then
		local saved = PlayerDataService.saveSession(player, true)
		if not saved then
			local key = "Player_" .. tostring(player.UserId)
			failedSavesLog[key] = {
				userId = player.UserId,
				sessionToken = session.sessionToken,
				error = "Failed to save on player leave",
				timestamp = os.time(),
			}
			warn("[PlayerDataService] CRITICAL: Session save on leave failed for UserId:", player.UserId, "Token:", session.sessionToken)
		end
	end

	activeSessions[player] = nil
end

-- Background autosave / lease renewal runner
local autosaveRunning = false
function PlayerDataService.startAutosaveLoop()
	if autosaveRunning then return end
	autosaveRunning = true

	task.spawn(function()
		while autosaveRunning do
			task.wait(AUTOSAVE_INTERVAL)
			for player, session in pairs(activeSessions) do
				if not session.isReadOnly then
					PlayerDataService.saveSession(player, false)
				end
			end
		end
	end)
end

function PlayerDataService.stopAutosaveLoop()
	autosaveRunning = false
end

return PlayerDataService
