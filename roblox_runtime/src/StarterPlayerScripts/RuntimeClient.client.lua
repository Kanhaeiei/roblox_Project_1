--!strict
-- RuntimeClient: Smallest playable vertical slice client controller and minimal HUD
-- Implements the core loop: spawn -> attack enemy -> gain mana -> buy upgrade -> display on HUD

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

local NumberFormatter = require(ReplicatedStorage:WaitForChild("Shared"):WaitForChild("NumberFormatter") :: ModuleScript)
local Config = require(ReplicatedStorage:WaitForChild("Shared"):WaitForChild("Config") :: ModuleScript)

local remotesFolder = ReplicatedStorage:WaitForChild("Remotes")
local rfTarget = remotesFolder:WaitForChild("request_target") :: RemoteFunction
local rfUpgrade = remotesFolder:WaitForChild("request_upgrade") :: RemoteFunction

-- Create minimal HUD
local screenGui = Instance.new("ScreenGui")
screenGui.Name = "ShadowArmyHUD"
screenGui.ResetOnSpawn = false
screenGui.Parent = playerGui

local mainFrame = Instance.new("Frame")
mainFrame.Name = "MainFrame"
mainFrame.Size = UDim2.new(0, 320, 0, 220)
mainFrame.Position = UDim2.new(0, 20, 0, 20)
mainFrame.BackgroundColor3 = Color3.fromRGB(24, 24, 32)
mainFrame.BorderSizePixel = 0
mainFrame.Parent = screenGui

local uiCorner = Instance.new("UICorner")
uiCorner.CornerRadius = UDim.new(0, 8)
uiCorner.Parent = mainFrame

local titleLabel = Instance.new("TextLabel")
titleLabel.Name = "Title"
titleLabel.Size = UDim2.new(1, -20, 0, 30)
titleLabel.Position = UDim2.new(0, 10, 0, 8)
titleLabel.BackgroundTransparency = 1
titleLabel.TextColor3 = Color3.fromRGB(240, 240, 255)
titleLabel.Text = "SHADOW ARMY: VERTICAL SLICE"
titleLabel.Font = Enum.Font.GothamBold
titleLabel.TextSize = 14
titleLabel.TextXAlignment = Enum.TextXAlignment.Left
titleLabel.Parent = mainFrame

local statsLabel = Instance.new("TextLabel")
statsLabel.Name = "Stats"
statsLabel.Size = UDim2.new(1, -20, 0, 24)
statsLabel.Position = UDim2.new(0, 10, 0, 42)
statsLabel.BackgroundTransparency = 1
statsLabel.TextColor3 = Color3.fromRGB(180, 220, 255)
statsLabel.Text = "Mana: 0 | Power: 100 | Level: 0"
statsLabel.Font = Enum.Font.GothamMedium
statsLabel.TextSize = 13
statsLabel.TextXAlignment = Enum.TextXAlignment.Left
statsLabel.Parent = mainFrame

local attackBtn = Instance.new("TextButton")
attackBtn.Name = "AttackButton"
attackBtn.Size = UDim2.new(1, -20, 0, 38)
attackBtn.Position = UDim2.new(0, 10, 0, 75)
attackBtn.BackgroundColor3 = Color3.fromRGB(180, 40, 60)
attackBtn.TextColor3 = Color3.fromRGB(255, 255, 255)
attackBtn.Text = "⚔️ Attack Forest Goblin"
attackBtn.Font = Enum.Font.GothamBold
attackBtn.TextSize = 14
attackBtn.Parent = mainFrame

local atkCorner = Instance.new("UICorner")
atkCorner.CornerRadius = UDim.new(0, 6)
atkCorner.Parent = attackBtn

local upgradeBtn = Instance.new("TextButton")
upgradeBtn.Name = "UpgradeButton"
upgradeBtn.Size = UDim2.new(1, -20, 0, 38)
upgradeBtn.Position = UDim2.new(0, 10, 0, 120)
upgradeBtn.BackgroundColor3 = Color3.fromRGB(40, 120, 200)
upgradeBtn.TextColor3 = Color3.fromRGB(255, 255, 255)
upgradeBtn.Text = "⚡ Upgrade Attack Power (Cost: 100)"
upgradeBtn.Font = Enum.Font.GothamBold
upgradeBtn.TextSize = 13
upgradeBtn.Parent = mainFrame

local upCorner = Instance.new("UICorner")
upCorner.CornerRadius = UDim.new(0, 6)
upCorner.Parent = upgradeBtn

local feedbackLabel = Instance.new("TextLabel")
feedbackLabel.Name = "Feedback"
feedbackLabel.Size = UDim2.new(1, -20, 0, 45)
feedbackLabel.Position = UDim2.new(0, 10, 0, 165)
feedbackLabel.BackgroundTransparency = 1
feedbackLabel.TextColor3 = Color3.fromRGB(200, 200, 200)
feedbackLabel.Text = "Ready to fight."
feedbackLabel.Font = Enum.Font.Gotham
feedbackLabel.TextSize = 12
feedbackLabel.TextWrapped = true
feedbackLabel.Parent = mainFrame

local currentMana = 0
local currentLevel = 0
local basePower = 100

local function updateHUD()
	local power = basePower + (currentLevel * 15)
	statsLabel.Text = string.format("Mana: %s | Power: %s | Level: %d",
		NumberFormatter.formatCompact(currentMana),
		NumberFormatter.formatCompact(power),
		currentLevel
	)
	local nextCost = math.floor(100 * (1.5 ^ currentLevel))
	upgradeBtn.Text = string.format("⚡ Upgrade Attack Power (Cost: %s)", NumberFormatter.formatCompact(nextCost))
end

-- Core Loop 1: Attack Enemy
attackBtn.MouseButton1Click:Connect(function()
	attackBtn.Active = false
	local res = rfTarget:InvokeServer("forest_goblin")
	attackBtn.Active = true

	if res and res.success then
		local data = res.data
		currentMana += (data.manaAwarded or 0)
		feedbackLabel.TextColor3 = Color3.fromRGB(100, 255, 100)
		if data.isDefeated then
			feedbackLabel.Text = string.format("Defeated Goblin! Dealt %d dmg. +%d Mana!", data.damageDealt, data.manaAwarded)
		else
			feedbackLabel.Text = string.format("Hit Goblin! Dealt %d dmg. (HP: %d)", data.damageDealt, data.remainingHealth)
		end
		updateHUD()
	else
		feedbackLabel.TextColor3 = Color3.fromRGB(255, 120, 120)
		feedbackLabel.Text = "Attack failed: " .. tostring(res and res.error or "Unknown error")
	end
end)

-- Core Loop 2: Buy Upgrade
upgradeBtn.MouseButton1Click:Connect(function()
	upgradeBtn.Active = false
	local res = rfUpgrade:InvokeServer("attack_power")
	upgradeBtn.Active = true

	if res and res.success then
		currentLevel = res.data.newLevel
		currentMana = math.max(0, currentMana - res.data.costPaid)
		feedbackLabel.TextColor3 = Color3.fromRGB(120, 220, 255)
		feedbackLabel.Text = string.format("Purchased Upgrade! Attack Power Level %d!", currentLevel)
		updateHUD()
	else
		feedbackLabel.TextColor3 = Color3.fromRGB(255, 120, 120)
		feedbackLabel.Text = "Upgrade failed: " .. tostring(res and res.error or "Unknown error")
	end
end)

updateHUD()
print("[ShadowArmyRuntime] Phase 6 Playable Vertical Slice HUD initialized")
