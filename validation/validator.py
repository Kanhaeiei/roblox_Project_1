from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator


STAGE_BY_TYPE = {
    "gameConcept": "00_concept",
    "director": "01_director",
    "layout": "02_layout",
    "terrain": "03_terrain",
    "props": "04_props",
    "lighting": "05_lighting",
    "qa": "06_qa",
    "economy": "07_economy",
    "vfxAudio": "08_vfx_audio",
}

REQUIRED_ARTIFACT_TYPES = frozenset(STAGE_BY_TYPE)
SAFE_INTEGER_CEILING = 9_000_000_000_000_000
ECONOMY_CHECKPOINTS = {300, 900, 1800, 3600}


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    path: str
    message: str
    artifact: str | None = None


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    artifact_count: int = 0

    @property
    def ok(self) -> bool:
        return not any(issue.severity in {"ERROR", "BLOCKER", "CRITICAL"} for issue in self.issues)

    def add(self, code: str, path: str, message: str, *, artifact: str | None = None, severity: str = "ERROR") -> None:
        self.issues.append(ValidationIssue(severity, code, path, message, artifact))

    def extend(self, issues: Iterable[ValidationIssue]) -> None:
        self.issues.extend(issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "artifactCount": self.artifact_count,
            "issueCount": len(self.issues),
            "issues": [asdict(issue) for issue in self.issues],
        }


