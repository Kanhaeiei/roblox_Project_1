--!strict
-- PlayerDataService: Server-authoritative player data persistence, session locking, and migrations
-- Includes idempotent developer-product receipt handling

local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)

local PlayerDataService = {}

local DATA_STORE_NAME = "ShadowArmy_PlayerData_v1"
local LEASE_DURATION = 30 -- seconds
local MAX_SAVE_RETRIES = 3

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
		Shadows: { { id: string, name: string, power: number, rarity: string } },
	},
	Pity: { [string]: number },
	Entitlements: { [string]: boolean },
	Settings: {
		ReducedMotion: boolean,
	},
	PurchaseHistory: { [string]: number },
}

export type SessionRecord = {
	sessionLock: string?,
	leaseTimestamp: number,
	data: PlayerProfile,
}

-- Active runtime session cache per player
local activeSessions: { [Player]: { data: PlayerProfile, isReadOnly: boolean, isDirty: boolean } } = {}

-- In-memory mock store for test environments or when DataStores are unavailable
local mockStore: { [string]: SessionRecord } = {}
local useMockStore = false

function PlayerDataService.setMockMode(enabled: boolean)
	useMockStore = enabled
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
local MIGRATIONS: { [number]: (data: any) -> () } = {
	-- Future schema migrations go here in ascending order
}

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

local function getDataStore()
	if useMockStore then
		return nil
	end
	local success, store = pcall(function()
		return DataStoreService:GetDataStore(DATA_STORE_NAME)
	end)
	if success and store then
		return store
	end
	return nil
end

function PlayerDataService.loadSession(player: Player): (PlayerProfile, boolean)
	local key = "Player_" .. tostring(player.UserId)
	local store = getDataStore()
	local now = os.time()
	local currentJobId = game.JobId ~= "" and game.JobId or "StandaloneJob"

	local record: SessionRecord? = nil

	if not store then
		-- Use mock store
		local existing = mockStore[key]
		if existing then
			if existing.sessionLock and existing.sessionLock ~= currentJobId and (now - existing.leaseTimestamp) < LEASE_DURATION then
				-- Conflict on mock store
				activeSessions[player] = { data = existing.data, isReadOnly = true, isDirty = false }
				return existing.data, true
			end
			existing.sessionLock = currentJobId
			existing.leaseTimestamp = now
			record = existing
		else
			record = {
				sessionLock = currentJobId,
				leaseTimestamp = now,
				data = PlayerDataService.getDefaultProfile(),
			}
			mockStore[key] = record
		end
	else
		-- DataStore with retry
		local success, result = pcall(function()
			return store:UpdateAsync(key, function(prevRecord: SessionRecord?)
				if prevRecord and prevRecord.sessionLock and prevRecord.sessionLock ~= currentJobId then
					if (now - prevRecord.leaseTimestamp) < LEASE_DURATION then
						-- Active lease held by another server; do not overwrite
						return prevRecord
					end
				end

				local data = if prevRecord and prevRecord.data then PlayerDataService.migrate(prevRecord.data) else PlayerDataService.getDefaultProfile()
				return {
					sessionLock = currentJobId,
					leaseTimestamp = now,
					data = data,
				}
			end)
		end)

		if success and result then
			record = result
		else
			warn("[PlayerDataService] Failed to load data for", player.UserId, "falling back to read-only defaults")
			local fallback = PlayerDataService.getDefaultProfile()
			activeSessions[player] = { data = fallback, isReadOnly = true, isDirty = false }
			return fallback, true
		end
	end

	local isReadOnly = false
	if record and record.sessionLock ~= currentJobId and (now - record.leaseTimestamp) < LEASE_DURATION then
		isReadOnly = true
	end

	local profile = record and record.data or PlayerDataService.getDefaultProfile()
	activeSessions[player] = { data = profile, isReadOnly = isReadOnly, isDirty = false }
	return profile, isReadOnly
end

