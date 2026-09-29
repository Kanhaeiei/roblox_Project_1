--!strict
-- RuntimeClient: Smallest playable vertical slice client controller and minimal HUD
-- Server-confirmed state is the single source of truth:
-- Initial snapshot -> server-confirmed Mana/upgrade level -> HUD reflection -> read-only / failure handling

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

local NumberFormatter = require(ReplicatedStorage:WaitForChild("Shared"):WaitForChild("NumberFormatter") :: ModuleScript)
local Config = require(ReplicatedStorage:WaitForChild("Shared"):WaitForChild("Config") :: ModuleScript)

local remotesFolder = ReplicatedStorage:WaitForChild("Remotes")
local rfSnapshot = remotesFolder:WaitForChild("request_snapshot") :: RemoteFunction
local rfTarget = remotesFolder:WaitForChild("request_target") :: RemoteFunction
local rfUpgrade = remotesFolder:WaitForChild("request_upgrade") :: RemoteFunction

-- Create minimal HUD
local screenGui = Instance.new("ScreenGui")
screenGui.Name = "ShadowArmyHUD"
screenGui.ResetOnSpawn = false
screenGui.Parent = playerGui

local mainFrame = Instance.new("Frame")
mainFrame.Name = "MainFrame"
mainFrame.Size = UDim2.new(0, 340, 0, 240)
mainFrame.Position = UDim2.new(0, 20, 0, 20)
mainFrame.BackgroundColor3 = Color3.fromRGB(24, 24, 32)
mainFrame.BorderSizePixel = 0
mainFrame.Parent = screenGui

local uiCorner = Instance.new("UICorner")
uiCorner.CornerRadius = UDim.new(0, 8)
uiCorner.Parent = mainFrame

local titleLabel = Instance.new("TextLabel")
titleLabel.Name = "Title"
titleLabel.Size = UDim2.new(1, -20, 0, 26)
titleLabel.Position = UDim2.new(0, 10, 0, 8)
titleLabel.BackgroundTransparency = 1
titleLabel.TextColor3 = Color3.fromRGB(240, 240, 255)
titleLabel.Text = "SHADOW ARMY: VERTICAL SLICE"
titleLabel.Font = Enum.Font.GothamBold
titleLabel.TextSize = 13
titleLabel.TextXAlignment = Enum.TextXAlignment.Left
titleLabel.Parent = mainFrame

local statusBanner = Instance.new("TextLabel")
statusBanner.Name = "StatusBanner"
statusBanner.Size = UDim2.new(1, -20, 0, 20)
statusBanner.Position = UDim2.new(0, 10, 0, 34)
statusBanner.BackgroundColor3 = Color3.fromRGB(36, 40, 50)
statusBanner.TextColor3 = Color3.fromRGB(160, 200, 255)
statusBanner.Text = "Connecting to server..."
statusBanner.Font = Enum.Font.GothamMedium
statusBanner.TextSize = 11
statusBanner.Parent = mainFrame

local bannerCorner = Instance.new("UICorner")
bannerCorner.CornerRadius = UDim.new(0, 4)
bannerCorner.Parent = statusBanner

local statsLabel = Instance.new("TextLabel")
statsLabel.Name = "Stats"
statsLabel.Size = UDim2.new(1, -20, 0, 24)
statsLabel.Position = UDim2.new(0, 10, 0, 58)
statsLabel.BackgroundTransparency = 1
statsLabel.TextColor3 = Color3.fromRGB(180, 220, 255)
statsLabel.Text = "Mana: -- | Power: -- | Level: --"
statsLabel.Font = Enum.Font.GothamMedium
statsLabel.TextSize = 13
statsLabel.TextXAlignment = Enum.TextXAlignment.Left
statsLabel.Parent = mainFrame

