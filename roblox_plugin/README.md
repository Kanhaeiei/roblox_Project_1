# Native Roblox Studio Adapter

This directory contains the first native Studio plugin adapter for the validated build-manifest contract. It is intentionally source-only: review it, build/install it as a local plugin, and test it in a disposable place before using a real project.

## Implemented operations

- `ensure_folder`
- `terrain_fill` and `terrain_subtract` for block, ball, cylinder, and wedge
- `create_primitive` for Part, WedgePart, and TrussPart
- registry-backed `create_prefab` (the current registry intentionally contains no prefabs)
- `configure_lighting`
- `create_local_light`
- `bind_gameplay_marker`

## Safety model

- The plugin accepts pasted JSON only; it performs no HTTP requests.
- `ManifestGuard` rechecks version, build namespace, sequence, unique operation IDs, action/class/folder/shape/token allowlists, and forbidden payload keys.
- Instances are staged off-DataModel before activation.
- Generated content is scoped to `Workspace.Generated.<buildId>` and tagged with `ShadowArmyGenerated` plus stable attributes.
- Terrain and Lighting are snapshotted before mutation and restored on an apply failure.
- `ChangeHistoryService:TryBeginRecording()` and `FinishRecording()` integrate a successful apply with Studio Undo/Redo.
- Apply requires an unchanged preview in the plugin UI.

This is not release authorization. Run the Python validator, Manifest Assembler, and Bridge Dry Run first. Placeholder audio still blocks a public release.

## Build and install

With Rojo available:

```powershell
rojo build roblox_plugin/default.project.json --output build/ShadowArmyMapBuilder.rbxmx
```

Install the generated model as a local Studio plugin, open a disposable test place, paste the validated manifest JSON into the dock widget, select **Preview**, inspect the summary, then select **Apply**. Use Studio Undo to revert the committed recording.

The source has been compiled with Rojo 7.7.0 and verified to load cleanly in Roblox Studio `0.740.19.7400003`; see `docs/evidence/native-studio-load-2026-09-29.md`. The repository does not bundle Rojo or end-to-end Roblox Studio UI automation, so the interactive Preview/Apply/Undo verification remains a manual release gate.

Official Roblox references:

- https://create.roblox.com/docs/reference/engine/classes/ChangeHistoryService
- https://create.roblox.com/docs/reference/engine/classes/Terrain
- https://create.roblox.com/docs/reference/engine/classes/CollectionService
- https://create.roblox.com/docs/reference/engine/classes/Plugin
