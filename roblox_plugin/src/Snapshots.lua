--!strict

local Lighting = game:GetService("Lighting")
local Terrain = workspace.Terrain

local Snapshots = {}

export type TerrainSnapshot = {
	region: Region3,
	materials: any,
	occupancy: any,
}

export type LightingSnapshot = {
	clockTime: number,
	brightness: number,
	ambient: Color3,
	outdoorAmbient: Color3,
	generatedEffects: Instance?,
}

local function vector3(values: { number }): Vector3
	return Vector3.new(values[1], values[2], values[3])
end

function Snapshots.captureTerrain(operations: { any }): { TerrainSnapshot }
	local snapshots = {}
	local seen = {}
	for _, operation in ipairs(operations) do
		if operation.action == "terrain_fill" or operation.action == "terrain_subtract" then
			local scope = operation.payload.scope
			local key = table.concat(scope.min, ",") .. ":" .. table.concat(scope.max, ",")
			if not seen[key] then
				seen[key] = true
				local region = Region3.new(vector3(scope.min), vector3(scope.max)):ExpandToGrid(4)
				local materials, occupancy = Terrain:ReadVoxels(region, 4)
				table.insert(snapshots, { region = region, materials = materials, occupancy = occupancy })
			end
		end
	end
	return snapshots
end

function Snapshots.restoreTerrain(snapshots: { TerrainSnapshot })
	for _, snapshot in ipairs(snapshots) do
		Terrain:WriteVoxels(snapshot.region, 4, snapshot.materials, snapshot.occupancy)
	end
end

function Snapshots.captureLighting(): LightingSnapshot
	local effects = Lighting:FindFirstChild("ShadowArmyGeneratedEffects")
	return {
		clockTime = Lighting.ClockTime,
		brightness = Lighting.Brightness,
		ambient = Lighting.Ambient,
		outdoorAmbient = Lighting.OutdoorAmbient,
		generatedEffects = if effects then effects:Clone() else nil,
	}
end

function Snapshots.restoreLighting(snapshot: LightingSnapshot)
	Lighting.ClockTime = snapshot.clockTime
	Lighting.Brightness = snapshot.brightness
	Lighting.Ambient = snapshot.ambient
	Lighting.OutdoorAmbient = snapshot.outdoorAmbient
	local current = Lighting:FindFirstChild("ShadowArmyGeneratedEffects")
	if current then
		current:Destroy()
	end
	if snapshot.generatedEffects then
		snapshot.generatedEffects.Parent = Lighting
	end
end

return table.freeze(Snapshots)
