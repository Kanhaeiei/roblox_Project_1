# Native Studio Plugin Load Evidence — 2026-09-29

## Environment

- Roblox Studio: `0.740.19.7400003`, Windows x86_64
- Rojo: `7.7.0`
- Source commit before the toolbar-icon correction: `c9a1758`
- Built plugin SHA-256 after correction: `F824DACB747FF4F3B64466706971A69F16A7E28AB312EC21DB13B8D140559400`
- Test place: disposable Rojo-generated empty DataModel; no production place was opened or published

## Observed results

1. Rojo built `ShadowArmyMapBuilder.rbxmx` successfully.
2. Roblox Studio opened the disposable `.rbxlx` place.
3. Studio logged both `loadPlugin user_ShadowArmyMapBuilder.rbxmx` and `Running plugin user_ShadowArmyMapBuilder.rbxmx`.
4. The first run exposed an invalid built-in toolbar icon path. The icon was removed, the plugin was rebuilt and reinstalled, and a second Studio run had no matching `CreatorError`, `ScriptContext` error, or icon-load error.

## Scope of this evidence

This proves compilation, local installation, plugin discovery, module initialization, and clean startup. It does **not** prove the interactive Preview/Apply gate, generated hierarchy, Terrain/Lighting fidelity, rollback, or Undo/Redo behavior. Those remain required by `docs/native-studio-verification.md` before release.
