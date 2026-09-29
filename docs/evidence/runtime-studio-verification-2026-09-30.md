# Runtime Foundation & Playable Vertical Slice Verification — 2026-09-30

> [!CAUTION]
> **CRITICAL SECURITY & DATA INTEGRITY NOTICE:**
> **DO NOT enable Studio API Access on live production places or Experience ID `10768628555` (Shadow Army Rebirth).**
> Any runtime testing in Roblox Studio must remain strictly within disposable test places with mock storage or isolated staging keys. Never expose live production DataStores or live player profiles to Studio Edit sessions.

---

## 1. Test Environment

- **Roblox Studio Version:** `0.740.19.7400003` (Windows x86_64)
- **Studio Session ID:** `d8dc7ac5-1d28-4d1f-8aa5-5c1b97e988ad` (`Place2`, PlaceId `107958834503266`, Universe/GameId `10768628555` — Private)
- **Rojo Version:** `7.7.0` (`roblox_runtime/default.project.json` compiled to `roblox_runtime.rbxm` cleanly with exit code 0)
- **Isolation Boundary:**
  - All tests executed inside an isolated disposable container: `game.ServerStorage.DisposableRuntimeTest`.
  - Zero live DataStore reads or writes occurred.
  - No code or assets were published to the live Experience.
  - Container and all test ModuleScripts were destroyed cleanly post-test (`ServerStorage:FindFirstChild('DisposableRuntimeTest') == nil`).

---

## 2. Verification Categorization

To maintain strict engineering rigor, test results are explicitly categorized into:
1. **Studio-verified**: Empirically executed and asserted in Roblox Studio via Luau runtime execution.
2. **Mock/Python-verified**: Verified in Python test suite (`unittest`, 79 tests) or via in-memory mock adapters.
3. **Not yet tested**: Features, timings, or hardware boundaries that require live player sessions, real cloud services, or visual human verification.

---

## 3. Studio-Verified Evidence (59 / 59 Assertions Passed)

Executed in Roblox Studio Edit mode (`execute_luau`) across 10 verification phases:

```json
{"summary": "Passed 59 assertions, 0 failures", "failed": 0, "passed": 59, "errors": []}
```

### Breakdown by Phase:

| Phase | Category | Assertions | Result | Empirical Invariant Verified |
|---|---|---|---|---|
| **Phase 1** | RemoteService Handler Registration | 6 | **PASS** | - Named local handler functions assigned to both `RemoteFunction.OnServerInvoke` and `RemoteService.handlers[name]`.<br>- Avoided reading write-only `OnServerInvoke` property.<br>- All 6 endpoints callable via handler table: `request_attack`, `request_upgrade`, `request_arise`, `request_summon`, `request_rebirth`, `request_snapshot`. |
| **Phase 2 & 3** | PlayerData Writable Session Load | 4 | **PASS** | - Session token generated via `HttpService:GenerateGUID(false)`.<br>- Initial session loaded with 0 Mana.<br>- `isReadOnly == false` and `isConflicted == false`.<br>- Session registered in active sessions table. |
| **Phase 4** | Server Authoritative Snapshot | 4 | **PASS** | - `request_snapshot` endpoint invoked.<br>- Returns server-confirmed values: Mana = 0, Level = 0, Attack Power = 10.<br>- Server confirms `isReadOnly = false` and `isConflicted = false`. |
| **Phase 5** | Authoritative Combat & Reward Flow | 6 | **PASS** | - Non-lethal attack against 500 HP goblin deals damage without defeat or Mana award.<br>- Attack cooldown (`0.125s`) enforced between strikes.<br>- Lethal attack defeats enemy and authoritatively awards 25 Mana.<br>- Snapshot confirms player balance updated to 25 Mana. |
| **Phase 6** | Session Save & Persistence | 4 | **PASS** | - Balance updated to 500 Mana.<br>- Explicit `saveSession` flushes dirty state.<br>- Adapter record reflects 500 Mana and matching GUID lease token. |
| **Phase 7** | Lease Preemption & Conflict Detection | 5 | **PASS** | - Simulated unexpired lease (`LEASE_DURATION = 30s`) takeover by `"other-server-token"`.<br>- Original session attempt to save detects token mismatch.<br>- Preempted session immediately forced to `isReadOnly = true` and `isConflicted = true`. |
| **Phase 8** | Complete Read-Only Mutation Lock | 8 | **PASS** | - Combat attack rejected with `"Session is read-only"`.<br>- Upgrade rejected with `"Session is read-only"`.<br>- Shadow ARISE rejected with `"Session is read-only"`.<br>- Shadow summon rejected with `"Session is read-only"`.<br>- Shadow rebirth rejected with `"Session is read-only"`.<br>- `PlayerDataService.addCurrency` rejected with `"Session is read-only"`.<br>- `PlayerDataService.deductCurrency` rejected with `"Session is read-only"`.<br>- 100% mutation lock guaranteed across all gameplay paths. |
| **Phase 9** | Player Leave & Rejoin Profile Match | 6 | **PASS** | - Player disconnect flushes data and removes active session.<br>- Adapter updated with modified profile: 750 Mana, Level 2 Attack Power.<br>- Reconnecting player loads persisted profile cleanly.<br>- Authoritative snapshot matches profile: Mana = 750, Level = 2, isReadOnly = false. |
| **Phase 10** | Developer Products & `processReceipt` | 16 | **PASS** | - `Config.DeveloperProductsEnabled = false` returns `Enum.ProductPurchaseDecision.NotProcessedYet`.<br>- When enabled in test harness: purchase granted and session in-memory balance updated (1,750 Mana).<br>- Duplicate receipt returns `PurchaseGranted` immediately without double-crediting.<br>- Currency cap overflow (999,999,500 + 1,000 > 1,000,000,000) blocks purchase and returns `NotProcessedYet` (0 balance added).<br>- Save failure across all 3 retries returns `NotProcessedYet` without balance deduction. |

