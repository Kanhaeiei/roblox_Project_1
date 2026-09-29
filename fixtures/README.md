# Validation Fixtures

## `world_01_shadow_forest/`

The canonical hand-authored golden build for the first vertical slice. It contains exactly one artifact for every pipeline stage:

```text
00_game_concept.json
01_director.json
02_layout.json
03_terrain.json
04_props.json
05_lighting.json
06_qa.json
07_economy.json
08_vfx_audio.json
```

All files share the same schema version, build ID, and seed. Every downstream artifact records the canonical hashes of its exact dependencies. Cross-artifact IDs resolve, the spatial graph is connected, terrain remains scoped, collidable props avoid clearance volumes, gacha odds total 10,000 basis points, and economy checkpoints cover 5/15/30/60 minutes.

The QA fixture represents the expected verdict after validators pass; it is not proof that an unvalidated build is approved.

This fixture intentionally uses registry keys and placeholder content definitions. It is ready for contract and bridge tests, not for a public Roblox release.

## `invalid/`

Contains one intentionally broken fixture for every artifact type. The failures cover schema and deterministic rules such as stage mismatch, missing bounds, narrow critical paths, out-of-scope terrain, duplicate IDs, invalid quality tiers, QA status inconsistency, incorrect probability totals, and invalid effect priority.

## `manifests/`

Contains the deterministic Studio build manifest assembled from the valid World 1 artifacts. It records exact source hashes, ordered allowlisted operations, planned budgets, runtime configuration, and rollback requirements. It is safe for dry-run validation but intentionally not release-ready while registry audio remains placeholder content.

## Regeneration

```powershell
python tools/generate_world01_fixtures.py
python tools/generate_world01_manifest.py
```

Generation is deterministic and safe to run repeatedly.
