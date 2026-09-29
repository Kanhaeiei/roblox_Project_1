--!strict

local Registry = {}

Registry.Materials = {
	ground_dark = Enum.Material.Ground,
	stone_moonlit = Enum.Material.Slate,
	stone_corrupted = Enum.Material.Basalt,
	neon = Enum.Material.Neon,
}

Registry.Colors = {
	shadow_black = Color3.fromRGB(18, 18, 28),
	moon_blue = Color3.fromRGB(90, 120, 180),
	mana_cyan = Color3.fromRGB(40, 220, 255),
	arise_violet = Color3.fromRGB(135, 45, 255),
	danger_crimson = Color3.fromRGB(230, 40, 65),
}

Registry.PrimitiveClasses = {
	Part = true,
	WedgePart = true,
	TrussPart = true,
}

Registry.Folders = {
	Structures = true,
	Props = true,
	LightingProps = true,
	Gameplay = true,
}

Registry.Prefabs = {}

return table.freeze(Registry)
