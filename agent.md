# Architecture Specification: Shadow Army Rebirth Pipeline

**Architecture version:** 2.0  
**Contract schema:** `schemas/pipeline.schema.json`

## 1. Purpose and non-goals

The pipeline turns a bounded product brief into a validated, reproducible Roblox build manifest. It separates creative generation from deterministic correctness.

The pipeline does not let an LLM execute arbitrary Luau, choose arbitrary asset IDs, mutate an open place without preview, grant player rewards, or bypass validation. Generated content is data. Allowlisted code interprets that data.

## 2. Architecture principles

1. **Contract first:** all stage outputs validate against one versioned schema.
2. **Single owner per field:** one stage owns each fact; downstream stages reference it by ID and may not redefine it.
3. **Deterministic where correctness matters:** use code for arithmetic, graph traversal, bounds intersection, probability totals, ID resolution, and budgets.
4. **Reproducible builds:** a `buildId`, `seed`, input hash, schema version, model metadata, and artifact hashes identify every build.
5. **Least authority:** the Studio Bridge accepts only allowlisted actions, classes, properties, and asset references.
6. **Server authority:** the live server owns combat, economy, inventory, gates, purchases, and saving; clients own input and presentation.
7. **Measured budgets:** part counts are only one signal. Validate instance count, mesh/texture uniqueness, transparency, lights, particles, scripts, memory, network rate, and frame time.
8. **Patch, do not regenerate blindly:** QA returns machine-addressable JSON Patch-style operations to the owning stage.
9. **Bounded iteration:** at most three repair rounds per stage. Escalate unresolved blockers with artifacts preserved.
10. **Player experience is a hard constraint:** an artifact can be technically valid and still fail onboarding, readability, accessibility, or pacing gates.

## 3. Canonical artifact envelope

Every stage returns this envelope:

```json
{
  "schemaVersion": "2.0.0",
  "artifactType": "layout",
  "buildId": "world01-20260929-001",
  "stageId": "02_layout",
  "revision": 1,
  "seed": 48151623,
  "inputArtifactHashes": ["sha256:..."],
  "payload": {},
  "assumptions": [],
  "warnings": []
}
```

`artifactType`, `stageId`, and payload schema are fixed. Arrays with semantic identity use stable IDs and deterministic ordering. Timestamps belong in build metadata, not creative payloads, so repeated seeded builds can be compared.

## 4. Ownership map

| Domain | Owner | Downstream consumers |
|---|---|---|
| Product promise, emotional beats, FTUE goals | 00 Product & Creative | all stages |
| World bounds, palette, performance envelope, zone briefs | 01 Director | layout, terrain, props, lighting, QA |
| Exact zone bounds, paths, clearance volumes, spawn markers | 02 Layout | terrain, props, VFX, QA |
| Terrain operations and foundation surfaces | 03 Terrain | props, QA, bridge |
| Instances and gameplay marker references | 04 Props | lighting, VFX, QA, bridge |
| Lighting/post-processing profiles and quality tiers | 05 Lighting | QA, bridge |
| Economy formulas, reward tables, save schema, simulation | 07 Economy | props, VFX, QA, runtime |
| Presentation recipes, sound roles, effect budgets | 08 VFX/Audio | QA, bridge/runtime |
| Validation verdict and owner-addressed patches | 06 QA | orchestrator |

No stage may silently change upstream-owned values. It can issue a constraint or patch request.

## 5. Orchestration state machine

```text
DRAFT
  → GENERATED
  → SCHEMA_VALIDATED
  → DETERMINISTIC_VALIDATED
  → QA_REVIEWED
  → APPROVED
  → BRIDGE_DRY_RUN
  → APPLIED
  → PLAYTEST_VERIFIED
```

Any failed validation moves the artifact to `NEEDS_PATCH`, with an owner, JSON pointer, rule ID, expected value, and suggested correction. An artifact is immutable after approval; changes create a new revision and invalidate dependent artifacts.

Parallelism is permitted only when dependencies are satisfied:

