# Contract Validator

## Setup

```powershell
python -m pip install -e .
```

## Validate the full golden build

```powershell
python -m validation fixtures/world_01_shadow_forest
```

Expected result:

```text
PASS: 9 artifact(s), 0 issue(s)
```

## Validate one artifact

```powershell
python -m validation fixtures/world_01_shadow_forest/02_layout.json
```

## Machine-readable report

```powershell
python -m validation fixtures/world_01_shadow_forest --json
```

The command returns exit code `0` on success, `1` for validation failures, and `2` for invalid input or setup errors.

## Run tests

```powershell
python -m unittest discover -s tests -v
```

## Implemented deterministic checks

- envelope `artifactType` / `stageId` / `payload.kind` consistency;
- complete pipeline and one artifact per type;
- build ID, schema version, and seed consistency;
- duplicate IDs within semantic collections;
- finite numbers and safe-integer ceiling;
- valid AABBs, world containment, and explicit symmetric overlaps;
- graph reachability from exactly one spawn zone;
- connection, path, zone, marker, instance, light, soundscape, and VFX references;
- 10-stud minimum width for critical squad paths;
- terrain operation size/scope and foundation references;
- collidable primitive AABBs against clearance volumes, including rotated bounds;
- currency references and exactly 10,000 basis points per gacha pool;
- required 5/15/30/60-minute economy simulation checkpoints;
- QA approval/readiness consistency.

Validators produce stable rule codes and JSON pointers suitable for owner-addressed QA patches.
