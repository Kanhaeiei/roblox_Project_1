# Agent Specifications

These files define reasoning roles, not independent sources of truth. All agents use the envelope and payload definitions in `../schemas/pipeline.schema.json` and the ownership rules in `../agent.md`.

## Shared operating rules

1. Return one JSON artifact only in production mode; prose belongs in `assumptions` or `warnings`.
2. Never invent an upstream value. Reference stable IDs or request a patch from the owner.
3. Prefer a small, testable artifact over a large speculative one.
4. Mark uncertainty and placeholder assets explicitly. Placeholders cannot pass release QA.
5. Use the supplied `buildId`, `schemaVersion`, and `seed`; do not generate timestamps or random IDs.
6. Obey bounds, budgets, accessibility, security, economy, and platform-policy constraints.
7. LLM arithmetic is provisional. Deterministic validators calculate totals and derived values.
8. Patch requests identify `ownerStageId`, `ruleId`, and `jsonPointer`.

## Roster

| Stage | File | Owns | Does not own |
|---|---|---|---|
| 00 | `00_creative_ideation_agent.md` | product promise, audience, loops, emotional beats, FTUE | coordinates, prices, assets |
| 01 | `01_director_agent.md` | world envelope, art direction, provisional budgets, zone briefs | exact placement, economy |
| 02 | `02_layout_planner_agent.md` | exact bounds, connections, paths, clearance, markers | art props, rewards |
| 03 | `03_terrain_shaper_agent.md` | terrain operations, foundations, water containment | prop placement |
| 04 | `04_prop_placer_agent.md` | instances, prefabs, gameplay marker hosts | gameplay logic, arbitrary assets |
| 05 | `05_lighting_atmosphere_agent.md` | quality-tier lighting and post-processing | global geometry |
| 07 | `07_economy_systems_agent.md` | formulas, tables, reset/save schema, simulation | map coordinates |
| 08 | `08_vfx_audio_agent.md` | effect recipes, sound roles, sensory budgets | authoritative rewards/damage |
| 06 | `06_qa_auditor_agent.md` | verdict, accepted risk, owner-addressed patches | rewriting other artifacts |

## Failure behavior

If required input is absent, return `status: "BLOCKED_INPUT"` with missing JSON pointers. Do not fill gaps from examples. If constraints conflict, preserve player safety/security/policy first, then playability, then performance, then aesthetics.

## Production invocation template

```text
SYSTEM: <agent specification>
SCHEMA: <relevant $defs from pipeline.schema.json>
INPUT ARTIFACTS: <validated JSON>
TASK: Produce one artifact for the supplied build and seed.
OUTPUT: JSON only. No markdown fences.
```
