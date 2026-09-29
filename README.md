# Shadow Army Rebirth — Design and Generation Specification

Version 2.0 is the source of truth for an anime minion battler built for Roblox. The repository defines the player experience, economy, generated-world contracts, validation gates, and the boundary between the build pipeline and the live game.

This repository is a specification package. It does **not** yet contain a runnable game, orchestrator, Studio plugin, or production assets.

## Product promise

Within the first minute, a new player commands a visible shadow squad, destroys an enemy, receives an exaggerated power increase, and sees the boss they will eventually extract. The fantasy is not “wait for numbers”; it is “I am becoming the Shadow Monarch, and my army proves it.”

## Source-of-truth order

When documents disagree, use this order:

1. `game_concept.md` — player promise, progression, economy, ethics, and content template.
2. `agent.md` — pipeline architecture, ownership, validation, security, and runtime boundary.
3. `schemas/pipeline.schema.json` — machine-readable interchange contract.
4. `agents/*.md` — agent behavior and domain-specific acceptance criteria.
5. Examples — illustrative only; examples never override schemas or design rules.

Every generated artifact must include `schemaVersion`, `buildId`, and deterministic IDs. Breaking contract changes increment the major version.

## Pipeline

```mermaid
flowchart TD
  Prompt[Product brief] --> Concept[00 Product & Creative]
  Concept --> Director[01 World Director]
  Concept --> Economy[07 Economy & Progression]
  Director --> Layout[02 Layout]
  Director --> Terrain[03 Terrain]
  Layout --> Props[04 Props & Gameplay Markers]
  Terrain --> Props
  Economy --> Props
  Props --> Lighting[05 Lighting]
  Props --> VFX[08 VFX & Audio]
  Economy --> VFX
  Director --> Assemble[Deterministic Assembler]
  Economy --> Assemble
  Layout --> Assemble
  Terrain --> Assemble
  Props --> Assemble
  Lighting --> Assemble
  VFX --> Assemble
  Assemble --> Validate[Schema + deterministic validators]
  Validate --> QA[06 QA gate]
  QA -->|patch requests, max 3 rounds| Director
  QA -->|approved| Manifest[Build Manifest]
  Manifest --> Bridge[Studio Bridge]
```

LLMs propose bounded artifacts. Code performs schema validation, graph checks, geometry checks, budget accounting, probability totals, referential integrity, and security linting. QA cannot approve a build that fails a deterministic validator.

## Repository map

```text
roblox-map-builder/
├── README.md
├── game_concept.md
├── agent.md
├── docs/
│   ├── implementation-readiness.md
│   └── roblox-references.md
├── schemas/
│   └── pipeline.schema.json
├── validation/              # Python schema + deterministic validator CLI
├── fixtures/                # Valid World 1 golden build and invalid fixtures
├── tests/                   # Contract and cross-artifact tests
├── tools/                   # Deterministic fixture generator
├── pyproject.toml
└── agents/
    ├── README.md
    ├── 00_creative_ideation_agent.md
    ├── 01_director_agent.md
    ├── 02_layout_planner_agent.md
    ├── 03_terrain_shaper_agent.md
    ├── 04_prop_placer_agent.md
    ├── 05_lighting_atmosphere_agent.md
    ├── 06_qa_auditor_agent.md
    ├── 07_economy_systems_agent.md
    └── 08_vfx_audio_agent.md
```

## MVP definition

The first playable vertical slice is one 256×256-stud island with:

- a spawn-to-first-kill time below 20 seconds;
- one free starter shadow and no forced shop interaction;
- one farm lane, one mini-boss, one boss arena, and one visible next-world gate;
- one server-authoritative combat loop, one gacha pool funded only by earned soft currency, and one rebirth;
- mobile, keyboard/mouse, and gamepad input;
- save migration, receipt idempotency, remote validation, analytics funnels, and performance profiling;
- an approved build manifest reproducible from a fixed seed.

## Definition of done for specifications

- All IDs resolve across artifacts.
- All random reward tables total exactly 100% in integer basis points.
- All currencies have at least one source, one sink, and a target time-to-afford.
- All required paths are connected and have clearance volumes.
- Gameplay state is server-authoritative; clients request intents and render presentation.
- Economy values use safe integer units; formatting is separate from storage.
- Monetization is transparent, age/location policy aware, and never required to complete onboarding.
- QA covers economy, terrain, VFX/audio, security, accessibility, performance, and data migration.

## Implementation order

1. Lock `pipeline.schema.json` and build validators/fixtures.
2. Implement a seeded orchestrator and immutable artifact store.
3. Implement Studio Bridge dry-run, diff preview, undo, and allowlisted instance/property creation.
4. Build the World 1 vertical slice with placeholder art.
5. Instrument the onboarding and economy funnels before scaling content.
6. Profile on low-end mobile and revise measured budgets before adding worlds.

## Validator quick start

```powershell
python -m pip install -e .
python tools/generate_world01_fixtures.py
python -m validation fixtures/world_01_shadow_forest
python -m unittest discover -s tests -v
```

The checked-in World 1 fixture is the hand-authored golden contract for the E-Rank Shadow Forest vertical slice. See `validation/README.md` and `fixtures/README.md`.
