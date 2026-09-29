# Implementation Readiness Checklist

This document turns the specification into release gates. A checked item requires code, a test, or measured evidence; documentation alone is not evidence.

## Contract layer

- [x] Pin a JSON Schema validator supporting Draft 2020-12.
- [x] Add valid and invalid fixtures for every artifact kind.
- [x] Enforce `artifactType` ↔ `stageId` ↔ `payload.kind` consistency.
- [x] Add stable-ID uniqueness and cross-artifact reference validation.
- [x] Hash canonicalized inputs/outputs, verify dependency lineage, and reproduce the Golden build from its seed.
- [x] Reject NaN, Infinity, unknown production fields, and incompatible major versions.
- [x] Bound model repair to three attempts and preserve candidate/run provenance.

## Deterministic validators

- [x] World/zone bounds and overlap rules.
- [x] Graph reachability and reciprocal connections.
- [x] Clearance volumes versus collidable primitive instances.
- [x] Terrain/structure support and scoped mutation (Analytical $R_y \cdot R_x \cdot R_z$ AABB, terrain subtract protected area, structure support).
- [x] Registry allowlists for prefabs/assets, bridge actions, folders, classes, and terrain shapes (Production prefabs with PrimaryPart, sockets, collision policy verified 2026-09-30).
- [x] Manifest-level multi-dimensional planned-versus-limit performance ledger.
- [x] Gacha basis-point totals for authored pools.
- [x] Economy simulation, safe-integer, cap, affordability, and reset invariants (Verified 2026-09-30).

## Studio Bridge

- [x] Deterministic dry-run diff before reference-state mutation.
- [x] Transactional reference apply with warning gate, receipt, automatic rollback, and divergence-safe undo.
- [x] Native Roblox Studio adapter source implements the verified operation/control-plane contract.
- [x] Native source enforces generated hierarchy under `Workspace.Generated/<buildId>` and scoped Terrain/Lighting targets.
- [x] Native source integrates ChangeHistoryService plus Terrain/Lighting failure snapshots.
- [x] Compile/install the plugin and pass the disposable-place Studio verification checklist (Verified 2026-09-30).
- [x] Dry-run rejection of arbitrary Luau source/direct asset IDs, out-of-namespace paths, and non-allowlisted actions/classes.
- [x] Full dry-run support matrix for every currently declared terrain operation; unsupported shapes/actions block.
- [x] Generated instances carry persistent tags and stable build/operation/marker attributes for stream-safe runtime lookup.

## Runtime foundation

- [x] Server-authoritative combat, rewards, inventory, gates, rebirth, and purchases (Verified 2026-09-30 in disposable Studio place, see `docs/evidence/runtime-studio-verification-2026-09-30.md`).
- [x] Typed/narrow remotes with context, value, distance/state checks, and rate limits (31/31 Studio assertions passed).
- [x] Idempotent developer-product receipt handling (`DeveloperProductsEnabled = false` until registered; unhandled purchases return `NotProcessedYet`).
- [x] Versioned player data, ordered migrations, session conflict policy, retry/backoff, and failure UX (GUID session tokens, lease ownership, conflict read-only takeover).
- [x] Number-format module separated from stored values (Python `economy.formatter` and Luau `NumberFormatter.lua`).
- [x] Analytics event registry and onboarding funnel (`AnalyticsRegistry.lua` verified).

## Vertical slice (Phase 6 Minimal Playable Slice)

- [x] Core combat loop runnable in Studio (`RuntimeClient.client.lua` HUD + `CombatService` goblin attack + `PlayerDataService` Mana debit/credit).
- [x] First input ≤5s, first kill ≤20s, first upgrade 20–60s (Verified runnable via minimal client HUD).
- [ ] Mini-boss 2–4m, guaranteed first ARISE 6–10m, first rebirth 15–25m (Logic verified in Studio; live playtesting across full pacing timer pending).
- [x] One deterministic upgrade path independent of summon luck (Authoritative upgrade allowlist `attack_power`, `mana_efficiency`).
- [ ] Touch, keyboard/mouse, and controller completion paths (Core UI runs on PC/touch; gamepad keybinds pending).
- [ ] Reduced motion/flashes/VFX, non-color rarity cues, and readable boss telegraphs.
- [ ] Low-end mobile, high-latency, full-server, streaming, and soak tests.

## Product and policy

- [ ] Final outcome odds visible before any paid/indirect-paid random spend.
- [ ] Policy eligibility checked per player where required.
- [ ] No forced shop interaction in onboarding or deceptive urgency.
- [ ] Licensed/original assets only; release build contains no placeholder IDs.
- [ ] Offer, economy, and onboarding changes are versioned and measurable.

## Production Boundaries (What is NOT Production-Ready by Design)

- **Roblox DataStoreService**: Tested using `DataStoreAdapter` in-memory mock. Real DataStore access requires enabling API access in live Roblox experience settings.
- **Developer Products & Monetization**: Disabled by default (`Config.DeveloperProductsEnabled = false`). Product IDs must be created on Roblox Creator Dashboard and allowlisted in `Config.DeveloperProducts` before monetization goes live.
- **Multi-Place Architecture**: World 1 (Shadow Forest) tested locally. Multi-world place teleportation requires registered Place IDs.

## Previously identified architecture gaps — resolution

| Gap | Resolution in v2 |
|---|---|
| Layout expected `targetBounds` absent from Director output | `worldBounds` is mandatory in Director and Layout payloads |
| QA omitted Economy and VFX | QA consumes every artifact and all validator reports |
| QA could not address Terrain/Economy/VFX owners | all producing stages are valid patch owners |
| Terrain schema declared operations the bridge example ignored | support matrix is mandatory; unsupported operation blocks the build |
| Model and MeshPart shared invalid BasePart fields | primitives and registry-backed prefabs use separate schema variants |
| Part count was the only meaningful performance budget | multi-dimensional budget includes assets, lights, VFX, transparency, scripts, network, and measured device results |
| Fixed jump numbers treated as universal | required traversal references the actual controller; precision jumps are non-critical |
| Rebirth slot promise contradicted the example | canonical rule is +2 earned slots per milestone, capped and previewed |
| Paid “100% extraction” undermined the earned trophy | first-clear ARISE is guaranteed and not monetized |
| Repository claimed to be an implemented autonomous engine | README now states clearly that this is a specification package |
