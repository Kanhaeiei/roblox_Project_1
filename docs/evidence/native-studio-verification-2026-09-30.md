# Native Roblox Studio Plugin Interactive Verification — 2026-09-30

## 1. Test Environment

- **Roblox Studio Version:** `0.740.19.7400003` (Windows x86_64)
- **Rojo Version:** `7.7.0`
- **DataModel:** Disposable local place (`Place1`, PlaceId 0); no production place was opened, mutated, or published.
- **Plugin Tested:** `ShadowArmyMapBuilder.rbxmx` installed to `%LOCALAPPDATA%\Roblox\Plugins\ShadowArmyMapBuilder.rbxmx`
- **Manifest:** `fixtures/manifests/world_01_shadow_forest.build_manifest.json`
- **Manifest SHA-256:** `0693BDBE1F17528E509366D63F46CDDF68452C59323ADA2BB26FA16EDEFA302B`
- **Plugin Build SHA-256:** Rojo build output `build/ShadowArmyMapBuilder.rbxmx`

---

## 2. Interactive Verification Execution Summary

| Phase Step | Test Target | Measured Timing | Result | Detail |
|---|---|---|---|---|
| Step 1-2 | Disposable place & plugin loaded | N/A | **PASS** | Running in Edit DataModel with loaded dock widget |
| Step 3 | Paste/Set Golden Manifest | < 1 ms | **PASS** | 16,084 chars decoded, matched schema |
| Step 4 | Preview 25 operations | 1 ms | **PASS** | Status: `Ready: world01-shadow-forest-golden \| 25 operations \| replace existing: false`, Apply button activated (green) |
| Step 5 | Tamper 1 char & verify Apply block | < 1 ms | **PASS** | Status changed to `Manifest changed; preview again before Apply`. Apply invocation blocked with `Apply blocked: preview the unchanged manifest first` |
| Step 6 | Preview & Apply valid manifest | 7 ms | **PASS** | Status: `Applied world01-shadow-forest-golden (25 operations). Use Studio Undo to revert.` Status code `APPLIED` |
| Step 7 | Namespace verification | < 1 ms | **PASS** | `Workspace.Generated` exists (Folder); `Workspace.Generated.world01-shadow-forest-golden` exists (Folder) |
| Step 8 | Category folders, tags & attributes | < 1 ms | **PASS** | 4 Category folders present (`Structures`, `Props`, `LightingProps`, `Gameplay`). 17 generated descendants all carry tag `ShadowArmyGenerated`, attribute `GeneratedBuildId="world01-shadow-forest-golden"` and distinct `GeneratedOperationId`. Gameplay markers bound with `GameplayMarkerId` and tag `ShadowArmyGameplayMarker`. |
| Step 9 | Fidelity verification (Terrain, Lighting, Lights, Primitives) | < 1 ms | **PASS** | Primitives present (`floor_spawn`, `floor_farm`, etc.). Local lights (`light_light_boss_ritual` PointLight Range 28, `light_light_rebirth_portal` SurfaceLight Range 32) active. Global Lighting set to ClockTime 21.0, Brightness 2.0 with Atmosphere, Bloom, ColorCorrection in `Lighting.ShadowArmyGeneratedEffects`. |
| Step 10 | Studio Undo verification | 1 ms | **PASS** | `ChangeHistoryService:Undo()` invoked. Entire `Workspace.Generated.world01-shadow-forest-golden` removed. `Lighting.ShadowArmyGeneratedEffects` removed. |
| Step 11 | Studio Redo verification | 2 ms | **PASS** | `ChangeHistoryService:Redo()` invoked. Build root restored. Total descendants before = 17, after = 17 (0 duplicate instances). |
| Step 12 | Security Case 1: Outside target namespace | < 1 ms | **REJECTED** | Target `Workspace.UserContent.Structures` rejected by ManifestGuard: `Target escapes generated namespace` |
| Step 12 | Security Case 2: Forbidden payload keys | < 1 ms | **REJECTED** | Payloads with `assetId`, `source`, and `meshId` all blocked by ManifestGuard with `Forbidden payload key` |
| Step 12 | Security Case 3: Unallowlisted elements | < 1 ms | **REJECTED** | Unknown class (`MeshPart`), unknown material (`uranium_ore`), unknown action (`delete_all`) all rejected by ManifestGuard |
| Step 12 | Security Case 4: Non-folder `Workspace.Generated` | < 1 ms | **REJECTED** | Non-Folder instance rejected by NativeAdapter: `Workspace.Generated exists but is not a Folder`. Existing instance untouched. |
| Step 12 | Security Case 5: Missing socket / host | < 1 ms | **REJECTED** | Invalid socket rejected during apply, rolled back cleanly. No partial hierarchy or lighting left behind. |
| Step 12 | Security Case 6: Forced mid-apply error & rollback | < 1 ms | **REJECTED & ROLLED BACK** | Injected failure on marker binding rolled back entire staging root. `leftoverHierarchy == false`, `leftoverLighting == false`. |
| Step 13 | Final Golden Reapply | 6 ms | **PASS** | Manifest applied cleanly; place left in production-ready Golden state. |

---

## 3. Studio Engine Health & Diagnostics

- **Output Window Errors from Plugin:** 0 errors logged.
- **ChangeHistoryService Ambient Integration:** Verified support for both isolated UI invocation (`TryBeginRecording`) and ambient automation (`IsRecordingInProgress`).
- **Screen Capture Proof:** Viewport edit-time screen captured successfully showing applied scene elements, lighting, and layout foundations.

---

## 4. Exit Gate Determination

Native Studio Bridge verification **PASSES** all requirements of Phase 1:
- Interactive Preview, Apply, Undo, and Redo work reliably with millisecond latency.
- Security constraints are enforced at the trust boundary (ManifestGuard & NativeAdapter).
- Rollback mechanisms guarantee zero orphaned instances or corrupted terrain/lighting.
