# Native Studio Adapter Verification

The native adapter is not production-ready until this checklist passes in a disposable Roblox Studio place. Record the Studio version, plugin build commit, manifest hash, screenshots, and any Output-window errors with the test result.

## Prerequisites

- Run the Python validator, assembler, and dry run successfully.
- Build `roblox_plugin/default.project.json` into a local plugin model.
- Use a copy or empty test place, never the only copy of production work.
- Keep Team Create disabled for the first mutation test.

## Golden smoke test

1. Open the plugin and paste `fixtures/manifests/world_01_shadow_forest.build_manifest.json`.
2. Select **Preview** and verify it reports 25 operations.
3. Modify one character in the manifest and confirm **Apply** is blocked until another Preview.
4. Restore valid JSON, Preview, then Apply.
5. Verify `Workspace.Generated.world01-shadow-forest-golden` exists with exactly the four declared category folders.
6. Verify generated descendants have `GeneratedBuildId` and `GeneratedOperationId`; gameplay hosts have `GameplayMarkerId`.
7. Verify three scoped terrain operations, global Lighting, two local lights, and eleven primitives visually match the manifest.
8. Use Studio Undo once and verify generated hierarchy, Terrain, and Lighting return to their prior state.
9. Use Redo once and verify the build returns without duplicate instances.

## Failure and security tests

- Change a target to `Workspace.UserContent...`; Preview must fail and the place must remain unchanged.
- Add `source`, `assetId`, or `meshId` anywhere in an operation payload; Preview must fail.
- Use an unknown class, material, color, folder, terrain shape, light type, or prefab; Preview must fail.
- Create a non-Folder instance named `Workspace.Generated`; Apply must fail without modifying it.
- Remove a required light socket or marker host; Apply must roll back all hierarchy, Terrain, and Lighting changes.
- Force a mid-apply error in a disposable development copy and verify the recording is canceled and snapshots restore.

## Performance and compatibility

- Test current production Studio on Windows and macOS if both are supported by the team.
- Measure preview/apply time and peak Studio memory for the Golden build.
- Close/reopen the place and confirm tags/attributes persist.
- Enable StreamingEnabled and confirm runtime consumers resolve tags/attributes instead of assuming descendants are loaded.

## Exit gate

Native Studio verification passes only with zero hierarchy, Terrain, Lighting, undo/redo, security, or Output-window errors. Attach the evidence to the release candidate; do not infer success from Python/static tests alone.