local attackBtn = Instance.new("TextButton")
attackBtn.Name = "AttackButton"
attackBtn.Size = UDim2.new(1, -20, 0, 36)
attackBtn.Position = UDim2.new(0, 10, 0, 88)
attackBtn.BackgroundColor3 = Color3.fromRGB(180, 40, 60)
attackBtn.TextColor3 = Color3.fromRGB(255, 255, 255)
attackBtn.Text = "⚔️ Attack Forest Goblin"
attackBtn.Font = Enum.Font.GothamBold
attackBtn.TextSize = 13
attackBtn.Parent = mainFrame

local atkCorner = Instance.new("UICorner")
atkCorner.CornerRadius = UDim.new(0, 6)
atkCorner.Parent = attackBtn

local upgradeBtn = Instance.new("TextButton")
upgradeBtn.Name = "UpgradeButton"
upgradeBtn.Size = UDim2.new(1, -20, 0, 36)
upgradeBtn.Position = UDim2.new(0, 10, 0, 130)
upgradeBtn.BackgroundColor3 = Color3.fromRGB(40, 120, 200)
upgradeBtn.TextColor3 = Color3.fromRGB(255, 255, 255)
upgradeBtn.Text = "⚡ Upgrade Attack Power"
upgradeBtn.Font = Enum.Font.GothamBold
upgradeBtn.TextSize = 13
upgradeBtn.Parent = mainFrame

local upCorner = Instance.new("UICorner")
upCorner.CornerRadius = UDim.new(0, 6)
upCorner.Parent = upgradeBtn

local feedbackLabel = Instance.new("TextLabel")
feedbackLabel.Name = "Feedback"
feedbackLabel.Size = UDim2.new(1, -20, 0, 56)
feedbackLabel.Position = UDim2.new(0, 10, 0, 174)
feedbackLabel.BackgroundTransparency = 1
feedbackLabel.TextColor3 = Color3.fromRGB(200, 200, 200)
feedbackLabel.Text = "Loading snapshot..."
feedbackLabel.Font = Enum.Font.Gotham
feedbackLabel.TextSize = 12
feedbackLabel.TextWrapped = true
feedbackLabel.Parent = mainFrame

-- Authoritative client state confirmed by server
local currentMana = 0
local currentLevel = 0
local currentPower = 100
local isReadOnlySession = false

local function setButtonsActive(active: boolean)
	attackBtn.Active = active
	attackBtn.AutoButtonColor = active
	upgradeBtn.Active = active
	upgradeBtn.AutoButtonColor = active
	if not active then
		attackBtn.BackgroundColor3 = Color3.fromRGB(80, 80, 90)
		upgradeBtn.BackgroundColor3 = Color3.fromRGB(60, 70, 80)
	else
		attackBtn.BackgroundColor3 = Color3.fromRGB(180, 40, 60)
		upgradeBtn.BackgroundColor3 = Color3.fromRGB(40, 120, 200)
	end
end

local function updateHUD()
	statsLabel.Text = string.format("Mana: %s | Power: %s | Level: %d",
		NumberFormatter.formatCompact(currentMana),
		NumberFormatter.formatCompact(currentPower),
		currentLevel
	)
	local nextCost = math.floor(100 * (1.5 ^ currentLevel))
	upgradeBtn.Text = string.format("⚡ Upgrade Power (Cost: %s)", NumberFormatter.formatCompact(nextCost))
end

local function applyReadOnlyMode(reason: string)
	isReadOnlySession = true
	setButtonsActive(false)
	statusBanner.BackgroundColor3 = Color3.fromRGB(120, 40, 40)
	statusBanner.TextColor3 = Color3.fromRGB(255, 200, 200)
	statusBanner.Text = "[READ-ONLY] " .. reason
	feedbackLabel.TextColor3 = Color3.fromRGB(255, 140, 140)
	feedbackLabel.Text = "Gameplay mutations disabled: session is read-only or in conflict."
end

