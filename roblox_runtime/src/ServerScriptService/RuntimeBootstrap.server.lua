--!strict
-- RuntimeBootstrap: Initializes server-authoritative services and registers World 1 gameplay actors

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")

local CombatService = require(ServerScriptService.Services.CombatService)
local RemoteService = require(ServerScriptService.Services.RemoteService)

-- Register World 1 enemies aligned to layout zones
CombatService.registerEnemy({
	id = "forest_goblin_1",
	name = "Forest Goblin",
	maxHealth = 100,
	health = 100,
	position = Vector3.new(0, 5, 20),
	rewardMana = 25,
	isBoss = false,
	isMiniBoss = false,
})

CombatService.registerEnemy({
	id = "wolf_alpha_miniboss",
	name = "Alpha Shadow Wolf",
	maxHealth = 1000,
	health = 1000,
	position = Vector3.new(0, 5, 50),
	rewardMana = 500,
	isBoss = false,
	isMiniBoss = true,
})

CombatService.registerEnemy({
	id = "shadow_monarch_boss",
	name = "Shadow Monarch",
	maxHealth = 5000,
	health = 5000,
	position = Vector3.new(0, 5, 75),
	rewardMana = 2500,
	isBoss = true,
	isMiniBoss = false,
})

-- Initialize remotes, rate limiters, and player lifecycle
RemoteService.init()

print("[ShadowArmyRuntime] Server foundation initialized successfully")
