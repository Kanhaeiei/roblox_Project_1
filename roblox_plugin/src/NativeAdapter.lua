--!strict

local ChangeHistoryService = game:GetService("ChangeHistoryService")
local CollectionService = game:GetService("CollectionService")
local Lighting = game:GetService("Lighting")
local ServerStorage = game:GetService("ServerStorage")
local Workspace = game:GetService("Workspace")

local ManifestGuard = require(script.Parent.ManifestGuard)
local Registry = require(script.Parent.Registry)
local Snapshots = require(script.Parent.Snapshots)

local NativeAdapter = {}

NativeAdapter.SupportedActions = table.freeze({
	ensure_folder = true,
	terrain_fill = true,
	terrain_subtract = true,
	create_primitive = true,
	create_prefab = true,
	configure_lighting = true,
	create_local_light = true,
	bind_gameplay_marker = true,
})

local GENERATED_TAG = "ShadowArmyGenerated"

local function vector3(values: { number }): Vector3
	return Vector3.new(values[1], values[2], values[3])
end

local function color3(values: { number }): Color3
	return Color3.fromRGB(values[1], values[2], values[3])
end

local function transform(value: any): CFrame
	local position = vector3(value.position)
	local rotation = value.orientationDegrees
	return CFrame.new(position)
		* CFrame.fromOrientation(math.rad(rotation[1]), math.rad(rotation[2]), math.rad(rotation[3]))
end

local function tagGenerated(instance: Instance, buildId: string, operationId: string)
	instance:SetAttribute("GeneratedBuildId", buildId)
	instance:SetAttribute("GeneratedOperationId", operationId)
	CollectionService:AddTag(instance, GENERATED_TAG)
end

local function chooseLightingProfile(profiles: { any }): any
	for _, profile in ipairs(profiles) do
		if profile.tier == "high" then
			return profile
		end
	end
	return profiles[1]
end

local function applyLighting(payload: any, buildId: string)
	local profile = chooseLightingProfile(payload.profiles)
	assert(profile, "Lighting profile is required")
	Lighting.ClockTime = profile.clockTime
	Lighting.Brightness = profile.brightness
	Lighting.Ambient = color3(profile.ambient)
	Lighting.OutdoorAmbient = color3(profile.outdoorAmbient)

	local oldEffects = Lighting:FindFirstChild("ShadowArmyGeneratedEffects")
	if oldEffects then
		oldEffects:Destroy()
	end
	local effects = Instance.new("Folder")
	effects.Name = "ShadowArmyGeneratedEffects"
	tagGenerated(effects, buildId, "lighting_global_profiles")

	local atmosphere = Instance.new("Atmosphere")
	atmosphere.Name = "Atmosphere"
	atmosphere.Density = profile.atmosphereDensity
	atmosphere.Parent = effects

	local bloom = Instance.new("BloomEffect")
	bloom.Name = "Bloom"
	bloom.Intensity = profile.bloomIntensity
	bloom.Parent = effects

	local correction = Instance.new("ColorCorrectionEffect")
	correction.Name = "ColorCorrection"
	correction.Contrast = profile.contrast
	correction.Saturation = profile.saturation
	correction.Parent = effects
	effects.Parent = Lighting
end

local function applyTerrain(operation: any)
	local payload = operation.payload
	local material = if operation.action == "terrain_subtract" then Enum.Material.Air else Registry.Materials[payload.materialToken]
	assert(material, "Terrain material token is not registered")
	local cframe = transform(payload.transform)
	local size = vector3(payload.size)
	if payload.shape == "block" then
		Workspace.Terrain:FillBlock(cframe, size, material)
	elseif payload.shape == "ball" then
		Workspace.Terrain:FillBall(cframe.Position, math.max(size.X, size.Y, size.Z) / 2, material)
	elseif payload.shape == "cylinder" then
		Workspace.Terrain:FillCylinder(cframe, size.Y, math.max(size.X, size.Z) / 2, material)
	elseif payload.shape == "wedge" then
		Workspace.Terrain:FillWedge(cframe, size, material)
	else
		error("Unsupported terrain shape")
	end
end

local function createPrimitive(operation: any, root: Folder, instancesById: { [string]: Instance }, buildId: string)
	local payload = operation.payload
	local parent = root:FindFirstChild(payload.parentCategory)
	assert(parent and parent:IsA("Folder"), "Primitive parent folder does not exist")
	local instance = Instance.new(payload.className) :: BasePart
	instance.Name = string.match(operation.target, "([^.]+)$") or operation.operationId
	instance.Size = vector3(payload.size)
	instance.CFrame = transform(payload.transform)
	instance.Material = Registry.Materials[payload.materialToken]
	instance.Color = Registry.Colors[payload.colorToken]
	instance.Anchored = payload.anchored
	instance.CanCollide = payload.canCollide
	instance.CanTouch = payload.canTouch
	instance.CanQuery = payload.canQuery
	instance.CastShadow = payload.castShadow
	tagGenerated(instance, buildId, operation.operationId)
	for _, tag in ipairs(payload.tags) do
		CollectionService:AddTag(instance, "ShadowArmy_" .. tag)
	end
	instance.Parent = parent
	instancesById[instance.Name] = instance
end

