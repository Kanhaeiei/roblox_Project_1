# Runtime Foundation & Playable Vertical Slice Verification — 2026-09-30

## 1. Test Environment

- **Roblox Studio Version:** `0.740.19.7400003` (Windows x86_64)
- **Rojo Version:** `7.7.0`
- **DataModel:** Disposable local place (`Place1`, PlaceId 0, Studio ID `bc902672-0d65-4770-91a1-1ea7ec183fd6`); no production place or live DataStore was touched.
- **Rojo Project:** `roblox_runtime/default.project.json` compiled to `roblox_runtime.rbxm` cleanly (exit code 0).
- **Target Runtime Installed:**
  - `ReplicatedStorage.Shared`: `Config`, `NumberFormatter`, `Remotes`, `AnalyticsRegistry`
  - `ServerScriptService`: `RuntimeBootstrap` (Script), `Services` (`PlayerDataService`, `CombatService`, `ShadowArmyService`, `RemoteService`)
  - `StarterPlayer.StarterPlayerScripts`: `RuntimeClient` (LocalScript)

---

## 2. Test Execution & Assertion Summary

All 31 runtime foundation assertions passed in Roblox Studio Edit execution (0 failures, 0 runtime exceptions).

| Category | Assertions | Result | Verified Invariants |
|---|---|---|---|
| **Session Lease & Ownership** | 4 | **PASS** | - Session token generated via `HttpService:GenerateGUID(false)`.<br>- Leases renew periodically with `LEASE_DURATION = 30s`.<br>- Conflicting session token takeover transitions original session to `isReadOnly = true` and `isConflicted = true`.<br>- Overwrite by expired/stolen session lease is rejected at DataStore adapter. |
| **Currency & Math Safety** | 8 | **PASS** | - Negative amounts (`-100`) rejected.<br>- `NaN` and `math.huge` (Infinity) rejected.<br>- Zero amounts rejected.<br>- Fractional/float amounts rejected (`math.floor(val) == val`).<br>- Caps enforced at `MaxCurrency` and `SafeIntegerCeiling` ($9 \times 10^{15}$).<br>- Balances update authoritatively and mark session dirty. |
| **Upgrades Allowlist & Cost** | 4 | **PASS** | - Unregistered upgrade keys (e.g. `god_mode`) rejected.<br>- Level upgrades beyond `maxLevel` rejected.<br>- Insufficient Mana rejected without debiting balance.<br>- Valid purchase debits server-calculated Mana and increments level. |
| **Combat Cooldown & Authority** | 5 | **PASS** | - Rapid successive attacks within `0.125s` cooldown rejected.<br>- Attack after cooldown succeeds.<br>- Character position read strictly from `Character.PrimaryPart` (never client-supplied vectors).<br>- Dead player / missing character attacks rejected.<br>- Enemy HP and defeat tracked authoritatively per player. |
| **ARISE Extraction & Ritual** | 6 | **PASS** | - Ritual altar dynamically resolved from `ShadowArmyGameplayMarker` attribute `socket_boss_ritual` (fallback to layout coordinate).<br>- Distance check enforces $\le 30$ studs; invocation from $> 30$ studs rejected.<br>- First-clear boss defeat unlocks guaranteed ARISE flag.<br>- Extraction consumes boss flag; subsequent extraction attempts without defeat rejected.<br>- Extracted shadow added to army data; dirty session marked. |
| **Session Release & Persistence** | 4 | **PASS** | - Clean player disconnect releases session lock atomically.<br>- Dirty session flushed to DataStore adapter.<br>- Saved data verified on subsequent reload.<br>- Clean memory cleanup of session records on player removal. |

**Total Assertions:** 31 / 31 Passed (100%).

---

## 3. Playable Vertical Slice Client (Phase 6)

- **Script:** `roblox_runtime/src/StarterPlayerScripts/RuntimeClient.client.lua`
- **Installation:** Deployed to `StarterPlayer.StarterPlayerScripts.RuntimeClient` in Studio DataModel.
- **Features:**
  - Reactive HUD displaying Player Level, Mana balance, and Attack Power in real-time.
  - Interactive "Attack Goblin" button invoking authoritative `RequestAttack` remote.
  - Interactive "Upgrade Power" button invoking authoritative `RequestUpgrade` remote.
  - Client rate-limiting / cooldown feedback aligned with server `Config.Combat.attackCooldown`.
  - Disconnect / read-only session banner displayed if session conflict or read-only state occurs.

---

## 4. Production Boundary Notice (What is NOT Production-Ready)

1. **Roblox DataStore Service:**
   - Evaluated with in-memory `DataStoreAdapter` and mock lease contracts.
   - Real `DataStoreService` must be enabled in Game Settings with production experience IDs before live publishing.
2. **Developer Products & Monetization:**
   - Hardcoded `DeveloperProductsEnabled = false` and empty product catalog `DeveloperProducts = {}`.
   - Purchases return `Enum.ProductPurchaseDecision.NotProcessedYet` to guarantee zero unhandled charges.
3. **Multi-World Content & Asset Streaming:**
   - Only World 1 (Shadow Forest) assets and prefabs are mapped.
   - Live asset IDs must be verified against Roblox moderation and audio/mesh asset privacy settings prior to multi-place deployment.
