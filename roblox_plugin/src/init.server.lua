--!strict

assert(plugin, "Shadow Army Map Builder must run as a Roblox Studio plugin")

local HttpService = game:GetService("HttpService")
local NativeAdapter = require(script.NativeAdapter)

local toolbar = plugin:CreateToolbar("Shadow Army Builder")
local toggleButton = toolbar:CreateButton(
	"Shadow Army Builder",
	"Preview and apply a validated Shadow Army build manifest",
	""
)

local widgetInfo = DockWidgetPluginGuiInfo.new(
	Enum.InitialDockState.Right,
	false,
	false,
	460,
	600,
	320,
	360
)
local widget = plugin:CreateDockWidgetPluginGuiAsync("ShadowArmyMapBuilderV1", widgetInfo)
widget.Title = "Shadow Army Map Builder"

local container = Instance.new("Frame")
container.BackgroundColor3 = Color3.fromRGB(30, 32, 38)
container.BorderSizePixel = 0
container.Size = UDim2.fromScale(1, 1)
container.Parent = widget

local padding = Instance.new("UIPadding")
padding.PaddingTop = UDim.new(0, 10)
padding.PaddingBottom = UDim.new(0, 10)
padding.PaddingLeft = UDim.new(0, 10)
padding.PaddingRight = UDim.new(0, 10)
padding.Parent = container

local manifestBox = Instance.new("TextBox")
manifestBox.Name = "ManifestJson"
manifestBox.ClearTextOnFocus = false
manifestBox.MultiLine = true
manifestBox.Text = "Paste a validated build-manifest JSON here"
manifestBox.TextXAlignment = Enum.TextXAlignment.Left
manifestBox.TextYAlignment = Enum.TextYAlignment.Top
manifestBox.TextWrapped = false
manifestBox.TextSize = 14
manifestBox.Font = Enum.Font.Code
manifestBox.BackgroundColor3 = Color3.fromRGB(20, 22, 27)
manifestBox.TextColor3 = Color3.fromRGB(225, 230, 240)
manifestBox.Size = UDim2.new(1, 0, 1, -112)
manifestBox.Parent = container

local previewButton = Instance.new("TextButton")
previewButton.Name = "Preview"
previewButton.Text = "Preview"
previewButton.Size = UDim2.new(0.5, -5, 0, 36)
previewButton.Position = UDim2.new(0, 0, 1, -102)
previewButton.BackgroundColor3 = Color3.fromRGB(60, 90, 150)
previewButton.TextColor3 = Color3.new(1, 1, 1)
previewButton.Parent = container

local applyButton = Instance.new("TextButton")
applyButton.Name = "Apply"
applyButton.Text = "Apply (preview required)"
applyButton.Size = UDim2.new(0.5, -5, 0, 36)
applyButton.Position = UDim2.new(0.5, 5, 1, -102)
applyButton.BackgroundColor3 = Color3.fromRGB(75, 75, 80)
applyButton.TextColor3 = Color3.new(1, 1, 1)
applyButton.AutoButtonColor = false
applyButton.Parent = container

local status = Instance.new("TextLabel")
status.Name = "Status"
status.BackgroundTransparency = 1
status.Text = "No manifest previewed"
status.TextColor3 = Color3.fromRGB(190, 195, 205)
status.TextWrapped = true
status.TextXAlignment = Enum.TextXAlignment.Left
status.TextYAlignment = Enum.TextYAlignment.Top
status.Size = UDim2.new(1, 0, 0, 56)
status.Position = UDim2.new(0, 0, 1, -56)
status.Parent = container

local previewedText: string? = nil

local function decodeManifest(): any
	local decoded = HttpService:JSONDecode(manifestBox.Text)
	assert(type(decoded) == "table", "Manifest JSON must decode to an object")
	return decoded
end

local function showError(message: string)
	status.TextColor3 = Color3.fromRGB(255, 110, 120)
	status.Text = message
	previewedText = nil
	applyButton.BackgroundColor3 = Color3.fromRGB(75, 75, 80)
	applyButton.AutoButtonColor = false
end

local automation = Instance.new("BindableFunction")
automation.Name = "AutomationBridge"
automation.Parent = container

local function runPreview(): (boolean, any)
	local ok, result = pcall(function()
		return NativeAdapter.preview(decodeManifest())
	end)
	if not ok then
		showError("Preview blocked: " .. tostring(result))
		return false, tostring(result)
	end
	previewedText = manifestBox.Text
	applyButton.BackgroundColor3 = Color3.fromRGB(75, 145, 95)
	applyButton.AutoButtonColor = true
	status.TextColor3 = Color3.fromRGB(130, 225, 155)
	status.Text = string.format(
		"Ready: %s | %d operations | replace existing: %s",
		result.buildId,
		result.operationCount,
		tostring(result.existingBuildWillBeReplaced)
	)
	return true, result
end

local function runApply(): (boolean, any)
	if not previewedText or manifestBox.Text ~= previewedText then
		showError("Apply blocked: preview the unchanged manifest first")
		return false, "Apply blocked: preview the unchanged manifest first"
	end
	applyButton.Active = false
	local ok, result = pcall(function()
		return NativeAdapter.apply(decodeManifest())
	end)
	applyButton.Active = true
	if not ok then
		showError("Apply rolled back: " .. tostring(result))
		return false, tostring(result)
	end
	status.TextColor3 = Color3.fromRGB(130, 225, 155)
	status.Text = string.format("Applied %s (%d operations). Use Studio Undo to revert.", result.buildId, result.operationCount)
	previewedText = nil
	applyButton.BackgroundColor3 = Color3.fromRGB(75, 75, 80)
	applyButton.AutoButtonColor = false
	return true, result
end

previewButton.Activated:Connect(runPreview)

manifestBox:GetPropertyChangedSignal("Text"):Connect(function()
	if previewedText and manifestBox.Text ~= previewedText then
		status.TextColor3 = Color3.fromRGB(235, 190, 100)
		status.Text = "Manifest changed; preview again before Apply"
		previewedText = nil
		applyButton.BackgroundColor3 = Color3.fromRGB(75, 75, 80)
		applyButton.AutoButtonColor = false
	end
end)

applyButton.Activated:Connect(runApply)

automation.OnInvoke = function(action: string, param: any): any
	if action == "SetManifest" then
		manifestBox.Text = tostring(param)
		return true
	elseif action == "Preview" then
		return runPreview()
	elseif action == "Apply" then
		return runApply()
	elseif action == "GetStatus" then
		return {
			text = status.Text,
			previewedText = previewedText,
			applyButtonColor = {
				r = applyButton.BackgroundColor3.R,
				g = applyButton.BackgroundColor3.G,
				b = applyButton.BackgroundColor3.B,
			},
			applyButtonAutoColor = applyButton.AutoButtonColor,
		}
	end
	return nil
end

toggleButton.Click:Connect(function()
	widget.Enabled = not widget.Enabled
end)
