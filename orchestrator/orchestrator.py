from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from manifest import ManifestAssembler
from validation import ArtifactValidator

from .store import ImmutableArtifactStore, content_hash


STAGE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
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
STAGE_ORDER = tuple(STAGE_DEPENDENCIES)


class OrchestrationError(ValueError):
    pass


class PipelineOrchestrator:
    def __init__(self, validator: ArtifactValidator, assembler: ManifestAssembler, store: ImmutableArtifactStore) -> None:
        self.validator = validator
        self.assembler = assembler
        self.store = store

    @classmethod
    def from_files(
        cls,
        pipeline_schema: Path | str,
        manifest_schema: Path | str,
        store_root: Path | str,
    ) -> "PipelineOrchestrator":
        validator = ArtifactValidator.from_schema_file(pipeline_schema)
        assembler = ManifestAssembler.from_files(pipeline_schema, manifest_schema)
        return cls(validator, assembler, ImmutableArtifactStore(store_root))

    @staticmethod
    def ready_stages(completed: set[str]) -> list[str]:
        unknown = completed - STAGE_DEPENDENCIES.keys()
        if unknown:
            raise OrchestrationError(f"Unknown completed artifact types: {', '.join(sorted(unknown))}")
        return [
            artifact_type
            for artifact_type in STAGE_ORDER
            if artifact_type not in completed and set(STAGE_DEPENDENCIES[artifact_type]).issubset(completed)
        ]

    def finalize(self, artifact_directory: Path | str, *, manifest_output: Path | str | None = None) -> dict[str, Any]:
        directory = Path(artifact_directory)
        report = self.validator.validate_directory(directory)
        if not report.ok:
            codes = ", ".join(issue.code for issue in report.issues[:5])
            raise OrchestrationError(f"Pipeline validation failed: {codes}")

        artifacts = self._load_by_type(directory)
        hashes = {artifact_type: content_hash(artifacts[artifact_type]) for artifact_type in STAGE_ORDER}
        self._validate_lineage(artifacts, hashes)

        for artifact_type in STAGE_ORDER:
            stored_hash = self.store.put_artifact(artifacts[artifact_type])
            if stored_hash != hashes[artifact_type]:
                raise OrchestrationError(f"Store returned an unexpected hash for {artifact_type}")

        manifest = self.assembler.assemble(directory)
        if manifest["artifactHashes"] != hashes:
            raise OrchestrationError("Manifest artifact hashes do not match immutable store hashes")
        manifest_hash = self.store.put_manifest(manifest)

        first = artifacts[STAGE_ORDER[0]]
        record = {
            "recordVersion": "1.0.0",
            "buildId": first["buildId"],
            "schemaVersion": first["schemaVersion"],
            "seed": first["seed"],
            "stageOrder": list(STAGE_ORDER),
            "artifactHashes": hashes,
            "manifestHash": manifest_hash,
        }
        record_hash = self.store.put_build_record(record)
        if manifest_output is not None:
            output = Path(manifest_output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"recordHash": record_hash, "record": record, "manifest": manifest}

    @staticmethod
    def _load_by_type(directory: Path) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for path in sorted(directory.glob("*.json")):
            artifact = json.loads(path.read_text(encoding="utf-8"))
            artifact_type = artifact.get("artifactType")
            if artifact_type in result:
                raise OrchestrationError(f"Duplicate artifact type {artifact_type!r}")
            result[artifact_type] = artifact
        missing = set(STAGE_ORDER) - result.keys()
        if missing:
            raise OrchestrationError(f"Missing artifact types: {', '.join(sorted(missing))}")
        return result

    @staticmethod
    def _validate_lineage(artifacts: Mapping[str, Mapping[str, Any]], hashes: Mapping[str, str]) -> None:
        for artifact_type in STAGE_ORDER:
            expected = [hashes[name] for name in STAGE_DEPENDENCIES[artifact_type]]
            actual = artifacts[artifact_type].get("inputArtifactHashes")
            if actual != expected:
                raise OrchestrationError(
                    f"{artifact_type} inputArtifactHashes do not match dependency order; expected {expected}, got {actual}"
                )
