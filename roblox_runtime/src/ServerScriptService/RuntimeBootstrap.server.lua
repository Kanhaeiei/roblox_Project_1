--!strict
-- RuntimeBootstrap: Initializes server-authoritative services and registers World 1 gameplay actors

local ServerScriptService = game:GetService("ServerScriptService")

local RemoteService = require(ServerScriptService.Services.RemoteService)

-- Initialize remotes, rate limiters, autosave loop, and player lifecycle
RemoteService.init()

print("[ShadowArmyRuntime] Server foundation initialized successfully")
