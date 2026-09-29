# Implementation Readiness Checklist

This document turns the specification into release gates. A checked item requires code, a test, or measured evidence; documentation alone is not evidence.

## Contract layer

- [x] Pin a JSON Schema validator supporting Draft 2020-12.
- [x] Add valid and invalid fixtures for every artifact kind.
- [x] Enforce `artifactType` ↔ `stageId` ↔ `payload.kind` consistency.
- [x] Add stable-ID uniqueness and cross-artifact reference validation.
- [x] Hash canonicalized inputs/outputs, verify dependency lineage, and reproduce the Golden build from its seed.
- [x] Reject NaN, Infinity, unknown production fields, and incompatible major versions.

## Deterministic validators

- [x] World/zone bounds and overlap rules.
- [x] Graph reachability and reciprocal connections.
- [x] Clearance volumes versus collidable primitive instances.
- [ ] Terrain/structure support and scoped mutation.
- [x] Registry allowlists for prefabs/assets, bridge actions, folders, classes, and terrain shapes.
- [x] Manifest-level multi-dimensional planned-versus-limit performance ledger.
- [x] Gacha basis-point totals for authored pools.
- [ ] Economy simulation, safe-integer, cap, affordability, and reset invariants.

## Studio Bridge

- [ ] Dry-run diff before mutation.
- [ ] Apply only under `Workspace.Generated/<buildId>`.
- [ ] Undo/history integration and rollback report.
- [x] Dry-run rejection of arbitrary Luau source/direct asset IDs, out-of-namespace paths, and non-allowlisted actions/classes.
- [x] Full dry-run support matrix for every currently declared terrain operation; unsupported shapes/actions block.
- [ ] Stream-safe tags/references rather than unconditional descendant assumptions.

## Runtime foundation

- [ ] Server-authoritative combat, rewards, inventory, gates, rebirth, and purchases.
- [ ] Typed/narrow remotes with context, value, distance/state checks, and rate limits.
- [ ] Idempotent developer-product receipt handling.
- [ ] Versioned player data, ordered migrations, session conflict policy, retry/backoff, and failure UX.
- [ ] Number-format module separated from stored values.
- [ ] Analytics event registry and onboarding funnel.

## Vertical slice

- [ ] First input ≤5s, first kill ≤20s, first upgrade 20–60s.
- [ ] Mini-boss 2–4m, guaranteed first ARISE 6–10m, first rebirth 15–25m.
- [ ] One deterministic upgrade path independent of summon luck.
- [ ] Touch, keyboard/mouse, and controller completion paths.
- [ ] Reduced motion/flashes/VFX, non-color rarity cues, and readable boss telegraphs.
- [ ] Low-end mobile, high-latency, full-server, streaming, and soak tests.

## Product and policy

- [ ] Final outcome odds visible before any paid/indirect-paid random spend.
- [ ] Policy eligibility checked per player where required.
- [ ] No forced shop interaction in onboarding or deceptive urgency.
- [ ] Licensed/original assets only; release build contains no placeholder IDs.
- [ ] Offer, economy, and onboarding changes are versioned and measurable.

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
