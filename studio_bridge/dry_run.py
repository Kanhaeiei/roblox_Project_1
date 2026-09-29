from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class DryRunIssue:
    code: str
    path: str
    message: str


@dataclass
class DryRunReport:
    build_id: str | None = None
    operation_count: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    issues: list[DryRunIssue] = field(default_factory=list)
    warnings: list[DryRunIssue] = field(default_factory=list)
    unresolved_references: int = 0
    forbidden_actions: int = 0

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def status(self) -> str:
        return "PASS" if self.ok else "FAIL"

    @property
    def release_ready(self) -> bool:
        return self.ok and not self.warnings

    def error(self, code: str, path: str, message: str) -> None:
        self.issues.append(DryRunIssue(code, path, message))

    def warn(self, code: str, path: str, message: str) -> None:
        self.warnings.append(DryRunIssue(code, path, message))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "buildId": self.build_id,
            "operationCount": self.operation_count,
            "counts": self.counts,
            "unresolvedReferences": self.unresolved_references,
            "forbiddenActions": self.forbidden_actions,
            "releaseReady": self.release_ready,
            "issues": [asdict(issue) for issue in self.issues],
            "warnings": [asdict(warning) for warning in self.warnings],
        }


class StudioBridgeDryRun:
    def __init__(self, manifest_schema: Mapping[str, Any], allowlist: Mapping[str, Any], asset_registry: Mapping[str, Any]) -> None:
        Draft202012Validator.check_schema(manifest_schema)
        self.schema_validator = Draft202012Validator(manifest_schema)
        self.allowlist = dict(allowlist)
        self.asset_registry = dict(asset_registry)

    @classmethod
    def from_files(cls, manifest_schema: Path | str, allowlist: Path | str, asset_registry: Path | str) -> "StudioBridgeDryRun":
        return cls(
            json.loads(Path(manifest_schema).read_text(encoding="utf-8")),
            json.loads(Path(allowlist).read_text(encoding="utf-8")),
            json.loads(Path(asset_registry).read_text(encoding="utf-8")),
        )

    def run_file(self, manifest_path: Path | str) -> DryRunReport:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        return self.run(manifest)

    def run(self, manifest: Mapping[str, Any]) -> DryRunReport:
        report = DryRunReport(build_id=manifest.get("buildId") if isinstance(manifest, Mapping) else None)
        for error in sorted(self.schema_validator.iter_errors(manifest), key=lambda item: list(item.absolute_path)):
            path = "/" + "/".join(str(part) for part in error.absolute_path)
            report.error("manifest.schema_invalid", path, error.message)
        if report.issues:
            return report

        operations = manifest["operations"]
        report.operation_count = len(operations)
        report.counts = dict(sorted(Counter(operation["action"] for operation in operations).items()))

        self._check_namespace(manifest, report)
        self._check_sequences_and_ids(operations, report)
        self._check_forbidden_payload_keys(manifest, report)
        self._check_operations(manifest, report)
        self._check_budgets(manifest, report)
        self._check_runtime_assets(manifest, report)
        return report

    def _check_namespace(self, manifest: Mapping[str, Any], report: DryRunReport) -> None:
        prefix = self.allowlist["allowedNamespacePrefix"]
        namespace = manifest["namespace"]
        expected = prefix + manifest["buildId"]
        if namespace != expected or ".." in namespace:
            report.error("bridge.invalid_namespace", "/namespace", f"Expected exact generated namespace {expected!r}")

    def _check_sequences_and_ids(self, operations: list[Mapping[str, Any]], report: DryRunReport) -> None:
        sequences = [operation["sequence"] for operation in operations]
        expected = list(range(1, len(operations) + 1))
        if sequences != expected:
            report.error("bridge.non_contiguous_sequence", "/operations", "Operation sequences must be contiguous and ordered from 1")
        identifiers = [operation["operationId"] for operation in operations]
        duplicates = sorted(identifier for identifier, count in Counter(identifiers).items() if count > 1)
        if duplicates:
            report.error("bridge.duplicate_operation_id", "/operations", f"Duplicate operation IDs: {', '.join(duplicates)}")

    def _check_forbidden_payload_keys(self, manifest: Mapping[str, Any], report: DryRunReport) -> None:
        forbidden = {key.casefold() for key in self.allowlist["forbiddenPayloadKeys"]}

        def visit(value: Any, path: str) -> None:
            if isinstance(value, Mapping):
                for key, item in value.items():
                    item_path = f"{path}/{key}"
                    if key.casefold() in forbidden:
                        report.error("bridge.forbidden_payload_key", item_path, f"Generated manifests may not contain {key!r}")
                        report.forbidden_actions += 1
                    visit(item, item_path)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, f"{path}/{index}")

        for index, operation in enumerate(manifest["operations"]):
            visit(operation["payload"], f"/operations/{index}/payload")

    def _check_operations(self, manifest: Mapping[str, Any], report: DryRunReport) -> None:
        namespace = manifest["namespace"]
        allowed_actions = set(self.allowlist["actions"])
        allowed_folders = set(self.allowlist["folders"])
        allowed_primitives = set(self.allowlist["classes"]["primitive"])
        allowed_lights = set(self.allowlist["classes"]["light"])
        allowed_shapes = set(self.allowlist["terrainShapes"])
        material_registry = self.asset_registry.get("materials", {})
        color_registry = self.asset_registry.get("colors", {})
        prefab_registry = self.asset_registry.get("prefabs", {})
        created_instances: set[str] = set()

        for index, operation in enumerate(manifest["operations"]):
            path = f"/operations/{index}"
            action = operation["action"]
            target = operation["target"]
            payload = operation["payload"]
            if action not in allowed_actions:
                report.error("bridge.forbidden_action", f"{path}/action", f"Action {action!r} is not allowlisted")
                report.forbidden_actions += 1
                continue

            if action in {"ensure_folder", "create_primitive", "create_prefab", "create_local_light", "bind_gameplay_marker"} and not target.startswith(namespace + "."):
                report.error("bridge.target_outside_namespace", f"{path}/target", "Generated instance target must stay under the build namespace")
            elif action.startswith("terrain_") and target != "Workspace.Terrain":
                report.error("bridge.invalid_terrain_target", f"{path}/target", "Terrain operations must target Workspace.Terrain")
            elif action == "configure_lighting" and target != "Lighting":
                report.error("bridge.invalid_lighting_target", f"{path}/target", "Lighting configuration must target Lighting")

            if action == "ensure_folder":
                if payload.get("folderName") not in allowed_folders:
                    report.error("bridge.folder_not_allowed", f"{path}/payload/folderName", "Folder is not allowlisted")
            elif action in {"terrain_fill", "terrain_subtract"}:
                if payload.get("shape") not in allowed_shapes:
                    report.error("bridge.terrain_shape_not_allowed", f"{path}/payload/shape", "Terrain shape is not allowlisted")
                self._require_registry_key(payload.get("materialToken"), material_registry, f"{path}/payload/materialToken", "material", report)
                if payload.get("buildNamespace") != namespace:
                    report.error("bridge.terrain_namespace_mismatch", f"{path}/payload/buildNamespace", "Terrain operation must declare the current build namespace")
            elif action == "create_primitive":
                if payload.get("className") not in allowed_primitives:
                    report.error("bridge.class_not_allowed", f"{path}/payload/className", "Primitive class is not allowlisted")
                if payload.get("parentCategory") not in allowed_folders:
                    report.error("bridge.folder_not_allowed", f"{path}/payload/parentCategory", "Parent category is not allowlisted")
                self._require_registry_key(payload.get("materialToken"), material_registry, f"{path}/payload/materialToken", "material", report)
                self._require_registry_key(payload.get("colorToken"), color_registry, f"{path}/payload/colorToken", "color", report)
                created_instances.add(target.rsplit(".", 1)[-1])
            elif action == "create_prefab":
                self._require_registry_key(payload.get("prefabKey"), prefab_registry, f"{path}/payload/prefabKey", "prefab", report)
                created_instances.add(target.rsplit(".", 1)[-1])
            elif action == "create_local_light":
                if payload.get("type") not in allowed_lights:
                    report.error("bridge.light_type_not_allowed", f"{path}/payload/type", "Light type is not allowlisted")
                socket_id = payload.get("socketInstanceId")
                if socket_id not in created_instances:
                    report.error("bridge.unresolved_light_socket", f"{path}/payload/socketInstanceId", f"Socket {socket_id!r} was not created earlier")
                    report.unresolved_references += 1
                self._require_registry_key(payload.get("colorToken"), color_registry, f"{path}/payload/colorToken", "color", report)
            elif action == "bind_gameplay_marker":
                instance_id = payload.get("instanceId")
                if instance_id not in created_instances:
                    report.error("bridge.unresolved_marker_instance", f"{path}/payload/instanceId", f"Instance {instance_id!r} was not created earlier")
                    report.unresolved_references += 1

    def _require_registry_key(self, key: Any, registry: Mapping[str, Any], path: str, kind: str, report: DryRunReport) -> None:
        if key not in registry:
            report.error(f"bridge.unknown_{kind}_token", path, f"Unknown {kind} registry key {key!r}")
            report.unresolved_references += 1

    def _check_budgets(self, manifest: Mapping[str, Any], report: DryRunReport) -> None:
        limits = manifest["budgets"]["limits"]
        planned = manifest["budgets"]["planned"]
        actual = report.counts
        expected_counts = {
            "terrainOperations": actual.get("terrain_fill", 0) + actual.get("terrain_subtract", 0),
            "instances": actual.get("create_primitive", 0) + actual.get("create_prefab", 0),
            "localLights": actual.get("create_local_light", 0),
            "markerBindings": actual.get("bind_gameplay_marker", 0),
        }
        for key, expected in expected_counts.items():
            if planned.get(key) != expected:
                report.error("bridge.planned_count_mismatch", f"/budgets/planned/{key}", f"Planned {planned.get(key)} but manifest contains {expected}")

        comparisons = {
            "instances": "instances",
            "activeParticleEmittersNearPlayer": "activeParticleEmittersNearPlayer",
            "particlesPerSecondNearPlayer": "particlesPerSecondNearPlayer",
            "transparentOverlapLayers": "transparentOverlapLayers",
        }
        for planned_key, limit_key in comparisons.items():
            if planned.get(planned_key, 0) > limits.get(limit_key, 0):
                report.error("bridge.budget_exceeded", f"/budgets/planned/{planned_key}", f"Planned {planned[planned_key]} exceeds limit {limits.get(limit_key)}")

    def _check_runtime_assets(self, manifest: Mapping[str, Any], report: DryRunReport) -> None:
        audio_registry = self.asset_registry.get("audio", {})
        keys: set[str] = set()
        for soundscape in manifest["runtimeConfig"]["soundscapes"]:
            if not isinstance(soundscape, Mapping):
                continue
            music = soundscape.get("musicRegistryKey")
            if isinstance(music, str):
                keys.add(music)
            keys.update(key for key in soundscape.get("ambientRegistryKeys", []) if isinstance(key, str))

        for key in sorted(keys):
            entry = audio_registry.get(key)
            if entry is None:
                report.error("bridge.unknown_audio_key", "/runtimeConfig/soundscapes", f"Unknown audio registry key {key!r}")
                report.unresolved_references += 1
            elif entry.get("status") != "approved":
                report.warn("bridge.placeholder_audio", "/runtimeConfig/soundscapes", f"Audio key {key!r} is {entry.get('status')!r}; dry run is valid but release is blocked")