**Total Studio Assertions:** 59 / 59 Passed (100%).

---

## 4. Mock / Python-Verified Evidence (79 / 79 Tests Passed)

Executed locally via `python -m unittest discover tests` (2.852s):

- **JSON Schema Validation:** All stage artifacts validated against Draft 2020-12 schemas (`tests/test_schemas.py`).
- **Economy Math Invariants:** Affordability curves, exponential scaling, safe-integer arithmetic, and formatting verified (`tests/test_economy_simulation.py`, `tests/test_economy_formatter.py`).
- **Deterministic Validators:** Bounds, overlap, graph reachability, clearance volumes, and terrain support verified (`tests/test_validators.py`).
- **Studio Bridge Dry-Run:** Reference diffing, namespace enforcement, tag verification, and rollback receipts verified (`tests/test_studio_bridge.py`).
- **Runtime Source Contracts:** AST parsing, remote signature matching, and security invariant presence verified (`tests/test_runtime_foundation.py`, `tests/test_runtime_executable.py`).

---

## 5. Not Yet Tested (Production Boundaries & Pending Items)

The following items are **NOT** verified by the current automated test suite and require future live testing:

1. **Live Cloud DataStoreService:**
   - Evaluated solely via in-memory `DataStoreAdapter`.
   - Real cloud `DataStoreService` partitions, throttling, and network partition failover have not been tested against live Roblox infrastructure.
2. **Developer Product Catalog & Monetization:**
   - `Config.DeveloperProductsEnabled` remains `false`.
   - No Developer Product IDs have been created on the Roblox Creator Dashboard.
   - Live Robux purchase transactions have not been processed.
3. **Physical Client GUI Rendering & Human Playtesting:**
   - `RuntimeClient.client.lua` source contains GUI creation, `request_snapshot` invocation, and read-only banner logic.
   - Remote invocation and snapshot return were verified via server-side assertions.
   - **Empirical viewport rendering, text layout on different aspect ratios, and visual appearance of the `[READ-ONLY]` banner were NOT human-verified on screen.**
4. **Pacing Timings:**
   - Specification targets (First input ≤5s, first kill ≤20s, first upgrade 20–60s, mini-boss 2–4m, guaranteed first ARISE 6–10m, first rebirth 15–25m) are enforced by mathematical progression rules and cooldown logic.
   - **Live multi-minute pacing timings have NOT been empirically clocked in a live playtest.**
5. **Cross-Platform Input & Soak Testing:**
   - Touch controls, gamepad navigation, low-end mobile memory pressure, and long-duration server soak testing remain untested.