- Director and Economy run after Concept.
- Layout and Terrain planning may run in parallel after Director, but final terrain consumes approved layout clearance/foundation data.
- Lighting and VFX may run in parallel after Props.
- QA runs only after deterministic assembly.

## 6. Deterministic validation suite

### Contract and identity

- JSON Schema validation with unknown production fields rejected.
- Unique IDs and referential integrity across all artifacts.
- Required artifact versions and compatible major versions.
- Finite numeric values; no NaN/Infinity; approved ranges and units.

### Spatial

- All zone AABBs remain inside world bounds.
- Zone overlaps require an explicit intersection relationship.
- BFS/DFS reachability from spawn to all required zones.
- Clearance volumes remain free of collidable props.
- Path width, ceiling, step, slope, jump, arena, and respawn constraints.
- Static supports intersect terrain/foundation within tolerance.
- Terrain operations align to the approved voxel/grid policy.

### Economy

- Random tables use integer basis points and total exactly 10,000.
- Currency references resolve; each currency has sources, sinks, and caps.
- Rebirth/reset manifests preserve declared permanent data.
- 5/15/30/60-minute simulations meet pacing bands.
- No negative, non-finite, unsafe-integer, or unreachable values.
- Pity and duplicate-protection state is persistent and migratable.
- Paid-random-item paths are marked and require policy/odds gates.

### Runtime and security

- Client messages express intent only and have schema, value, context, distance, state, and rate-limit rules.
- No arbitrary instance paths, class names, asset IDs, or executable source from generated payloads.
- Developer products use idempotent receipt processing.
- Save schema has a version, migrations, session ownership policy, retries, and graceful failure behavior.

### Presentation and accessibility

- VFX, sound, light, and transparency budgets by quality tier.
- Enemy telegraphs are never occluded by generated cosmetics.
- Critical information has non-color and non-audio alternatives.
- Reduced-motion/flash profiles exist for intense effects.
- Placeholder asset IDs are rejected for release builds.

## 7. Spatial conventions

- Coordinate system: Roblox studs, right-handed world convention with Y up; all vectors are `[x, y, z]`.
- Angles: degrees in authored JSON, converted once at the bridge.
- Bounds: axis-aligned `min` inclusive and `max` exclusive for deterministic intersection tests.
- Grid: structural placement snaps to 2 studs; terrain foundations prefer 4-stud alignment.
- Default avatar design envelope: about 5 studs tall and 2 studs wide, but validate with the actual supported avatar rig and camera during playtests.
- Minimum authored doorway: 6 studs wide × 9 studs high.
- Critical squad route: 10 studs wide, 12-stud preferred camera clearance.
- Boss arena: 80-stud minimum diameter and 24-stud vertical/camera clearance for MVP.

Jump numbers are not treated as universal truths. Required traversal uses walkable paths, ramps, stairs, or explicit movement abilities. Any optional jump is tested against the actual controller configuration.

## 8. Budget model

The Director supplies provisional budgets; QA records measured results from representative devices. MVP starting caps are hypotheses, not guarantees:

```json
{
  "instances": 6000,
  "baseParts": 3500,
  "uniqueMeshIds": 150,
  "uniqueTextureIds": 220,
  "shadowCastingLights": 8,
  "activeParticleEmittersNearPlayer": 24,
  "particlesPerSecondNearPlayer": 350,
  "transparentOverlapLayers": 4,
  "serverScriptActivityMsPerFrame": 4,
  "clientFrameTargetFps": 30,
  "preferredClientFps": 60
}
```

Instance streaming is expected for multi-world production. Scripts must tolerate streamed-out instances and use stable tags/IDs instead of assuming descendants are always present. Cosmetic VFX should be produced locally after a server-approved event.

## 9. Studio Bridge contract

The bridge has two modes:

1. **Dry run:** validate, resolve allowlisted assets, estimate changes, show diff, and create no instances.
2. **Apply:** create under `Workspace.Generated/<buildId>`, record undo history, tag generated instances, and produce an application report.

