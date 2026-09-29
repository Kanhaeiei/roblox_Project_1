--!strict
-- NumberFormatter: Formats large currency and power numbers for UI display
-- Values stored in DataStores/services must remain raw integers.

local NumberFormatter = {}

local SUFFIXES = {
	{ threshold = 1e15, suffix = "Q" },
	{ threshold = 1e12, suffix = "T" },
	{ threshold = 1e9,  suffix = "B" },
	{ threshold = 1e6,  suffix = "M" },
	{ threshold = 1e3,  suffix = "K" },
}

function NumberFormatter.formatCompact(value: number, decimals: number?): string
	local dec = decimals or 2
	local sign = if value < 0 then "-" else ""
	local absVal = math.abs(value)

	if absVal < 1000 then
		return string.format("%s%d", sign, math.floor(absVal))
	end

	for _, entry in ipairs(SUFFIXES) do
		if absVal >= entry.threshold then
			local scaled = absVal / entry.threshold
			local formatted = string.format("%." .. dec .. "f", scaled)
			return string.format("%s%s%s", sign, formatted, entry.suffix)
		end
	end

	return string.format("%s%d", sign, math.floor(absVal))
end

function NumberFormatter.formatDelimiter(value: number): string
	local sign = if value < 0 then "-" else ""
	local absStr = tostring(math.floor(math.abs(value)))
	local formatted = absStr:reverse():gsub("(%d%d%d)", "%1,"):reverse()
	if formatted:sub(1, 1) == "," then
		formatted = formatted:sub(2)
	end
	return sign .. formatted
end

return NumberFormatter
