# Studio Bridge Dry Run

The current bridge is intentionally non-mutating. It validates an assembled manifest and simulates whether the future Roblox Studio plugin would be allowed to apply it.

## Assemble World 1

```powershell
python -m manifest fixtures/world_01_shadow_forest `
  --output build/world_01/build_manifest.json
```

## Dry run

```powershell
python -m studio_bridge build/world_01/build_manifest.json
```

The dry run checks:

- manifest schema and exact generated namespace;
- contiguous operation sequence and unique operation IDs;
- action, class, folder, terrain shape, and light allowlists;
- material, color, prefab, and audio registry keys;
- no arbitrary Luau/source/code or direct asset IDs;
- scoped Terrain and Lighting targets;
- instances exist before local lights and gameplay markers bind to them;
- planned operation counts match the manifest;
- planned instances, VFX, particles, and transparency stay within Director limits.

A manifest can pass dry run while remaining `releaseReady: false` when allowlisted placeholder assets still need real approved Roblox asset IDs. Dry run never opens or changes Roblox Studio.