-- 1. Fetch initial snapshot from server
local function fetchInitialSnapshot()
	local ok, res = pcall(function()
		return rfSnapshot:InvokeServer()
	end)

	if ok and res and res.success then
		local data = res.data
		currentMana = data.mana or 0
		currentLevel = data.level or 0
		currentPower = data.power or 100
		updateHUD()

		if data.isReadOnly then
			applyReadOnlyMode("Session conflict detected")
		else
			statusBanner.BackgroundColor3 = Color3.fromRGB(30, 80, 50)
			statusBanner.TextColor3 = Color3.fromRGB(160, 255, 180)
			statusBanner.Text = "● Connected (Server Authoritative)"
			feedbackLabel.TextColor3 = Color3.fromRGB(200, 220, 200)
			feedbackLabel.Text = "Data loaded from server. Ready to fight."
		end
	else
		setButtonsActive(false)
		statusBanner.BackgroundColor3 = Color3.fromRGB(120, 40, 40)
		statusBanner.TextColor3 = Color3.fromRGB(255, 200, 200)
		statusBanner.Text = "[LOAD FAILED] Could not load profile"
		feedbackLabel.TextColor3 = Color3.fromRGB(255, 120, 120)
		feedbackLabel.Text = "Failed to load snapshot from server: " .. tostring(res and res.error or "Unknown error")
	end
end

-- 2. Attack Enemy (Server Confirmed)
attackBtn.MouseButton1Click:Connect(function()
	if isReadOnlySession then return end

	attackBtn.Active = false
	local res = rfTarget:InvokeServer("forest_goblin")
	if not isReadOnlySession then
		attackBtn.Active = true
	end

	if res and res.success then
		local data = res.data
		-- Authoritative Mana from server response
		if data.totalMana ~= nil then
			currentMana = data.totalMana
		else
			currentMana += (data.manaAwarded or 0)
		end

		feedbackLabel.TextColor3 = Color3.fromRGB(100, 255, 100)
		if data.isDefeated then
			feedbackLabel.Text = string.format("Defeated Goblin! Dealt %d dmg. +%d Mana!", data.damageDealt, data.manaAwarded)
		else
			feedbackLabel.Text = string.format("Hit Goblin! Dealt %d dmg. (HP: %d)", data.damageDealt, data.remainingHealth)
		end
		updateHUD()
	else
		local errMsg = tostring(res and res.error or "Unknown error")
		if errMsg == "Session is read-only" then
			applyReadOnlyMode("Session transitioned to read-only")
		else
			feedbackLabel.TextColor3 = Color3.fromRGB(255, 120, 120)
			feedbackLabel.Text = "Attack failed: " .. errMsg
		end
	end
end)

-- 3. Buy Upgrade (Server Confirmed)
upgradeBtn.MouseButton1Click:Connect(function()
	if isReadOnlySession then return end

	upgradeBtn.Active = false
	local res = rfUpgrade:InvokeServer("attack_power")
	if not isReadOnlySession then
		upgradeBtn.Active = true
	end

	if res and res.success then
		-- Authoritative level and Mana from server response
		currentLevel = res.data.newLevel
		if res.data.totalMana ~= nil then
			currentMana = res.data.totalMana
		else
			currentMana = math.max(0, currentMana - res.data.costPaid)
		end
		currentPower = 100 + (currentLevel * 15)

		feedbackLabel.TextColor3 = Color3.fromRGB(120, 220, 255)
		feedbackLabel.Text = string.format("Purchased Upgrade! Attack Power Level %d!", currentLevel)
		updateHUD()
	else
		local errMsg = tostring(res and res.error or "Unknown error")
		if errMsg == "Session is read-only" then
			applyReadOnlyMode("Session transitioned to read-only")
		else
			feedbackLabel.TextColor3 = Color3.fromRGB(255, 120, 120)
			feedbackLabel.Text = "Upgrade failed: " .. errMsg
		end
	end
end)

-- Initial load
fetchInitialSnapshot()
print("[ShadowArmyRuntime] Server-authoritative RuntimeClient initialized")