local function createPrefab(operation: any, root: Folder, instancesById: { [string]: Instance }, buildId: string)
	local payload = operation.payload
	local registryName = Registry.Prefabs[payload.prefabKey]
	assert(registryName, "Prefab key is not registered")
	local prefabFolder = ServerStorage:FindFirstChild("ShadowArmyPrefabs")
	assert(prefabFolder, "ServerStorage.ShadowArmyPrefabs is missing")
	local source = prefabFolder:FindFirstChild(registryName)
	assert(source, "Registered prefab source is missing")
	local parent = root:FindFirstChild(payload.parentCategory)
	assert(parent, "Prefab parent folder does not exist")
	local instance = source:Clone()
	instance.Name = string.match(operation.target, "([^.]+)$") or operation.operationId
	tagGenerated(instance, buildId, operation.operationId)
	instance.Parent = parent
	instancesById[instance.Name] = instance
end

local function createLocalLight(operation: any, instancesById: { [string]: Instance }, buildId: string)
	local payload = operation.payload
	local socket = instancesById[payload.socketInstanceId]
	assert(socket, "Local-light socket was not created")
	local className = ({ point = "PointLight", spot = "SpotLight", surface = "SurfaceLight" })[payload.type]
	assert(className, "Local-light type is not allowlisted")
	local light = Instance.new(className) :: Light
	light.Name = operation.operationId
	light.Color = Registry.Colors[payload.colorToken]
	light.Range = payload.range
	light.Brightness = payload.brightness
	light.Shadows = payload.castsShadows
	tagGenerated(light, buildId, operation.operationId)
	light.Parent = socket
end

local function bindMarker(operation: any, instancesById: { [string]: Instance })
	local payload = operation.payload
	local host = instancesById[payload.instanceId]
	assert(host, "Gameplay marker host was not created")
	host:SetAttribute("GameplayMarkerId", payload.markerId)
	CollectionService:AddTag(host, "ShadowArmyGameplayMarker")
end

local function buildStagingRoot(manifest: any): (Folder, { [string]: Instance }, { any })
	local root = Instance.new("Folder")
	root.Name = manifest.buildId
	tagGenerated(root, manifest.buildId, "build_root")
	local instancesById = {}
	local deferred = {}

	for _, operation in ipairs(manifest.operations) do
		if operation.action == "ensure_folder" then
			local folder = Instance.new("Folder")
			folder.Name = operation.payload.folderName
			tagGenerated(folder, manifest.buildId, operation.operationId)
			folder.Parent = root
		elseif operation.action == "create_primitive" then
			createPrimitive(operation, root, instancesById, manifest.buildId)
		elseif operation.action == "create_prefab" then
			createPrefab(operation, root, instancesById, manifest.buildId)
		else
			table.insert(deferred, operation)
		end
	end

	for _, operation in ipairs(deferred) do
		if operation.action == "create_local_light" then
			createLocalLight(operation, instancesById, manifest.buildId)
		elseif operation.action == "bind_gameplay_marker" then
			bindMarker(operation, instancesById)
		end
	end
	return root, instancesById, deferred
end

function NativeAdapter.preview(manifest: any): any
	ManifestGuard.validate(manifest)
	local generated = Workspace:FindFirstChild("Generated")
	local existing = if generated then generated:FindFirstChild(manifest.buildId) else nil
	return {
		buildId = manifest.buildId,
		operationCount = #manifest.operations,
		existingBuildWillBeReplaced = existing ~= nil,
		terrainSnapshotRequired = true,
		lightingSnapshotRequired = true,
	}
end

function NativeAdapter.apply(manifest: any): any
	local preview = NativeAdapter.preview(manifest)
	local stagingRoot, _, deferred = buildStagingRoot(manifest)
	local terrainSnapshots = Snapshots.captureTerrain(manifest.operations)
	local lightingSnapshot = Snapshots.captureLighting()
	local recording = nil
	if not ChangeHistoryService:IsRecordingInProgress() then
		recording = ChangeHistoryService:TryBeginRecording(
			"ShadowArmyApply_" .. manifest.buildId,
			"Apply Shadow Army build " .. manifest.buildId
		)
		assert(recording, "Could not begin Studio change-history recording")
	end
	local generated = Workspace:FindFirstChild("Generated")
	local createdGenerated = false
	assert(not generated or generated:IsA("Folder"), "Workspace.Generated exists but is not a Folder")
	if not generated then
		generated = Instance.new("Folder")
		generated.Name = "Generated"
		generated.Parent = Workspace
		createdGenerated = true
	end
	local oldRoot = generated:FindFirstChild(manifest.buildId)

	local ok, failure = xpcall(function()
		if oldRoot then
			oldRoot.Name = manifest.buildId .. "__rollback"
			oldRoot.Parent = nil
		end
		stagingRoot.Parent = generated
		for _, operation in ipairs(deferred) do
			if operation.action == "terrain_fill" or operation.action == "terrain_subtract" then
				applyTerrain(operation)
			elseif operation.action == "configure_lighting" then
				applyLighting(operation.payload, manifest.buildId)
			end
		end
		if oldRoot then
			oldRoot:Destroy()
		end
	end, debug.traceback)

	if not ok then
		Snapshots.restoreTerrain(terrainSnapshots)
		Snapshots.restoreLighting(lightingSnapshot)
		stagingRoot:Destroy()
		if oldRoot and oldRoot.Parent == nil then
			oldRoot.Name = manifest.buildId
			oldRoot.Parent = generated
		end
		if createdGenerated and #generated:GetChildren() == 0 then
			generated:Destroy()
		end
		if recording then
			ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Cancel)
		end
		error(failure)
	end

	if recording then
		ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
	end
	if lightingSnapshot.generatedEffects then
		lightingSnapshot.generatedEffects:Destroy()
	end
	return {
		status = "APPLIED",
		buildId = manifest.buildId,
		operationCount = preview.operationCount,
		undoManagedByStudio = true,
	}
end

return table.freeze(NativeAdapter)