class ArtifactValidator:
    def __init__(self, schema: Mapping[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)
        self.schema = dict(schema)
        self.schema_validator = Draft202012Validator(self.schema)

    @classmethod
    def from_schema_file(cls, path: Path | str) -> "ArtifactValidator":
        schema_path = Path(path)
        return cls(json.loads(schema_path.read_text(encoding="utf-8")))

    def validate_file(self, path: Path | str) -> ValidationReport:
        artifact_path = Path(path)
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        return self.validate_artifact(artifact, name=artifact_path.name)

    def validate_artifact(self, artifact: Any, *, name: str = "artifact.json") -> ValidationReport:
        report = ValidationReport(artifact_count=1)
        self._validate_schema_and_envelope(artifact, name, report)
        if not report.ok:
            return report
        self._validate_single_artifact(artifact, name, report)
        return report

    def validate_directory(self, path: Path | str, *, require_complete: bool = True) -> ValidationReport:
        directory = Path(path)
        files = sorted(p for p in directory.glob("*.json") if p.is_file())
        if not files:
            raise ValueError(f"No JSON artifacts found in {directory}")

        report = ValidationReport(artifact_count=len(files))
        artifacts: dict[str, dict[str, Any]] = {}
        names: dict[str, str] = {}

        for file_path in files:
            artifact = json.loads(file_path.read_text(encoding="utf-8"))
            self._validate_schema_and_envelope(artifact, file_path.name, report)
            artifact_type = artifact.get("artifactType")
            if not isinstance(artifact_type, str):
                continue
            if artifact_type in artifacts:
                report.add("artifact.duplicate_type", "/artifactType", f"Duplicate artifact type {artifact_type!r}", artifact=file_path.name)
                continue
            artifacts[artifact_type] = artifact
            names[artifact_type] = file_path.name

        if require_complete:
            missing = sorted(REQUIRED_ARTIFACT_TYPES - artifacts.keys())
            if missing:
                report.add("pipeline.missing_artifacts", "/", f"Missing artifact types: {', '.join(missing)}")

        for artifact_type, artifact in artifacts.items():
            self._validate_single_artifact(artifact, names[artifact_type], report)

        self._validate_cross_artifact(artifacts, names, report)
        return report

    def _validate_schema_and_envelope(self, artifact: Any, name: str, report: ValidationReport) -> None:
        for error in sorted(self.schema_validator.iter_errors(artifact), key=lambda item: list(item.absolute_path)):
            path = "/" + "/".join(str(part) for part in error.absolute_path)
            report.add("schema.invalid", path, error.message, artifact=name)

        if not isinstance(artifact, Mapping):
            return
        artifact_type = artifact.get("artifactType")
        payload = artifact.get("payload")
        expected_stage = STAGE_BY_TYPE.get(artifact_type)
        if expected_stage and artifact.get("stageId") != expected_stage:
            report.add(
                "envelope.stage_mismatch",
                "/stageId",
                f"{artifact_type!r} must use stageId {expected_stage!r}",
                artifact=name,
            )
        if isinstance(payload, Mapping) and artifact_type and payload.get("kind") != artifact_type:
            report.add(
                "envelope.kind_mismatch",
                "/payload/kind",
                f"payload.kind must equal artifactType {artifact_type!r}",
                artifact=name,
            )

    def _validate_single_artifact(self, artifact: Mapping[str, Any], name: str, report: ValidationReport) -> None:
        payload = artifact.get("payload")
        if not isinstance(payload, Mapping):
            return
        artifact_type = artifact.get("artifactType")
        self._check_unique_ids(payload, name, report)
        self._check_finite_numbers(payload, name, report)

        if artifact_type == "layout":
            self._validate_layout(payload, name, report)
        elif artifact_type == "terrain":
            self._validate_terrain(payload, name, report)
        elif artifact_type == "economy":
            self._validate_economy(payload, name, report)
        elif artifact_type == "props":
            self._validate_props(payload, name, report)
        elif artifact_type == "qa":
            approved = payload.get("status") == "APPROVED"
            ready = payload.get("readyForStudioBridge") is True
            if approved != ready:
                report.add("qa.status_ready_mismatch", "/payload", "APPROVED and readyForStudioBridge must agree", artifact=name)

    def _check_unique_ids(self, payload: Mapping[str, Any], name: str, report: ValidationReport) -> None:
        def visit(value: Any, path: str) -> None:
            if isinstance(value, list):
                by_key: dict[str, set[Any]] = defaultdict(set)
                for index, item in enumerate(value):
                    if isinstance(item, Mapping):
                        identity_key = None
                        if "id" in item:
                            identity_key = "id"
                        elif "stepId" in item:
                            identity_key = "stepId"
                        elif path.endswith(("/zones", "/zoneBriefs", "/worldBands", "/zoneSoundscapes")) and "zoneId" in item:
                            identity_key = "zoneId"
                        if identity_key is not None:
                            identifier = item[identity_key]
                            if identifier in by_key[identity_key]:
                                report.add(
                                    "id.duplicate",
                                    f"{path}/{index}/{identity_key}",
                                    f"Duplicate {identity_key} {identifier!r} in the same collection",
                                    artifact=name,
                                )
                            by_key[identity_key].add(identifier)
                    visit(item, f"{path}/{index}")
            elif isinstance(value, Mapping):
                for key, item in value.items():
                    visit(item, f"{path}/{key}")

        visit(payload, "/payload")

    def _check_finite_numbers(self, value: Any, name: str, report: ValidationReport, path: str = "/payload") -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                report.add("number.non_finite", path, "Numbers must be finite", artifact=name)
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                self._check_finite_numbers(item, name, report, f"{path}/{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self._check_finite_numbers(item, name, report, f"{path}/{index}")

    def _validate_layout(self, payload: Mapping[str, Any], name: str, report: ValidationReport) -> None:
        world = payload.get("worldBounds")
        zones = payload.get("zones", [])
        if not _valid_aabb(world):
            report.add("spatial.invalid_world_bounds", "/payload/worldBounds", "worldBounds must have min < max on every axis", artifact=name)
            return

        zone_by_id = {zone.get("zoneId"): zone for zone in zones if isinstance(zone, Mapping)}
        for index, zone in enumerate(zones):
            if not isinstance(zone, Mapping):
                continue
            bounds = zone.get("bounds")
            if not _valid_aabb(bounds):
                report.add("spatial.invalid_zone_bounds", f"/payload/zones/{index}/bounds", "Zone bounds must have min < max", artifact=name)
            elif not _contains(world, bounds):
                report.add("spatial.zone_outside_world", f"/payload/zones/{index}/bounds", "Zone bounds exceed worldBounds", artifact=name)

        for left_index, left in enumerate(zones):
            if not isinstance(left, Mapping) or not _valid_aabb(left.get("bounds")):
                continue
            for right_index in range(left_index + 1, len(zones)):
                right = zones[right_index]
                if not isinstance(right, Mapping) or not _valid_aabb(right.get("bounds")):
                    continue
                if _overlap(left["bounds"], right["bounds"]):
                    left_allowed = right.get("zoneId") in left.get("allowedOverlapZoneIds", [])
                    right_allowed = left.get("zoneId") in right.get("allowedOverlapZoneIds", [])
                    if not (left_allowed and right_allowed):
                        report.add(
                            "spatial.undeclared_overlap",
                            f"/payload/zones/{left_index}",
                            f"Zones {left.get('zoneId')!r} and {right.get('zoneId')!r} overlap without symmetric permission",
                            artifact=name,
                        )

        connection_ids: set[str] = set()
        graph: dict[str, set[str]] = defaultdict(set)
        for index, connection in enumerate(payload.get("connections", [])):
            if not isinstance(connection, Mapping):
                continue
            connection_id = connection.get("id")
            if isinstance(connection_id, str):
                connection_ids.add(connection_id)
            source, target = connection.get("fromZoneId"), connection.get("toZoneId")
            if source not in zone_by_id or target not in zone_by_id:
                report.add("ref.unknown_zone", f"/payload/connections/{index}", "Connection references an unknown zone", artifact=name)
                continue
            graph[source].add(target)
            if connection.get("bidirectional"):
                graph[target].add(source)

        spawn_ids = [zone_id for zone_id, zone in zone_by_id.items() if zone.get("role") == "spawn"]
        if len(spawn_ids) != 1:
            report.add("layout.spawn_count", "/payload/zones", "Layout must contain exactly one spawn zone", artifact=name)
        elif zone_by_id:
            visited = _reachable(graph, spawn_ids[0])
            unreachable = sorted(set(zone_by_id) - visited)
            if unreachable:
                report.add("layout.unreachable_zones", "/payload/connections", f"Zones unreachable from spawn: {', '.join(unreachable)}", artifact=name)

        for index, path in enumerate(payload.get("paths", [])):
            if not isinstance(path, Mapping):
                continue
            if path.get("connectionId") not in connection_ids:
                report.add("ref.unknown_connection", f"/payload/paths/{index}/connectionId", "Path references an unknown connection", artifact=name)
            if path.get("critical") and isinstance(path.get("widthStuds"), (int, float)) and path["widthStuds"] < 10:
                report.add("layout.critical_path_too_narrow", f"/payload/paths/{index}/widthStuds", "Critical squad paths must be at least 10 studs wide", artifact=name)

        for index, marker in enumerate(payload.get("markers", [])):
            if isinstance(marker, Mapping) and marker.get("zoneId") not in zone_by_id:
                report.add("ref.marker_unknown_zone", f"/payload/markers/{index}/zoneId", "Marker references an unknown zone", artifact=name)

    def _validate_terrain(self, payload: Mapping[str, Any], name: str, report: ValidationReport) -> None:
        scope = payload.get("scope")
        if not _valid_aabb(scope):
            report.add("terrain.invalid_scope", "/payload/scope", "Terrain scope must have min < max", artifact=name)
            return
        operation_ids: set[str] = set()
        for index, operation in enumerate(payload.get("operations", [])):
            if not isinstance(operation, Mapping):
                continue
            operation_ids.add(operation.get("id"))
            size = operation.get("size")
            transform = operation.get("transform", {})
            if not _positive_vec3(size):
                report.add("terrain.invalid_size", f"/payload/operations/{index}/size", "Terrain operation size must be positive", artifact=name)
                continue
            bounds = _terrain_aabb(operation)
            if bounds and not _contains(scope, bounds):
                report.add("terrain.operation_outside_scope", f"/payload/operations/{index}", "Terrain operation exceeds its scoped bounds", artifact=name)

        for index, operation_id in enumerate(payload.get("waterContainmentIds", [])):
            if operation_id not in operation_ids:
                report.add("ref.unknown_terrain_operation", f"/payload/waterContainmentIds/{index}", "Unknown terrain operation ID", artifact=name)

    def _validate_economy(self, payload: Mapping[str, Any], name: str, report: ValidationReport) -> None:
        ceiling = payload.get("safeIntegerCeiling")
        if ceiling != SAFE_INTEGER_CEILING:
            report.add("economy.safe_ceiling", "/payload/safeIntegerCeiling", f"Expected safe integer ceiling {SAFE_INTEGER_CEILING}", artifact=name)

        currency_ids = {item.get("id") for item in payload.get("currencies", []) if isinstance(item, Mapping)}
        for pool_index, pool in enumerate(payload.get("gachaPools", [])):
            if not isinstance(pool, Mapping):
                continue
            if pool.get("currencyId") not in currency_ids:
                report.add("ref.unknown_currency", f"/payload/gachaPools/{pool_index}/currencyId", "Gacha pool references an unknown currency", artifact=name)
            total = sum(outcome.get("rateBasisPoints", 0) for outcome in pool.get("outcomes", []) if isinstance(outcome, Mapping))
            if total != 10_000:
                report.add("economy.gacha_total", f"/payload/gachaPools/{pool_index}/outcomes", f"Gacha rates total {total}; expected 10000 basis points", artifact=name)

        checkpoints = {item.get("elapsedSeconds") for item in payload.get("simulations", []) if isinstance(item, Mapping)}
        if checkpoints != ECONOMY_CHECKPOINTS:
            report.add("economy.simulation_checkpoints", "/payload/simulations", f"Expected checkpoints {sorted(ECONOMY_CHECKPOINTS)}", artifact=name)

        self._check_safe_integers(payload, name, report)
        try:
            from economy.simulator import EconomySimulator
            sim = EconomySimulator(payload)
            sim_results = sim.simulate(max_seconds=3600)
            checks = sim.verify_invariants(sim_results)
            for check in checks:
                if not check.passed:
                    report.add(f"economy.{check.name}", "/payload", check.detail, artifact=name)
        except Exception as err:
            report.add("economy.simulation_error", "/payload", f"Simulation failed: {err}", artifact=name)

    def _check_safe_integers(self, value: Any, name: str, report: ValidationReport, path: str = "/payload") -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, int) and abs(value) > SAFE_INTEGER_CEILING:
            report.add("economy.unsafe_integer", path, f"Integer exceeds safe ceiling {SAFE_INTEGER_CEILING}", artifact=name)
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                self._check_safe_integers(item, name, report, f"{path}/{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self._check_safe_integers(item, name, report, f"{path}/{index}")

    def _validate_props(self, payload: Mapping[str, Any], name: str, report: ValidationReport) -> None:
        asset_reg = _load_asset_registry()
        prefabs_reg = asset_reg.get("prefabs", {})
        for index, instance in enumerate(payload.get("instances", [])):
            if not isinstance(instance, Mapping):
                continue
            if instance.get("kind") == "prefab":
                prefab_key = instance.get("prefabKey")
                if prefabs_reg and prefab_key not in prefabs_reg:
                    report.add(
                        "ref.unknown_prefab_key",
                        f"/payload/instances/{index}/prefabKey",
                        f"Unknown prefab key {prefab_key!r}",
                        artifact=name,
                    )
                elif prefabs_reg and prefab_key in prefabs_reg:
                    reg_entry = prefabs_reg[prefab_key]
                    expected_cat = reg_entry.get("category")
                    actual_cat = instance.get("parentCategory")
                    if expected_cat and actual_cat != expected_cat:
                        report.add(
                            "ref.prefab_category_mismatch",
                            f"/payload/instances/{index}/parentCategory",
                            f"Prefab {prefab_key!r} requires category {expected_cat!r}, got {actual_cat!r}",
                            artifact=name,
                        )

    def _validate_cross_artifact(self, artifacts: Mapping[str, Mapping[str, Any]], names: Mapping[str, str], report: ValidationReport) -> None:
        build_ids = {artifact.get("buildId") for artifact in artifacts.values()}
        versions = {artifact.get("schemaVersion") for artifact in artifacts.values()}
        seeds = {artifact.get("seed") for artifact in artifacts.values()}
        if len(build_ids) > 1:
            report.add("pipeline.build_id_mismatch", "/buildId", "All artifacts in a build must share one buildId")
        if len(versions) > 1:
            report.add("pipeline.version_mismatch", "/schemaVersion", "All artifacts in a build must share one schemaVersion")
        if len(seeds) > 1:
            report.add("pipeline.seed_mismatch", "/seed", "All artifacts in a build must share one seed")

        director = _payload(artifacts, "director")
        layout = _payload(artifacts, "layout")
        terrain = _payload(artifacts, "terrain")
        props = _payload(artifacts, "props")
        lighting = _payload(artifacts, "lighting")
        economy = _payload(artifacts, "economy")
        vfx = _payload(artifacts, "vfxAudio")

        if director and layout:
            if director.get("worldBounds") != layout.get("worldBounds"):
                report.add("cross.world_bounds_mismatch", "/payload/worldBounds", "Director and Layout worldBounds must match", artifact=names.get("layout"))
            director_zones = {item.get("zoneId") for item in director.get("zoneBriefs", []) if isinstance(item, Mapping)}
            layout_zones = {item.get("zoneId") for item in layout.get("zones", []) if isinstance(item, Mapping)}
            if director_zones != layout_zones:
                report.add("cross.zone_set_mismatch", "/payload/zones", "Layout zones must exactly implement Director zone briefs", artifact=names.get("layout"))

        marker_ids = {item.get("id") for item in (layout or {}).get("markers", []) if isinstance(item, Mapping)}
        zone_ids = {item.get("zoneId") for item in (layout or {}).get("zones", []) if isinstance(item, Mapping)}
        instance_ids = {item.get("id") for item in (props or {}).get("instances", []) if isinstance(item, Mapping)}

        if terrain and layout:
            if not _contains(layout.get("worldBounds"), terrain.get("scope")):
                report.add("cross.terrain_scope_outside_world", "/payload/scope", "Terrain scope must stay inside worldBounds", artifact=names.get("terrain"))
            world_bounds = layout.get("worldBounds")
            if _valid_aabb(world_bounds):
                for index, operation in enumerate(terrain.get("operations", [])):
                    if not isinstance(operation, Mapping):
                        continue
                    op_bounds = _terrain_aabb(operation)
                    if op_bounds and not _contains(world_bounds, op_bounds):
                        report.add(
                            "cross.terrain_operation_outside_world",
                            f"/payload/operations/{index}",
                            f"Terrain operation {operation.get('id')!r} exceeds worldBounds",
                            artifact=names.get("terrain"),
                        )
            self._validate_terrain_subtract(terrain, layout, names.get("terrain"), report)
            for index, marker_id in enumerate(terrain.get("foundationMarkerIds", [])):
                if marker_id not in marker_ids:
                    report.add("ref.unknown_foundation_marker", f"/payload/foundationMarkerIds/{index}", "Unknown layout marker ID", artifact=names.get("terrain"))

        if props:
            self._validate_structure_support(props, terrain, names.get("props"), report)

        if props and layout:
            for marker_id, instance_id in props.get("gameplayMarkerHosts", {}).items():
                if marker_id not in marker_ids:
                    report.add("ref.unknown_host_marker", f"/payload/gameplayMarkerHosts/{marker_id}", "Unknown layout marker ID", artifact=names.get("props"))
                if instance_id not in instance_ids:
                    report.add("ref.unknown_host_instance", f"/payload/gameplayMarkerHosts/{marker_id}", "Unknown props instance ID", artifact=names.get("props"))
            self._validate_prop_clearance(props, layout, names.get("props"), report)

        if lighting and props:
            for index, light in enumerate(lighting.get("localLights", [])):
                if isinstance(light, Mapping) and light.get("socketInstanceId") not in instance_ids:
                    report.add("ref.unknown_light_socket", f"/payload/localLights/{index}/socketInstanceId", "Unknown props instance ID", artifact=names.get("lighting"))

        if economy and layout:
            world_ids = {item.get("worldId") for item in economy.get("worldBands", []) if isinstance(item, Mapping)}
            director_world = director.get("worldId") if director else None
            if director_world and director_world not in world_ids:
                report.add("cross.missing_world_economy", "/payload/worldBands", "Economy must define the Director worldId", artifact=names.get("economy"))

        if vfx and layout:
            for index, soundscape in enumerate(vfx.get("zoneSoundscapes", [])):
                if isinstance(soundscape, Mapping) and soundscape.get("zoneId") not in zone_ids:
                    report.add("ref.unknown_soundscape_zone", f"/payload/zoneSoundscapes/{index}/zoneId", "Unknown layout zone ID", artifact=names.get("vfxAudio"))
            for recipe_index, recipe in enumerate(vfx.get("effectRecipes", [])):
                if not isinstance(recipe, Mapping):
                    continue
                for socket_index, socket_id in enumerate(recipe.get("socketIds", [])):
                    if socket_id not in instance_ids and socket_id not in marker_ids:
                        report.add("ref.unknown_effect_socket", f"/payload/effectRecipes/{recipe_index}/socketIds/{socket_index}", "Unknown instance or marker ID", artifact=names.get("vfxAudio"))

    def _validate_prop_clearance(self, props: Mapping[str, Any], layout: Mapping[str, Any], name: str | None, report: ValidationReport) -> None:
        clearances = [item for item in layout.get("clearanceVolumes", []) if isinstance(item, Mapping) and _valid_aabb(item.get("bounds"))]
        for index, instance in enumerate(props.get("instances", [])):
            if not isinstance(instance, Mapping) or instance.get("kind") != "primitive" or not instance.get("canCollide"):
                continue
            bounds = _primitive_aabb(instance)
            if not bounds:
                continue
            for clearance in clearances:
                if _overlap(bounds, clearance["bounds"]):
                    report.add(
                        "spatial.prop_blocks_clearance",
                        f"/payload/instances/{index}",
                        f"Collidable instance {instance.get('id')!r} intersects clearance {clearance.get('id')!r}",
                        artifact=name,
                    )

    def _validate_terrain_subtract(self, terrain: Mapping[str, Any], layout: Mapping[str, Any], name: str | None, report: ValidationReport) -> None:
        zones = layout.get("zones", [])
        zone_by_id = {z.get("zoneId"): z for z in zones if isinstance(z, Mapping)}
        zone_by_role = {z.get("role"): z for z in zones if isinstance(z, Mapping)}

        spawn_zone = zone_by_role.get("spawn") or zone_by_id.get("zone_spawn_hub")
        boss_zone = zone_by_role.get("boss") or zone_by_id.get("zone_boss_arena")

        protected_boxes: list[tuple[str, dict[str, list[float]]]] = []

        if spawn_zone and _valid_aabb(spawn_zone.get("bounds")):
            sb = spawn_zone["bounds"]
            protected_boxes.append((
                "spawn hub floor",
                {
                    "min": [sb["min"][0], sb["min"][1] - 4.0, sb["min"][2]],
                    "max": [sb["max"][0], sb["min"][1] + 2.0, sb["max"][2]],
                },
            ))

        if boss_zone and _valid_aabb(boss_zone.get("bounds")):
            bb = boss_zone["bounds"]
            protected_boxes.append((
                "boss arena floor",
                {
                    "min": [bb["min"][0], bb["min"][1] - 4.0, bb["min"][2]],
                    "max": [bb["max"][0], bb["min"][1] + 2.0, bb["max"][2]],
                },
            ))

        for path in layout.get("paths", []):
            if not isinstance(path, Mapping) or not path.get("critical"):
                continue
            width = float(path.get("widthStuds", 10))
            half_w = width / 2.0
            waypoints = [wp for wp in path.get("waypoints", []) if _vec3(wp)]
            if not waypoints:
                continue
            xs = [wp[0] for wp in waypoints]
            ys = [wp[1] for wp in waypoints]
            zs = [wp[2] for wp in waypoints]
            protected_boxes.append((
                f"critical path {path.get('id')!r}",
                {
                    "min": [min(xs) - half_w, min(ys) - 4.0, min(zs) - half_w],
                    "max": [max(xs) + half_w, max(ys) + 2.0, max(zs) + half_w],
                },
            ))

        for index, operation in enumerate(terrain.get("operations", [])):
            if not isinstance(operation, Mapping):
                continue
            if operation.get("action") in {"subtract", "terrain_subtract"}:
                bounds = _terrain_aabb(operation)
                if not bounds:
                    continue
                for label, p_box in protected_boxes:
                    if _overlap(bounds, p_box):
                        report.add(
                            "terrain.subtract_violates_protected_area",
                            f"/payload/operations/{index}",
                            f"Terrain subtract {operation.get('id')!r} intersects protected area: {label}",
                            artifact=name,
                        )
                        break

    def _validate_structure_support(self, props: Mapping[str, Any], terrain: Mapping[str, Any] | None, name: str | None, report: ValidationReport) -> None:
        instances = props.get("instances", [])
        foundation_boxes: list[tuple[str, dict[str, list[float]]]] = []
        for instance in instances:
            if not isinstance(instance, Mapping):
                continue
            tags = set(instance.get("tags", []))
            if "foundation" in tags:
                bounds = _primitive_aabb(instance)
                if bounds:
                    foundation_boxes.append((instance.get("id"), bounds))

        terrain_fill_boxes: list[tuple[str, dict[str, list[float]]]] = []
        if terrain:
            for operation in terrain.get("operations", []):
                if not isinstance(operation, Mapping):
                    continue
                if operation.get("action") in {"fill", "terrain_fill"}:
                    bounds = _terrain_aabb(operation)
                    if bounds:
                        terrain_fill_boxes.append((operation.get("id"), bounds))

        critical_categories = {"Structures", "Gameplay"}
        critical_tags = {"landmark", "interaction", "vfx_socket"}

        for index, instance in enumerate(instances):
            if not isinstance(instance, Mapping):
                continue
            category = instance.get("parentCategory")
            collide = instance.get("canCollide", False)
            tags = set(instance.get("tags", []))
            is_critical = category in critical_categories or collide or bool(tags & critical_tags)
            if not is_critical:
                continue

            bounds = _primitive_aabb(instance)
            if not bounds:
                transform = instance.get("transform")
                pos = transform.get("position") if isinstance(transform, Mapping) else None
                if instance.get("kind") == "prefab" and _vec3(pos):
                    px, py, pz = pos
                    supported = False
                    for f_id, f_bounds in foundation_boxes:
                        if f_bounds["min"][0] <= px <= f_bounds["max"][0] and f_bounds["min"][2] <= pz <= f_bounds["max"][2]:
                            if abs(py - f_bounds["max"][1]) <= 0.5:
                                supported = True
                                break
                    if not supported and terrain_fill_boxes:
                        for t_id, t_bounds in terrain_fill_boxes:
                            if t_bounds["min"][0] <= px <= t_bounds["max"][0] and t_bounds["min"][2] <= pz <= t_bounds["max"][2]:
                                if t_bounds["min"][1] - 0.25 <= py <= t_bounds["max"][1] + 0.5:
                                    supported = True
                                    break
                    if not supported:
                        report.add(
                            "spatial.unsupported_structure",
                            f"/payload/instances/{index}",
                            f"Structure prefab {instance.get('id')!r} is floating without foundation or terrain support",
                            artifact=name,
                        )
                continue

            bottom_y = bounds["min"][1]
            is_foundation = "foundation" in tags

            supported = False

            if not is_foundation:
                for f_id, f_bounds in foundation_boxes:
                    if instance.get("id") == f_id:
                        continue
                    if _horizontal_overlap(bounds, f_bounds):
                        top_y = f_bounds["max"][1]
                        if abs(bottom_y - top_y) <= 0.25:
                            supported = True
                            break

            if not supported and terrain_fill_boxes:
                for t_id, t_bounds in terrain_fill_boxes:
                    if _horizontal_overlap(bounds, t_bounds):
                        t_top = t_bounds["max"][1]
                        t_bottom = t_bounds["min"][1]
                        if abs(bottom_y - t_top) <= 0.25:
                            supported = True
                            break
                        if is_foundation and t_bottom <= bottom_y <= t_top:
                            supported = True
                            break

            if not supported and not terrain and is_foundation:
                supported = True

            if not supported:
                report.add(
                    "spatial.unsupported_structure",
                    f"/payload/instances/{index}",
                    f"Structure instance {instance.get('id')!r} is floating without foundation or terrain support",
                    artifact=name,
                )


def _load_asset_registry() -> dict[str, Any]:
    registry_path = Path(__file__).resolve().parents[1] / "registry" / "asset_registry.json"
    if registry_path.exists():
        try:
            return json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _payload(artifacts: Mapping[str, Mapping[str, Any]], artifact_type: str) -> Mapping[str, Any] | None:
    artifact = artifacts.get(artifact_type)
    payload = artifact.get("payload") if artifact else None
    return payload if isinstance(payload, Mapping) else None


def _valid_aabb(bounds: Any) -> bool:
    if not isinstance(bounds, Mapping):
        return False
    minimum, maximum = bounds.get("min"), bounds.get("max")
    return _vec3(minimum) and _vec3(maximum) and all(minimum[i] < maximum[i] for i in range(3))


def _vec3(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 3 and all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item) for item in value)


def _positive_vec3(value: Any) -> bool:
    return _vec3(value) and all(item > 0 for item in value)


def _contains(outer: Any, inner: Any) -> bool:
    if not (_valid_aabb(outer) and _valid_aabb(inner)):
        return False
    return all(outer["min"][i] <= inner["min"][i] and inner["max"][i] <= outer["max"][i] for i in range(3))


def _overlap(left: Mapping[str, Sequence[float]], right: Mapping[str, Sequence[float]]) -> bool:
    return all(left["min"][i] < right["max"][i] and right["min"][i] < left["max"][i] for i in range(3))


def _reachable(graph: Mapping[str, set[str]], start: str) -> set[str]:
    visited: set[str] = set()
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(graph.get(current, ()))
    return visited


def _center_size_aabb(position: Any, size: Any) -> dict[str, list[float]] | None:
    if not (_vec3(position) and _positive_vec3(size)):
        return None
    half = [component / 2 for component in size]
    return {
        "min": [position[i] - half[i] for i in range(3)],
        "max": [position[i] + half[i] for i in range(3)],
    }


def _rotation_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> tuple[tuple[float, float, float], ...]:
    rx, ry, rz = math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return (
        (cy * cz + sy * sx * sz, -cy * sz + sy * sx * cz, sy * cx),
        (cx * sz, cx * cz, -sx),
        (-sy * cz + cy * sx * sz, sy * sz + cy * sx * cz, cy * cx),
    )


def _horizontal_overlap(left: Mapping[str, Sequence[float]], right: Mapping[str, Sequence[float]]) -> bool:
    return (
        left["min"][0] < right["max"][0]
        and right["min"][0] < left["max"][0]
        and left["min"][2] < right["max"][2]
        and right["min"][2] < left["max"][2]
    )


def _primitive_aabb(instance: Mapping[str, Any]) -> dict[str, list[float]] | None:
    size = instance.get("size")
    transform = instance.get("transform")
    if not (_positive_vec3(size) and isinstance(transform, Mapping) and _vec3(transform.get("position")) and _vec3(transform.get("orientationDegrees"))):
        return None

    rotation = _rotation_matrix(*transform["orientationDegrees"])
    half = [component / 2 for component in size]
    extent = [sum(abs(rotation[row][column]) * half[column] for column in range(3)) for row in range(3)]
    position = transform["position"]
    return {
        "min": [position[i] - extent[i] for i in range(3)],
        "max": [position[i] + extent[i] for i in range(3)],
    }


def _terrain_aabb(operation: Mapping[str, Any]) -> dict[str, list[float]] | None:
    size = operation.get("size")
    transform = operation.get("transform")
    shape = operation.get("shape", "block")
    if not (_positive_vec3(size) and isinstance(transform, Mapping) and _vec3(transform.get("position")) and _vec3(transform.get("orientationDegrees"))):
        return None

    position = transform["position"]
    rotation = _rotation_matrix(*transform["orientationDegrees"])

    if shape == "ball":
        radius = max(size) / 2.0
        return {
            "min": [position[i] - radius for i in range(3)],
            "max": [position[i] + radius for i in range(3)],
        }

    if shape == "cylinder":
        # In Roblox Part convention, cylinder height is along local X (RightVector R[:, 0]),
        # while Terrain:FillCylinder axis is along local Y (UpVector R[:, 1]).
        # If orientation has RightVector pointing along world Y (e.g. [0, 0, 90]),
        # the cylinder was oriented with Part conventions to stand vertical.
        if abs(rotation[1][0]) > 0.99:
            axis = (rotation[0][0], rotation[1][0], rotation[2][0])
        else:
            axis = (rotation[0][1], rotation[1][1], rotation[2][1])
        h = size[1]
        r = max(size[0], size[2]) / 2.0
        extent = [
            (h / 2.0) * abs(axis[i]) + r * math.sqrt(max(0.0, 1.0 - axis[i] ** 2))
            for i in range(3)
        ]
        return {
            "min": [position[i] - extent[i] for i in range(3)],
            "max": [position[i] + extent[i] for i in range(3)],
        }

    if shape == "wedge":
        half = [s / 2.0 for s in size]
        local_vertices = [
            [-half[0], -half[1], -half[2]],
            [ half[0], -half[1], -half[2]],
            [-half[0], -half[1],  half[2]],
            [ half[0], -half[1],  half[2]],
            [-half[0],  half[1],  half[2]],
            [ half[0],  half[1],  half[2]],
        ]
        world_vertices = [
            [position[i] + sum(rotation[i][j] * v[j] for j in range(3)) for i in range(3)]
            for v in local_vertices
        ]
        return {
            "min": [min(v[i] for v in world_vertices) for i in range(3)],
            "max": [max(v[i] for v in world_vertices) for i in range(3)],
        }

    # Default: "block"
    half = [component / 2 for component in size]
    extent = [sum(abs(rotation[row][column]) * half[column] for column in range(3)) for row in range(3)]
    return {
        "min": [position[i] - extent[i] for i in range(3)],
        "max": [position[i] + extent[i] for i in range(3)],
    }
