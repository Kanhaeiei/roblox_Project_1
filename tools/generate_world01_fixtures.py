"""Generate deterministic World 1 golden artifacts and one invalid fixture per type."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALID_DIR = ROOT / "fixtures" / "world_01_shadow_forest"
INVALID_DIR = ROOT / "fixtures" / "invalid"
BUILD_ID = "world01-shadow-forest-golden"
SEED = 48151623
DEPENDENCIES = {
    "gameConcept": (),
    "director": ("gameConcept",),
    "economy": ("gameConcept",),
    "layout": ("director",),
    "terrain": ("director", "layout"),
    "props": ("layout", "terrain", "economy"),
    "lighting": ("director", "props"),
    "vfxAudio": ("director", "props", "economy"),
    "qa": ("gameConcept", "director", "economy", "layout", "terrain", "props", "lighting", "vfxAudio"),
}


def envelope(artifact_type: str, stage_id: str, payload: dict) -> dict:
    return {
        "schemaVersion": "2.0.0",
        "artifactType": artifact_type,
        "buildId": BUILD_ID,
        "stageId": stage_id,
        "revision": 1,
        "seed": SEED,
        "inputArtifactHashes": [],
        "payload": payload,
        "assumptions": ["Golden fixture uses allowlisted placeholder registry keys, not release asset IDs."],
        "warnings": [],
    }


BUDGETS = {
    "instances": 6000,
    "baseParts": 3500,
    "uniqueMeshIds": 150,
    "uniqueTextureIds": 220,
    "shadowCastingLights": 8,
    "activeParticleEmittersNearPlayer": 24,
    "particlesPerSecondNearPlayer": 350,
    "transparentOverlapLayers": 4,
    "clientFrameTargetFps": 30,
}

WORLD_BOUNDS = {"min": [-128, -16, -128], "max": [128, 80, 128]}


def concept() -> dict:
    return envelope(
        "gameConcept",
        "00_concept",
        {
            "kind": "gameConcept",
            "status": "READY",
            "title": "Shadow Army Rebirth — E-Rank Shadow Forest",
            "audience": "Roblox action-simulator players on mobile, PC, and console",
            "fantasy": "Defeat enemies and command their shadows as a visible, rapidly growing army.",
            "differentiator": "Legendary boss shadows are earned through readable fights and guaranteed first-clear ARISE rituals.",
            "loops": [
                {
                    "id": "loop_hit_reward",
                    "cadenceSeconds": 5,
                    "steps": ["choose target", "shadows strike", "loot returns"],
                    "playerDecision": "Select the priority enemy and trigger burst timing.",
                },
                {
                    "id": "loop_farm_upgrade",
                    "cadenceSeconds": 60,
                    "steps": ["clear pack", "collect mana", "buy deterministic upgrade", "equip squad"],
                    "playerDecision": "Spend on guaranteed power or an earned-currency summon.",
                },
                {
                    "id": "loop_boss_arise",
                    "cadenceSeconds": 480,
                    "steps": ["prepare squad", "break boss stance", "defeat boss", "perform arise"],
                    "playerDecision": "Dodge the tell and commit burst during the break window.",
                },
            ],
            "ftue": [
                {"stepId": "ftue_spawn", "deadlineSeconds": 5, "eventName": "ftue_spawned", "successCondition": "Player gains control facing the first enemy."},
                {"stepId": "ftue_kill", "deadlineSeconds": 20, "eventName": "ftue_first_kill", "successCondition": "First enemy dies."},
                {"stepId": "ftue_upgrade", "deadlineSeconds": 60, "eventName": "ftue_first_upgrade", "successCondition": "Player buys guaranteed damage."},
                {"stepId": "ftue_miniboss", "deadlineSeconds": 240, "eventName": "ftue_miniboss_clear", "successCondition": "Mini-boss is defeated."},
                {"stepId": "ftue_arise", "deadlineSeconds": 600, "eventName": "ftue_first_arise", "successCondition": "Guaranteed first boss shadow joins the squad."},
                {"stepId": "ftue_rebirth_goal", "deadlineSeconds": 900, "eventName": "ftue_goal_revealed", "successCondition": "Rebirth reward and requirements are visible."},
            ],
            "landmarkIds": ["zone_spawn_hub", "zone_farm_lane", "zone_miniboss", "zone_boss_arena", "zone_rebirth_gate"],
            "accessibility": ["non-color rarity icons", "reduced motion", "reduced flashes", "touch and controller parity"],
            "monetizationBoundaries": ["no shop before first upgrade", "no paid first-clear extraction", "no fake urgency", "paid randomness disabled for MVP"],
            "prototypeRisks": ["auto-combat may feel passive", "squad crowding may hide boss tells", "three-order world jumps may outrun safe integers"],
        },
    )


def director() -> dict:
    briefs = [
        ("zone_spawn_hub", "spawn", "Teach targeting and upgrading", [100, 48], "First enemy and distant gate visible", 0),
        ("zone_farm_lane", "farm", "Fast unobstructed pack farming", [120, 92], "Mini-boss silhouette anchors the route", 1),
        ("zone_miniboss", "miniboss", "Teach one telegraphed break mechanic", [90, 30], "Boss gate visible after clear", 2),
        ("zone_boss_arena", "boss", "First mastery fight and ARISE climax", [100, 55], "Boss remains readable from arena entry", 3),
        ("zone_rebirth_gate", "gate", "Preview the next world and rebirth reward", [50, 23], "Portal is visible behind the boss", 4),
    ]
    return envelope(
        "director",
        "01_director",
        {
            "kind": "director",
            "status": "READY",
            "worldId": "world_01_shadow_forest",
            "worldBounds": WORLD_BOUNDS,
            "theme": "Moonlit E-Rank forest invaded by violet shadow corruption",
            "paletteTokens": ["shadow_black", "moon_blue", "mana_cyan", "arise_violet", "danger_crimson"],
            "zoneBriefs": [
                {"zoneId": zone_id, "role": role, "gameplayPurpose": purpose, "targetFootprintStuds": footprint, "sightlineGoal": sightline, "order": order}
                for zone_id, role, purpose, footprint, sightline, order in briefs
            ],
            "budgets": BUDGETS,
            "qualityTiers": ["low", "medium", "high"],
            "streamingStrategy": "enabled_spatial",
            "experienceConstraints": ["first kill within 20 seconds", "critical routes at least 10 studs", "boss telegraphs outrank cosmetics"],
        },
    )


def layout() -> dict:
    zones = [
        {"zoneId": "zone_spawn_hub", "role": "spawn", "bounds": {"min": [-50, 0, -120], "max": [50, 30, -72]}, "allowedOverlapZoneIds": []},
        {"zoneId": "zone_farm_lane", "role": "farm", "bounds": {"min": [-60, 0, -72], "max": [60, 30, 20]}, "allowedOverlapZoneIds": []},
        {"zoneId": "zone_miniboss", "role": "miniboss", "bounds": {"min": [-45, 0, 20], "max": [45, 35, 50]}, "allowedOverlapZoneIds": []},
        {"zoneId": "zone_boss_arena", "role": "boss", "bounds": {"min": [-50, 0, 50], "max": [50, 40, 105]}, "allowedOverlapZoneIds": []},
        {"zoneId": "zone_rebirth_gate", "role": "gate", "bounds": {"min": [-25, 0, 105], "max": [25, 35, 128]}, "allowedOverlapZoneIds": []},
    ]
    connections = [
        {"id": "conn_spawn_farm", "fromZoneId": "zone_spawn_hub", "toZoneId": "zone_farm_lane", "bidirectional": True, "traversalMethod": "walk"},
        {"id": "conn_farm_miniboss", "fromZoneId": "zone_farm_lane", "toZoneId": "zone_miniboss", "bidirectional": True, "traversalMethod": "walk"},
        {"id": "conn_miniboss_boss", "fromZoneId": "zone_miniboss", "toZoneId": "zone_boss_arena", "bidirectional": True, "traversalMethod": "walk"},
        {"id": "conn_boss_gate", "fromZoneId": "zone_boss_arena", "toZoneId": "zone_rebirth_gate", "bidirectional": True, "traversalMethod": "walk"},
    ]
    paths = [
        {"id": "path_spawn_farm", "connectionId": "conn_spawn_farm", "widthStuds": 14, "waypoints": [[0, 1, -96], [0, 1, -72]], "critical": True},
        {"id": "path_farm_miniboss", "connectionId": "conn_farm_miniboss", "widthStuds": 16, "waypoints": [[0, 1, -25], [0, 1, 20]], "critical": True},
        {"id": "path_miniboss_boss", "connectionId": "conn_miniboss_boss", "widthStuds": 14, "waypoints": [[0, 1, 35], [0, 1, 50]], "critical": True},
        {"id": "path_boss_gate", "connectionId": "conn_boss_gate", "widthStuds": 12, "waypoints": [[0, 1, 78], [0, 1, 105], [0, 1, 116]], "critical": True},
    ]
    clearances = [
        {"id": "clear_spawn", "purpose": "spawn", "bounds": {"min": [-12, 0.25, -108], "max": [12, 12, -84]}},
        {"id": "clear_main_route", "purpose": "squad", "bounds": {"min": [-7, 0.25, -84], "max": [7, 14, 58]}},
        {"id": "clear_boss_arena", "purpose": "telegraph", "bounds": {"min": [-40, 0.25, 58], "max": [40, 24, 98]}},
        {"id": "clear_gate_route", "purpose": "camera", "bounds": {"min": [-6, 0.25, 98], "max": [6, 16, 124]}},
    ]
    markers = [
        {"id": "marker_player_spawn", "type": "player_spawn", "zoneId": "zone_spawn_hub", "transform": {"position": [0, 2, -102], "orientationDegrees": [0, 0, 0]}},
        {"id": "marker_upgrade_altar", "type": "upgrade", "zoneId": "zone_spawn_hub", "transform": {"position": [-20, 1, -92], "orientationDegrees": [0, 20, 0]}},
        {"id": "marker_summon_altar", "type": "summon_altar", "zoneId": "zone_spawn_hub", "transform": {"position": [20, 1, -92], "orientationDegrees": [0, -20, 0]}},
        {"id": "marker_enemy_cluster_a", "type": "enemy_cluster", "zoneId": "zone_farm_lane", "transform": {"position": [-24, 1, -48], "orientationDegrees": [0, 0, 0]}},
        {"id": "marker_enemy_cluster_b", "type": "enemy_cluster", "zoneId": "zone_farm_lane", "transform": {"position": [24, 1, -18], "orientationDegrees": [0, 180, 0]}},
        {"id": "marker_miniboss", "type": "miniboss", "zoneId": "zone_miniboss", "transform": {"position": [0, 2, 36], "orientationDegrees": [0, 180, 0]}},
        {"id": "marker_boss", "type": "boss", "zoneId": "zone_boss_arena", "transform": {"position": [0, 3, 82], "orientationDegrees": [0, 180, 0]}},
        {"id": "marker_rebirth_gate", "type": "gate", "zoneId": "zone_rebirth_gate", "transform": {"position": [0, 6, 116], "orientationDegrees": [0, 180, 0]}},
        {"id": "marker_foundation_spawn", "type": "foundation", "zoneId": "zone_spawn_hub", "transform": {"position": [0, 0, -96], "orientationDegrees": [0, 0, 0]}},
        {"id": "marker_foundation_boss", "type": "foundation", "zoneId": "zone_boss_arena", "transform": {"position": [0, 0, 78], "orientationDegrees": [0, 0, 0]}},
    ]
    return envelope(
        "layout",
        "02_layout",
        {
            "kind": "layout",
            "status": "READY",
            "worldBounds": WORLD_BOUNDS,
            "zones": zones,
            "connections": connections,
            "paths": paths,
            "clearanceVolumes": clearances,
            "markers": markers,
            "sightlineAssertions": ["marker_player_spawn sees marker_enemy_cluster_a", "marker_miniboss sees marker_boss", "marker_boss sees marker_rebirth_gate"],
        },
    )


def terrain() -> dict:
    return envelope(
        "terrain",
        "03_terrain",
        {
            "kind": "terrain",
            "status": "READY",
            "scope": WORLD_BOUNDS,
            "replacePolicy": "generated_namespace_only",
            "operations": [
                {"id": "terrain_base", "action": "fill", "shape": "block", "materialToken": "ground_dark", "transform": {"position": [0, -4, 0], "orientationDegrees": [0, 0, 0]}, "size": [256, 8, 256]},
                {"id": "terrain_spawn_pad", "action": "fill", "shape": "block", "materialToken": "stone_moonlit", "transform": {"position": [0, -1, -96], "orientationDegrees": [0, 0, 0]}, "size": [100, 2, 48]},
                {"id": "terrain_boss_pad", "action": "fill", "shape": "cylinder", "materialToken": "stone_corrupted", "transform": {"position": [0, -1, 78], "orientationDegrees": [0, 0, 90]}, "size": [100, 2, 100]},
            ],
            "foundationMarkerIds": ["marker_foundation_spawn", "marker_foundation_boss"],
            "waterContainmentIds": [],
        },
    )


def primitive(instance_id: str, position: list[float], size: list[float], *, collide: bool, category: str, material: str, color: str, tags: list[str]) -> dict:
    return {
        "kind": "primitive",
        "id": instance_id,
        "className": "Part",
        "parentCategory": category,
        "size": size,
        "transform": {"position": position, "orientationDegrees": [0, 0, 0]},
        "materialToken": material,
        "colorToken": color,
        "anchored": True,
        "canCollide": collide,
        "canTouch": False,
        "canQuery": collide,
        "castShadow": collide,
        "tags": tags,
    }


def props() -> dict:
    instances = [
        primitive("floor_spawn", [0, -1, -96], [100, 2, 48], collide=True, category="Structures", material="stone_moonlit", color="moon_blue", tags=["generated", "foundation"]),
        primitive("floor_farm", [0, -1, -26], [120, 2, 92], collide=True, category="Structures", material="ground_dark", color="shadow_black", tags=["generated", "foundation"]),
        primitive("floor_miniboss", [0, -1, 35], [90, 2, 30], collide=True, category="Structures", material="stone_corrupted", color="shadow_black", tags=["generated", "foundation"]),
        primitive("floor_boss", [0, -1, 77.5], [100, 2, 55], collide=True, category="Structures", material="stone_corrupted", color="shadow_black", tags=["generated", "foundation"]),
        primitive("floor_gate", [0, -1, 116.5], [50, 2, 23], collide=True, category="Structures", material="stone_moonlit", color="moon_blue", tags=["generated", "foundation"]),
        primitive("upgrade_altar", [-20, 2, -92], [8, 4, 8], collide=False, category="Gameplay", material="stone_moonlit", color="mana_cyan", tags=["interaction", "upgrade"]),
        primitive("summon_altar", [20, 2, -92], [8, 4, 8], collide=False, category="Gameplay", material="stone_moonlit", color="arise_violet", tags=["interaction", "summon"]),
        primitive("miniboss_totem", [18, 5, 38], [4, 10, 4], collide=True, category="Structures", material="stone_corrupted", color="danger_crimson", tags=["landmark"]),
        primitive("boss_ritual_socket", [0, 0.2, 82], [24, 0.2, 24], collide=False, category="Gameplay", material="neon", color="arise_violet", tags=["vfx_socket", "boss"]),
        primitive("rebirth_portal_socket", [0, 8, 118], [18, 16, 1], collide=False, category="LightingProps", material="neon", color="mana_cyan", tags=["vfx_socket", "portal"]),
        primitive("spawn_beacon", [0, 6, -116], [4, 12, 4], collide=True, category="Structures", material="stone_moonlit", color="moon_blue", tags=["landmark"]),
    ]
    estimate = dict(BUDGETS)
    estimate.update({"instances": len(instances), "baseParts": len(instances), "uniqueMeshIds": 0, "uniqueTextureIds": 0, "shadowCastingLights": 0, "activeParticleEmittersNearPlayer": 0, "particlesPerSecondNearPlayer": 0, "transparentOverlapLayers": 1, "clientFrameTargetFps": 30})
    return envelope(
        "props",
        "04_props",
        {
            "kind": "props",
            "status": "READY",
            "namespace": "world01_shadow_forest",
            "instances": instances,
            "gameplayMarkerHosts": {
                "marker_upgrade_altar": "upgrade_altar",
                "marker_summon_altar": "summon_altar",
                "marker_boss": "boss_ritual_socket",
                "marker_rebirth_gate": "rebirth_portal_socket",
            },
            "budgetEstimate": estimate,
        },
    )


def lighting() -> dict:
    profiles = [
        {"tier": "low", "clockTime": 21.0, "brightness": 1.5, "ambient": [45, 50, 70], "outdoorAmbient": [55, 60, 85], "atmosphereDensity": 0.18, "bloomIntensity": 0.2, "contrast": 0.05, "saturation": 0.0},
        {"tier": "medium", "clockTime": 21.0, "brightness": 1.8, "ambient": [35, 40, 65], "outdoorAmbient": [48, 55, 82], "atmosphereDensity": 0.24, "bloomIntensity": 0.45, "contrast": 0.10, "saturation": 0.05},
        {"tier": "high", "clockTime": 21.0, "brightness": 2.0, "ambient": [30, 35, 60], "outdoorAmbient": [45, 52, 80], "atmosphereDensity": 0.28, "bloomIntensity": 0.65, "contrast": 0.12, "saturation": 0.08},
    ]
    return envelope(
        "lighting",
        "05_lighting",
        {
            "kind": "lighting",
            "status": "READY",
            "profiles": profiles,
            "localLights": [
                {"id": "light_boss_ritual", "socketInstanceId": "boss_ritual_socket", "type": "point", "colorToken": "arise_violet", "range": 28, "brightness": 1.5, "castsShadows": False},
                {"id": "light_rebirth_portal", "socketInstanceId": "rebirth_portal_socket", "type": "surface", "colorToken": "mana_cyan", "range": 32, "brightness": 2.0, "castsShadows": False},
            ],
            "readabilityTargets": ["enemy silhouettes remain readable", "boss danger red remains distinct", "critical path visible on low tier"],
            "fallbackRules": ["disable decorative shadows first", "reduce bloom and local-light range on low tier"],
        },
    )


def economy() -> dict:
    return envelope(
        "economy",
        "07_economy",
        {
            "kind": "economy",
            "status": "READY",
            "safeIntegerCeiling": 9_000_000_000_000_000,
            "currencies": [
                {"id": "mana", "scope": "world", "sources": ["enemy defeats", "mana crystals"], "sinks": ["guaranteed upgrades", "earned summon"], "cap": 1_000_000_000, "targetTimeToAffordSeconds": 45},
                {"id": "essence", "scope": "account", "sources": ["duplicates", "achievements"], "sinks": ["chosen fusion", "evolution"], "cap": 10_000_000, "targetTimeToAffordSeconds": 300},
                {"id": "rebirth_sigils", "scope": "account", "sources": ["rebirth", "mastery milestones"], "sinks": ["permanent mastery"], "cap": 1_000_000, "targetTimeToAffordSeconds": 1200},
                {"id": "soul_shards", "scope": "premium", "sources": ["boss challenges", "optional purchase"], "sinks": ["cosmetics", "non-random quantified boosts"], "cap": 1_000_000, "targetTimeToAffordSeconds": 1800},
            ],
            "formulas": [
                {"id": "world_base_power", "expression": "100 * 1000^(worldIndex-1)", "inputs": ["world_index"], "outputUnit": "power"},
                {"id": "rebirth_cost", "expression": "round(25000 * 6^r * 1.18^(max(0,r-5)^1.35))", "inputs": ["rebirth_count"], "outputUnit": "mana"},
                {"id": "rebirth_power", "expression": "1 + 0.50*r + 0.05*r^2", "inputs": ["rebirth_count"], "outputUnit": "multiplier"},
            ],
            "worldBands": [{"worldId": "world_01_shadow_forest", "basePower": 100, "targetDurationSeconds": 1200}],
            "rebirth": {"costFormulaId": "rebirth_cost", "powerFormulaId": "rebirth_power", "baseSquadSlots": 3, "earnedSlotsPerMilestone": 2, "firstTargetSeconds": 1200},
            "gachaPools": [
                {
                    "id": "pool_shadow_forest",
                    "currencyId": "mana",
                    "cost": 100,
                    "paidRandomEligible": False,
                    "outcomes": [
                        {"definitionId": "shadow_imp", "rateBasisPoints": 6500},
                        {"definitionId": "shadow_hound", "rateBasisPoints": 2500},
                        {"definitionId": "shadow_mage", "rateBasisPoints": 900},
                        {"definitionId": "shadow_footman", "rateBasisPoints": 100},
                    ],
                    "pityCounterKey": "pity_shadow_forest_legendary",
                    "pityThreshold": 50,
                    "duplicateProtection": "Duplicates award essence and choice-progress toward a selected soldier.",
                }
            ],
            "resetManifest": {"reset": ["Currencies.Mana", "Progression.WorldUpgrades"], "keep": ["Inventory.Shadows", "Entitlements", "Cosmetics", "Pity"], "transform": ["Progression.RebirthCount += 1", "Currencies.RebirthSigils += reward"]},
            "playerData": {"schemaVersion": 1, "defaults": {"Currencies": {"Mana": 0, "Essence": 0, "RebirthSigils": 0, "SoulShards": 0}, "Progression": {"RebirthCount": 0, "WorldId": "world_01_shadow_forest"}, "Inventory": {"Shadows": []}, "Pity": {}, "Entitlements": {}, "Settings": {"ReducedMotion": False}}, "migrations": [], "sessionPolicy": "Server-owned session lease with conflict-safe update and graceful read-only fallback."},
            "simulations": [
                {"elapsedSeconds": 300, "expectedPower": 2_500, "expectedCurrency": 3_000, "unlockedMilestones": ["mini_boss_ready"]},
                {"elapsedSeconds": 900, "expectedPower": 50_000, "expectedCurrency": 18_000, "unlockedMilestones": ["first_arise", "rebirth_goal_visible"]},
                {"elapsedSeconds": 1800, "expectedPower": 250_000, "expectedCurrency": 80_000, "unlockedMilestones": ["first_rebirth"]},
                {"elapsedSeconds": 3600, "expectedPower": 1_200_000, "expectedCurrency": 400_000, "unlockedMilestones": ["world_one_mastery"]},
            ],
            "invariants": ["currencies are non-negative integers", "first boss clear guarantees ARISE", "all gacha outcomes total 10000 basis points", "owned boss shadows survive rebirth"],
            "remoteRules": [
                {"intent": "request_target", "ratePerSecond": 8, "validations": ["type", "enemy ownership", "range", "player alive"]},
                {"intent": "request_upgrade", "ratePerSecond": 2, "validations": ["type", "server price", "balance", "upgrade state"]},
                {"intent": "request_arise", "ratePerSecond": 1, "validations": ["boss clear", "first-clear state", "distance", "not already owned"]},
            ],
            "analyticsEvents": ["ftue_spawned", "ftue_first_kill", "ftue_first_upgrade", "ftue_miniboss_clear", "ftue_first_arise", "ftue_first_rebirth"],
        },
    )


def vfx_audio() -> dict:
    return envelope(
        "vfxAudio",
        "08_vfx_audio",
        {
            "kind": "vfxAudio",
            "status": "READY",
            "zoneSoundscapes": [
                {"zoneId": "zone_spawn_hub", "musicRegistryKey": "music_shadow_hub", "ambientRegistryKeys": ["ambience_forest_night"], "crossfadeSeconds": 2.0},
                {"zoneId": "zone_boss_arena", "musicRegistryKey": "music_boss_blood_knight", "ambientRegistryKeys": ["ambience_shadow_rumble"], "crossfadeSeconds": 1.5},
            ],
            "effectRecipes": [
                {"id": "fx_first_arise", "eventName": "boss_arise_approved", "priority": "reward", "socketIds": ["boss_ritual_socket", "marker_boss"], "layers": ["particle", "beam", "highlight", "sound", "camera", "ui", "animation"], "qualityTiers": ["low", "medium", "high"], "reducedMotionVariant": "No camera shake; shorter mist and static ownership card.", "skippable": True},
                {"id": "fx_rebirth_gate", "eventName": "rebirth_gate_ready", "priority": "reward", "socketIds": ["rebirth_portal_socket"], "layers": ["particle", "light", "sound", "ui"], "qualityTiers": ["low", "medium", "high"], "reducedMotionVariant": "Static portal glow with no swirl.", "skippable": False},
            ],
            "budgetEstimate": {"nearbyEmitters": 12, "particlesPerSecond": 180, "transparencyLayers": 3, "simultaneousSounds": 12},
            "accessibilityProfiles": ["default", "reduced_motion", "reduced_flashes", "low_vfx"],
        },
    )


def qa() -> dict:
    return envelope(
        "qa",
        "06_qa",
        {
            "kind": "qa",
            "status": "APPROVED",
            "validatorReportHashes": ["sha256:" + "f" * 64],
            "domainSummaries": [
                {"domain": domain, "passed": True, "evidence": "Golden fixture validated by schema and deterministic checks."}
                for domain in ["contract", "experience", "spatial", "economy", "security", "performance", "accessibility", "release"]
            ],
            "issues": [],
            "acceptedRisks": [],
            "readyForStudioBridge": True,
        },
    )


def build_artifacts() -> dict[str, dict]:
    artifacts = {
        "00_game_concept.json": concept(),
        "01_director.json": director(),
        "02_layout.json": layout(),
        "03_terrain.json": terrain(),
        "04_props.json": props(),
        "05_lighting.json": lighting(),
        "06_qa.json": qa(),
        "07_economy.json": economy(),
        "08_vfx_audio.json": vfx_audio(),
    }
    by_type = {artifact["artifactType"]: artifact for artifact in artifacts.values()}
    hashes: dict[str, str] = {}
    for artifact_type, dependencies in DEPENDENCIES.items():
        artifact = by_type[artifact_type]
        artifact["inputArtifactHashes"] = [hashes[dependency] for dependency in dependencies]
        hashes[artifact_type] = canonical_hash(artifact)
    return artifacts


def canonical_hash(value: dict) -> str:
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def invalid_artifacts(valid: dict[str, dict]) -> dict[str, dict]:
    result = {name: copy.deepcopy(artifact) for name, artifact in valid.items()}
    result["00_game_concept.json"]["stageId"] = "01_director"
    del result["01_director.json"]["payload"]["worldBounds"]
    result["02_layout.json"]["payload"]["paths"][0]["widthStuds"] = 6
    result["03_terrain.json"]["payload"]["operations"][0]["transform"]["position"] = [500, 0, 500]
    result["04_props.json"]["payload"]["instances"][1]["id"] = result["04_props.json"]["payload"]["instances"][0]["id"]
    result["05_lighting.json"]["payload"]["profiles"][0]["tier"] = "ultra"
    result["06_qa.json"]["payload"]["readyForStudioBridge"] = False
    result["07_economy.json"]["payload"]["gachaPools"][0]["outcomes"][0]["rateBasisPoints"] = 6499
    result["08_vfx_audio.json"]["payload"]["effectRecipes"][0]["priority"] = "cinematic"
    return result


def write_artifacts(directory: Path, artifacts: dict[str, dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, artifact in artifacts.items():
        (directory / name).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    valid = build_artifacts()
    write_artifacts(VALID_DIR, valid)
    write_artifacts(INVALID_DIR, invalid_artifacts(valid))
    print(f"Generated {len(valid)} valid and {len(valid)} invalid fixtures.")


if __name__ == "__main__":
    main()
