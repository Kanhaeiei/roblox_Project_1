--!strict
-- AnalyticsRegistry: Whitelist and validation for game analytics events
-- Ensures data integrity before emitting telemetry to external or internal sinks

local Config = require(script.Parent.Config)

local AnalyticsRegistry = {}

AnalyticsRegistry.APPROVED_EVENTS = {
	ftue_spawned = true,
	ftue_first_kill = true,
	ftue_first_upgrade = true,
	ftue_miniboss_clear = true,
	ftue_first_arise = true,
	ftue_first_rebirth = true,
}

export type AnalyticsPayload = {
	eventName: string,
	userId: number,
	timestamp: number,
	worldId: string,
	elapsedSeconds: number?,
	metadata: { [string]: any }?,
}

function AnalyticsRegistry.isValidEvent(eventName: string): boolean
	return AnalyticsRegistry.APPROVED_EVENTS[eventName] == true or (Config.AnalyticsEvents and Config.AnalyticsEvents[eventName] == true)
end

function AnalyticsRegistry.validateEvent(payload: any): (boolean, string?)
	if type(payload) ~= "table" then
		return false, "Payload must be a table"
	end

	if type(payload.eventName) ~= "string" or not AnalyticsRegistry.isValidEvent(payload.eventName) then
		return false, "Invalid or non-allowlisted eventName: " .. tostring(payload.eventName)
	end

	if type(payload.userId) ~= "number" or payload.userId <= 0 then
		return false, "Invalid userId"
	end

	if type(payload.timestamp) ~= "number" or payload.timestamp <= 0 then
		return false, "Invalid timestamp"
	end

	if type(payload.worldId) ~= "string" or payload.worldId == "" then
		return false, "Invalid worldId"
	end

	return true, nil
end

function AnalyticsRegistry.logEvent(payload: AnalyticsPayload): (boolean, string?)
	local valid, err = AnalyticsRegistry.validateEvent(payload)
	if not valid then
		warn("[AnalyticsRegistry] Rejected invalid event:", err)
		return false, err
	end

	-- In live production, forward to AnalyticsService or external sink
	return true, nil
end

return AnalyticsRegistry
