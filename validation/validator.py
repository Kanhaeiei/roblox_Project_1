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
        report = ValidationReport(artifact_count=1)
        self._validate_schema_and_envelope(artifact, artifact_path.name, report)
        if not report.ok:
            return report
        self._validate_single_artifact(artifact, artifact_path.name, report)
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
            bounds = _center_size_aabb(transform.get("position"), size)
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
            for index, marker_id in enumerate(terrain.get("foundationMarkerIds", [])):
                if marker_id not in marker_ids:
                    report.add("ref.unknown_foundation_marker", f"/payload/foundationMarkerIds/{index}", "Unknown layout marker ID", artifact=names.get("terrain"))

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


def _primitive_aabb(instance: Mapping[str, Any]) -> dict[str, list[float]] | None:
    size = instance.get("size")
    transform = instance.get("transform")
    if not (_positive_vec3(size) and isinstance(transform, Mapping) and _vec3(transform.get("position")) and _vec3(transform.get("orientationDegrees"))):
        return None

    rx, ry, rz = [math.radians(value) for value in transform["orientationDegrees"]]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    rotation = (
        (cy * cz, cz * sx * sy - cx * sz, sx * sz + cx * cz * sy),
        (cy * sz, cx * cz + sx * sy * sz, cx * sy * sz - cz * sx),
        (-sy, cy * sx, cx * cy),
    )
    half = [component / 2 for component in size]
    extent = [sum(abs(rotation[row][column]) * half[column] for column in range(3)) for row in range(3)]
    position = transform["position"]
    return {
        "min": [position[i] - extent[i] for i in range(3)],
        "max": [position[i] + extent[i] for i in range(3)],
    }
