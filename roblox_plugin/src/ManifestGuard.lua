--!strict

local Registry = require(script.Parent.Registry)

local ManifestGuard = {}

local ALLOWED_ACTIONS = {
	ensure_folder = true,
	terrain_fill = true,
	terrain_subtract = true,
	create_primitive = true,
	create_prefab = true,
	configure_lighting = true,
	create_local_light = true,
	bind_gameplay_marker = true,
}

local FORBIDDEN_KEYS = {
	source = true,
	scriptsource = true,
	code = true,
	luau = true,
	assetid = true,
	meshid = true,
	soundid = true,
}

local TERRAIN_SHAPES = { block = true, ball = true, cylinder = true, wedge = true }
local LIGHT_TYPES = { point = true, spot = true, surface = true }

local function scanForbidden(value: any, path: string)
	if type(value) ~= "table" then
		return
	end
	for key, child in pairs(value) do
		local keyString = tostring(key)
		if FORBIDDEN_KEYS[string.lower(keyString)] then
			error(string.format("Forbidden manifest key at %s.%s", path, keyString))
		end
		scanForbidden(child, path .. "." .. keyString)
	end
end

function ManifestGuard.validate(manifest: any): ()
	assert(type(manifest) == "table", "Manifest must be a table")
	assert(manifest.manifestVersion == "1.0.0", "Unsupported manifestVersion")
	assert(type(manifest.buildId) == "string" and string.match(manifest.buildId, "^[a-z0-9][a-z0-9._%-]+$"), "Invalid buildId")
	local namespace = "Workspace.Generated." .. manifest.buildId
	assert(manifest.namespace == namespace, "Manifest namespace must exactly match the build ID")
	assert(type(manifest.operations) == "table" and #manifest.operations > 0, "Manifest requires operations")

	local operationIds = {}
	for index, operation in ipairs(manifest.operations) do
		assert(operation.sequence == index, "Operation sequence must be contiguous")
		assert(type(operation.operationId) == "string" and not operationIds[operation.operationId], "Duplicate operation ID")
		operationIds[operation.operationId] = true
		assert(ALLOWED_ACTIONS[operation.action], "Operation action is not allowlisted")
		assert(type(operation.payload) == "table", "Operation payload must be a table")
		scanForbidden(operation.payload, operation.operationId)
		if operation.action == "terrain_fill" or operation.action == "terrain_subtract" then
			assert(operation.target == "Workspace.Terrain", "Terrain operation target is invalid")
		elseif operation.action == "configure_lighting" then
			assert(operation.target == "Lighting", "Lighting target is invalid")
		else
			assert(string.sub(operation.target, 1, #namespace + 1) == namespace .. ".", "Target escapes generated namespace")
		end

		if operation.action == "ensure_folder" then
			assert(Registry.Folders[operation.payload.folderName], "Folder is not allowlisted")
			assert(operation.target == namespace .. "." .. operation.payload.folderName, "Folder target does not match folderName")
		elseif operation.action == "create_primitive" then
			assert(Registry.PrimitiveClasses[operation.payload.className], "Primitive class is not allowlisted")
			assert(Registry.Folders[operation.payload.parentCategory], "Primitive parent is not allowlisted")
			assert(Registry.Materials[operation.payload.materialToken], "Material token is not registered")
			assert(Registry.Colors[operation.payload.colorToken], "Color token is not registered")
			assert(string.sub(operation.target, 1, #(namespace .. "." .. operation.payload.parentCategory .. ".")) == namespace .. "." .. operation.payload.parentCategory .. ".", "Primitive target does not match parentCategory")
		elseif operation.action == "create_prefab" then
			assert(Registry.Prefabs[operation.payload.prefabKey], "Prefab key is not registered")
			assert(Registry.Folders[operation.payload.parentCategory], "Prefab parent is not allowlisted")
			assert(string.sub(operation.target, 1, #(namespace .. "." .. operation.payload.parentCategory .. ".")) == namespace .. "." .. operation.payload.parentCategory .. ".", "Prefab target does not match parentCategory")
		elseif operation.action == "terrain_fill" or operation.action == "terrain_subtract" then
			assert(operation.payload.buildNamespace == namespace, "Terrain namespace mismatch")
			assert(TERRAIN_SHAPES[operation.payload.shape], "Terrain shape is not allowlisted")
			assert(Registry.Materials[operation.payload.materialToken], "Terrain material is not registered")
		elseif operation.action == "create_local_light" then
			assert(LIGHT_TYPES[operation.payload.type], "Light type is not allowlisted")
			assert(Registry.Colors[operation.payload.colorToken], "Light color is not registered")
			assert(string.match(operation.target, "([^.]+)$") == operation.payload.socketInstanceId, "Light target does not match socket")
		elseif operation.action == "bind_gameplay_marker" then
			assert(operation.target == namespace .. ".Gameplay", "Marker binding target must be Gameplay")
		end
	end
end

return table.freeze(ManifestGuard)
