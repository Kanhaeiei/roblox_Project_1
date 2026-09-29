--!strict
-- Remotes: Typed remote definitions and token-bucket rate limiters
-- Enforces server-side throughput caps per remote per player

local Config = require(script.Parent.Config)

local Remotes = {}

export type RateLimiter = {
	consume: (player: Player) -> (boolean, string?),
	reset: (player: Player) -> (),
}

function Remotes.createRateLimiter(ratePerSecond: number, burstCapacity: number?): RateLimiter
	local maxTokens = burstCapacity or ratePerSecond
	local fillRate = ratePerSecond
	local buckets: { [Player]: { tokens: number, lastUpdate: number } } = {}

	local limiter = {}

	function limiter.consume(player: Player): (boolean, string?)
		local now = os.clock()
		local bucket = buckets[player]
		if not bucket then
			bucket = { tokens = maxTokens - 1, lastUpdate = now }
			buckets[player] = bucket
			return true, nil
		end

		local elapsed = now - bucket.lastUpdate
		bucket.tokens = math.min(maxTokens, bucket.tokens + (elapsed * fillRate))
		bucket.lastUpdate = now

		if bucket.tokens >= 1 then
			bucket.tokens -= 1
			return true, nil
		else
			return false, "Rate limit exceeded"
		end
	end

	function limiter.reset(player: Player)
		buckets[player] = nil
	end

	return limiter
end

function Remotes.ensureRemoteFolder(): Folder
	local ReplicatedStorage = game:GetService("ReplicatedStorage")
	local folder = ReplicatedStorage:FindFirstChild("Remotes")
	if not folder then
		folder = Instance.new("Folder")
		folder.Name = "Remotes"
		folder.Parent = ReplicatedStorage
	end
	return folder :: Folder
end

function Remotes.ensureRemoteFunction(name: string): RemoteFunction
	local folder = Remotes.ensureRemoteFolder()
	local existing = folder:FindFirstChild(name)
	if existing and existing:IsA("RemoteFunction") then
		return existing
	end
	local rf = Instance.new("RemoteFunction")
	rf.Name = name
	rf.Parent = folder
	return rf
end

function Remotes.ensureRemoteEvent(name: string): RemoteEvent
	local folder = Remotes.ensureRemoteFolder()
	local existing = folder:FindFirstChild(name)
	if existing and existing:IsA("RemoteEvent") then
		return existing
	end
	local re = Instance.new("RemoteEvent")
	re.Name = name
	re.Parent = folder
	return re
end

return Remotes
