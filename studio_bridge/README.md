# Studio Bridge Control Plane

The bridge control plane validates a manifest, calculates an exact change plan, and exercises transactional apply/undo against a deterministic reference backend. The reference backend mutates a JSON state file only; it does **not** open or modify Roblox Studio. A native Studio adapter remains a separate release gate.

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

## Diff, reference apply, and undo

```powershell
python -m studio_bridge.control_cli diff fixtures/manifests/world_01_shadow_forest.build_manifest.json `
  --state build/bridge-state.json `
  --output build/bridge-plan.json

python -m studio_bridge.control_cli apply fixtures/manifests/world_01_shadow_forest.build_manifest.json `
  --state build/bridge-state.json `
  --receipt build/bridge-receipt.json `
  --allow-warnings

python -m studio_bridge.control_cli undo build/bridge-receipt.json `
  --state build/bridge-state.json `
  --output build/undo-report.json
```

The change plan labels every operation as `create`, `update`, `delete`, or `noop`. Apply always reruns the dry run. Warnings require explicit acceptance. If any operation fails, the reference backend restores its exact snapshot. Undo verifies receipt integrity and refuses to run if the current state has diverged since apply.

State, plans, and receipts are written atomically. Receipts are integrity hashes, not cryptographic signatures; production Studio integration must store trusted history inside the plugin/session boundary.

## Native adapter still required

The future Roblox Studio adapter must implement the same backend interface using allowlisted Roblox instances and properties, `ChangeHistoryService` waypoints, CollectionService tags/stable IDs, scoped Terrain/Lighting snapshots, and a staging namespace before activation. Until that adapter and Studio integration tests exist, `apply` means reference-state apply only.
