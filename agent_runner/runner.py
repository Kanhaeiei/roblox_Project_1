from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

from orchestrator import ImmutableArtifactStore, PipelineOrchestrator, content_hash
from orchestrator.orchestrator import STAGE_DEPENDENCIES, STAGE_ORDER
from validation import ArtifactValidator

from .providers import AgentProvider, AgentRequest, stage_output_schema


STAGE_IDS = {
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
ARTIFACT_FILENAMES = {
    "gameConcept": "00_game_concept.json",
    "director": "01_director.json",
    "layout": "02_layout.json",
    "terrain": "03_terrain.json",
    "props": "04_props.json",
    "lighting": "05_lighting.json",
    "qa": "06_qa.json",
    "economy": "07_economy.json",
    "vfxAudio": "08_vfx_audio.json",
}
AGENT_DOCS = {
    "gameConcept": "00_creative_ideation_agent.md",
    "director": "01_director_agent.md",
    "layout": "02_layout_planner_agent.md",
    "terrain": "03_terrain_shaper_agent.md",
    "props": "04_prop_placer_agent.md",
    "lighting": "05_lighting_atmosphere_agent.md",
    "qa": "06_qa_auditor_agent.md",
    "economy": "07_economy_systems_agent.md",
    "vfxAudio": "08_vfx_audio_agent.md",
}


class AgentRunError(ValueError):
    pass


class AgentRunner:
    def __init__(
        self,
        provider: AgentProvider,
        validator: ArtifactValidator,
        orchestrator: PipelineOrchestrator,
        store: ImmutableArtifactStore,
        pipeline_schema: Mapping[str, Any],
        agents_directory: Path | str,
        *,
        max_attempts: int = 3,
    ) -> None:
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5")
        self.provider = provider
        self.validator = validator
        self.orchestrator = orchestrator
        self.store = store
        self.pipeline_schema = dict(pipeline_schema)
        self.agents_directory = Path(agents_directory)
        self.max_attempts = max_attempts

    def run(
        self,
        brief: str,
        *,
        build_id: str,
        seed: int,
        artifact_output: Path | str,
        manifest_output: Path | str | None = None,
    ) -> dict[str, Any]:
        if not brief.strip():
            raise AgentRunError("Brief must not be empty")
        completed: dict[str, dict[str, Any]] = {}
        hashes: dict[str, str] = {}
        attempts: list[dict[str, Any]] = []
        output_directory = Path(artifact_output)
        output_directory.mkdir(parents=True, exist_ok=True)

        for artifact_type in STAGE_ORDER:
            dependencies = STAGE_DEPENDENCIES[artifact_type]
            feedback: list[dict[str, Any]] = []
            accepted = False
            for attempt_number in range(1, self.max_attempts + 1):
                request = AgentRequest(
                    artifact_type=artifact_type,
                    stage_id=STAGE_IDS[artifact_type],
                    build_id=build_id,
                    seed=seed,
                    revision=attempt_number,
                    brief=brief,
                    input_hashes=[hashes[name] for name in dependencies],
                    dependencies={name: completed[name] for name in dependencies},
                    agent_instructions=self._agent_instructions(artifact_type),
                    validation_feedback=feedback,
                )
                schema = stage_output_schema(self.pipeline_schema, artifact_type, STAGE_IDS[artifact_type])
                try:
                    result = self.provider.generate(request, schema)
                    candidate = result.artifact
                    candidate_hash = self.store.put_candidate(candidate)
                    feedback = self._validate_candidate(candidate, request, completed)
                    attempts.append(
                        {
                            "artifactType": artifact_type,
                            "attempt": attempt_number,
                            "candidateHash": candidate_hash,
                            "provider": result.provider,
                            "model": result.model,
                            "responseId": result.response_id,
                            "usage": result.usage,
                            "accepted": not feedback,
                            "issueCodes": [issue["code"] for issue in feedback],
                        }
                    )
                except Exception as exc:
                    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                        raise
                    feedback = [{"code": f"provider.{type(exc).__name__}", "path": "/", "message": "Provider call failed"}]
                    attempts.append(
                        {
                            "artifactType": artifact_type,
                            "attempt": attempt_number,
                            "candidateHash": None,
                            "provider": type(self.provider).__name__,
                            "model": None,
                            "responseId": None,
                            "usage": {},
                            "accepted": False,
                            "issueCodes": [feedback[0]["code"]],
                        }
                    )
                    candidate = None

                if not feedback and candidate is not None:
                    self._write_working_artifact(output_directory / ARTIFACT_FILENAMES[artifact_type], candidate)
                    completed[artifact_type] = candidate
                    hashes[artifact_type] = content_hash(candidate)
                    self.store.put_artifact(candidate)
                    accepted = True
                    break

            if not accepted:
                run_hash = self._store_run_record(build_id, seed, brief, attempts, status="FAILED", failed_stage=artifact_type)
                raise AgentRunError(
                    f"Stage {artifact_type} exhausted {self.max_attempts} attempts; provenance record {run_hash}"
                )

        finalized = self.orchestrator.finalize(output_directory, manifest_output=manifest_output)
        run_hash = self._store_run_record(build_id, seed, brief, attempts, status="COMPLETED", failed_stage=None)
        return {
            "runRecordHash": run_hash,
            "attempts": attempts,
            "buildRecordHash": finalized["recordHash"],
            "record": finalized["record"],
            "manifest": finalized["manifest"],
        }

    def _validate_candidate(
        self,
        candidate: Mapping[str, Any],
        request: AgentRequest,
        completed: Mapping[str, Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        expected = {
            "schemaVersion": "2.0.0",
            "artifactType": request.artifact_type,
            "stageId": request.stage_id,
            "buildId": request.build_id,
            "seed": request.seed,
            "revision": request.revision,
            "inputArtifactHashes": request.input_hashes,
        }
        for key, value in expected.items():
            if candidate.get(key) != value:
                issues.append(
                    {
                        "code": "runner.identity_mismatch",
                        "path": f"/{key}",
                        "message": f"Expected {value!r}",
                    }
                )
        report = self.validator.validate_artifact(candidate, name=ARTIFACT_FILENAMES[request.artifact_type])
        issues.extend({"code": issue.code, "path": issue.path, "message": issue.message} for issue in report.issues)
        if issues:
            return issues

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for artifact_type, artifact in {**completed, request.artifact_type: candidate}.items():
                directory.joinpath(ARTIFACT_FILENAMES[artifact_type]).write_text(
                    json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            cross_report = self.validator.validate_directory(directory, require_complete=False)
            issues.extend(
                {"code": issue.code, "path": issue.path, "message": issue.message}
                for issue in cross_report.issues
            )
        return issues

    def _agent_instructions(self, artifact_type: str) -> str:
        path = self.agents_directory / AGENT_DOCS[artifact_type]
        return path.read_text(encoding="utf-8") + "\nReturn only the requested JSON artifact. Never emit executable source or direct asset IDs."

    @staticmethod
    def _write_working_artifact(path: Path, artifact: Mapping[str, Any]) -> None:
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != artifact:
                raise AgentRunError(f"Refusing to overwrite different working artifact: {path}")
            return
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _store_run_record(
        self,
        build_id: str,
        seed: int,
        brief: str,
        attempts: list[dict[str, Any]],
        *,
        status: str,
        failed_stage: str | None,
    ) -> str:
        record = {
            "recordVersion": "1.0.0",
            "buildId": build_id,
            "seed": seed,
            "briefHash": "sha256:" + hashlib.sha256(brief.encode("utf-8")).hexdigest(),
            "status": status,
            "failedStage": failed_stage,
            "maxAttemptsPerStage": self.max_attempts,
            "attempts": attempts,
        }
        return self.store.put_run_record(record)