function PlayerDataService.saveSession(player: Player, releaseLease: boolean): boolean
	local session = activeSessions[player]
	if not session or session.isReadOnly then
		return false
	end

	local key = "Player_" .. tostring(player.UserId)
	local store = getDataStore()
	local now = os.time()
	local currentJobId = game.JobId ~= "" and game.JobId or "StandaloneJob"

	if not store then
		mockStore[key] = {
			sessionLock = if releaseLease then nil else currentJobId,
			leaseTimestamp = if releaseLease then 0 else now,
			data = session.data,
		}
		session.isDirty = false
		return true
	end

	local retries = 0
	while retries < MAX_SAVE_RETRIES do
		retries += 1
		local success, err = pcall(function()
			store:UpdateAsync(key, function(prevRecord: SessionRecord?)
				return {
					sessionLock = if releaseLease then nil else currentJobId,
					leaseTimestamp = if releaseLease then 0 else now,
					data = session.data,
				}
			end)
		end)
		if success then
			session.isDirty = false
			return true
		end
		task.wait(1 * retries)
	end

	warn("[PlayerDataService] Failed to save session for", player.UserId, "after", MAX_SAVE_RETRIES, "attempts")
	return false
end

function PlayerDataService.getProfile(player: Player): PlayerProfile?
	local session = activeSessions[player]
	return session and session.data or nil
end

function PlayerDataService.isReadOnly(player: Player): boolean
	local session = activeSessions[player]
	return session and session.isReadOnly or false
end

function PlayerDataService.getCurrency(player: Player, currencyId: string): number
	local profile = PlayerDataService.getProfile(player)
	if not profile then return 0 end
	return (profile.Currencies :: any)[currencyId] or 0
end

function PlayerDataService.addCurrency(player: Player, currencyId: string, amount: number): (boolean, string?)
	if amount <= 0 then
		return false, "Amount must be positive"
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

	local newAmount = math.min(current + math.floor(amount), cap)
	newAmount = math.min(newAmount, Config.SafeIntegerCeiling)
	curMap[currencyId] = newAmount
	session.isDirty = true
	return true, nil
end

function PlayerDataService.deductCurrency(player: Player, currencyId: string, amount: number): (boolean, string?)
	if amount <= 0 then
		return false, "Amount must be positive"
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
	local floorAmt = math.floor(amount)
	if current < floorAmt then
		return false, "Insufficient balance"
	end

	curMap[currencyId] = current - floorAmt
	session.isDirty = true
	return true, nil
end

-- Idempotent Developer-Product Receipt Processing
function PlayerDataService.processReceipt(receiptInfo: {
	PurchaseId: string,
	PlayerId: number,
	ProductId: number,
	CurrencySpent: number?,
}): Enum.ProductPurchaseDecision
	local player = Players:GetPlayerByUserId(receiptInfo.PlayerId)
	if not player then
		-- Player not currently in server; retry later
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	local session = activeSessions[player]
	if not session or session.isReadOnly then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	-- Idempotency check
	if session.data.PurchaseHistory[receiptInfo.PurchaseId] then
		return Enum.ProductPurchaseDecision.PurchaseGranted
	end

	-- Authoritative product grant mapping
	-- Product 1001: 500 SoulShards
	-- Product 1002: 10,000 Mana
	if receiptInfo.ProductId == 1001 then
		PlayerDataService.addCurrency(player, "SoulShards", 500)
	elseif receiptInfo.ProductId == 1002 then
		PlayerDataService.addCurrency(player, "Mana", 10000)
	end

	session.data.PurchaseHistory[receiptInfo.PurchaseId] = os.time()
	session.isDirty = true

	local saved = PlayerDataService.saveSession(player, false)
	if saved then
		return Enum.ProductPurchaseDecision.PurchaseGranted
	else
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
end

function PlayerDataService.closeSession(player: Player)
	PlayerDataService.saveSession(player, true)
	activeSessions[player] = nil
end

return PlayerDataService
