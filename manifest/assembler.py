from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from validation import ArtifactValidator


ARTIFACT_ORDER = ["gameConcept", "director", "layout", "terrain", "props", "lighting", "economy", "vfxAudio", "qa"]


class AssemblyError(ValueError):
    pass


class ManifestAssembler:
    def __init__(self, pipeline_validator: ArtifactValidator, manifest_schema: Mapping[str, Any]) -> None:
        Draft202012Validator.check_schema(manifest_schema)
        self.pipeline_validator = pipeline_validator
        self.manifest_validator = Draft202012Validator(manifest_schema)

    @classmethod
    def from_files(cls, pipeline_schema: Path | str, manifest_schema: Path | str) -> "ManifestAssembler":
        pipeline_validator = ArtifactValidator.from_schema_file(pipeline_schema)
        manifest_data = json.loads(Path(manifest_schema).read_text(encoding="utf-8"))
        return cls(pipeline_validator, manifest_data)

    def assemble(self, artifact_directory: Path | str, *, runtime_version: str = "0.1.0") -> dict[str, Any]:
        directory = Path(artifact_directory)
        validation_report = self.pipeline_validator.validate_directory(directory)
        if not validation_report.ok:
            codes = ", ".join(issue.code for issue in validation_report.issues[:5])
            raise AssemblyError(f"Artifact validation failed before assembly: {codes}")

        artifacts, raw_bytes = self._load_artifacts(directory)
        qa = artifacts["qa"]["payload"]
        if qa.get("status") != "APPROVED" or qa.get("readyForStudioBridge") is not True:
            raise AssemblyError("QA artifact must be APPROVED and readyForStudioBridge before assembly")

        build_id = artifacts["director"]["buildId"]
        namespace = f"Workspace.Generated.{build_id}"
        operations = self._build_operations(artifacts, namespace)
        director_budget = artifacts["director"]["payload"]["budgets"]
        props_budget = artifacts["props"]["payload"]["budgetEstimate"]
        vfx_budget = artifacts["vfxAudio"]["payload"]["budgetEstimate"]

        planned = {
            "terrainOperations": len(artifacts["terrain"]["payload"]["operations"]),
            "instances": len(artifacts["props"]["payload"]["instances"]),
            "localLights": len(artifacts["lighting"]["payload"]["localLights"]),
            "markerBindings": len(artifacts["props"]["payload"]["gameplayMarkerHosts"]),
            "activeParticleEmittersNearPlayer": vfx_budget.get("nearbyEmitters", 0),
            "particlesPerSecondNearPlayer": vfx_budget.get("particlesPerSecond", 0),
            "transparentOverlapLayers": max(props_budget.get("transparentOverlapLayers", 0), vfx_budget.get("transparencyLayers", 0)),
        }

        manifest = {
            "manifestVersion": "1.0.0",
            "sourceSchemaVersion": artifacts["director"]["schemaVersion"],
            "buildId": build_id,
            "seed": artifacts["director"]["seed"],
            "runtimeVersion": runtime_version,
            "namespace": namespace,
            "artifactHashes": {artifact_type: _sha256(raw_bytes[artifact_type]) for artifact_type in ARTIFACT_ORDER},
            "policies": {
                "terrainReplacePolicy": artifacts["terrain"]["payload"]["replacePolicy"],
                "allowArbitrarySource": False,
                "allowDirectAssetIds": False,
                "generatedOnlyMutation": True,
            },
            "budgets": {"limits": director_budget, "planned": planned},
            "operations": operations,
            "runtimeConfig": {
                "economy": artifacts["economy"]["payload"],
                "soundscapes": artifacts["vfxAudio"]["payload"]["zoneSoundscapes"],
                "effectRecipes": artifacts["vfxAudio"]["payload"]["effectRecipes"],
                "accessibilityProfiles": artifacts["vfxAudio"]["payload"]["accessibilityProfiles"],
            },
            "rollback": {
                "strategy": "restore_snapshots_and_remove_generated_namespace",
                "previousCompatibleBuildId": None,
                "terrainSnapshotRequired": True,
                "lightingSnapshotRequired": True,
            },
        }

        errors = sorted(self.manifest_validator.iter_errors(manifest), key=lambda error: list(error.absolute_path))
        if errors:
            summary = "; ".join(f"/{'/'.join(map(str, error.absolute_path))}: {error.message}" for error in errors[:5])
            raise AssemblyError(f"Assembler produced an invalid manifest: {summary}")
        return manifest

    def _load_artifacts(self, directory: Path) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
        artifacts: dict[str, dict[str, Any]] = {}
        raw: dict[str, bytes] = {}
        for path in sorted(directory.glob("*.json")):
            data = path.read_bytes()
            artifact = json.loads(data.decode("utf-8"))
            artifact_type = artifact["artifactType"]
            artifacts[artifact_type] = artifact
            raw[artifact_type] = data
        missing = [name for name in ARTIFACT_ORDER if name not in artifacts]
        if missing:
            raise AssemblyError(f"Missing artifacts after validation: {', '.join(missing)}")
        return artifacts, raw

    def _build_operations(self, artifacts: Mapping[str, Mapping[str, Any]], namespace: str) -> list[dict[str, Any]]:
        operations: list[dict[str, Any]] = []

        def add(operation_id: str, action: str, target: str, payload: Mapping[str, Any]) -> None:
            operations.append(
                {
                    "sequence": len(operations) + 1,
                    "operationId": operation_id,
                    "action": action,
                    "target": target,
                    "payload": dict(payload),
                }
            )

        for folder in ("Structures", "Props", "LightingProps", "Gameplay"):
            add(f"folder_{folder.lower()}", "ensure_folder", f"{namespace}.{folder}", {"folderName": folder})

        terrain = artifacts["terrain"]["payload"]
        for item in terrain["operations"]:
            action = "terrain_fill" if item["action"] == "fill" else "terrain_subtract"
            add(
                f"terrain_{item['id']}",
                action,
                "Workspace.Terrain",
                {
                    "shape": item["shape"],
                    "materialToken": item["materialToken"],
                    "transform": item["transform"],
                    "size": item["size"],
                    "scope": terrain["scope"],
                    "buildNamespace": namespace,
                },
            )

        props = artifacts["props"]["payload"]
        instance_targets: dict[str, str] = {}
        for item in props["instances"]:
            target = f"{namespace}.{item['parentCategory']}.{item['id']}"
            instance_targets[item["id"]] = target
            if item["kind"] == "primitive":
                add(
                    f"instance_{item['id']}",
                    "create_primitive",
                    target,
                    {key: value for key, value in item.items() if key not in {"kind", "id"}},
                )
            else:
                add(
                    f"prefab_{item['id']}",
                    "create_prefab",
                    target,
                    {key: value for key, value in item.items() if key not in {"kind", "id"}},
                )

        lighting = artifacts["lighting"]["payload"]
        add(
            "lighting_global_profiles",
            "configure_lighting",
            "Lighting",
            {
                "profiles": lighting["profiles"],
                "readabilityTargets": lighting["readabilityTargets"],
                "fallbackRules": lighting["fallbackRules"],
            },
        )
        for light in lighting["localLights"]:
            socket_id = light["socketInstanceId"]
            socket_target = instance_targets.get(socket_id)
            if socket_target is None:
                raise AssemblyError(f"Local light references unknown socket instance {socket_id!r}")
            add(
                f"light_{light['id']}",
                "create_local_light",
                socket_target,
                {key: value for key, value in light.items() if key != "id"},
            )

        for marker_id, instance_id in sorted(props["gameplayMarkerHosts"].items()):
            add(
                f"marker_{marker_id}",
                "bind_gameplay_marker",
                f"{namespace}.Gameplay",
                {"markerId": marker_id, "instanceId": instance_id},
            )

        duplicate_ids = [operation_id for operation_id, count in Counter(item["operationId"] for item in operations).items() if count > 1]
        if duplicate_ids:
            raise AssemblyError(f"Assembler generated duplicate operation IDs: {', '.join(duplicate_ids)}")
        return operations


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