Rules:

- Never clear `Workspace` or Terrain globally without an explicit scoped operation and confirmation.
- Replace only instances tagged with the same generated build namespace.
- Allowlist creatable classes and writable properties.
- Resolve palette tokens and prefab IDs through a local registry; generation cannot provide arbitrary asset/source URLs.
- Apply in a transaction-like sequence: prepare → validate → create disabled/in staging → link references → activate → report.
- On failure, preserve diagnostics and roll back the generated namespace.

## 10. Live game architecture

```text
ReplicatedStorage/
  Shared/Types, Config, NumberFormat, Remotes
ServerScriptService/
  Services/Combat, Units, Economy, Data, Products, Worlds, Analytics
ServerStorage/
  Prefabs, ServerOnlyConfigs
StarterPlayerScripts/
  Controllers/Input, Targeting, UI, Camera, VFX, Audio
Workspace/
  Generated/<buildId>, RuntimeActors
```

- Service APIs are explicit and dependency-injected; configuration is data, not duplicated constants.
- The server validates every client request and computes authoritative outcomes.
- Remote endpoints have narrow purposes and rate limits. High-frequency, non-critical presentation data may use unreliable transport where appropriate.
- Data writes use protected calls, backoff, schema migration, and update semantics suitable for multi-server conflicts.
- Save on meaningful checkpoints and shutdown opportunities, but never promise lossless shutdown saving.
- Analytics events have a registry, version, required fields, and sampling/privacy rules.

## 11. Build manifest

An approved manifest contains:

- artifact hashes and versions;
- seed and build metadata;
- ordered terrain and instance operations;
- asset registry references;
- lighting and presentation profiles;
- gameplay marker map;
- economy/runtime configuration;
- validation results and accepted warnings;
- required migrations and minimum runtime version;
- rollback namespace and previous compatible build ID.

The manifest contains no secrets and no executable source generated by an LLM.

## 12. QA severity and release gates

- **BLOCKER:** data loss, exploit, policy failure, purchase loss, crash, inaccessible core loop, schema failure.
- **CRITICAL:** broken progression, unreachable zone, severe performance/readability failure.
- **MAJOR:** degraded UX, balance outside target band, missing accessibility alternative.
- **MINOR:** polish issue with no material gameplay impact.

Release requires zero unresolved BLOCKER/CRITICAL issues. MAJOR issues require an explicit owner and accepted-risk record; warnings never silently become approval.

## 13. Testing strategy

- Unit tests: formulas, number formatting, probability tables, migrations, rate limits.
- Property tests: random valid inputs never produce negative/non-finite/unsafe values.
- Contract fixtures: one valid and multiple invalid artifacts per schema.
- Integration tests: orchestrator → manifest → bridge dry-run → generated hierarchy.
- Exploit tests: malformed remotes, spam, distance spoofing, duplicate receipts, stale saves.
- Playtests: new player with no instructions, low-end mobile, controller-only, high latency, full server, reduced motion.
- Soak tests: repeated joins/leaves, 60-minute economy, streaming traversal, memory growth.

## 14. Current implementation roadmap

1. Implement schema validation and deterministic validators before model orchestration. **Complete.**
2. Create World 1 hand-authored golden fixtures to test the pipeline. **Complete.**
3. Add seeded dependency orchestration, immutable storage, manifest assembly, and Bridge dry-run. **Complete.**
4. Connect the orchestrator to replay and optional live model runners with bounded patch rounds and preserved provenance. **Complete.**
5. Add provider evals and execute a credentialed World 1 generation run before accepting AI-authored artifacts as Golden candidates.
6. Add Studio Bridge diff and transactional reference apply/undo. **Complete.**
7. Implement the native Roblox Studio adapter with ChangeHistoryService, scoped snapshots, tags, and integration tests.
8. Implement the runtime combat/economy slice with placeholder geometry and run player tests for time-to-first-kill and first ARISE.
9. Tune from telemetry and device profiling; only then automate additional worlds.
